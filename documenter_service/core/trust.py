"""Trust classification for delegate(preview) — mvp-interfaces §2, §Trust table.

The effective trust level is assigned by Documenter, not the caller (index.md
§Trust Classification): on the scale safe < review the invariant is
`requested >= derived`; a lower request is rejected with `trust_mismatch`
before any approval stage. Policy may raise the floor, never lower it.

MVP static floors (mvp-interfaces §2 Trust classification table):

    update    -> safe   (static floor; dynamic derivation is a Tier 2+ hook)
    split     -> review
    create_ru -> review (RU auto-fix banned in MVP)
    custom    -> review (default when indeterminate)
"""
from __future__ import annotations

from ..core.errors import StructuredError

__all__ = ["STATIC_FLOORS", "CHANGE_TYPES", "TRUST_LEVELS", "derive_trust",
           "check_invariant"]

#: change_type enum (mvp-interfaces §2 request table).
CHANGE_TYPES = ("update", "split", "create_ru", "custom")

#: trust_level enum (safe < review).
TRUST_LEVELS = ("safe", "review")

#: Static floor per change_type (policy-reference validator/authority rule).
STATIC_FLOORS = {
    "update": "safe",
    "split": "review",
    "create_ru": "review",
    "custom": "review",
}

_RANK = {"safe": 0, "review": 1}


def derive_trust(change_type: str) -> tuple:
    """Return (derived_level, reason) for ``change_type``.

    MVP derivation is static: `update` keeps the static floor `safe` — the
    dynamic "every hunk mechanical" derivation is reserved for the Tier 2+
    write path (mvp-contract §4) and MUST NOT gate MVP previews. Unknown
    change_type raises StructuredError(unknown): enum enforcement is a defect,
    not operator action.
    """
    if change_type not in STATIC_FLOORS:
        raise StructuredError(
            "unknown", f"unknown change_type: {change_type!r} "
                       "(closed enum: " + ", ".join(CHANGE_TYPES) + ")")
    floor = STATIC_FLOORS[change_type]
    return floor, f"static floor for change_type {change_type!r} is {floor!r} " \
                  "(mvp-interfaces §2 Trust classification table)"


def check_invariant(change_type: str, trust_level: str) -> tuple:
    """Validate the request against the derived floor; returns (level, reason).

    Raises StructuredError("trust_mismatch") when requested < derived, and
    StructuredError("unknown") for an unknown trust_level value.
    """
    derived, reason = derive_trust(change_type)
    if trust_level not in _RANK:
        raise StructuredError(
            "unknown", f"unknown trust_level: {trust_level!r} "
                       "(closed enum: " + ", ".join(TRUST_LEVELS) + ")")
    if _RANK[trust_level] < _RANK[derived]:
        raise StructuredError(
            "trust_mismatch",
            f"requested trust_level {trust_level!r} is below the derived floor "
            f"{derived!r} for change_type {change_type!r}: {reason}")
    return derived, reason
