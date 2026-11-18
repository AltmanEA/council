"""documenter.status() core — mvp-interfaces §3.

Single answer to "why is the gate rejecting right now?". Under
idle-until-invoked there is no background probe, so this call is the only
channel through which registry degradation becomes observable: a corrupt
registry MUST surface here instead of being silently skipped, and the service
never crashes because of it.

Response fields are exactly the §3 table (snake_case, no invented fields):
active_tier, registry {status, last_audit, staged_files, override_counter},
scan_status {has_pending_scan, pending_scan_cursor, blocking_operator},
tier_interlock {tier_2_plus_locked, reason}.
"""
from __future__ import annotations

import os

from .audit import _utc
from . import registry as reg
from .policy import OPERATOR_INGRESS_SENTINEL, operator_ingress_ready

__all__ = ["status", "TIER_INTERLOCK_REASON", "OPERATOR_INGRESS_SENTINEL"]

#: Static fallback reason (dual interlock, ADR-013). Used when the readiness
#: state cannot be probed (root unknown); status() prefers the dynamic
#: reason from _tier_interlock_state below.
TIER_INTERLOCK_REASON = (
    "Tier 2+ is dormant behind the dual interlock (ADR-013): the write branch "
    "is implemented but gated by policy (active_tier >= 2, allowed_operations, "
    "briefing_ref) AND by the unbuilt Operator Ingress — not activatable until "
    "the surface exists as code providing authenticated operator ingress "
    "(the Operator Ingress specification alone is not sufficient).")


def _tier_interlock_state(policy, root) -> dict:
    """Dynamic tier_interlock per mvp-interfaces §3 (dual interlock, ADR-013).

    tier_2_plus_locked is true while EITHER interlock level holds: policy tier
    below 2, or the Operator Ingress readiness sentinel missing under root.
    The reason names the blocking level so the operator sees "why is the gate
    rejecting right now?".
    """
    tier = int(policy.get("active_tier")) if policy is not None else 0
    if tier < 2:
        return {"tier_2_plus_locked": True,
                "reason": f"active_tier={tier} < 2 — policy gate holds "
                          "Tier 2+ dormant (first interlock level, ADR-013)"}
    if root is None or not operator_ingress_ready(root):
        sentinel = (os.path.join(root, OPERATOR_INGRESS_SENTINEL)
                    if root else OPERATOR_INGRESS_SENTINEL)
        return {"tier_2_plus_locked": True,
                "reason": "Operator Ingress not built (ADR-013): Tier 2+ is "
                          f"not activatable until the surface exists as code — "
                          f"sentinel missing at {sentinel}"}
    return {"tier_2_plus_locked": False,
            "reason": "both interlock levels released (policy gate open, "
                      "Operator Ingress sentinel present) — Tier 2+ calls "
                      "still pass the full guard chain in delegate()"}


def status(registry, policy=None, *, target_id: str | None = None,
           root: str | None = None) -> dict:
    """Build the documenter.status() response. Never raises on registry damage.

    registry — a JsonlAuditRegistry (read_all()/now()); policy — a loaded
    Policy or None. ``policy=None`` means the policy failed to load or was
    not consulted: active_tier falls back to 0 (the most restrictive tier —
    fail closed, Zero silent defaults) and the caller-visible degradation
    signal is the StructuredError surfaced by delegate() / the CLI stderr
    warning; status itself carries no policy_status field (VAL.001 — fields
    only from the mvp-interfaces §3 table).

    target_id is accepted per the §3 request table; in the MVP there is no
    per-document gate state to filter, so it is informational only.
    """
    records, reg_status = registry.read_all()

    # Collect all audit_records with their positions for ordering.
    audit_list = [(i, rec["data"]) for i, rec in enumerate(records)
                  if rec["record_type"] == "audit_record"]

    # last_audit: the very last audit_record in the file (for last_audit field).
    last_record = audit_list[-1][1] if audit_list else None
    last_audit = None
    if last_record is not None:
        data = last_record
        last_audit = {
            "audit_id": data.get("audit_id"),
            "issued_at": data.get("issued_at"),
            "fresh": _is_fresh(data.get("issued_at"), registry, policy),
        }

    # pending: any audit_id whose LATEST record has has_remaining=True.
    # Group by audit_id, keep the latest per id (last in list wins),
    # then find which have has_remaining=True.  Among those, pick the
    # most recently issued one.
    _latest_per_id: dict = {}
    for _i, rec_data in audit_list:
        aid = rec_data.get("audit_id")
        _latest_per_id[aid] = rec_data  # last write wins by position
    unclosed = [
        rec for rec in _latest_per_id.values()
        if rec.get("has_remaining") is True]
    # Most recent by issued_at among unclosed.
    pending = None
    if unclosed:
        pending = max(unclosed, key=lambda r: r.get("issued_at", ""))

    active_tier = int(policy.get("active_tier")) if policy is not None else 0

    # -- staged_files & override_counter (mvp-interfaces §3 table fields) ----
    # staged_files: unresolved intent_record leftovers from interrupted writes.
    # Source: logical intents (both legacy format with per_file_sha256 and
    # changeset format with tx_id/entries); only the latest record per intent
    # counts, so a resolved copy masks the staging record it resolves.
    # Deduplication keeps only the latest unresolved intent per target.
    _latest_intent: dict = {}
    for rec in records:
        if rec["record_type"] == reg.INTENT_RECORD:
            _latest_intent[reg.intent_key(rec["data"])] = rec["data"]
    _staged_map: dict = {}
    for data in _latest_intent.values():
        if data.get("resolved") is False:
            for tid in data.get("target_ids", []):
                _staged_map[tid] = {
                    "target_id": tid,
                    "staged_at": data.get("staged_at"),
                }
    staged_files = list(_staged_map.values())

    # override_counter: count of token_record entries with token_type=override_gate.
    # This is a registry-level counter (session-scoped deferred to Layer 2 — no
    # session identity in the MVP); single-operator deployment (ADR-007).
    override_counter = 0
    for rec in records:
        if (rec["record_type"] == reg.TOKEN_RECORD
                and rec["data"].get("token_type") == "override_gate"):
            override_counter += 1

    return {
        "active_tier": active_tier,
        "registry": {
            "status": reg_status,
            "last_audit": last_audit,
            "staged_files": staged_files,
            "override_counter": override_counter,
        },
        "scan_status": {
            "has_pending_scan": pending is not None,
            "pending_scan_cursor": pending.get("scan_cursor") if pending else None,
            # The MVP registry carries no operator identity (mvp-data-models
            # §1 has no operator field), so the blocker is named by the
            # pending audit_id; single-operator deployment (ADR-007).
            "blocking_operator": (
                f"pending scan audit_id={pending['audit_id']!r} "
                f"(scope={pending['scope']!r}) blocks every write under "
                "pre-audit rule 5; release by completing the rescan with "
                "audit(scan_cursor=...) — releasing another operator's scan "
                "is an operator-only action" if pending else None),
        },
        "tier_interlock": _tier_interlock_state(policy, root),
    }


def _is_fresh(issued_at, registry, policy):
    """`fresh` = issued_at within audit_freshness (mvp-interfaces §3)."""
    if not issued_at:
        return False
    freshness = policy.get("audit_freshness") if policy is not None else 30
    age_min = (_utc(registry.now()) - _utc(issued_at)).total_seconds() / 60.0
    return age_min <= float(freshness)
