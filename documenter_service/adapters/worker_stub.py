"""WorkerPort stub — Tier 2+ execution port, permanently interlocked (ADR-007).

The MVP build contains NO worker implementation and NO write path: the
absence of code is the interlock (mvp-contract §MVP boundary). This stub
exists only so the port surface is testable: EVERY method call raises
StructuredError(error_category="tier_interlock", next_action="preview_denied")
without touching the filesystem. Removing this file would not widen any
capability — there is nothing behind it.

Advancement (mvp-contract §4): requires a policy file with
allowed_operations, a non-null briefing_ref, AND an Operator Surface spec
defining an authenticated out-of-band approval channel. A real Layer 1
adapter arrives with that work, never here.
"""
from __future__ import annotations

from ..core.errors import StructuredError
from ..ports import WorkerPort

__all__ = ["InterlockedWorkerStub"]

_INTERLOCK_REASON = (
    "Tier 2+ is locked in the MVP scaffold: the write branch of delegate(), "
    "documenter.approve, override_gate and the Multi-file Commit Protocol "
    "are structurally absent (mvp-contract §MVP boundary, ADR-007). "
    "delegate(preview: true) is the only preview surface available.")


class InterlockedWorkerStub(WorkerPort):
    """Every execution attempt refused with the tier interlock — by design."""

    def execute(self, intent: dict) -> dict:
        raise StructuredError("tier_interlock", _INTERLOCK_REASON)
