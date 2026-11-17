"""Volatile escalation store — in-process, never touches disk.

Frozen API:
  - EscalationStore(session_dir): open / get / list / resolve /
    supersede / mark_expired / had_escalations / volatile_notice
  - render(record) → dict  (exactly 4 keys)

Design: volatile / in-memory only.  The ``session_dir`` argument
provides a root for isolation testing but the store **never** opens,
writes, or accesses files on disk — a disk write is a defect.

Events are emitted via an injected ``EventSink`` (make_envelope)
at open() and resolve() time.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .events import make_envelope


# ---------------------------------------------------------------------------
# EscalationStore
# ---------------------------------------------------------------------------

_VALID_DECISIONS = frozenset(("accept", "reject"))


class EscalationStore:
    """Volatile in-process escalation record store.

    Two instances with different *session_dir* values share nothing.
    No disk I/O occurs in any method.
    """

    def __init__(self, session_dir: str) -> None:
        self._session_dir = session_dir
        self._records: dict[str, dict] = {}
        self._had: bool = False

    # -- lifecycle ops --------------------------------------------------

    def open(
        self,
        *,
        session_id: str,
        request: str,
        fallback_strategy: str,
        timeout_at: str | None,
        resume_phase: str,
        event_sink=None,
        actor: dict | None = None,
    ) -> dict:
        """Create a new pending escalation record."""
        esc_id = "esc-" + uuid.uuid4().hex
        record = {
            "escalation_id": esc_id,
            "session_id": session_id,
            "request": request,
            "fallback_strategy": fallback_strategy,
            "timeout_at": timeout_at,
            "resume_phase": resume_phase,
            "status": "pending",
            "created_at": _now_utc(),
        }
        self._records[esc_id] = record
        self._had = True

        if event_sink is not None:
            _actor = actor if actor is not None else {"kind": "service", "id": "operator-surface"}
            envelope = make_envelope(
                "escalation.opened",
                session_id=session_id,
                actor=_actor,
                payload={
                    "escalation_id": esc_id,
                    "session_id": session_id,
                    "request": request,
                },
            )
            event_sink.append(envelope)

        return dict(record)

    def get(self, escalation_id: str) -> dict | None:
        """Return a shallow copy of the record dict, or *None*."""
        rec = self._records.get(escalation_id)
        return dict(rec) if rec is not None else None

    def list(self, session_id: str | None = None) -> list[dict]:
        """Return shallow copies of records (or filtered by *session_id*)."""
        if session_id is None:
            return [dict(r) for r in self._records.values()]
        return [
            dict(r) for r in self._records.values()
            if r["session_id"] == session_id
        ]

    # -- state transitions ----------------------------------------------

    def resolve(
        self,
        escalation_id: str,
        decision: str,
        operator_id: str,
        event_sink=None,
    ) -> dict:
        """Transition pending→accepted|rejected (terminal, immutable)."""
        if decision not in _VALID_DECISIONS:
            raise ValueError(
                f"Invalid decision {decision!r}; "
                f"expected one of {sorted(_VALID_DECISIONS)}"
            )
        rec = self._records.get(escalation_id)
        if rec is None:
            raise ValueError(f"Unknown escalation: {escalation_id}")
        if rec["status"] != "pending":
            raise ValueError(
                f"Cannot resolve escalation {escalation_id}: "
                f"already {rec['status']}"
            )
        rec["status"] = "accepted" if decision == "accept" else "rejected"
        rec["resolved_by"] = operator_id

        if event_sink is not None:
            envelope = make_envelope(
                "escalation.resolved",
                session_id=rec["session_id"],
                actor={"kind": "operator", "id": operator_id},
                payload={
                    "escalation_id": escalation_id,
                    "session_id": rec["session_id"],
                    "decision": decision,
                    "operator_id": operator_id,
                },
            )
            event_sink.append(envelope)

        return dict(rec)

    def supersede(self, escalation_id: str) -> dict:
        """Transition pending→superseded (single-shot)."""
        rec = self._records.get(escalation_id)
        if rec is None:
            raise ValueError(f"Unknown escalation: {escalation_id}")
        if rec["status"] != "pending":
            raise ValueError(
                f"Cannot supersede escalation {escalation_id}: "
                f"already {rec['status']}"
            )
        rec["status"] = "superseded"
        return dict(rec)

    def mark_expired(self, escalation_id: str) -> dict:
        """Transition pending→expired (single-shot)."""
        rec = self._records.get(escalation_id)
        if rec is None:
            raise ValueError(f"Unknown escalation: {escalation_id}")
        if rec["status"] != "pending":
            raise ValueError(
                f"Cannot mark_expired escalation {escalation_id}: "
                f"already {rec['status']}"
            )
        rec["status"] = "expired"
        return dict(rec)

    # -- volatility helpers ---------------------------------------------

    def had_escalations(self) -> bool:
        """Return True if any record was ever opened."""
        return self._had

    def volatile_notice(self) -> dict | None:
        """Return a notice dict if had_escalations() else None."""
        if not self._had:
            return None
        return {
            "type": "notice.fallback-deferred",
            "severity": "Advisory",
            "text": (
                "This session has pending or unresolved escalation(s). "
                "Escalation state is volatile — on process restart it "
                "will not persist. Confirm fallback behaviour before "
                "continuing."
            ),
        }


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

def render(record: dict) -> dict:
    """Project an *EscalationRecord* to the MVP 4-field view.

    Returns exactly {request, fallback_consequences, deadline, status}.
    """
    return {
        "request": record["request"],
        "fallback_consequences": record["fallback_strategy"],
        "deadline": record["timeout_at"] if record.get("timeout_at") else "no deadline",
        "status": record["status"],
    }


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    """Return current UTC time as ISO-8601 string with Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
