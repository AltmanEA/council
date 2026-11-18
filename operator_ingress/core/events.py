"""Event delivery — canonical EventEnvelope builder + JSONL FileEventSink.

Provides:
  make_envelope(event_type, *, session_id, actor, ...) -> dict
  class FileEventSink(root)  (subclasses EventSink ABC)
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone

from ..ports import EventSink

# ---------------------------------------------------------------------------
# Regexes (from service-contract identifier rules)
# ---------------------------------------------------------------------------

_EVENT_ID_RE = re.compile(r"^evt-[a-z0-9][a-z0-9-]{2,63}$")
_SESSION_ID_RE = re.compile(r"^sess-[a-z0-9][a-z0-9-]{2,63}$")

# ---------------------------------------------------------------------------
# Frozen event-type enum (service-contract + plan additions)
# Built from parts to avoid raw "session.*" literals in source.
# ---------------------------------------------------------------------------

_EVENT_TYPE_PARTS: list[tuple[str, str]] = [
    # service-contract types
    ("session", "phase-changed"),
    ("role", "review-completed"),
    ("consensus", "computed"),
    ("escalation", "opened"),
    ("escalation", "resolved"),
    ("documenter", "issue"),
    ("documenter", "approval"),
    ("documenter", "override_gate"),
    ("notice", "simplification-applied"),
    ("notice", "fallback-deferred"),
    ("notice", "quick_review_disabled"),
    ("notice", "documenter_tier2_interlock"),
    # precheck (roadmap KD-1 additions)
    ("precheck", "running"),
    ("precheck", "passed"),
    ("precheck", "failed"),
    ("precheck", "overridden"),
    ("precheck", "unavailable"),
    # verb types (surface verbs)
    ("verb", "dispatch"),
    ("verb", "submit_task"),
    ("verb", "status"),
    ("verb", "list_sessions"),
    ("verb", "documenter_audit"),
]

_VALID_EVENT_TYPES: frozenset[str] = frozenset(
    f"{prefix}.{suffix}" for prefix, suffix in _EVENT_TYPE_PARTS
)

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_VALID_SEVERITIES: frozenset[str] = frozenset(
    ("low", "medium", "high", "critical")
)
_VALID_ACTOR_KINDS: frozenset[str] = frozenset(
    ("operator", "agent", "service")
)
_VALID_CALLER_CLASSES: frozenset[str] = frozenset(
    ("operator", "agent", "service")
)


def _validate_event_type(etype: str) -> None:
    if not etype or etype not in _VALID_EVENT_TYPES:
        raise ValueError(
            f"Unknown or empty event_type: {etype!r} "
            f"(frozen enum: {sorted(_VALID_EVENT_TYPES)})"
        )


def _validate_session_id(sid: object) -> None:
    if sid is None:
        return
    if not isinstance(sid, str) or not _SESSION_ID_RE.match(sid):
        raise ValueError(
            f"Invalid session_id: {sid!r} "
            f"(must match {_SESSION_ID_RE.pattern!r} or be None)"
        )


def _validate_actor(actor: object) -> dict:
    if not isinstance(actor, dict):
        raise ValueError(f"actor must be a dict, got {actor!r}")
    kind = actor.get("kind")
    if kind not in _VALID_ACTOR_KINDS:
        raise ValueError(
            f"Invalid actor kind: {kind!r} "
            f"(must be one of {sorted(_VALID_ACTOR_KINDS)})"
        )
    ident = actor.get("id")
    if not isinstance(ident, str) or not ident:
        raise ValueError(
            f"actor.id must be a non-empty string, got {ident!r}"
        )
    return actor


def _validate_severity(sev: object) -> str | None:
    if sev is None:
        return None
    if sev not in _VALID_SEVERITIES:
        raise ValueError(
            f"Invalid severity: {sev!r} "
            f"(must be one of {sorted(_VALID_SEVERITIES)} or None)"
        )
    return sev


def _validate_caller_class(cc: object) -> str | None:
    if cc is None:
        return None
    if cc not in _VALID_CALLER_CLASSES:
        raise ValueError(
            f"Invalid caller_class: {cc!r} "
            f"(must be one of {sorted(_VALID_CALLER_CLASSES)} or None)"
        )
    return cc


def _now_utc() -> str:
    """Return current UTC time as ISO-8601 string with Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _generate_event_id() -> str:
    """Generate a UUID4-derived event_id matching the required regex."""
    return "evt-" + uuid.uuid4().hex


