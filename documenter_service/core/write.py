"""Core write branch functions.

Public entry points (called by Service):
  - propose_write(...)    → {"approval_required": True, ...}  (NO file written)
  - approve(...)          → {"approval_id", "decision", "next_action"}
  - apply_write(...)      → {"applied": True, ...}            (atomic rename)
  - reconcile(...)        → list[resolution_info]             (cold-start)

All I/O is via params (registry, manifest, events, engine); the core is
unit-testable without a real filesystem except for the apply_write path which
uses explicit seams.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import posixpath
import shutil
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from ..adapters.applier import apply_unified_diff
from ..adapters.git_snapshot import capture_git_snapshot as _default_git_snapshot
from ..core.errors import StructuredError

# Import shared helpers (pure, no I/O beyond what's passed in).
from ..core.policy import (
    check_tier2_authorized,
    match_operation,
    operator_id_valid,
    trust_rank,
)
from ..ports import ManifestSource, AuditRegistry, DiffEngine, EventSink
from ..adapters.lock import DelegateLock
from ..adapters import commit_protocol as _commit_protocol

# Sentinel for a file that does not exist (create operations).
# Used consistently across propose_write, _apply_write_changeset, and
# _reconcile_new_format so that the "file absent" state is always
# represented by the same string.
BEFORE_HASH_MISSING = "missing"


def _before_hash_of(root, rel_path):
    """sha256:<hex> of the file, or BEFORE_HASH_MISSING when absent/unreadable."""
    try:
        with open(os.path.join(root, rel_path), "rb") as fh:
            return "sha256:" + hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return BEFORE_HASH_MISSING

# Lazy import these to avoid circular imports (audit.py imports check_all).
def _get_resolve_scope():
    from ..core.audit import _resolve_scope
    return _resolve_scope

def _get_pre_audit_gate():
    from ..core.audit import pre_audit_gate
    return pre_audit_gate

__all__ = ["propose_write", "approve", "apply_write", "reconcile"]


# --- propose_write ---------------------------------------------------------


def propose_write(
    root: str,
    manifest: ManifestSource,
    registry: AuditRegistry,
    policy,  # Policy | None — call-site uses load_policy_safe()
    events: EventSink,
    engine: DiffEngine,
    *,
    target_id: str,
    change_type: str,
    trust_level: str,
    diff_input: str,
    audit_id: str | None,
    proposer_id: str | None = None,
    preview: bool = False,
    max_diff_bytes: int = 524288,
    sync_latency_budget_ms: int = 30000,
    changeset: list[dict] | None = None,
) -> dict:
    """Propose a write (Tier 2+ write branch).

    ORDER of guards (fail-closed, each step its own guard):

      (a) preview MUST be False — structural guard.
      (b) check_tier2_authorized(policy, root) → tier_interlock.
      (c) sync_latency_budget_ms check (single deadline computed at entry) —
          mvp-interfaces §5.
      (d) registry.status() == "corrupt" → gate_failure.
      (e) audit_id REQUIRED: None → audit_mismatch.
      (f) _resolve_scope — off-manifest → unknown.
      (g) match_operation → None → gate_failure.
      (gg) policy floor — trust_level below entry floor → trust_mismatch
          (policy may only tighten, never weaken, the requested floor).
      (h) decode_diff_input + engine.normalize + check_invariant →
          trust_mismatch.
      (i) pre_audit_gate → propagate error (audit_mismatch / blocking_finding).
      (j) Compute new content: read target file → apply_unified_diff → new_text.
      (k) diff_hash + approval_id; registry.issue_approval(...) with
          source_sha256 in extra (the approval's source hash).
      (l) Return result with next_action="await_approval".  NO file written.

    Changeset support (Multi-file commit protocol):
      When *changeset* is provided (list of dict with "path"/"content_b64"),
      validation is performed BEFORE any side-effects (steps a–j are unchanged
      guards, only step k carries changeset_digest).  If changeset is empty
      or None the behaviour is identical to the legacy path.
    """
    # (a) preview MUST be False — structural guard
    if preview is True:
        raise StructuredError(
            "unknown",
            "propose_write is the write branch; received preview=True")

    # (a.5) preview=True + changeset is forbidden
    if preview is False and changeset is not None and len(changeset) > 0:
        _validate_changeset(changeset, manifest, target_id, root)

    # (b) tier 2+ authorization (MUST precede budget so Tier 0 always yields
    # tier_interlock, never gate_failure from the budget check).
    check_tier2_authorized(policy, root)

    # (c) Sync-latency budget: compute deadline ONCE at operation entry,
    # then pass it to all internal _check_budget calls (audit.py pattern).
    deadline = time.monotonic() + sync_latency_budget_ms / 1000.0
    _check_budget(sync_latency_budget_ms, deadline)

    # (d) corrupt registry check
    if registry.status() == "corrupt":
        raise StructuredError(
            "gate_failure",
            "audit registry is corrupt — write intent refused "
            "(restore the registry from git; status() reports details)")

    # (d) audit_id required
    if audit_id is None:
        raise StructuredError(
            "audit_mismatch",
            "audit_id is required for write intent (pre-audit gate)",
            next_action="rerun_audit")

    # (e) scope check — off-manifest → unknown
    resolve_scope = _get_resolve_scope()
    entries, scope_ids = resolve_scope(manifest, target_id)

    # (f) match_operation
    match_entry = match_operation(
        policy, change_type=change_type, target_id=target_id)
    if match_entry is None:
        raise StructuredError(
            "gate_failure",
            "operation not in allowed_operations — change_type={!r} for "
            "target_id={!r} is not permitted by policy".format(change_type, target_id),
            next_action="preview_denied")

    # (gg) policy floor: requested trust_level must not be below the
    #      entry's trust_level floor (policy may only tighten, never weaken).
    entry_floor = match_entry.get("trust_level", "safe")
    if trust_rank(trust_level) < trust_rank(entry_floor):
        raise StructuredError(
            "trust_mismatch",
            f"requested trust_level {trust_level!r} is below the policy "
            f"entry floor {entry_floor!r} for change_type={change_type!r} "
            f"target={target_id!r} (policy may only tighten the floor)",
            next_action="preview_denied")

    # (g) decode, normalize, trust check (lazy imports to avoid circular deps)
    from ..adapters.diff_engine import decode_diff_input
    from ..core.trust import check_invariant

    text = decode_diff_input(diff_input, max_diff_bytes)
    normalized = engine.normalize(text)
    derived, reason = check_invariant(change_type, trust_level,
                                      diff_text=normalized.decode("utf-8"))

    # (h) pre-audit gate
    pre_audit = _get_pre_audit_gate()
    record = registry.find_audit(audit_id)
    now_iso = registry.now()
    audit_freshness = int(policy.get("audit_freshness")) if policy else 30
    err = pre_audit(record, target_id, now_iso, audit_freshness)
    if err:
        raise err

    # (i) compute new content via applier
    target_entry = manifest.resolve(target_id)
    if target_entry is None:
        raise StructuredError(
            "unknown", f"manifest entry for target_id {target_id!r} not found")
    target_path = os.path.join(root, target_entry["path"])

    # Read source file as bytes (for source_sha256) and as text (for diff).
    with open(target_path, "rb") as fh:
        source_bytes = fh.read()
    original_text = source_bytes.decode("utf-8")
    new_text = apply_unified_diff(original_text, normalized.decode("utf-8"))

    # (j) issue approval — NO file written
    diff_hash = engine.diff_hash(normalized)
    approval_id = str(uuid.uuid4())

    # Compute source_sha256 for the OCC check on apply (always present).
    source_sha256 = "sha256:" + hashlib.sha256(source_bytes).hexdigest()

    # Build extra: always carries source_sha256; additionally carries
    # changeset_digest when *changeset* is a non-empty list.
    extra: dict = {"source_sha256": source_sha256}
    if changeset is not None and len(changeset) > 0:
        # We need before_hashes for the digest; re-read them.
        all_paths = [target_entry["path"]]
        for rec in changeset:
            p = posixpath.normpath(rec["path"].replace("\\", "/"))
            all_paths.append(p)
        path_hashes: list[list] = []
        for p in all_paths:
            after_hash: str
            if p == target_entry["path"]:
                # after hash is the staged hash for the target document
                after_hash = _staged_hash_for_diff(target_path, original_text,
                                                   normalized)
            else:
                # Look up the correct changeset record for this path
                rec_for_p = None
                for _rec in changeset:
                    rp = posixpath.normpath(_rec["path"].replace("\\", "/"))
                    if rp == p:
                        rec_for_p = _rec
                        break
                rec_b64 = rec_for_p.get("content_b64", "") if rec_for_p else ""
                after_hash = "sha256:" + hashlib.sha256(
                    base64.b64decode(rec_b64)).hexdigest()
            before_hash = _before_hash_of(root, p)
            path_hashes.append([p, before_hash, after_hash])
        path_hashes.sort(key=lambda x: x[0])
        _json_str = json.dumps(path_hashes, sort_keys=True)
        changeset_digest = "sha256:" + hashlib.sha256(_json_str.encode()).hexdigest()
        extra["changeset_digest"] = changeset_digest
        # Extract normalized paths (sorted alongside path_hashes)
        extra["changeset_paths"] = sorted(
            [posixpath.normpath(rec["path"].replace("\\", "/")) for rec in changeset]
        )

    registry.issue_approval(
        approval_id=approval_id,
        target_ids=[target_id],
        diff_hash=diff_hash,
        proposer_id=proposer_id,
        audit_id=audit_id,
        extra=extra,
    )

    return {
        "approval_required": True,
        "approval_id": approval_id,
        "diff_hash": diff_hash,
        "derived_trust_level": derived,
        "derived_trust_reason": reason,
        "next_action": "await_approval",
        "findings": [],  # populated by caller if needed
        "expires_in_min": int(policy.get("approval_expiry_window")) if policy else 30,
    }


# --- _validate_changeset (changeset path validation) ------------------------


def _validate_changeset(changeset: list, manifest, target_id: str, root: str):
    """Validate a non-empty changeset before any side-effects.

    Raises StructuredError("unknown", ...) on any validation failure.
    Called BEFORE any guard chain (except the preview check) so that
    no files are created on failure.

    Validation steps:
      1. Each record must be a dict with exactly {path, content_b64}
      2. Normalize paths, check for absolute/.. paths, deduplicate
      3. All paths must be manifest-tracked (validate_changeset_paths, R2)
      4. All paths must be within target scope (validate_changeset_scope, R3)
         — target file-set + commit bookkeeping only.
    """
    import posixpath

    # 1. Each record must be a dict with exactly {path, content_b64}
    seen_paths: list[str] = []
    for rec in changeset:
        if not isinstance(rec, dict):
            raise StructuredError(
                "unknown", "each changeset entry must be a dict with keys path "
                "and content_b64")
        keys = set(rec.keys())
        if keys != {"path", "content_b64"}:
            raise StructuredError(
                "unknown", "each changeset entry must have exactly keys path and "
                "content_b64, got " + repr(keys))

    # 2. Normalize paths, check for absolute/.. paths, deduplicate against
    #    target_id and each other.
    norm_paths: list[str] = []
    for rec in changeset:
        p = rec["path"]
        np = posixpath.normpath(p.replace("\\", "/"))
        if np.startswith("/") or ".." in np.split("/"):
            raise StructuredError(
                "unknown", f"changeset path {p!r} is invalid (absolute or parent "
                "reference)")
        norm_paths.append(np)

        # Check target_id path isn't duplicated in changeset
        target_entry = manifest.resolve(target_id)
        if target_entry is not None:
            if np == target_entry["path"].replace("\\", "/"):
                raise StructuredError(
                    "unknown", f"changeset path {p!r} duplicates the target "
                    "document path {target_id!r}")

        # Check no internal duplicates
        if np in norm_paths[:-1]:
            raise StructuredError(
                "unknown", f"changeset path {p!r} is duplicated")

        # Decode base64
        try:
            base64.b64decode(rec["content_b64"])
        except Exception:
            raise StructuredError(
                "unknown", f"changeset content_b64 for path {p!r} is not valid "
                "base64")

    # 3. All paths must be manifest-tracked (validate_changeset_paths raises
    #    unknown for non-manifest paths, with no writes — spec #9b)
    _commit_protocol.validate_changeset_paths(norm_paths, manifest)

    # 4. Second-level scope guard (R3): changeset may only touch the
    #    target's own file-set + commit bookkeeping files.
    _commit_protocol.validate_changeset_scope(norm_paths, manifest,
                                              target_id, policy_entry=None)


def _staged_hash_for_diff(full_path, original_text, normalized):
    """Compute the sha256 of the file that *would* be staged (source + diff).

    This mirrors what the legacy write path does: reads source, applies diff,
    and hashes the result.  Used to compute the after_hash for the target
    document's entry in the changeset digest.
    """
    try:
        with open(full_path, "rb") as fh:
            source_bytes = fh.read()
    except OSError:
        source_bytes = original_text.encode("utf-8")
    new_text = apply_unified_diff(source_bytes.decode("utf-8"),
                                  normalized.decode("utf-8"))
    return "sha256:" + hashlib.sha256(new_text.encode("utf-8")).hexdigest()


# --- approve ---------------------------------------------------------------


def approve(
    registry: AuditRegistry,
    policy,
    events: EventSink,
    *,
    root,
    approval_id: str,
    operator_id: str,
) -> dict:
    """Approve a pending write proposal.

    Steps (per mvp-contract §4 / operator-surface §Documenter Integration):
      1. operator_id_valid → else StructuredError("unknown").
      2. check_tier2_authorized(policy, root) → tier_interlock (ADR-013).
      3. find_approval → None → StructuredError("audit_mismatch").
      4. expired → StructuredError("approval_expired", next_action="preview_denied").
         (Approval expiry ≠ audit staleness; "preview_denied" tells the operator
         to re-propose.  "rerun_audit" is reserved for audit-level staleness.)
      5. self-approval check: if proposer_id == operator_id →
         StructuredError("gate_failure", "self-approval denied").
         (proposer_id is None → allowed: unattributed proposal.)
      6. resolve_approval(approval_id, "approved", operator_id) → raises
         token_replay if already resolved.
      7. emit event documenter.approval.
      8. Return {approval_id, decision, next_action="await_approval"}.
         (Write is still pending application; the operator re-invokes
         delegate(preview=False, approval_id=...) to apply.)
    """
    # 1. Validate operator_id
    if not operator_id_valid(operator_id):
        raise StructuredError(
            "unknown",
            f"malformed operator_id {operator_id!r} — "
            "expected format ^op-[a-z0-9][a-z0-9-]{{2,63}}$")

    # 2. Tier 2+ authorization (ADR-013 dual interlock) — before any
    # registry lookup, so Tier 0 yields tier_interlock without touching
    # approval state.
    check_tier2_authorized(policy, root)

    # 3. Find approval
    approval = registry.find_approval(approval_id)
    if approval is None:
        raise StructuredError(
            "audit_mismatch",
            f"approval_id {approval_id!r} was not issued by this registry")

    # 4. Expired check (MUST come before resolve_approval)
    expiry_min = (int(policy.get("approval_expiry_window")) if policy else 30)
    from ..core.registry import approval_is_expired
    if approval_is_expired(approval, registry.now(), expiry_min):
        raise StructuredError(
            "approval_expired",
            f"approval_id {approval_id!r} has expired "
            f"(window {expiry_min} min) — re-propose with delegate(preview=False)",
            next_action="preview_denied")

    # 5. Self-approval check
    proposer = approval.get("proposer_id")
    if proposer is not None and proposer == operator_id:
        raise StructuredError(
            "gate_failure",
            "self-approval denied: approver must differ from the proposing "
            "actor (operator-surface §Documenter Integration)")
    # proposer_id is None → allowed: unattributed proposal

    # 6. Resolve approval (single-use — raises token_replay if already resolved)
    resolved = registry.resolve_approval(approval_id, decision="approved",
                                         operator_id=operator_id)

    # 7. Emit event
    diff_hash = approval.get("diff_hash", "")
    target_id = approval.get("bound_to", {}).get("target_id", "")
    events.emit("documenter.approval", {
        "approval_id": approval_id,
        "operator_id": operator_id,
        "target_id": target_id,
        "diff_hash": diff_hash,
        "decision": "approved",
    })

    # 8. Return — write still pending application
    return {
        "approval_id": approval_id,
        "decision": "approved",
        "next_action": "await_approval",
    }


# --- apply_write -----------------------------------------------------------


def apply_write(
    root: str,
    manifest: ManifestSource,
    registry: AuditRegistry,
    policy,
    events: EventSink,
    engine: DiffEngine,
    *,
    approval_id: str,
    operator_id: str,
    diff_input: str,
    max_diff_bytes: int = 524288,
    data_dir: str | None = None,
    seams: Dict[str, Callable[[], Any]] | None = None,
    sync_latency_budget_ms: int = 30000,
    changeset: list[dict] | None = None,
) -> dict:
    """Apply an approved write to the target file (mvp-contract §2.2).

    The first check is check_tier2_authorized(policy, root) -> tier_interlock
    (ADR-013); it precedes the sync-latency budget check.

    OCC (optimistic concurrency control): source hash from the approval
    (source_sha256) is verified before staging; legacy approvals without it
    fail closed with approval_invalidated.  The staged output is verified
    against the approved diff applied to the current source.

    When *changeset* is None or empty the legacy single-file path is used
    (intent_<approval_id>.json, per_file_sha256, etc.).  When *changeset* is
    a non-empty list the Multi-file Commit Protocol (#9) path is used.

    Durability sequence: stage in target dir → fsync(file) → intent record
    (temp+rename+fsync) → rename → fsync(dir).

    Parameters
    ----------
    seams : dict, optional
        {key: callable} called at boundary points: "after_stage",
        "after_intent", "before_rename".  Used by tests to inject crash
        conditions.
    sync_latency_budget_ms : int, optional
        Maximum wall-clock budget (milliseconds) for synchronous operations
        (mvp-interfaces §5).  Default 30000.  A single monotonic-clock
        deadline is computed once at operation entry and passed to all
        internal _check_budget calls.
    changeset : list[dict] | None, optional
        Each entry: {"path": <rel posix path>, "content_b64": <base64 of new
        content>}.  Used with the Multi-file commit protocol path.  When
        provided, *preview* in propose_write MUST have been False (validated
        there); the digest is checked against the approval's stored
        changeset_digest.

    Returns
    -------
    dict with keys: applied, target_id, diff_hash, approval_id, next_action.
    For changeset path additionally includes ``changeset_paths``.
    """
    # 00. Tier 2+ authorization (ADR-013 dual interlock) — MUST run before
    # every other check so Tier 0 always yields tier_interlock, never
    # gate_failure from the budget check.
    check_tier2_authorized(policy, root)

    # 0. Sync-latency budget: compute deadline ONCE at operation entry, then
    # pass it to all internal _check_budget calls (audit.py pattern).
    deadline = time.monotonic() + sync_latency_budget_ms / 1000.0
    _check_budget(sync_latency_budget_ms, deadline)

    # 1. Find approval
    approval = registry.find_approval(approval_id)
    if approval is None:
        raise StructuredError(
            "audit_mismatch",
            f"approval_id {approval_id!r} was not issued by this registry")

    # 2. Decision check
    if approval.get("decision") != "approved":
        raise StructuredError(
            "gate_failure",
            "approval not approved (decision={!r}) — "
            "{} approvals cannot be applied".format(
                approval.get("decision"),
                approval.get("decision") or "pending"))

    # 2b. Single consumption (mvp-data-models §1 Token model): an approval
    # consumed by a prior apply can never be applied again.
    if approval.get("consumed"):
        raise StructuredError(
            "token_replay",
            f"approval_id {approval_id!r} was already consumed by a previous "
            "apply — approvals are single-use; re-propose")

    # 3. Expiry check
    expiry_min = (int(policy.get("approval_expiry_window")) if policy else 30)
    from ..core.registry import approval_is_expired
    if approval_is_expired(approval, registry.now(), expiry_min):
        raise StructuredError(
            "approval_expired",
            f"approval_id {approval_id!r} has expired — re-propose",
            next_action="preview_denied")

    # 4. Re-normalize diff and verify hash
    from ..adapters.diff_engine import decode_diff_input
    text = decode_diff_input(diff_input, max_diff_bytes)
    normalized = engine.normalize(text)
    diff_hash = engine.diff_hash(normalized)
    if diff_hash != approval["diff_hash"]:
        raise StructuredError(
            "approval_invalidated",
            "the diff changed since approval — approval invalidated, "
            "re-propose")

    # 5. Resolve target
    target_id = approval["target_ids"][0] if approval.get("target_ids") else ""
    entry = manifest.resolve(target_id)
    if entry is None:
        raise StructuredError(
            "unknown", f"manifest entry for target_id {target_id!r} not found")
    target_path = os.path.join(root, entry["path"])
    target_dir = os.path.dirname(target_path)
    target_basename = os.path.basename(target_path)

    # Get data_dir for staging
    if data_dir is None:
        data_dir = os.path.join(root, "documenter")

    # === Legacy path (changeset is None or empty) ===
    if not changeset or len(changeset) == 0:
        return _apply_write_legacy(
            root, manifest, registry, policy, events, engine,
            approval, approval_id, operator_id, text, normalized, diff_hash,
            target_id, target_path, target_dir, target_basename,
            data_dir, seams, sync_latency_budget_ms, deadline)

    # === Multi-file commit protocol path ===
    return _apply_write_changeset(
        root, manifest, registry, policy, events, engine,
        approval, approval_id, operator_id, text, normalized, diff_hash,
        target_id, target_path, entry["path"],
        changeset, data_dir, seams, sync_latency_budget_ms, deadline)


def _apply_write_legacy(
    root, manifest, registry, policy, events, engine,
    approval, approval_id, operator_id, text, normalized, diff_hash,
    target_id, target_path, target_dir, target_basename,
    data_dir, seams, sync_latency_budget_ms, deadline):
    """Legacy single-file apply_write (unchanged from original, except OCC)."""
    # OCC source hash check (before any file modification):
    # read the stored source SHA from the approval; legacy approvals without
    # it fail closed (approval_invalidated); if present, verify the current
    # source file matches.
    stored_src = approval.get("source_sha256")
    if stored_src is None:
        raise StructuredError(
            "approval_invalidated",
            "legacy approval without source_sha256 — re-propose",
            next_action="preview_denied")

    with DelegateLock(data_dir, policy.get("lock_wait_timeout") or 30):
        # 6x. Pre-change git snapshot (mvp-contract §2.2 line 64, ADR-007).
        _git_snapshot_fn = (seams or {}).get(
            "git_snapshot_fn", _default_git_snapshot)
        snapshot = _git_snapshot_fn(root)

        _check_budget(sync_latency_budget_ms, deadline)

        # 6a. Read source file bytes, sha256
        with open(target_path, "rb") as fh:
            source_bytes = fh.read()
        source_sha = "sha256:" + hashlib.sha256(source_bytes).hexdigest()

        # OCC: verify source has not changed between propose and apply.
        if source_sha != stored_src:
            raise StructuredError(
                "hash_mismatch",
                "source changed between propose and apply — "
                "rerun audit then re-propose",
                next_action="rerun_audit")

        # 6b. Apply unified diff to get new_text
        original_text = source_bytes.decode("utf-8")
        new_text = apply_unified_diff(original_text, normalized.decode("utf-8"))

        # 6c. Stage: write to .<basename>.<diffhash16>.tmp in target dir, fsync
        diffhash16 = diff_hash[7:23]
        staged_name = f".{target_basename}.{diffhash16}.tmp"
        staged_path = os.path.join(target_dir, staged_name)
        staged_bytes = new_text.encode("utf-8")
        fd = os.open(staged_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        try:
            os.write(fd, staged_bytes)
            os.fsync(fd)
        finally:
            os.close(fd)

        if seams and "after_stage" in seams:
            seams["after_stage"]()

        # 6d. Intent record: append to registry + intent file (temp+rename+fsync)
        now_iso = registry.now()
        intent_record = {
            "target_ids": [target_id],
            "staged_at": now_iso,
            "per_file_sha256": {target_id: source_sha},
            "resolved": False,
            "git_snapshot": snapshot,
            "tx_id": approval_id,
            "entries": None,
        }
        registry.append("intent_record", intent_record)

        intent_file_name = f"intent_{approval_id}.json"
        intent_file_path = os.path.join(data_dir, intent_file_name)
        os.makedirs(data_dir, exist_ok=True)
        tmp_intent = intent_file_path + ".tmp"
        fd2 = os.open(tmp_intent, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        try:
            os.write(fd2, json.dumps(intent_record).encode("utf-8"))
            os.fsync(fd2)
        finally:
            os.close(fd2)
        os.rename(tmp_intent, intent_file_path)
        data_dir_fd = os.open(data_dir, os.O_RDONLY)
        try:
            os.fsync(data_dir_fd)
        finally:
            os.close(data_dir_fd)

        if seams and "after_intent" in seams:
            seams["after_intent"]()

        # 6e. Apply-time verification (C2, mvp-contract §2.2.3)
        # (1) Re-read the source: catches an external edit AFTER the 6a read
        # (mid-apply race) — the intent record was already written, so this
        # abort leaves a resolvable unresolved intent.
        # (2) Staged output: verify the staged file matches the approved diff
        # applied to the source (catches stage corruption / tampering).
        with open(target_path, "rb") as fh:
            source_recheck = fh.read()
        source_sha_recheck = "sha256:" + hashlib.sha256(source_recheck).hexdigest()
        if source_sha_recheck != source_sha:
            raise StructuredError(
                "hash_mismatch",
                "source changed between approval and apply — "
                "write denied (expected {}, got {})".format(
                    source_sha, source_sha_recheck),
                next_action="resolve_finding")

        approved_new_text = apply_unified_diff(
            source_bytes.decode("utf-8"), normalized.decode("utf-8"))
        expected_staged_sha = "sha256:" + hashlib.sha256(
            approved_new_text.encode("utf-8")).hexdigest()
        with open(staged_path, "rb") as fh:
            staged_recheck = fh.read()
        staged_recheck_sha = "sha256:" + hashlib.sha256(staged_recheck).hexdigest()
        if staged_recheck_sha != expected_staged_sha:
            raise StructuredError(
                "hash_mismatch",
                "staged output does not match the approved diff applied to "
                "the source — write denied (expected {}, got {})".format(
                    expected_staged_sha, staged_recheck_sha),
                next_action="resolve_finding")

        if seams and "before_rename" in seams:
            seams["before_rename"]()

        _check_budget(sync_latency_budget_ms, deadline)

        os.replace(staged_path, target_path)
        dir_fd = os.open(target_dir, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

        if seams and "after_rename" in seams:
            seams["after_rename"]()

        # 6g. Append resolved intent_record; remove intent file
        resolved_intent = dict(intent_record)
        resolved_intent["resolved"] = True
        registry.append("intent_record", resolved_intent)
        consumed = dict(registry.find_approval(approval_id))
        consumed["consumed"] = True
        consumed["consumed_at"] = registry.now()
        registry.append("token_record", consumed)
        try:
            os.remove(intent_file_path)
        except OSError:
            pass

    return {
        "applied": True,
        "target_id": target_id,
        "diff_hash": diff_hash,
        "approval_id": approval_id,
        "next_action": "write_applied",
    }


def _apply_write_changeset(
    root, manifest, registry, policy, events, engine,
    approval, approval_id, operator_id, text, normalized, diff_hash,
    target_id, target_path, target_path_rel,
    changeset, data_dir, seams, sync_latency_budget_ms, deadline):
    """Multi-file commit protocol apply_write path (#9).

    Steps:
      1. git snapshot
      2. recompute changeset_digest → compare with approval["changeset_digest"]
      3. read-before-write: compare before_hash from digest with current file
      4. read source, apply diff → new_text
      5. tx_id, stage ALL files via commit_protocol.stage_bytes
      6. _check_budget
      7. write_intent + append registry intent_record (cross-index with legacy)
         for observability by status().staged_files and find_intent()
      8. seams: after_stage, after_intent, before_rename
      9. C2 verify staged hashes
      10. _check_budget + ordered_renames
      11. cleanup: append resolved registry intent_record → emit event →
          delete_intent (LAST)
      12. consume approval
      13. return
    """
    from hashlib import sha256 as _sha256

    # Collect all files in the changeset including the target document.
    # We need entries for ordering: [target_doc] + changeset_files
    entries: list[dict] = []

    # Helper to compute staged hash (source + diff applied)
    def _staged_hash(path, source_bytes):
        try:
            with open(os.path.join(root, path), "rb") as fh:
                actual = fh.read()
        except OSError:
            actual = source_bytes
        new_text = apply_unified_diff(actual.decode("utf-8"),
                                      normalized.decode("utf-8"))
        return "sha256:" + hashlib.sha256(new_text.encode("utf-8")).hexdigest()

    # Step 1: git snapshot (inside lock, same as legacy)
    with DelegateLock(data_dir, policy.get("lock_wait_timeout") or 30):
        _git_snapshot_fn = (seams or {}).get(
            "git_snapshot_fn", _default_git_snapshot)
        snapshot = _git_snapshot_fn(root)

        _check_budget(sync_latency_budget_ms, deadline)

        # Step 2: recompute changeset_digest and compare with approval
        # Build the path_hashes list like propose_write did
        path_hashes: list[list] = []
        for rec in changeset:
            p = posixpath.normpath(rec["path"].replace("\\", "/"))
            after_hash = "sha256:" + hashlib.sha256(
                base64.b64decode(rec["content_b64"])).hexdigest()
            before_hash = _before_hash_of(root, p)
            path_hashes.append([p, before_hash, after_hash])
        # Add the target document
        try:
            with open(target_path, "rb") as fh:
                src_bytes = fh.read()
            source_sha = "sha256:" + hashlib.sha256(src_bytes).hexdigest()
            target_new_text = apply_unified_diff(
                src_bytes.decode("utf-8"), normalized.decode("utf-8"))
            staged_sha = "sha256:" + hashlib.sha256(
                target_new_text.encode("utf-8")).hexdigest()
        except OSError:
            source_sha = ""
            staged_sha = ""
        path_hashes.append([target_path_rel, source_sha, staged_sha])
        path_hashes.sort(key=lambda x: x[0])
        _json_str_apply = json.dumps(path_hashes, sort_keys=True)
        recomputed_digest = "sha256:" + hashlib.sha256(_json_str_apply.encode()).hexdigest()

        stored_digest = approval.get("changeset_digest")
        if stored_digest is None:
            raise StructuredError(
                "approval_invalidated",
                "changeset provided but approval has no changeset_digest — "
                "re-propose")
        if recomputed_digest != stored_digest:
            raise StructuredError(
                "approval_invalidated",
                "changeset changed since approval — re-propose")

        # Step 3: read-before-write — verify before_hash for each changeset path
        for rec in changeset:
            p = posixpath.normpath(rec["path"].replace("\\", "/"))
            # Find the before_hash from path_hashes (it's the one that isn't target)
            for ph in path_hashes:
                if ph[0] == p:
                    expected_before = ph[1]
                    break
            else:
                expected_before = ""
            if expected_before == BEFORE_HASH_MISSING:
                # Create operation: file must not exist.
                if os.path.exists(os.path.join(root, p)):
                    raise StructuredError(
                        "hash_mismatch",
                        f"create operation for {p!r} but file already exists — "
                        "rerun audit then re-propose",
                        next_action="rerun_audit")
            elif expected_before:
                try:
                    with open(os.path.join(root, p), "rb") as fh:
                        actual = fh.read()
                except OSError:
                    actual = b""
                actual_sha = "sha256:" + hashlib.sha256(actual).hexdigest()
                if actual_sha != expected_before:
                    raise StructuredError(
                        "hash_mismatch",
                        f"file changed since proposal: {p!r} — "
                        f"rerun audit then re-propose",
                        next_action="rerun_audit")
            else:
                # before_hash is "" → legacy compatibility: file must not exist.
                if os.path.exists(os.path.join(root, p)):
                    raise StructuredError(
                        "hash_mismatch",
                        f"create operation for {p!r} but file already exists — "
                        "rerun audit then re-propose",
                        next_action="rerun_audit")

        # Verify target document before_hash
        for ph in path_hashes:
            if ph[0] == target_path_rel:
                expected_target_before = ph[1]
                break
        else:
            expected_target_before = ""
        if expected_target_before == BEFORE_HASH_MISSING:
            # Create doc: file must not exist.
            if os.path.exists(target_path):
                raise StructuredError(
                    "hash_mismatch",
                    f"create operation for target {target_path_rel!r} but file exists")
        elif expected_target_before:
            actual_src = "sha256:" + hashlib.sha256(src_bytes).hexdigest()
            if actual_src != expected_target_before:
                raise StructuredError(
                    "hash_mismatch",
                    f"source changed between approval and apply — "
                    "write denied (rerun audit then re-propose)",
                    next_action="rerun_audit")
        else:
            # before="" means file must not exist (legacy compat).
            if os.path.exists(target_path):
                raise StructuredError(
                    "hash_mismatch",
                    f"create operation for target {target_path_rel!r} but file exists")

        # Step 4: read source, apply diff → new_text (already have src_bytes)
        new_text = apply_unified_diff(
            src_bytes.decode("utf-8"), normalized.decode("utf-8"))

        # Step 5: tx_id, stage ALL files
        tx_id = uuid.uuid4().hex

        # Stage the target document
        staged_entries = []  # {path, tmp_path, before_hash, after_hash}
        # Target doc entry
        staged_entries.append({
            "path": target_path_rel,
            "tmp_path": _commit_protocol.stage_bytes(
                root, target_path_rel, new_text.encode("utf-8"), tx_id),
            "before_hash": expected_target_before,
            "after_hash": staged_sha,
        })

        # Stage each changeset file
        for rec in changeset:
            p = posixpath.normpath(rec["path"].replace("\\", "/"))
            content = base64.b64decode(rec["content_b64"])
            content_sha = "sha256:" + hashlib.sha256(content).hexdigest()
            staged_entries.append({
                "path": p,
                "tmp_path": _commit_protocol.stage_bytes(root, p, content, tx_id),
                "before_hash": (
                    [ph for ph in path_hashes if ph[0] == p][0][1]
                    if any(ph[0] == p for ph in path_hashes)
                    else ""),
                "after_hash": content_sha,
            })

        # Step 6: _check_budget
        _check_budget(sync_latency_budget_ms, deadline)

        # Step 7: seams (legacy parity: after_stage fires BEFORE the intent
        # record — a crash here leaves staged tmp files and NO intent, the
        # detectable partial state of mvp-contract §2.2.4)
        if seams and "after_stage" in seams:
            seams["after_stage"]()

        # Step 7b: write_intent (on-disk intent file for cold-start recovery).
        # Also emit a registry intent_record for cross-format observability:
        # status().staged_files and find_intent() resolve it via
        # target_ids + resolved=False, same as legacy intent_record.
        intent_record = {
            "tx_id": tx_id,
            "target_id": target_id,
            "created_at": registry.now(),
            "entries": staged_entries,
        }
        _commit_protocol.write_intent(data_dir, tx_id, intent_record)

        registry_intent = {
            "target_ids": [target_id],
            "staged_at": registry.now(),
            "per_file_sha256": {target_id: source_sha},
            "tx_id": tx_id,
            "entries": staged_entries,
            "resolved": False,
        }
        registry.append("intent_record", registry_intent)

        # Step 8: seams
        if seams and "after_intent" in seams:
            seams["after_intent"]()

        # Step 9: C2 verify staged hashes (for each entry)
        hasher_fn = lambda b: "sha256:" + _sha256(b).hexdigest()
        for entry in staged_entries:
            tmp_path = entry["tmp_path"]
            expected_after = entry["after_hash"]
            with open(tmp_path, "rb") as fh:
                actual = fh.read()
            actual_sha = hasher_fn(actual)
            if actual_sha != expected_after:
                raise StructuredError(
                    "hash_mismatch",
                    f"staged file {tmp_path!r} hash mismatch "
                    f"(expected {expected_after}, got {actual_sha}) "
                    "next_action: resolve_finding",
                    next_action="resolve_finding")
            # Additional worker-output check for the target document:
            # staged must match diff applied to source
            if entry["path"] == target_path_rel:
                # Already verified above via staged_sha computed from source + diff
                pass

        if seams and "before_rename" in seams:
            seams["before_rename"]()

        # Step 10: _check_budget + ordered_renames
        _check_budget(sync_latency_budget_ms, deadline)
        _commit_protocol.ordered_renames(root, staged_entries, sha_func=hasher_fn)

        # Step 11: cleanup #9d
        # 11a: mark registry intent_record resolved (cross-format compat: the
        # unresolved registry_intent written at step 7b+ is now resolved).
        resolved_registry = dict(registry_intent)
        resolved_registry["resolved"] = True
        registry.append("intent_record", resolved_registry)

        # 11b: emit event
        diff_hash_val = approval.get("diff_hash", "")
        events.emit("documenter.approval", {
            "approval_id": approval_id,
            "operator_id": operator_id,
            "target_id": target_id,
            "diff_hash": diff_hash_val,
            "decision": "approved",
        })

        # 11c: hash store update — documented but not done (rebuildable cache
        # per ADR-010; the hash store file if in the changeset is already
        # renamed; a subsequent audit rebuilds it).

        # 11d: delete_intent (MUST be last per #9d)
        _commit_protocol.delete_intent(data_dir, tx_id)

    # Step 12: consume approval
    consumed = dict(registry.find_approval(approval_id))
    consumed["consumed"] = True
    consumed["consumed_at"] = registry.now()
    registry.append("token_record", consumed)

    # Step 13: return
    return {
        "applied": True,
        "target_id": target_id,
        "diff_hash": diff_hash,
        "approval_id": approval_id,
        "changeset_paths": [
            posixpath.normpath(rec["path"].replace("\\", "/"))
            for rec in changeset
        ],
        "next_action": "write_applied",
    }


# --- sync_latency_budget_ms enforcement (mvp-interfaces §5) -----------------


def _check_budget(budget_ms: int, deadline: float) -> None:
    """Raise StructuredError("gate_failure", ...) when the monotonic clock
    exceeds the budget.

    The deadline is computed ONCE at the entry point of an operation and
    passed to all checks within that operation.  A zero budget expires on
    the first check (deadline ≈ now).

    This mirrors the pattern in audit.py (_check_budget) where a single
    monotonic deadline governs the entire operation.
    """
    if time.monotonic() >= deadline:
        raise StructuredError(
            "gate_failure",
            f"call exceeded sync_latency_budget_ms={budget_ms} — "
            "re-invoke apply (intent record enables safe resume)",
            next_action="rerun_audit",
        )


# --- reconcile -------------------------------------------------------------


def reconcile(
    registry: AuditRegistry,
    manifest: ManifestSource,
    root: str,
    data_dir: str,
    sha256_func=None,
) -> list:
    """Cold-start reconciliation of unresolved intent records.

    For each unresolved intent:
      - If every target's sha256 still matches per_file_sha256 → clean up
        (move staged temp to data_dir/staged/), append resolved intent with
        note "reconciled: no changes detected".
      - If hash mismatch → append {"target_id", "status": "needs_attention",
        "detail"} to the results list.

    Returns the list of resolution dicts.
    """
    from hashlib import sha256 as _sha256
    hasher = sha256_func or (lambda b: "sha256:" + _sha256(b).hexdigest())

    unresolved = registry.unresolved_intents()
    results: list[dict] = []

    for intent in unresolved:
        target_ids = intent.get("target_ids", [])
        per_file_sha = intent.get("per_file_sha256", {})

        all_match = True
        for tid in target_ids:
            expected_sha = per_file_sha.get(tid, "")
            target_entry = manifest.resolve(tid)
            if target_entry is None:
                all_match = False
                results.append({
                    "target_id": tid,
                    "status": "needs_attention",
                    "detail": f"manifest entry {tid!r} not found",
                })
                continue
            target_path = os.path.join(root, target_entry["path"])
            try:
                with open(target_path, "rb") as fh:
                    actual_bytes = fh.read()
                actual_sha = hasher(actual_bytes)
                if actual_sha != expected_sha:
                    all_match = False
                    results.append({
                        "target_id": tid,
                        "status": "needs_attention",
                        "detail": "hash mismatch: expected {}, got {}".format(
                            expected_sha, actual_sha),
                    })
            except OSError as exc:
                all_match = False
                results.append({
                    "target_id": tid,
                    "status": "needs_attention",
                    "detail": "cannot read {}: {}".format(target_path, exc),
                })

        if all_match and target_ids:
            # Clean up: move staged temp files to data_dir/staged/.
            # Only for legacy intent records (entries is None or absent).
            # Changeset-style intents carry structured entries; Phase 2
            # (_reconcile_new_format) handles their roll-forward, so leave
            # staged files in place to avoid breaking branch-2 roll-forward.
            entries = intent.get("entries")
            if entries is None:
                staged_dir = os.path.join(data_dir, "staged")
                os.makedirs(staged_dir, exist_ok=True)
                for tid in target_ids:
                    target_entry = manifest.resolve(tid)
                    if target_entry is None:
                        continue
                    target_path = os.path.join(root, target_entry["path"])
                    target_dir_of_target = os.path.dirname(target_path)
                    target_basename = os.path.basename(target_path)
                    # Find staged temp files matching pattern .<basename>.<hex16>.tmp
                    for fname in os.listdir(target_dir_of_target):
                        if (fname.startswith(".{}.".format(target_basename))
                                and fname.endswith(".tmp")):
                            src = os.path.join(target_dir_of_target, fname)
                            dst = os.path.join(staged_dir, fname)
                            try:
                                shutil.move(src, dst)
                            except OSError:
                                pass
            # Append resolved intent record
            resolved_intent = dict(intent)
            resolved_intent["resolved"] = True
            resolved_intent["_reconciled_note"] = "reconciled: no changes detected"
            registry.append("intent_record", resolved_intent)

    # --- Phase 2: new-format intent directory (Multi-file commit protocol) ---

    new_results = _reconcile_new_format(
        registry, manifest, root, data_dir, sha256_func)
    results.extend(new_results)

    return results


# --- reconcile: new-format intent directory (Multi-file commit protocol) ----


def _reconcile_new_format(registry, manifest, root, data_dir, sha256_func=None):
    """Reconcile multi-file commit protocol intent records from disk.

    Scans ``<data_dir>/intent/`` for leftover intent files (cold-start
    recovery per index.md §Safety Protocol #9 Recovery).  For each intent
    file:

      Branch 1 — files match after_hash: already committed, skip.
      Branch 2 — files match before_hash: roll forward from tmp (when
                 tmp exists and its sha matches after_hash).
      Branch 3 — neither: external modification detected → needs_attention.

    Appends resolved intent records to the registry and deletes the intent
    file on success; otherwise adds a needs_attention result.

    Returns a list of resolution dicts for entries that need attention.
    """
    from hashlib import sha256 as _sha256
    hasher = sha256_func or (lambda b: "sha256:" + _sha256(b).hexdigest())

    intents = _commit_protocol.scan_intents(data_dir)
    results: list[dict] = []

    for intent_record in intents:
        tx_id = intent_record.get("tx_id", "")
        target_id = intent_record.get("target_id", "")
        entries = intent_record.get("entries", [])

        needs_attention_list = []

        for entry in entries:
            path = entry.get("path", "")
            tmp_path = entry.get("tmp_path", "")
            before_hash = entry.get("before_hash", "")
            after_hash = entry.get("after_hash", "")

            current_sha = _file_sha(root, path, hasher)

            if current_sha == after_hash:
                # Branch 1: already committed — nothing to do.
                continue

            if current_sha == before_hash:
                # Branch 2: roll forward from staged file.
                if os.path.exists(tmp_path):
                    with open(tmp_path, "rb") as f:
                        tmp_bytes = f.read()
                    if hasher(tmp_bytes) == after_hash:
                        os.replace(tmp_path, os.path.join(root, path))
                        target_dir = os.path.dirname(os.path.join(root, path))
                        try:
                            dir_fd = os.open(target_dir, os.O_RDONLY)
                            try:
                                os.fsync(dir_fd)
                            finally:
                                os.close(dir_fd)
                        except OSError:
                            pass
                        # Roll forward succeeded — entry is done.
                        continue

                # Branch 2 fallback: tmp missing or hash mismatch → NA.
                needs_attention_list.append(path)
                continue

            # Branch 3: neither before nor after hash matches.
            needs_attention_list.append(path)

        if needs_attention_list:
            results.append({
                "tx_id": tx_id,
                "target_id": target_id,
                "status": "needs_attention",
                "detail": "external modification detected for: "
                          + ", ".join(needs_attention_list),
            })
        else:
            # All entries resolved (branch 1 or 2).
            resolved_intent = dict(intent_record)
            resolved_intent["resolved"] = True
            resolved_intent["_reconciled_note"] = (
                "reconciled: multi-file roll-forward/committed")
            registry.append("intent_record", resolved_intent)
            _commit_protocol.delete_intent(data_dir, tx_id)

    return results


def _file_sha(root, rel_path, hasher):
    """Return the sha256 of *rel_path* (relative to *root*), or sentinel."""
    abs_path = os.path.join(root, rel_path)
    try:
        with open(abs_path, "rb") as f:
            return hasher(f.read())
    except OSError:
        return "missing"
