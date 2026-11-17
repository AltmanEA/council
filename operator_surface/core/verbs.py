"""Pure-function verb handlers for the Operator Surface.

Core modules know only the ports defined in ports.py; they never import
operator_surface.adapters.* (assembly wiring in __main__.py).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..core.approval import ApprovalError, hash_diff
from ..core.envelope import error_envelope
from ..core.events import make_envelope
from ..core.notices import default_notices
from ..core.precheck import run_precheck
from ..core.escalations import render


# ---------------------------------------------------------------------------
# Volatile single-use registry for precheck overrides (in-memory only).
# ---------------------------------------------------------------------------
_precheck_override_consumed: set[tuple[str, str]] = set()


# ---------------------------------------------------------------------------
# Verb functions
# ---------------------------------------------------------------------------


def submit_task(
    store,
    events,
    task_brief: str,
    scenario_id: str,
    operator_id: str,
    precheck_gate=None,
    documenter_port=None,
) -> dict:
    """Run pre-check, create session, write session + intent, emit event.

    Returns dict with keys: session_id, status, operator_id.
    Adds "precheck":"unavailable" when the gate is unavailable but
    auto-proceeds (timeout-and-continue).
    """
    # Pre-check before committing (boundary-capable call site).
    if precheck_gate is not None:
        precheck_result = precheck_gate(scenario_id=scenario_id)
    else:
        precheck_result = run_precheck(
            target_id=scenario_id,
            documenter_port=documenter_port,
            event_sink=events,
            actor={"kind": "operator", "id": operator_id},
        )

    if precheck_result.get("verdict") == "pass":
        session_id = _commit_session(
            store, events, task_brief, scenario_id, operator_id,
        )
        return {
            "session_id": session_id,
            "status": "submitted",
            "operator_id": operator_id,
        }

    if precheck_result.get("verdict") == "unavailable":
        # Auto-proceed: commit the session but mark the gate as unavailable.
        session_id = _commit_session(
            store, events, task_brief, scenario_id, operator_id,
        )
        return {
            "session_id": session_id,
            "status": "submitted",
            "operator_id": operator_id,
            "precheck": "unavailable",
        }

    # Fail → REFUSE: no session, no intent.
    return {
        "error": error_envelope(
            "VAL.003",
            message=precheck_result.get(
                "reason",
                "A required field is missing from the input",
            ),
        ),
    }


def _commit_session(store, events, task_brief, scenario_id, operator_id):
    """Create session, write intent, emit verb event.

    Called when precheck passes or when auto-proceeding on unavailable.

    Returns:
        The generated session_id string.
    """
    session_id = "sess-" + uuid.uuid4().hex[:12]

    store.create_session(session_id)
    store.append_record(session_id, {
        "intent_id": "evt-" + uuid.uuid4().hex,
        "session_id": session_id,
        "verb": "council.submit_task",
        "operator_id": operator_id,
    })

    envelope = make_envelope(
        "verb.submit_task",
        session_id=session_id,
        actor={"kind": "operator", "id": operator_id},
        payload={
            "task_brief": task_brief,
            "scenario_id": scenario_id,
        },
    )
    events.append(envelope)

    return session_id


def status(store, notices_provider, operator_id: str | None = None, escalation_store=None) -> dict:
    """Operator status: list of sessions + notices + identity markers.

    Always returns session_id=None (operator-level view).

    Args:
        store: Layer1Port session store.
        notices_provider: callable returning a list of notice dicts.
        operator_id: operator identifier.
        escalation_store: optional EscalationStore instance.  When present
            and had_escalations() is True, pending records are rendered via
            render() into result["escalations"] and a volatile notice is
            appended to result["notices"].
    """
    notices_list = notices_provider()

    result: dict = {
        "sessions": store.list_sessions(),
        "notices": notices_list,
        "operator_id": operator_id,
        "session_id": None,
    }

    if escalation_store is not None:
        all_records = escalation_store.list()
        pending_records = [r for r in all_records if r["status"] == "pending"]
        result["escalations"] = [render(r) for r in pending_records]

        if escalation_store.had_escalations():
            notice = escalation_store.volatile_notice()
            if notice is not None:
                result["notices"] = list(notices_list) + [notice]
    else:
        result["escalations"] = []

    return result


def list_sessions(store, phase_state=None, mode=None, operator_id: str | None = None) -> dict:
    """List all sessions (read-only — never writes).

    Returns dict with sessions list, operator_id, and session_id=None.
    """
    return {
        "sessions": store.list_sessions(),
        "operator_id": operator_id,
        "session_id": None,
    }


def documenter_audit(documenter_port, target_id: str = "*") -> dict:
    """Pass-through to DocumenterPort.audit().

    Returns the result dict verbatim.
    """
    return documenter_port.audit(target_id)


def documenter_delegate(
    documenter_port,
    approval_registry,
    target_id: str,
    change_type: str,
    diff: str,
    operator_id: str,
    events,
) -> dict:
    """Create a delegate request: preview + register approval request.

    Calls the documenter port's delegate_preview (Tier 0-1 pass-through),
    registers an ApprovalRegistry request, and returns the result with
    status "approval_required". Emits NO surface event (Tier 0-1 pass-through).

    Args:
        documenter_port: injected DocumenterPort.
        approval_registry: ApprovalRegistry instance.
        target_id: target document identifier.
        change_type: type of change (e.g. "edit", "update").
        diff: the diff text.
        operator_id: the proposer operator.
        events: EventSink for event delivery (unused — no emission).

    Returns:
        dict with request_id, diff_preview, target_id, change_type, status.
    """
    request_id = str(uuid.uuid4())
    diff_hash_val = hash_diff(diff)
    preview = documenter_port.delegate_preview(
        target_id, change_type, "operator", diff
    )
    approval_registry.register_request(request_id, diff_hash_val, operator_id)
    return {
        "request_id": request_id,
        "diff_preview": preview,
        "target_id": target_id,
        "change_type": change_type,
        "status": "approval_required",
    }


def documenter_approve(
    approval_registry,
    request_id: str,
    operator_id: str,
    diff: str,
    events,
) -> dict:
    """Approve a delegate request via the approval registry.

    On success emits ONE "documenter.approval" event; on error returns
    an envelope with the ApprovalError's code and reason.

    Args:
        approval_registry: ApprovalRegistry instance.
        request_id: UUID string of the request to approve.
        operator_id: operator performing the approval.
        diff: diff text for hash verification.
        events: EventSink for event delivery.

    Returns:
        dict with request_id, status, proposer_operator_id, approver_operator_id
        on success, or {"error": envelope} on failure.
    """
    try:
        record = approval_registry.approve(request_id, operator_id, diff)
    except ApprovalError as exc:
        return {"error": error_envelope(exc.code, reason=exc.reason)}

    events.append(
        make_envelope(
            "documenter.approval",
            session_id=None,
            actor={"kind": "operator", "id": operator_id},
            payload={
                "request_id": request_id,
                "proposer_operator_id": record["proposer_operator_id"],
                "approver_operator_id": operator_id,
            },
        )
    )
    return {
        "request_id": request_id,
        "status": "approved",
        "proposer_operator_id": record["proposer_operator_id"],
        "approver_operator_id": operator_id,
    }


# ---------------------------------------------------------------------------
# Override / resolve verbs (Cycle 9 Step 8)
# ---------------------------------------------------------------------------


def resolve_escalation(
    escalation_store,
    *,
    session_id: str,
    escalation_id: str,
    decision: str,
    operator_id: str,
    events,
    note: str | None = None,
    caller_class: str = "operator",
) -> dict:
    """Resolve a pending escalation.

    Guard order (fail-fast, no mutation on failure):
      1. caller_class != "operator"     → AUTH.003 (no event, no change)
      2. escalation_store is None        → VAL.003 (no event, no change)
      3. store.get(escalation_id) is None → VAL.003 (no event, no change)
      4. record.session_id mismatch      → VAL.003 (no event, no change)
      5. decision not in {accept,reject} → VAL.002 (no event, no change)
      6. store.resolve ValueError        → VAL.001 (reason mentions pending/already)

    On success the store itself emits ONE escalation.resolved event via
    event_sink=events; this verb emits nothing itself.

    Returns the resolved record dict (fresh copy) or an error envelope.
    """
    # Guard 1: caller must be operator.
    if caller_class != "operator":
        return {
            "error": {
                "code": "AUTH.003",
                "message": "unauthorized caller",
                "action": "use operator role",
                "reason": (
                    f"Only operators may resolve escalations "
                    f"(caller_class={caller_class!r})"
                ),
            },
        }

    # Guard 2: store must exist.
    if escalation_store is None:
        return {"error": error_envelope("VAL.003")}

    # Guard 3: escalation must exist.
    record = escalation_store.get(escalation_id)
    if record is None:
        return {"error": error_envelope("VAL.003")}

    # Guard 4: session_id binding.
    if record["session_id"] != session_id:
        return {"error": error_envelope("VAL.003")}

    # Guard 5: decision must be valid.
    if decision not in ("accept", "reject"):
        return {"error": error_envelope("VAL.002")}

    # Guard 6: resolve via store (ValueError → VAL.001).
    try:
        result = escalation_store.resolve(
            escalation_id, decision, operator_id, event_sink=events
        )
        result = dict(result)  # defensive copy
        if note is not None:
            result["note"] = note
        return result
    except ValueError as exc:
        return {"error": error_envelope("VAL.001", reason=str(exc))}


def override_precheck(
    store,
    *,
    session_id: str,
    reason: str | None,
    operator_id: str,
    events,
) -> dict:
    """Grant a single-use precheck override.

    Mandatory reason: None / empty / whitespace-only → VAL.003, no side
    effects (no event, no append_record).

    On valid grant:
      - store.append_record(session_id, {...})
      - ONE precheck.overridden event via events
      - populate single-use registry
      - return {"status": "override_granted", ...}

    Returns a fresh dict (defensive copy).
    """
    # Guard: mandatory reason.
    if not reason or not reason.strip():
        return {"error": error_envelope("VAL.003")}

    override_id = uuid.uuid4().hex
    granted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Append record to store.
    store.append_record(session_id, {
        "verb": "council.override_precheck",
        "session_id": session_id,
        "operator_id": operator_id,
        "reason": reason,
        "override_id": override_id,
        "granted_at": granted_at,
    })

    # Emit ONE event.
    events.append(
        make_envelope(
            "precheck.overridden",
            session_id=session_id,
            actor={"kind": "operator", "id": operator_id},
            payload={
                "session_id": session_id,
                "reason": reason,
                "operator_id": operator_id,
            },
        )
    )

    # Populate single-use registry.
    _precheck_override_consumed.add((session_id, operator_id))

    # Return fresh dict.
    return {
        "status": "override_granted",
        "session_id": session_id,
        "operator_id": operator_id,
    }


def consume_precheck_override(session_id: str, operator_id: str) -> bool:
    """Consume a single-use precheck override grant.

    Returns True exactly once for a (session_id, operator_id) that was
    granted via override_precheck, then False.  Returns False when never
    granted.

    Volatile in-memory only — no disk I/O.
    """
    key = (session_id, operator_id)
    if key in _precheck_override_consumed:
        _precheck_override_consumed.remove(key)
        return True
    return False


def override_gate(
    documenter_port,
    *,
    target_id: str,
    reason: str | None,
    operator_id: str,
    events,
) -> dict:
    """Override a documenter gate failure (Tier 2+ writes remain dormant).

    Mandatory reason: None / empty / whitespace → VAL.003, NO event,
    PORT NEVER CALLED.

    On valid grant:
      - ONE documenter.override_gate event via events
      - return {"status": "overridden", ...}

    documenter_port is accepted but never invoked (ADR-013: write branch
    unreachable).
    """
    # Guard: mandatory reason.
    if not reason or not reason.strip():
        return {"error": error_envelope("VAL.003")}

    # Emit ONE event (port NOT called).
    events.append(
        make_envelope(
            "documenter.override_gate",
            session_id=None,
            actor={"kind": "operator", "id": operator_id},
            payload={
                "target_id": target_id,
                "reason": reason,
                "operator_id": operator_id,
            },
        )
    )

    # Return fresh dict.
    return {
        "status": "overridden",
        "target_id": target_id,
        "operator_id": operator_id,
    }
