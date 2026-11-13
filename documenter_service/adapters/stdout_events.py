"""EventSink adapter — structured JSON events on stdout (conflict C4).

MVP carrier (operator-approved, mvp-data-models §3): the audit registry plus
ONE structured JSON line per event on stdout — a documented channel, not an
invented side-channel.

Every payload is schema-checked before emission:
  * VAL.001 — the payload keys must EXACTLY match the schema for the event
    type; unknown fields are rejected, never silently dropped.
  * Redaction rule — payload strings are capped at the description limit and
    may never carry full document text. Event producers pass identifiers,
    severities, and short summaries only; `diff_text` has no lawful path into
    any payload schema below.
"""
from __future__ import annotations

import json
import sys

from ..core.errors import StructuredError
from ..ports import EventSink

__all__ = ["StdoutEventSink", "EVENT_SCHEMAS", "DESCRIPTION_MAX_LEN"]

#: description bound from mvp-interfaces §1 (`description` 1–500 chars).
DESCRIPTION_MAX_LEN = 500

#: Payload schemas: event_type -> exact required key set (mvp-data-models §3
#: Event Channel table). Tier 2+ rows (documenter.approval, override_gate,
#: precheck.overridden, notice.*) stay reserved but their schemas are declared
#: here so a future adapter cannot widen MVP payloads ad hoc; the MVP emitter
#: only ever emits the three read-only types below.
EVENT_SCHEMAS = {
    "documenter.issue": frozenset(
        {"audit_id", "subject_id", "severity", "description"}),
    "documenter.approval": frozenset(
        {"approval_id", "operator_id", "target_id", "diff_hash"}),
    "documenter.override_gate": frozenset(
        {"reason", "operator_id", "target_id"}),
    "precheck.passed": frozenset({"audit_id", "target_id"}),
    "precheck.failed": frozenset(
        {"audit_id", "target_id", "blocking_severities"}),
    "precheck.overridden": frozenset({"reason", "operator_id"}),
    "notice.documenter_tier2_interlock": frozenset(
        {"requested_tier", "reason"}),
}

#: Event types the MVP build may emit.
MVP_EVENT_TYPES = ("documenter.issue", "precheck.passed", "precheck.failed",
                   "notice.documenter_tier2_interlock")

_SEVERITIES = ("low", "medium", "high", "critical")


class StdoutEventSink(EventSink):
    """Emit one structured JSON line per event to a text stream (stdout)."""

    def __init__(self, stream=None) -> None:
        self._stream = stream

    @property
    def stream(self):
        return self._stream if self._stream is not None else sys.stdout

    def emit(self, event_type: str, payload: dict) -> None:
        """Validate (VAL.001 + redaction) then emit; invalid → StructuredError.

        Rejection is a defect signal, not an operator condition: category is
        `unknown` (escalate) per mvp-interfaces §4.
        """
        if event_type not in EVENT_SCHEMAS:
            raise StructuredError(
                "unknown", f"unknown event type: {event_type!r}")
        if event_type not in MVP_EVENT_TYPES:
            raise StructuredError(
                "tier_interlock",
                f"event type {event_type!r} belongs to the Tier 2+ surface; "
                "the MVP build is read-only and cannot emit it")
        if not isinstance(payload, dict):
            raise StructuredError("unknown", "event payload must be a dict")
        keys = frozenset(payload.keys())
        if keys != EVENT_SCHEMAS[event_type]:
            raise StructuredError(
                "unknown",
                f"payload fields for {event_type} are {sorted(keys)}, "
                f"schema requires exactly {sorted(EVENT_SCHEMAS[event_type])} "
                "(VAL.001: producers MUST NOT emit unknown fields)")
        if event_type == "documenter.issue":
            if payload["severity"] not in _SEVERITIES:
                raise StructuredError(
                    "unknown", f"invalid severity in event payload: "
                               f"{payload['severity']!r}")
            self._check_description(payload["description"])
        elif event_type == "precheck.failed":
            sevs = payload["blocking_severities"]
            if not isinstance(sevs, list) or any(
                    s not in ("high", "critical") for s in sevs):
                raise StructuredError(
                    "unknown", "blocking_severities must be a list of "
                               "high|critical")
        for value in payload.values():
            for s in _strings_of(value):
                if len(s) > DESCRIPTION_MAX_LEN:
                    raise StructuredError(
                        "unknown",
                        f"payload string exceeds {DESCRIPTION_MAX_LEN} chars — "
                        "full document text must never reach an event")
        line = {"event_type": event_type, "payload": payload}
        self.stream.write(json.dumps(line, sort_keys=True,
                                     ensure_ascii=False) + "\n")
        self.stream.flush()

    @staticmethod
    def _check_description(description) -> None:
        if (not isinstance(description, str)
                or not 1 <= len(description) <= DESCRIPTION_MAX_LEN):
            raise StructuredError(
                "unknown",
                f"finding description must be a string of 1-{DESCRIPTION_MAX_LEN} "
                f"chars, got {type(description).__name__} len="
                f"{len(description) if isinstance(description, str) else 'n/a'}")


def _strings_of(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings_of(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings_of(v)
