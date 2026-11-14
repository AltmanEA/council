"""EventSink adapter — append-only JSONL persistence (corpus-audit).

mvp-contract §1 / configuration-guide §Delivery Semantics: events are emitted
synchronously and persisted via ``$WORKSPACE/documenter/events/`` for operator
replay. Single storage location — corpus-wide Documenter audits read from
``documenter/corpus-audit/events.jsonl``. Consumers deduplicate by ``event_id``;
the contract is append-only.

mvp-data-models §3 (MVP channel): the primary carrier is the registry plus
stdout JSON (StdoutEventSink). FileEventSink adds durable persistence alongside
that carrier, so a crash does not lose events the operator could replay.

File format (one JSON object per line):
  {
      "event_id":    "<uuid4>",        # consumer dedup key
      "emitted_at":  "<ISO-8601 Z>",  # wall-clock at write time
      "event_type":  "<string>",      # event type (VAL.001 schema)
      "payload":     { ... }          # validated payload, exact schema keys
  }

Validation is delegated to the parent StdoutEventSink — no schema logic is
duplicated in this module.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone

from ..core.errors import StructuredError
from .stdout_events import StdoutEventSink

__all__ = ["FileEventSink"]


class _DiscardStream:
    """No-op stream: writes are silently dropped."""

    def write(self, data: str) -> int:
        return len(data)

    def flush(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Log-level filter (local copy — avoids circular import with __main__).
# ---------------------------------------------------------------------------
_STDERR_LOG_RANK = {"debug": 10, "info": 20, "warn": 30, "error": 40}


def _file_event_log_warn(msg: str) -> None:
    """Emit a stderr warning filtered by DOCUMENTER_LOG_LEVEL.

    Default log level is "info" (rank 20); "warn" (rank 30) is emitted.
    When DOCUMENTER_LOG_LEVEL=error (rank 40), this warning is suppressed.
    """
    configured = os.environ.get("DOCUMENTER_LOG_LEVEL", "info").lower()
    threshold = _STDERR_LOG_RANK.get(configured, _STDERR_LOG_RANK["info"])
    if _STDERR_LOG_RANK.get("warn", _STDERR_LOG_RANK["warn"]) >= threshold:
        print(msg, file=sys.stderr)


class FileEventSink(StdoutEventSink):
    """Structured event emitter with append-only JSONL file persistence.

    Inherits all validation from StdoutEventSink (VAL.001, MVP_EVENT_TYPES,
    redaction, severity checks). Validation output goes to the configured
    stream (default stdout); file persistence is separate and append-only.

    Constructor:
        events_dir: directory that holds ``events.jsonl`` (typically
            ``<data_dir>/corpus-audit``).
        stream: text stream for stdout events (None → ``sys.stdout``,
            matching StdoutEventSink default).
    """

    def __init__(self, events_dir: str, stream=None) -> None:
        self._events_dir = os.path.abspath(events_dir)
        self._file_path = os.path.join(self._events_dir, "events.jsonl")
        # Validate against parent's logic, but drop stdout during validation
        # by injecting a discard stream into the parent.
        super().__init__(stream=_DiscardStream())
        #: The actual stream for emission (None → sys.stdout at call time).
        self._stream = stream

    def emit(self, event_type: str, payload: dict) -> None:
        """Validate (via parent), persist to file, then emit to stream.

        Validation errors raise StructuredError before any side effect.
        Persistence failures degrade to a stderr warning (filtered by
        DOCUMENTER_LOG_LEVEL ≤ warn); events are NOT silently dropped —
        the stream still receives them.
        """
        # Validate via parent (drops stdout to _DiscardStream).
        super().emit(event_type, payload)

        # Persistent write (append-only, fsync).
        os.makedirs(self._events_dir, exist_ok=True)
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        event_id = str(uuid.uuid4())
        envelope = {
            "event_id": event_id,
            "emitted_at": now_utc,
            "event_type": event_type,
            "payload": payload,
        }
        line = json.dumps(envelope, sort_keys=True, ensure_ascii=False)
        try:
            fd = os.open(
                self._file_path,
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o644,
            )
            try:
                os.write(fd, (line + "\n").encode("utf-8"))
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            _file_event_log_warn(
                f"WARNING: event persistence failed ({type(exc).__name__}): "
                f"{exc}; event emitted to stream only")
            # Event still goes to stream below — NOT silently dropped.

        # Emit to the public stream (stdout if stream=None).
        if self._stream is not None:
            self._stream.write(line + "\n")
            self._stream.flush()
