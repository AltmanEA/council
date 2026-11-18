"""Approval registry and diff hashing — JSONL-backed, stdlib only.

Provides:
  - hash_diff(diff) -> str  (sha256 hash with "sha256:" prefix)
  - ApprovalError(code, reason) with .code and .reason attributes
  - ApprovalRegistry(state_root) — JSONL persistence at
    ``<state_root>/documenter/intent/approvals.jsonl``

When *state_root* is not provided, the registry falls back to in-memory
mode (identical to the legacy implementation).  When state_root is given,
records are appended to JSONL and loaded from disk on instantiation.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

__all__ = [
    "ApprovalError",
    "ApprovalRegistry",
    "hash_diff",
    # Journal persistence for precheck overrides (used by verbs.py).
    "PrecheckOverrideJournal",
]


# ---------------------------------------------------------------------------
# hash_diff
# ---------------------------------------------------------------------------


def hash_diff(diff: str) -> str:
    """SHA-256 hash of the diff text, with 'sha256:' prefix.

    Args:
        diff: the raw diff text to hash.

    Returns:
        String in the form "sha256:<hex>" where hex is the lowercase
        SHA-256 hexdigest of diff.encode("utf-8").
    """
    hex_digest = hashlib.sha256(diff.encode("utf-8")).hexdigest()
    return f"sha256:{hex_digest}"


# ---------------------------------------------------------------------------
# ApprovalError
# ---------------------------------------------------------------------------


class ApprovalError(Exception):
    """Structured approval error.

    Attributes:
        code: canonical error code string (e.g. "VAL.001", "VAL.003").
        reason: human-readable explanation.
    """

    def __init__(self, code: str, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}")


# ---------------------------------------------------------------------------
# ApprovalRegistry
# ---------------------------------------------------------------------------

#: Path to the approvals JSONL file inside the state_root.
_APPROVALS_JSONL = os.path.join("documenter", "intent", "approvals.jsonl")


class ApprovalRegistry:
    """Backed approval registry.

    When *state_root* is None the registry is purely in-memory (volatile).
    When *state_root* is provided, pending approval requests are persisted as
    JSONL at ``<state_root>/documenter/intent/approvals.jsonl``: each
    ``register_request`` call appends a line, and instantiation loads all
    prior lines so records survive a simulated process restart.

    Thread-unsafe; suitable for single-threaded MVP operations.
    """

    def __init__(
        self,
        *,
        state_root: str | None = None,
    ) -> None:
        self._requests: dict[str, dict] = {}
        self._state_root = state_root

        if state_root is not None:
            self._load()

    # -- persistence --------------------------------------------------------

    def _jsonl_path(self) -> str | None:
        if self._state_root is None:
            return None
        return os.path.join(self._state_root, *_APPROVALS_JSONL.split(os.sep))

    def _load(self) -> None:
        """Load all prior request records from the JSONL file."""
        path = self._jsonl_path()
        if path is None or not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        req_id = record.get("request_id")
                        if req_id:
                            self._requests[req_id] = dict(record)
                    except (json.JSONDecodeError, KeyError):
                        pass  # Skip malformed lines.
        except OSError:
            pass  # Best-effort load; empty if unreadable.

    def _save(self, record: dict) -> None:
        """Append a single record to the JSONL file."""
        path = self._jsonl_path()
        if path is None:
            return
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    # -- public API ---------------------------------------------------------

    def register_request(
        self,
        request_id: str,
        diff_hash: str,
        proposer_operator_id: str,
    ) -> dict:
        """Register a new approval request with state 'pending'.

        Args:
            request_id: UUID4 string.
            diff_hash: "sha256:<hex>" hash of the diff text.
            proposer_operator_id: operator who created the request.

        Returns:
            A defensive COPY of the stored record dict.
        """
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        record: dict = {
            "request_id": request_id,
            "diff_hash": diff_hash,
            "proposer_operator_id": proposer_operator_id,
            "state": "pending",
            "created_at": now_iso,
            "single_use": True,
        }
        self._requests[request_id] = record

        # Persist to disk (best-effort).
        self._save(record)

        return dict(record)

    def approve(
        self,
        request_id: str,
        approver_operator_id: str,
        diff: str,
    ) -> dict:
        """Approve a request after applying all guard checks.

        Guard order (load-bearing — each must be checked in isolation):
          1. Unknown request_id  -> VAL.003 "unknown request_id"
          2. Non-pending (already approved/invalidated)
                                -> VAL.001 "request already consumed (single-use)"
          3. Self-approval       -> VAL.001 "approver must differ from proposer"
                                (NO state change; record STAYS "pending")
          4. Diff hash mismatch  -> set state "invalidated" +
                                VAL.001 "changed-diff invalidation"
          5. All pass            -> set state "approved"; return dict COPY

        Args:
            request_id: UUID string identifying the request.
            approver_operator_id: operator attempting the approval.
            diff: raw diff text (for hash verification).

        Returns:
            A defensive COPY of the record dict with state="approved"
            and approver_operator_id populated.

        Raises:
            ApprovalError: when any guard check fails.
        """
        record = self._requests.get(request_id)

        # Guard 1: unknown request_id
        if record is None:
            raise ApprovalError("VAL.003", "unknown request_id")

        # Guard 2: non-pending → single-use
        if record["state"] != "pending":
            raise ApprovalError(
                "VAL.001", "request already consumed (single-use)"
            )

        # Guard 3: self-approval (no state change — record stays pending)
        if approver_operator_id == record["proposer_operator_id"]:
            raise ApprovalError(
                "VAL.001", "approver must differ from proposer"
            )

        # Guard 4: diff hash mismatch → invalidate
        if hash_diff(diff) != record["diff_hash"]:
            record["state"] = "invalidated"
            raise ApprovalError(
                "VAL.001", "changed-diff invalidation"
            )

        # Guard 5: all pass → approved
        record["state"] = "approved"
        record["approver_operator_id"] = approver_operator_id
        self._save(dict(record))
        return dict(record)

    def get(self, request_id: str) -> dict | None:
        """Return a defensive COPY of the record, or None if not found."""
        record = self._requests.get(request_id)
        if record is None:
            return None
        return dict(record)


# ---------------------------------------------------------------------------
# PrecheckOverrideJournal — disk-backed journal for override_precheck.
# ---------------------------------------------------------------------------

#: Path suffix for the precheck override JSONL file.
_PRECHECK_OVERRIDE_JSONL = os.path.join(
    "documenter", "precheck_override_journal.jsonl")

# Module-level cache: state_root (or None) → PrecheckOverrideJournal instance.
# Ensures that within a single process, calls with the same state_root
# share the same in-memory journal (backed by disk when state_root is set).
_precheck_journal_cache: dict[str | None, "PrecheckOverrideJournal"] = {}


class PrecheckOverrideJournal:
    """Thread-unsafe, disk-backed journal for precheck override grants.

    The journal lives at ``<state_root>/documenter/precheck_override_journal.jsonl``.
    Each grant appends a record; consume checks the journal (rebuilt on first
    access) and refuses re-consumption.

    When *state_root* is None the journal is in-memory only (volatile).
    """

    def __init__(
        self,
        *,
        state_root: str | None = None,
    ) -> None:
        self._state_root = state_root
        self._state: dict[str, dict] = {}  # (session_id, operator_id) -> record
        if state_root is not None:
            self._load()

    # -- persistence --------------------------------------------------------

    def _jsonl_path(self) -> str | None:
        if self._state_root is None:
            return None
        return os.path.join(
            self._state_root, *_PRECHECK_OVERRIDE_JSONL.split(os.sep))

    def _load(self) -> None:
        """Load all prior records from the JSONL file."""
        path = self._jsonl_path()
        if path is None or not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        sid = record.get("session_id")
                        oid = record.get("operator_id")
                        if sid and oid:
                            self._state[(sid, oid)] = dict(record)
                    except (json.JSONDecodeError, KeyError):
                        pass
        except OSError:
            pass

    def _save(self, record: dict) -> None:
        """Append a single record to the JSONL file."""
        path = self._jsonl_path()
        if path is None:
            return
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                for rec in self._state.values():
                    fh.write(json.dumps(rec) + "\n")
            os.replace(tmp, path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass

    # -- public API ---------------------------------------------------------

    def grant(self, session_id: str, operator_id: str,
              granted_at: str) -> None:
        """Record a new override grant."""
        self._state[(session_id, operator_id)] = {
            "session_id": session_id,
            "operator_id": operator_id,
            "granted_at": granted_at,
            "consumed_at": None,
        }
        self._save(self._state[(session_id, operator_id)])

    def consume(self, session_id: str, operator_id: str) -> bool:
        """Consume a single-use grant.

        Returns True exactly once for a (session_id, operator_id) that was
        granted, then False.  Returns False when never granted.
        """
        key = (session_id, operator_id)
        rec = self._state.get(key)
        if rec is None:
            return False
        if rec.get("consumed_at") is None:
            rec["consumed_at"] = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
            self._save(rec)
            return True
        return False


def _get_precheck_journal(state_root: str | None) -> "PrecheckOverrideJournal":
    """Return a cached journal instance for the given *state_root*.

    Within a single process, all calls with the same state_root value
    share the same in-memory journal instance (disk-backed when
    state_root is provided, volatile when it is None).
    """
    if state_root not in _precheck_journal_cache:
        _precheck_journal_cache[state_root] = PrecheckOverrideJournal(
            state_root=state_root)
    return _precheck_journal_cache[state_root]
