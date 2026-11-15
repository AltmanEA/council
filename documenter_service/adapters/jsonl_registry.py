"""AuditRegistry adapter — append-only JSONL with prev_hash chain.

File: <data_dir>/audit_registry.jsonl (default documenter/, mvp-data-models
§4). This is the ONLY writer path in the entire service: a single `open(path,
"a")` per append, guarded by a per-appender fcntl advisory lock
(<data_dir>/.registry.lock).  The file is never rewritten in place; compaction
happens only through the explicit, checkpoint-governed `truncate()` below.

Health model (mvp-interfaces §3 "Registry health"):
  healthy  — readable, prev_hash chain consistent
  degraded — chain break, or size above retention without a trailing checkpoint
  corrupt  — truncated or unparsable content (malformed JSON, bad envelope)

Distinction between "missing" and "corrupt": a MISSING or 0-byte file is an
empty registry — healthy, zero records (the first append lands with
prev_hash null). Only content that fails to parse is corrupt. That keeps a
fresh checkout (no runs yet, or a committed empty .gitkeep-only state) from
reporting as corruption while still failing closed on real damage.
"""
from __future__ import annotations

import base64
import fcntl
import json
import os
import secrets
import time
from datetime import datetime, timezone

from ..core import registry as reg
from ..core.errors import StructuredError
from ..ports import AuditRegistry

__all__ = ["JsonlAuditRegistry", "REGISTRY_FILENAME", "new_token"]

#: Registry file name inside the data directory (mvp-data-models §4).
REGISTRY_FILENAME = "audit_registry.jsonl"

#: Lock file name used for serializing concurrent appends.
_REGISTRY_LOCK_FILENAME = ".registry.lock"

#: scan_cursor token length: 32 random bytes, base64 (mvp-data-models §1).
TOKEN_BYTES = 32

#: Default timeout (seconds) for acquiring the registry append lock.
_REGISTRY_LOCK_TIMEOUT = 30


def new_token() -> str:
    """Opaque continuation token: 32 random bytes, base64url-safe on disk."""
    return base64.b64encode(secrets.token_bytes(TOKEN_BYTES)).decode("ascii")


def _latest_unresolved(records) -> list:
    """Unresolved logical intents, latest record per intent first.

    Only the latest record per logical intent counts: a resolved copy
    appended after the staging record hides the original, so a second
    cold-start reconcile does not re-resolve the same intent forever.
    """
    seen = set()
    result = []
    for rec in reversed(records):
        if rec["record_type"] != reg.INTENT_RECORD:
            continue
        data = rec["data"]
        key = reg.intent_key(data)
        if key in seen:
            continue
        seen.add(key)
        if not data.get("resolved", False):
            result.append(data)
    return result