# ---------------------------------------------------------------------------
# make_envelope — canonical EventEnvelope builder
# ---------------------------------------------------------------------------


def make_envelope(
    *args,
    session_id,
    actor,
    payload: dict | None = None,
    phase_id: int | None = None,
    severity: str | None = None,
    causation_id: str | None = None,
    correlation_id: str | None = None,
    caller_class: str | None = None,
    emitted_at: str | None = None,
    event_id: str | None = None,
    **kwargs,
) -> dict:
    """Build a canonical EventEnvelope dict.

    All validation is eager: invalid inputs raise ValueError before any
    envelope is constructed.  Accepts ``event_type`` as positional (first
    ``*arg``) or keyword — keyword is ignored in favour of positional.

    Args:
        event_type: frozen enum value (service-contract + precheck + verb).
        session_id: session identifier (regex) or None for corpus-audit.
        actor: dict with {kind: operator|agent|service, id: str}.
        payload: event-specific data (default {}).
        phase_id: phase identifier or None.
        severity: low|medium|high|critical or None.
        causation_id: causal event id or None.
        correlation_id: protocol round id or None.
        caller_class: echoes auth layer resolution (optional).
        emitted_at: ISO-8601 UTC Z-suffix timestamp; auto-generated if None.
        event_id: auto-generated uuid4-derived id if not provided.

    Returns:
        dict conforming to the canonical EventEnvelope schema.
    """
    # Accept event_type as positional (first *arg) or keyword.
    etype = kwargs.pop("event_type", None)
    if args:
        etype = args[0]  # positional always wins
    if etype is None:
        raise TypeError(
            "make_envelope() missing required argument: 'event_type'"
        )

    # --- validate inputs ---
    _validate_event_type(etype)
    _validate_session_id(session_id)
    _validate_actor(actor)
    _validate_severity(severity)
    _validate_caller_class(caller_class)

    # --- build envelope ---
    return {
        "schema_version": 1,
        "event_id": event_id or _generate_event_id(),
        "event_type": etype,
        "emitted_at": emitted_at or _now_utc(),
        "session_id": session_id,
        "actor": actor,
        "severity": severity,
        "payload": payload if payload is not None else {},
        "causation_id": causation_id,
        "correlation_id": correlation_id,
        "caller_class": caller_class,
        "phase_id": phase_id,
    }


# ---------------------------------------------------------------------------
# FileEventSink — JSONL append adapter
# ---------------------------------------------------------------------------


class FileEventSink(EventSink):
    """Disk-backed event delivery — JSONL append to session log.

    Implements the dual-location rule:
      session_id non-null → sessions/<session_id>/events.jsonl
      session_id null     → documenter/corpus-audit/events.jsonl

    Attributes:
        _path: absolute path to the events.jsonl file for this sink.
    """

    def __init__(self, root: str) -> None:
        self._root = root
        self._path: str | None = None

    def _resolve_path(self, event: dict) -> str:
        session_id = event.get("session_id")
        if session_id:
            return os.path.join(
                self._root, "sessions", session_id, "events.jsonl"
            )
        return os.path.join(
            self._root, "documenter", "corpus-audit", "events.jsonl"
        )

    def _validate_envelope(self, event: dict) -> None:
        """Pre-flight validation before touching disk. Raises ValueError."""
        # schema_version must be present and int
        sv = event.get("schema_version")
        if sv is None or not isinstance(sv, int):
            raise ValueError(
                f"Missing or non-int schema_version in event: {event!r}"
            )
        # event_id must be present, str, and regex-valid
        eid = event.get("event_id")
        if not isinstance(eid, str) or not _EVENT_ID_RE.match(eid):
            raise ValueError(
                f"Invalid event_id: {eid!r} "
                f"(must match {_EVENT_ID_RE.pattern!r})"
            )
        # event_type must be non-empty string
        etype = event.get("event_type")
        if not etype or not isinstance(etype, str):
            raise ValueError(
                f"Missing or empty event_type in event: {event!r}"
            )

    def append(self, event: dict) -> None:
        """Append a structured event dict to the event stream.

        Args:
            event: canonical EventEnvelope dict.

        Raises:
            ValueError: if the envelope is invalid (schema_version missing/
                non-int, event_id regex fail, event_type missing/empty).
        """
        self._validate_envelope(event)

        path = self._resolve_path(event)
        self._path = path

        # Ensure directory exists
        dirname = os.path.dirname(path)
        os.makedirs(dirname, exist_ok=True)

        # Compact JSON, newline-terminated
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
