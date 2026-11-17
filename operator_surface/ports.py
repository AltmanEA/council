"""Ports (hexagon face) for the Operator Surface MVP.

Layer-2 only: core/ knows ONLY these abstractions; adapters/ supplies
the concrete implementations.  No direct imports of Layer-1 modules
are permitted in this package — assembly wiring in __main__.py uses
relative imports (intra-package).

OD-1 convention (pinned by Layer1Port docstring):
  - Sessions stored under ``sessions/<session-id>/`` directories
  - Event log: ``sessions/<session-id>/events.jsonl``
  - Stub notice: "temporary adapter; sessions are stored in a provisional format"

| Port          | Direction  | Responsibility                                  |
|---------------|------------|-------------------------------------------------|
| Layer1Port    | Read/Write | Disk-backed session store (OD-1)                |
| DocumenterPort| Call       | Bind Tier 0–1 audit/status/delegate-preview     |
| EventSink     | Emit       | Structured event delivery (JSONL)               |
| SecretStore   | Read       | Authenticated secret material (HMAC keys)       |
"""
from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = [
    "Layer1Port",
    "DocumenterPort",
    "EventSink",
    "SecretStore",
]


class Layer1Port(ABC):
    """Layer 1 session store port — CRUD only, no protocol logic.

    OD-1 convention (pinned): sessions stored under
    ``sessions/<session-id>/`` directories, event log at
    ``sessions/<session-id>/events.jsonl`` per session.

    Record schema (JSONL under the session directory):
      {
        "event_id": str | None,    # optional, at-least-once dedup
        "event_type": str,         # e.g. "verb.submit_task"
        "payload": dict,           # verb payload
        "session_id": str,         # parent session identifier
        "written_at": str          # ISO-8601 timestamp
      }

    Note: temporary adapter; sessions are stored in a provisional format.
    This is a stub that must be replaced by real Layer 1 at Phase 3.

    Methods are CRUD only (create / get / list / append) — no phase_state,
    mode, or consensus transitions are performed here.
    """

    @abstractmethod
    def create_session(self, session_id: str) -> dict:
        """Create a new session record; returns the session dict."""

    @abstractmethod
    def get_session(self, session_id: str) -> dict | None:
        """Return the session dict, or None when absent."""

    @abstractmethod
    def list_sessions(self) -> list:
        """Return a list of all session dicts."""

    @abstractmethod
    def append_record(self, session_id: str, record: dict) -> dict:
        """Append an event record to the session; return the envelope."""


class DocumenterPort(ABC):
    """Bind to the existing Tier 0–1 Documenter Service.

    Core verbs that Layer 2 delegates through:
      - audit(): read-only compliance report
      - status(): registry health, pending scan, tier interlock
      - delegate(preview=True): canonical diff preview
    """

    @abstractmethod
    def audit(self, target_id: str, **kwargs) -> dict:
        """Run audit(); returns compliance report dict."""

    @abstractmethod
    def status(self, target_id: str | None = None) -> dict:
        """Run status(); returns service status dict."""

    @abstractmethod
    def delegate_preview(
        self,
        target_id: str,
        change_type: str,
        trust_level: str,
        diff_input: str,
    ) -> dict:
        """Run delegate(preview=True); returns diff preview dict."""


class EventSink(ABC):
    """Structured event delivery — JSONL append to session log.

    Events written to sessions/<session-id>/events.jsonl.
    session_id=null writes to documenter/corpus-audit/events.jsonl.
    """

    @abstractmethod
    def append(self, event: dict) -> None:
        """Append a structured event dict to the event stream."""


class SecretStore(ABC):
    """Authenticated secret material (HMAC-SHA256 keys, etc.).

    Secrets are never returned in output or logs; only used for signing.
    """

    @abstractmethod
    def get_hmac_secret(self) -> str:
        """Return the HMAC-SHA256 signing secret."""
