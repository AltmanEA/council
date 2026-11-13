"""Structured errors for the Documenter Service MVP — mvp-interfaces §4.

Every refusal is a StructuredError carrying a CLOSED error_category enum and a
next_action from the CLOSED next_action enum, so the operator always knows the
next step (mvp-interfaces §4). `unknown` is reserved for genuine defects.
"""
from __future__ import annotations

__all__ = [
    "StructuredError",
    "ERROR_CATEGORIES",
    "NEXT_ACTIONS",
    "CATEGORY_DEFAULT_ACTION",
]

#: Closed error_category enum (mvp-interfaces §4 "Error categories").
ERROR_CATEGORIES = (
    "audit_mismatch",
    "blocking_finding",
    "tier_interlock",
    "approval_expired",
    "approval_invalidated",
    "hash_mismatch",
    "trust_mismatch",
    "token_replay",
    "lock_conflict",
    "gate_failure",
    "unknown",
)

#: Closed next_action enum (mvp-interfaces §4).
NEXT_ACTIONS = (
    "preview_only",
    "await_approval",
    "rerun_audit",
    "resolve_finding",
    "rescan_to_completion",
    "preview_denied",
    "escalate",
)

#: Default next_action per error category (canonical pairing table,
#: mvp-interfaces §4 "Returned when" column).
CATEGORY_DEFAULT_ACTION = {
    "audit_mismatch": "rerun_audit",
    "blocking_finding": "resolve_finding",
    "tier_interlock": "preview_denied",
    "approval_expired": "rerun_audit",
    "approval_invalidated": "rerun_audit",
    "hash_mismatch": "rerun_audit",
    "trust_mismatch": "resolve_finding",
    "token_replay": "rerun_audit",
    "lock_conflict": "rerun_audit",
    "gate_failure": "rerun_audit",
    "unknown": "escalate",
}


class StructuredError(Exception):
    """Fatal refusal with a machine-readable category and next step.

    ``error_category`` MUST be one of ERROR_CATEGORIES and ``next_action`` one
    of NEXT_ACTIONS; a default action is derived from the category when not
    given explicitly. Fail loud on enum violations: an unenumerated refusal is
    a contract bug (mvp-interfaces §4).
    """

    def __init__(self, error_category: str, message: str,
                 next_action: str | None = None) -> None:
        if error_category not in ERROR_CATEGORIES:
            raise ValueError(f"unknown error_category: {error_category!r}")
        action = next_action or CATEGORY_DEFAULT_ACTION[error_category]
        if action not in NEXT_ACTIONS:
            raise ValueError(f"unknown next_action: {action!r}")
        super().__init__(message)
        self.error_category = error_category
        self.next_action = action
        self.message = message

    def to_dict(self) -> dict:
        """Error response body (snake_case, no unknown fields)."""
        return {
            "error_category": self.error_category,
            "message": self.message,
            "next_action": self.next_action,
        }
