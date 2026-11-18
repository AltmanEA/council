# STUB: replaced by real Layer 1 at Phase 3
"""MVP disk-backed JSONL session store for Operator Ingress.

OD-1 convention: sessions stored under <root>/sessions/<session-id>/
with session.jsonl (session record) and intent.jsonl (intent log).

CRUD only — no protocol logic.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from ..ports import Layer1Port


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class MvpSessionStore(Layer1Port):
    """OD-1 disk-backed JSONL session store.

    Attributes:
        _root: base directory for all session data.
    """

    def __init__(self, root: str) -> None:
        self._root = root

    def _session_dir(self, session_id: str) -> str:
        return os.path.join(self._root, "sessions", session_id)

    def _session_jsonl_path(self, session_id: str) -> str:
        return os.path.join(self._session_dir(session_id), "session.jsonl")

    def _intent_jsonl_path(self, session_id: str) -> str:
        return os.path.join(self._session_dir(session_id), "intent.jsonl")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_session(self, session_id: str) -> dict:
        """Create a new session directory and write session.jsonl + intent.jsonl."""
        session_dir = self._session_dir(session_id)
        os.makedirs(session_dir, exist_ok=True)

        record = {
            "session_id": session_id,
            "status": "submitted",
            "emitted_at": _now_utc(),
        }

        # Write session record.
        session_path = self._session_jsonl_path(session_id)
        with open(session_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

        # Create intent log.
        intent_path = self._intent_jsonl_path(session_id)
        with open(intent_path, "w", encoding="utf-8") as fh:
            fh.write("")  # empty file

        return dict(record)

    def get_session(self, session_id: str) -> dict | None:
        """Return the session dict from session.jsonl, or None if absent.

        Malformed JSON in the first line is silently treated as absent
        (never raises) — cold-start tolerant.
        """
        path = self._session_jsonl_path(session_id)
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as fh:
            line = fh.readline().strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            # Malformed JSON → treat as absent (never raise).
            return None

    def list_sessions(self) -> list:
        """Return a list of all session dicts (read-only)."""
        base = os.path.join(self._root, "sessions")
        if not os.path.isdir(base):
            return []
        results = []
        for name in sorted(os.listdir(base)):
            sid = os.path.join(base, name)
            if os.path.isdir(sid):
                record = self.get_session(name)
                if record is not None:
                    results.append(dict(record))
        return results

    def append_record(self, session_id: str, record: dict) -> dict:
        """Append record to intent.jsonl and return it as-is."""
        path = self._intent_jsonl_path(session_id)
        # Ensure the session directory exists (covers calls before create_session).
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        return record
