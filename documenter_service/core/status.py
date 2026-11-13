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

from .audit import _utc

__all__ = ["status", "TIER_INTERLOCK_REASON"]

#: tier_2_plus_locked is ALWAYS true in the MVP: there is no write code — that
#: absence IS the interlock (mvp-contract §MVP boundary).
TIER_INTERLOCK_REASON = (
    "No Tier 2+ code exists in the MVP build: the write branch of delegate(), "
    "documenter.approve, override_gate and the Multi-file Commit Protocol are "
    "structurally absent (mvp-contract §MVP boundary, §4). Advancement needs "
    "a policy file with allowed_operations, a non-null briefing_ref, and an "
    "Operator Surface out-of-band approval spec.")


def status(registry, policy=None, *, target_id: str | None = None) -> dict:
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

    last_audit = None
    last_record = None
    for rec in reversed(records):
        if rec["record_type"] == "audit_record":
            last_record = rec["data"]
            break
    pending = last_record if (last_record and last_record.get("has_remaining")) \
        else None
    if last_record is not None:
        data = last_record
        last_audit = {
            "audit_id": data.get("audit_id"),
            "issued_at": data.get("issued_at"),
            "fresh": _is_fresh(data.get("issued_at"), registry, policy),
        }

    active_tier = int(policy.get("active_tier")) if policy is not None else 0

    return {
        "active_tier": active_tier,
        "registry": {
            "status": reg_status,
            "last_audit": last_audit,
            # Staged files are Tier 2+ crash leftovers; the MVP cannot stage,
            # so this list is empty by construction (mvp-interfaces §3).
            "staged_files": [],
            # override_gate does not exist in the MVP (structurally absent),
            # so its counter is pinned at 0.
            "override_counter": 0,
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
        "tier_interlock": {
            "tier_2_plus_locked": True,
            "reason": TIER_INTERLOCK_REASON,
        },
    }


def _is_fresh(issued_at, registry, policy):
    """`fresh` = issued_at within audit_freshness (mvp-interfaces §3)."""
    if not issued_at:
        return False
    freshness = policy.get("audit_freshness") if policy is not None else 30
    age_min = (_utc(registry.now()) - _utc(issued_at)).total_seconds() / 60.0
    return age_min <= float(freshness)
