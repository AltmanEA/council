"""Pre-check gate — real wiring with timeout enforcement, verdict logic, events.

Called by submit_task before committing a session (boundary-capable call site).
"""
from __future__ import annotations

import os
import threading

from ..core.events import make_envelope

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class RegistryIntegrityError(Exception):
    """Raised when the documenter registry is absent or corrupt.

    Distinct from general unavailability: this is a structural /
    configuration failure that should cause the gate to **fail**
    (fail-closed per C-03) rather than auto-proceed.
    """


# Read ONCE at module import time (immutability: changing os.environ
# after import must NOT affect this value — see test_case_9).
_PRE_CHECK_TIMEOUT_RAW = os.environ.get("PRE_CHECK_TIMEOUT")
PRE_CHECK_TIMEOUT_SECONDS: float = (
    float(_PRE_CHECK_TIMEOUT_RAW)
    if _PRE_CHECK_TIMEOUT_RAW is not None
    else 5.0
)

# Mapping from internal verdict string to event-type suffix.
_VERDICT_TO_EVENT: dict[str, str] = {
    "pass": "passed",
    "fail": "failed",
    "unavailable": "unavailable",
}


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def run_precheck(
    target_id: str,
    documenter_port=None,
    *,
    timeout=None,
    clock=None,  # reserved for future injection; unused
    event_sink=None,
    session_id=None,
    actor=None,
) -> dict:
    """Run the pre-check audit with timeout enforcement.

    Args:
        target_id: identifier for the target being pre-checked.
        documenter_port: optional DocumenterPort for audit call.
        timeout: wall-clock timeout in seconds (None → PRE_CHECK_TIMEOUT_SECONDS).
        clock: reserved for future injection; currently unused.
        event_sink: optional EventSink to receive envelope append calls.
        session_id: session identifier for event emission.
        actor: actor dict {kind, id} for event emission.

    Returns:
        dict with keys "verdict", "reason", "finding_count".
    """
    effective_timeout = (
        timeout
        if timeout is not None
        else PRE_CHECK_TIMEOUT_SECONDS
    )

    # --- Emit "running" event (always first) ---
    if event_sink is not None:
        _emit_event(
            event_sink,
            "precheck.running",
            session_id,
            actor,
        )

    # --- Perform the audit with timeout enforcement ---
    audit_result: dict | None = None
    try:
        audit_result = _run_audit_with_timeout(
            documenter_port,
            target_id,
            effective_timeout,
        )
    except RegistryIntegrityError:
        # Fail-closed: registry integrity problem → fail (NOT unavailable).
        _emit_verdict_event(
            event_sink, "fail",
            "Registry integrity error detected",
            session_id, actor,
        )
        return {
            "verdict": "fail",
            "reason": "Registry integrity error detected",
            "finding_count": 0,
        }
    except Exception:
        # Any other exception (TimeoutError, OSError, etc.) → unavailable.
        audit_result = {
            "verdict": "unavailable",
            "reason": "Documenter audit raised an exception",
            "finding_count": 0,
        }

    # --- Handle "audit result unavailable" (no port or exception) ---
    if audit_result is not None and audit_result.get("verdict") == "unavailable":
        _emit_verdict_event(
            event_sink,
            "unavailable",
            audit_result.get("reason", "unavailable"),
            session_id,
            actor,
        )
        return {
            "verdict": "unavailable",
            "reason": audit_result.get("reason", "unavailable"),
            "finding_count": 0,
        }

    # --- No port available → unavailable ---
    if audit_result is None:
        _emit_verdict_event(
            event_sink,
            "unavailable",
            "Audit disabled — no documenter port",
            session_id,
            actor,
        )
        return {
            "verdict": "unavailable",
            "reason": "Audit disabled — no documenter port",
            "finding_count": 0,
        }

    # --- Parse findings and determine verdict ---
    findings = _extract_findings(audit_result)
    finding_count = len(findings)

    if not findings:
        _emit_verdict_event(
            event_sink,
            "pass",
            "No findings",
            session_id,
            actor,
        )
        return {
            "verdict": "pass",
            "reason": "No findings",
            "finding_count": finding_count,
        }

    # Check for high/critical severity
    blocking_count = sum(
        1
        for f in findings
        if f.get("severity") in ("high", "critical")
    )

    if blocking_count > 0:
        reasons = [
            f["description"]
            for f in findings
            if f.get("severity") in ("high", "critical")
        ]
        _emit_verdict_event(
            event_sink,
            "fail",
            f"Blocked by {blocking_count} high/critical finding(s): "
            + "; ".join(reasons),
            session_id,
            actor,
        )
        return {
            "verdict": "fail",
            "reason": f"Blocked by {blocking_count} high/critical finding(s): "
            + "; ".join(reasons),
            "finding_count": finding_count,
        }

    # All low/medium → pass
    _emit_verdict_event(
        event_sink,
        "pass",
        "All findings are low/medium severity",
        session_id,
        actor,
    )
    return {
        "verdict": "pass",
        "reason": "All findings are low/medium severity",
        "finding_count": finding_count,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _run_audit_with_timeout(documenter_port, target_id, timeout):
    """Run the audit in a single daemon worker thread with wall-clock join.

    A daemon thread calls ``documenter_port.audit()``.  The main flow
    does ``worker.join(timeout)``; if the worker is still alive after
    the join the audit hung → raise ``TimeoutError``.  Because the
    worker is daemon, no further join is needed and the interpreter
    can exit without stalling — satisfying the spec's "MUST NOT block
    indefinitely" guarantee.

    Args:
        documenter_port: the port to call audit() on (must not be None).
        target_id: passed through to the audit call.
        timeout: seconds before the operation is considered timed out.

    Returns:
        The audit result dict.

    Raises:
        TimeoutError: if the audit takes longer than `timeout` seconds.
        RegistryIntegrityError: if the port raises this (propagated).
        Any other exception from the port: propagated.
    """
    _Holder = type("_Holder", (), {"result": None, "exc": None})
    holder = _Holder()

    def worker():
        """Execute the audit call; capture result or exception."""
        try:
            holder.result = documenter_port.audit(
                target_id=target_id, pre_check=True
            )
        except Exception as e:
            holder.exc = e

    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()
    worker_thread.join(timeout=timeout)

    if worker_thread.is_alive():
        # Still running → timeout.  Do NOT join again (daemon thread;
        # leaving it alive is safe — interpreter exit proceeds).
        raise TimeoutError("Pre-check timed out")

    # Worker finished.  Re-raise captured exception (or return result).
    if holder.exc is not None:
        raise holder.exc
    return holder.result


def _emit_event(sink, event_type, session_id, actor):
    """Emit an event to the sink if it's provided."""
    if sink is None:
        return
    eff_actor = actor if actor else {"kind": "service", "id": "operator-surface"}
    envelope = make_envelope(
        event_type,
        session_id=session_id,
        actor=eff_actor,
    )
    sink.append(envelope)


def _emit_verdict_event(sink, verdict, reason, session_id, actor):
    """Emit a precheck verdict event.

    Verdict strings are mapped to the frozen event-type enum:
      pass    → precheck.passed
      fail    → precheck.failed
      unavailable → precheck.unavailable
    """
    event_suffix = _VERDICT_TO_EVENT.get(verdict, verdict)
    _emit_event(sink, f"precheck.{event_suffix}", session_id, actor)


def _extract_findings(result):
    """Extract the findings list from an audit result.

    Accepts both the nested structure
    ``{"report": {"findings": [...]}}`` and the flat structure
    ``{"findings": [...]}``.

    Args:
        result: dict returned by the documenter audit.

    Returns:
        The findings list (may be empty).
    """
    findings = result.get("report", {}).get("findings")
    if findings is not None:
        return findings
    return result.get("findings", [])