class JsonlAuditRegistry(AuditRegistry):
    """Filesystem-backed registry. Writes: append only (see module docstring)."""

    def __init__(self, data_dir: str, clock=None) -> None:
        self.data_dir = os.path.abspath(data_dir)
        #: Injectable clock (callable → aware datetime) for deterministic
        #: freshness boundaries in tests (mvp-contract §3.1 test_clock_injection).
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # -- low-level ----------------------------------------------------------

    @property
    def path(self) -> str:
        return os.path.join(self.data_dir, REGISTRY_FILENAME)

    def now(self) -> str:
        """ISO 8601 UTC `Z` timestamp from the injected clock."""
        return self._clock().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _raw_lines(self):
        """Raw non-empty lines, or None when the file does not exist."""
        if not os.path.exists(self.path):
            return None
        with open(self.path, encoding="utf-8") as fh:
            return [ln for ln in fh.read().splitlines() if ln.strip()]

    # -- registry append lock (separate from DelegateLock) -------------------

    def _acquire_registry_lock(self):
        """Acquire a per-appender advisory lock.

        Uses ``fcntl.flock(LOCK_EX | LOCK_NB)`` on a dedicated lock file
        ``<data_dir>/.registry.lock`` with a poll loop (0.1 s sleep) up to
        ``_REGISTRY_LOCK_TIMEOUT`` seconds.  Returns the file descriptor on
        success; the caller is responsible for unlocking.
        """
        lock_path = os.path.join(self.data_dir, _REGISTRY_LOCK_FILENAME)
        os.makedirs(self.data_dir, exist_ok=True)
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        deadline = time.monotonic() + _REGISTRY_LOCK_TIMEOUT
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd  # acquired
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise StructuredError(
                        "lock_conflict",
                        "Another process holds the registry append lock. "
                        "Retry later.",
                        next_action="preview_denied",
                    )
                time.sleep(0.1)
            except OSError as exc:
                os.close(fd)
                raise StructuredError(
                    "lock_conflict",
                    "unexpected error acquiring registry lock: "
                    f"{exc}",
                    next_action="preview_denied",
                )

    def _release_registry_lock(self, fd: int) -> None:
        """Release a registry append lock acquired by ``_acquire_registry_lock``."""
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        except OSError:
            pass  # best-effort release

    # -- AuditRegistry port ---------------------------------------------------

    def append(self, record_type: str, data: dict) -> dict:
        """Append one envelope record (the only write path); returns envelope.

        Serializes concurrent appends via a per-appender advisory lock
        (``.registry.lock`` via fcntl) to prevent torn lines when multiple
        processes write simultaneously.  Lock timeout is ``_REGISTRY_LOCK_TIMEOUT``
        seconds; timeout → StructuredError("lock_conflict", …).

        Creates the data directory when absent (permitted state mutation).
        """
        # Acquire lock, read-modify-write, release lock.
        fd_lock = self._acquire_registry_lock()
        try:
            lines = self._raw_lines() or []
            records = [reg.parse_line(ln) for ln in lines]  # corrupt → ValueError
            prev = reg.record_hash(records[-1]) if records else None
            envelope = reg.make_envelope(record_type, data, prev)
            os.makedirs(self.data_dir, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(envelope, sort_keys=True) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            return envelope
        finally:
            self._release_registry_lock(fd_lock)

    def read_all(self) -> tuple:
        """Return (records, status); status ∈ healthy|degraded|corrupt.

        Never raises: degradation is data the operator must SEE (status is the
        only channel through which registry degradation becomes observable —
        mvp-interfaces §3), so parse failures degrade the answer, not crash it.
        """
        lines = self._raw_lines()
        if lines is None or not lines:
            return [], "healthy"  # missing/0-byte = empty fresh registry
        try:
            records = [reg.parse_line(ln) for ln in lines]
        except ValueError:
            return [], "corrupt"
        return records, reg.verify_chain(records)

    def status(self) -> str:
        _, status = self.read_all()
        return status

    def find_audit(self, audit_id: str):
        """Latest audit_record data for ``audit_id``, or None.

        Returns the LAST record with that audit_id: in a paginated scan each
        batch appends a new record whose scanned_ids/findings are CUMULATIVE,
        so resuming must continue from the most recent batch, not the first.
        """
        records, _ = self.read_all()
        found = None
        for rec in records:
            if rec["record_type"] == reg.AUDIT_RECORD and \
                    rec["data"].get("audit_id") == audit_id:
                found = rec["data"]
        return found

    def last_audit(self):
        records, _ = self.read_all()
        for rec in reversed(records):
            if rec["record_type"] == reg.AUDIT_RECORD:
                return rec["data"]
        return None

    # -- approval lifecycle (mvp-data-models §1 token_type=approval_id) --------

    def issue_approval(self, *, approval_id: str, target_ids: list,
                       diff_hash: str, proposer_id: str,
                       audit_id: str | None,
                       extra: dict | None = None) -> dict:
        """Persist an approval token_record (consumed=False).

        Returns the envelope data dict (same as ``consume_token`` return).

        Raises StructuredError("unknown", ...) when ``approval_id`` is not a
        non-empty string or ``diff_hash`` does not match ``sha256:<64-hex>``.

        bound_to is contract-compatible: target_id is the single target when
        len(target_ids)==1, else a comma-joined string.  Extra keys (target_ids,
        diff_hash, proposer_id, created_at, decision=None,
        resolved_at=None) ride alongside the base token_record fields.

        *extra* is an optional dict of additional fields merged into the
        approval record (used by the changeset path to carry
        ``changeset_digest``).  Passed through as-is; the caller is
        responsible for correctness.
        """
        if not isinstance(approval_id, str) or not approval_id:
            raise StructuredError(
                "unknown", f"approval_id must be a non-empty string, got {approval_id!r}")
        if not isinstance(diff_hash, str) or not reg.SHA256_RE.match(diff_hash):
            raise StructuredError(
                "unknown", f"diff_hash must match sha256:<64-hex>, got {diff_hash!r}")
        if target_ids:
            target_id = target_ids[0] if len(target_ids) == 1 else ",".join(target_ids)
        else:
            target_id = ""
        now = self.now()
        bound_to = {"audit_id": audit_id, "target_id": target_id}
        data = {
            "token_type": reg.APPROVAL_ID,
            "token_value": approval_id,
            "bound_to": bound_to,
            "consumed": False,
            "consumed_at": None,
            "target_ids": list(target_ids),
            "diff_hash": diff_hash,
            "proposer_id": proposer_id,
            "created_at": now,
            "decision": None,
            "resolved_at": None,
        }
        if extra:
            data.update(extra)
        return self.append(reg.TOKEN_RECORD, data)["data"]

    def find_approval(self, approval_id: str):
        """Latest token_record data for ``approval_id``, or None."""
        records, _ = self.read_all()
        found = None
        for rec in records:
            if (rec["record_type"] == reg.TOKEN_RECORD
                    and rec["data"].get("token_value") == approval_id
                    and rec["data"].get("token_type") == reg.APPROVAL_ID):
                found = rec["data"]
        return found

    def resolve_approval(self, approval_id: str, *, decision: str,
                         operator_id: str) -> dict:
        """Resolve an approval by appending a new token_record with the decision.

        Raises StructuredError("audit_mismatch", ...) when ``approval_id`` was
        not issued by this registry.  Raises
        StructuredError("token_replay", ...) when already resolved.
        Raises StructuredError("unknown", ...) when ``decision`` is not
        approved/rejected or ``operator_id`` does not match the expected format.

        Returns the newly appended token_record data dict.
        """
        if decision not in ("approved", "rejected"):
            raise StructuredError(
                "unknown", f"decision must be 'approved' or 'rejected', got {decision!r}")
        if not reg.OPERATOR_ID_RE.match(operator_id):
            raise StructuredError(
                "unknown", f"malformed operator_id {operator_id!r} "
                           f"(expected ^op-[a-z0-9][a-z0-9-]{{2,63}}$)")
        approval = self.find_approval(approval_id)
        if approval is None:
            raise StructuredError(
                "audit_mismatch",
                f"approval_id {approval_id!r} was not issued by this registry")
        if approval.get("decision") is not None:
            raise StructuredError(
                "token_replay",
                f"approval_id {approval_id!r} already resolved (decision={approval['decision']!r}) "
                "— approvals are single-use; request a new approval")
        resolved = dict(approval)
        resolved["decision"] = decision
        resolved["resolved_by"] = operator_id
        resolved["resolved_at"] = self.now()
        return self.append(reg.TOKEN_RECORD, resolved)["data"]

    # -- intent helpers (Tier 2+ read; W2 writes via generic append()) ---------

    def find_intent(self, target_id: str):
        """Latest logical intent containing ``target_id`` that is unresolved,
        or None. A later resolved copy of the same intent masks the original."""
        records, _ = self.read_all()
        seen = set()
        for rec in reversed(records):
            if rec["record_type"] != reg.INTENT_RECORD:
                continue
            data = rec["data"]
            key = reg.intent_key(data)
            if key in seen:
                continue
            seen.add(key)
            if data.get("resolved", False):
                continue
            tids = data.get("target_ids", [])
            if isinstance(tids, list) and target_id in tids:
                return data
        return None

    def unresolved_intents(self) -> list:
        """All unresolved logical intents (latest first).

        Latest record per logical intent wins, so a resolved copy masks the
        staging record that produced it.
        """
        records, _ = self.read_all()
        return _latest_unresolved(records)

    # -- metrics (mvp-interfaces §3 — do NOT change status() shape) -------------

    def registry_metrics(self) -> dict:
        """Return counts useful for monitoring (mvp-interfaces §3).

        Counts latest state per approval_id (not all records).
        """
        pending = 0
        intents = 0
        records, _ = self.read_all()
        # Track latest token_type=approval_id per token_value
        latest_approval = {}
        for rec in records:
            data = rec["data"]
            if (rec["record_type"] == reg.TOKEN_RECORD
                    and data.get("token_type") == reg.APPROVAL_ID):
                val = data.get("token_value")
                latest_approval[val] = data
        # Count only latest state
        for data in latest_approval.values():
            if data.get("decision") is None:
                pending += 1
        intents = len(_latest_unresolved(records))
        return {"pending_approvals": pending, "unresolved_intents": intents}

    # -- token lifecycle (mvp-data-models §1 Token model) ---------------------

    def issue_token(self, token_type: str, token_value: str,
                    bound_to: dict) -> dict:
        """Persist a token_record (consumed=False) bound to (audit_id, target_id)."""
        return self.append(reg.TOKEN_RECORD, {
            "token_type": token_type,
            "token_value": token_value,
            "bound_to": {"audit_id": bound_to["audit_id"],
                         "target_id": bound_to["target_id"]},
            "consumed": False,
            "consumed_at": None,
        })

    def _latest_token(self, token_value: str):
        records, _ = self.read_all()
        found = None
        for rec in records:
            if rec["record_type"] == reg.TOKEN_RECORD and \
                    rec["data"].get("token_value") == token_value:
                found = rec["data"]
        return found

    def _latest_token_typed(self, token_value: str, token_type: str):
        """Latest token_record data for token_value, only when its token_type
        matches token_type (defence: approval ids can never be consumed as
        scan cursors and vice versa)."""
        records, _ = self.read_all()
        found = None
        for rec in records:
            if rec["record_type"] == reg.TOKEN_RECORD and \
                    rec["data"].get("token_value") == token_value and \
                    rec["data"].get("token_type") == token_type:
                found = rec["data"]
        return found

    def consume_token(self, token_value: str, target_id: str,
                      audit_id: str | None = None) -> dict:
        """Validate + single-use consume a scan_cursor; returns the token data.

        The token is bound to (audit_id, target_id) (mvp-data-models §1): the
        resuming request must name the same target; a caller that knows its
        audit_id (audit_id != None) must also match the binding. audit_id=None
        (the audit() resume path) ADOPTS the bound audit_id — a token for
        target A can never resume a scan for target B.

        Unknown token → audit_mismatch (forged/expired cursor: pre-audit rules
        1-3 semantics). Consumed replay → token_replay. Consumption is
        recorded as a NEW token_record (append-only: records are never
        rewritten in place).

        A token_value that exists with a different token_type (e.g. an approval
        id) is rejected as audit_mismatch: tokens are type-checked on
        consumption.
        """
        token = self._latest_token_typed(token_value, reg.SCAN_CURSOR)
        if token is None and self._latest_token(token_value) is not None:
            raise StructuredError(
                "audit_mismatch",
                f"token {token_value!r} exists but is not a scan_cursor — "
                "approval ids cannot resume scans")
        if token is None:
            raise StructuredError(
                "audit_mismatch",
                f"scan_cursor {token_value!r} is not a token issued by this "
                "registry (unknown, expired, or fabricated)")
        bound = token.get("bound_to") or {}
        if bound.get("target_id") != target_id or (
                audit_id is not None and bound.get("audit_id") != audit_id):
            raise StructuredError(
                "audit_mismatch",
                f"scan_cursor is bound to (audit_id={bound.get('audit_id')!r}, "
                f"target_id={bound.get('target_id')!r}), but the request is "
                "for target "
                + repr(target_id) + (f" under audit_id {audit_id!r}" if audit_id
                                     else "")
                + " — a cursor for target A cannot resume a scan for target B")
        if token.get("consumed"):
            raise StructuredError(
                "token_replay",
                "scan_cursor already consumed — tokens are single-use "
                "(mvp-data-models §1); re-run audit() for a fresh scan")
        consumed = dict(token)
        consumed["consumed"] = True
        consumed["consumed_at"] = self.now()
        self.append(reg.TOKEN_RECORD, consumed)
        return consumed

    # -- retention / checkpoint (mvp-data-models §1) ---------------------------

    def truncate(self, count: int) -> dict:
        """Checkpoint-governed compaction. Refuses without a valid checkpoint.

        Sequence: verify trailing checkpoint_record covers exactly the
        ``count`` oldest records (core.registry.plan_truncation → StructuredError
        on refusal), then atomically rewrite the file WITHOUT those records.
        This rewrite is the single, explicitly-requested, checkpoint-authorized
        compaction path — it is not an append, and it never runs implicitly
        from audit()/status().
        """
        records, status = self.read_all()
        if status == "corrupt":
            raise StructuredError("gate_failure",
                                  "registry corrupt — truncate refused")
        try:
            doomed = reg.plan_truncation(records, count)
        except ValueError as exc:
            raise StructuredError("gate_failure", str(exc)) from exc
        retained = records[count:-1] + [records[-1]]
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                for rec in retained:
                    fh.write(json.dumps(rec, sort_keys=True) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        except BaseException:
            raise StructuredError("unknown", "registry compaction write failed")
        return {"truncated_count": len(doomed),
                "segment_hash": reg.segment_hash(doomed)}

    def write_checkpoint(self) -> dict:
        """Append a checkpoint_record sized for the oldest segment.

        Convenience for the operator workflow (and tests): the checkpoint's
        truncated_count is min(count, len(records) - 1) so the checkpoint
        itself always survives the later truncate(count)."""
        records, _ = self.read_all()
        count = min(len(records) - 1, len(records))
        if count <= 0:
            raise StructuredError("gate_failure",
                                  "nothing to checkpoint: fewer than 2 records")
        return self.append(reg.CHECKPOINT_RECORD,
                           reg.make_checkpoint_data(records[:count]))
