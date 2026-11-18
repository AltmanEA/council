"""Notices subsystem for the Operator Ingress.

Provides ``default_notices(policy_info=None, layer1_stub=True)`` that
returns a list of notice dicts with keys {type, severity, text}.
Severity values are drawn from {"Info", "Advisory", "Blocking"}.

This module NEVER reads documenter_policy.yml — policy_info is injected
as a dict {active_tier: int}.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Valid notice type identifiers
# ---------------------------------------------------------------------------

_VALID_TYPES = frozenset((
    "notice.simplification-applied",
    "notice.fallback-deferred",
    "notice.quick_review_disabled",
    "notice.documenter_tier2_interlock",
    "notice.layer1_stub_active",
))

_VALID_SEVERITIES = frozenset(("Info", "Advisory", "Blocking"))

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def default_notices(policy_info: dict | None = None,
                    layer1_stub: bool = True) -> list:
    """Build the default notices list for the operator status view.

    Args:
        policy_info: injected policy dict with optional ``active_tier``.
            When ``None`` the function fails closed (includes interlock).
        layer1_stub: when True, include the layer1-stub advisory notice.

    Returns:
        List of notice dicts, each with keys {type, severity, text}.
    """
    notices: list = []

    # Layer-1 stub advisory (always included when layer1_stub is True).
    if layer1_stub:
        notices.append({
            "type": "notice.layer1_stub_active",
            "severity": "Advisory",
            "text": (
                "temporary adapter; sessions are stored in a "
                "provisional format"
            ),
        })

    # Tier-2 interlock — fail closed when policy is unreadable (None)
    # or active_tier is below 2.
    tier_ok = False
    if policy_info is not None:
        tier_ok = policy_info.get("active_tier", 0) >= 2

    if not tier_ok:
        notices.append({
            "type": "notice.documenter_tier2_interlock",
            "severity": "Blocking",
            "text": (
                "Documenter Tier-2 write operations are interlocked; "
                "active_tier < 2 or policy unreadable"
            ),
        })

    return notices
