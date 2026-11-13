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

import hashlib
import json
import os
import shutil
import uuid
from typing import Any, Callable, Dict, List, Optional

from ..adapters.applier import apply_unified_diff
from ..core.errors import StructuredError

# Import shared helpers (pure, no I/O beyond what's passed in).
from ..core.policy import (
    check_tier2_authorized,
    match_operation,
    operator_id_valid,
)
from ..ports import ManifestSource, AuditRegistry, DiffEngine, EventSink
from ..adapters.lock import DelegateLock

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
) -> dict:
    """Propose a write (Tier 2+ write branch).

    ORDER of guards (fail-closed, each step its own guard):

      (a) preview MUST be False — structural guard.
      (b) check_tier2_authorized(policy, root) → tier_interlock.
      (c) registry.status() == "corrupt" → gate_failure.
      (d) audit_id REQUIRED: None → audit_mismatch.
      (e) _resolve_scope — off-manifest → unknown.
      (f) match_operation → None → gate_failure.
      (g) decode_diff_input + engine.normalize + check_invariant → trust_mismatch.
      (h) pre_audit_gate → propagate error (audit_mismatch / blocking_finding).
      (i) Compute new content: read target file → apply_unified_diff → new_text.
      (j) diff_hash + approval_id; registry.issue_approval(...).
      (k) Return result with next_action="await_approval".  NO file written.
    """
    # (a) preview MUST be False — defensive check
    if preview is True:
        raise StructuredError(
            "unknown",
            "propose_write is the write branch; received preview=True")

    # (b) tier 2+ authorization
    check_tier2_authorized(policy, root)

    # (c) corrupt registry check
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
    if match_operation(policy, change_type=change_type, target_id=target_id) is None:
        raise StructuredError(
            "gate_failure",
            "operation not in allowed_operations — change_type={!r} for "
            "target_id={!r} is not permitted by policy".format(change_type, target_id),
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
    with open(target_path, encoding="utf-8") as fh:
        original_text = fh.read()
    new_text = apply_unified_diff(original_text, normalized.decode("utf-8"))

    # (j) issue approval — NO file written
    diff_hash = engine.diff_hash(normalized)
    approval_id = str(uuid.uuid4())
    registry.issue_approval(
        approval_id=approval_id,
        target_ids=[target_id],
        diff_hash=diff_hash,
        proposer_id=proposer_id,
        audit_id=audit_id,
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


# --- approve ---------------------------------------------------------------


def approve(
    registry: AuditRegistry,
    policy,
    events: EventSink,
    *,
    approval_id: str,
    operator_id: str,
) -> dict:
    """Approve a pending write proposal.

    Steps (per mvp-contract §4 / operator-surface §Documenter Integration):
      1. operator_id_valid → else StructuredError("unknown").
      2. find_approval → None → StructuredError("audit_mismatch").
      3. expired → StructuredError("approval_expired", next_action="preview_denied").
         (Approval expiry ≠ audit staleness; "preview_denied" tells the operator
         to re-propose.  "rerun_audit" is reserved for audit-level staleness.)
      4. self-approval check: if proposer_id == operator_id →
         StructuredError("gate_failure", "self-approval denied").
         (proposer_id is None → allowed: unattributed proposal.)
      5. resolve_approval(approval_id, "approved", operator_id) → raises
         token_replay if already resolved.
      6. emit event documenter.approval.
      7. Return {approval_id, decision, next_action="await_approval"}.
         (Write is still pending application; the operator re-invokes
         delegate(preview=False, approval_id=...) to apply.)
    """
    # 1. Validate operator_id
    if not operator_id_valid(operator_id):
        raise StructuredError(
            "unknown",
            f"malformed operator_id {operator_id!r} — "
            "expected format ^op-[a-z0-9][a-z0-9-]{{2,63}}$")

    # 2. Find approval
    approval = registry.find_approval(approval_id)
    if approval is None:
        raise StructuredError(
            "audit_mismatch",
            f"approval_id {approval_id!r} was not issued by this registry")

    # 3. Expired check (MUST come before resolve_approval)
    expiry_min = (int(policy.get("approval_expiry_window")) if policy else 30)
    from ..core.registry import approval_is_expired
    if approval_is_expired(approval, registry.now(), expiry_min):
        raise StructuredError(
            "approval_expired",
            f"approval_id {approval_id!r} has expired "
            f"(window {expiry_min} min) — re-propose with delegate(preview=False)",
            next_action="preview_denied")

    # 4. Self-approval check
    proposer = approval.get("proposer_id")
    if proposer is not None and proposer == operator_id:
        raise StructuredError(
            "gate_failure",
            "self-approval denied: approver must differ from the proposing "
            "actor (operator-surface §Documenter Integration)")
    # proposer_id is None → allowed: unattributed proposal

    # 5. Resolve approval (single-use — raises token_replay if already resolved)
    resolved = registry.resolve_approval(approval_id, decision="approved",
                                         operator_id=operator_id)

    # 6. Emit event
    diff_hash = approval.get("diff_hash", "")
    target_id = approval.get("bound_to", {}).get("target_id", "")
    events.emit("documenter.approval", {
        "approval_id": approval_id,
        "operator_id": operator_id,
        "target_id": target_id,
        "diff_hash": diff_hash,
        "decision": "approved",
    })

    # 7. Return — write still pending application
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
) -> dict:
    """Apply an approved write to the target file (mvp-contract §2.2).

    Durability sequence: stage in target dir → fsync(file) → intent record
    (temp+rename+fsync) → rename → fsync(dir).

    Parameters
    ----------
    seams : dict, optional
        {key: callable} called at boundary points: "after_stage",
        "after_intent", "before_rename".  Used by tests to inject crash
        conditions.

    Returns
    -------
    dict with keys: applied, target_id, diff_hash, approval_id, next_action.
    """
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

    # 6. Acquire lock and perform the atomic sequence
    with DelegateLock(data_dir, policy.get("lock_wait_timeout") or 30):
        # 6a. Read source file bytes, sha256
        with open(target_path, "rb") as fh:
            source_bytes = fh.read()
        source_sha = "sha256:" + hashlib.sha256(source_bytes).hexdigest()

        # 6b. Apply unified diff to get new_text
        original_text = source_bytes.decode("utf-8")
        new_text = apply_unified_diff(original_text, normalized.decode("utf-8"))

        # 6c. Stage: write to .<basename>.<diffhash16>.tmp in target dir, fsync
        diffhash16 = diff_hash[7:23]  # first 16 hex chars after "sha256:"
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
        }
        registry.append("intent_record", intent_record)

        # Write intent_<approval_id>.json via temp+rename+fsync (crash safety)
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
        # fsync the data dir so the intent record is durable BEFORE the rename
        # (mvp-contract §2.2.4: intent record → fsync(dir) → rename).
        data_dir_fd = os.open(data_dir, os.O_RDONLY)
        try:
            os.fsync(data_dir_fd)
        finally:
            os.close(data_dir_fd)

        if seams and "after_intent" in seams:
            seams["after_intent"]()

        # 6e. Apply-time verification (C2, mvp-contract §2.2.3): recompute
        # sha256 of the SOURCE and compare against intent_record.per_file_sha256
        # (the intent record is the durable record of what was verified);
        # recompute sha256 of the WORKER/STAGED output and compare against the
        # APPROVED diff_hash. Any mismatch → hash_mismatch, write denied.
        intent_verified = registry.find_intent(target_id) or intent_record
        expected_source = intent_verified.get("per_file_sha256", {}).get(
            target_id, source_sha)
        with open(target_path, "rb") as fh:
            source_recheck = fh.read()
        source_sha_recheck = "sha256:" + hashlib.sha256(source_recheck).hexdigest()
        if source_sha_recheck != expected_source:
            raise StructuredError(
                "hash_mismatch",
                "source changed between approval and apply — "
                "write denied (expected {}, got {})".format(
                    expected_source, source_sha_recheck),
                next_action="resolve_finding")

        # Worker-output verification (C2): the staged bytes must equal the
        # bytes deterministically re-derived from the APPROVED diff (its
        # normalized hash was checked against the approval's diff_hash at
        # step 4) applied to the verified source. This closes the gap between
        # "approved hash" and "written bytes" (mvp-contract §2.2.3): a
        # tampered staged file diverges from new_text and is denied.
        approved_new_text = apply_unified_diff(
            source_recheck.decode("utf-8"), normalized.decode("utf-8"))
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

        # 6f. Atomic rename (same filesystem) + fsync dir
        os.replace(staged_path, target_path)
        dir_fd = os.open(target_dir, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

        if seams and "after_rename" in seams:
            seams["after_rename"]()

        # 6g. Append resolved intent_record; remove intent file (best-effort)
        resolved_intent = dict(intent_record)
        resolved_intent["resolved"] = True
        registry.append("intent_record", resolved_intent)
        # Consume the approval (append-only copy): a second apply_write with
        # the same approval_id hits the token_replay guard at step 2b.
        consumed = dict(registry.find_approval(approval_id))
        consumed["consumed"] = True
        consumed["consumed_at"] = registry.now()
        registry.append("token_record", consumed)
        try:
            os.remove(intent_file_path)
        except OSError:
            pass  # best-effort

    return {
        "applied": True,
        "target_id": target_id,
        "diff_hash": diff_hash,
        "approval_id": approval_id,
        "next_action": "write_applied",
    }


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
            # Clean up: move staged temp files to data_dir/staged/
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
                # Staged names are ".<basename>.<16hex>.tmp" (see apply_write).
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

    return results
