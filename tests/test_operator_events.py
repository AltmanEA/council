"""Unit tests for operator_surface.core.events (Step 3 — Event delivery, JSONL envelope).

Acceptance criteria (target-task.md, plan Step 3):
  - make_envelope produces canonical envelope with all required fields,
    schema_version==1, event_id regex-valid, emitted_at ISO-8601 Z-suffix;
  - frozen event_type enum: all listed types accepted, unknown → ValueError;
  - session_id regex enforced, None allowed for corpus-audit;
  - actor dict validated (kind in operator|agent|service, id non-empty str);
  - severity enum (low|medium|high|critical), None allowed;
  - caller_class optional, valid set;
  - FileEventSink dual-location: session→sessions/<sid>/events.jsonl,
    null→documenter/corpus-audit/events.jsonl, no stray files;
  - append-only: two appends → two lines, first line unchanged;
  - duplicate-tolerance: same event twice → two lines on disk;
  - invalid envelope → ValueError, file untouched;
  - JSONL round-trip: each line valid compact JSON.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import unittest

# ---------------------------------------------------------------------------
# Regex constants for validation
# ---------------------------------------------------------------------------

_EVENT_ID_RE = re.compile(r"^evt-[a-z0-9][a-z0-9-]{2,63}$")
_SESSION_ID_RE = re.compile(r"^sess-[a-z0-9][a-z0-9-]{2,63}$")

# ---------------------------------------------------------------------------
# Frozen enum: event types from service-contract + plan additions
# ---------------------------------------------------------------------------

_SERVICE_CONTRACT_TYPES = [
    "session.phase-changed",
    "role.review-completed",
    "consensus.computed",
    "escalation.opened",
    "escalation.resolved",
    "documenter.issue",
    "documenter.approval",
    "documenter.override_gate",
    "notice.simplification-applied",
    "notice.fallback-deferred",
    "notice.quick_review_disabled",
    "notice.documenter_tier2_interlock",
]

_PRECHECK_TYPES = [
    "precheck.running",
    "precheck.passed",
    "precheck.failed",
    "precheck.overridden",
    "precheck.unavailable",
]

_VERB_TYPES = [
    "verb.submit_task",
    "verb.status",
    "verb.list_sessions",
    "verb.documenter_audit",
]

_VALID_EVENT_TYPES = (
    _SERVICE_CONTRACT_TYPES
    + _PRECHECK_TYPES
    + _VERB_TYPES
)

# ---------------------------------------------------------------------------
# Import the module under test — fails before implementation exists
# ---------------------------------------------------------------------------

try:
    from operator_surface.core.events import (  # noqa: F401
        FileEventSink,
        make_envelope,
    )
except ImportError as _import_err:
    _import_err  # silence unused-variable

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_VALID_ACTOR = {"kind": "operator", "id": "op-alice"}

_VALID_ACTOR_AGENT = {"kind": "agent", "id": "agent-abc123"}

_VALID_ACTOR_SERVICE = {"kind": "service", "id": "svc-runner"}

_VALID_SESSION_ID = "sess-phase1"

_VALID_EVENT_ID = "evt-test001"

_VALID_EMITTED_AT = "2026-11-15T10:00:00Z"

_VALID_SEVERITY = "high"


def _make_base_kwargs():
    """Return keyword args sufficient for make_envelope() with a valid event."""
    return {
        "session_id": _VALID_SESSION_ID,
        "actor": dict(_VALID_ACTOR),
        "severity": _VALID_SEVERITY,
    }


def _read_lines(sink: FileEventSink):
    """Read all JSON lines from the sink's events.jsonl path."""
    path = sink._path
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return [ln.rstrip("\n") for ln in fh if ln.strip()]


def _walk_file_count(root: str):
    """Count all files under root via os.walk."""
    count = 0
    for _dirpath, _dirnames, filenames in os.walk(root):
        count += len(filenames)
    return count


# ---------------------------------------------------------------------------
# make_envelope: required fields
# ---------------------------------------------------------------------------


class TestMakeEnvelopeRequiredFields(unittest.TestCase):
    """Envelope must contain all required fields with correct schema_version."""

    def test_all_required_keys_present(self):
        env = make_envelope(
            "session.phase-changed", **_make_base_kwargs()
        )
        required = {"schema_version", "event_id", "event_type",
                     "emitted_at", "session_id", "actor", "severity", "payload"}
        self.assertTrue(required.issubset(set(env.keys())),
                        f"missing keys: {required - set(env.keys())}")

    def test_schema_version_is_1(self):
        env = make_envelope("session.phase-changed", **_make_base_kwargs())
        self.assertEqual(env["schema_version"], 1)

    def test_event_id_regex_valid(self):
        env = make_envelope("session.phase-changed", **_make_base_kwargs())
        self.assertRegex(env["event_id"], _EVENT_ID_RE.pattern)

    def test_emitted_at_z_suffix(self):
        env = make_envelope("session.phase-changed", **_make_base_kwargs())
        self.assertTrue(
            env["emitted_at"].endswith("Z"),
            f"emitted_at must end with Z: {env['emitted_at']!r}",
        )

    def test_emitted_at_parses_iso8601(self):
        from datetime import datetime
        env = make_envelope("session.phase-changed", **_make_base_kwargs())
        ts = env["emitted_at"].rstrip("Z")
        datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------------------
# make_envelope: frozen event_type enum
# ---------------------------------------------------------------------------


class TestEventTypeFrozen(unittest.TestCase):
    """Every listed valid type must be accepted; unknown → ValueError."""

    def test_all_valid_types_accepted(self):
        for etype in _VALID_EVENT_TYPES:
            with self.subTest(etype=etype):
                env = make_envelope(etype, **_make_base_kwargs())
                self.assertEqual(env["event_type"], etype)

    def test_unknown_event_type_raises_value_error(self):
        with self.assertRaises(ValueError):
            make_envelope("bogus.type", **_make_base_kwargs())

    def test_empty_event_type_raises_value_error(self):
        with self.assertRaises(ValueError):
            make_envelope("", **_make_base_kwargs())


# ---------------------------------------------------------------------------
# make_envelope: session_id validation
# ---------------------------------------------------------------------------


class TestSessionIdValidation(unittest.TestCase):
    """Valid sess-... regex; 'SESS-X' → ValueError; None ok."""

    def test_valid_session_id_passes(self):
        base = _make_base_kwargs()
        base.pop("session_id")  # avoid duplicate kwarg at call site
        env = make_envelope(
            "session.phase-changed", session_id="sess-phase1", **base
        )
        self.assertEqual(env["session_id"], "sess-phase1")

    def test_none_session_id_passes_corpus_audit(self):
        kwargs = _make_base_kwargs()
        del kwargs["session_id"]
        kwargs["session_id"] = None
        env = make_envelope(
            "session.phase-changed", **kwargs
        )
        self.assertIsNone(env["session_id"])

    def test_invalid_session_id_scss_dash_raises(self):
        base = _make_base_kwargs()
        base.pop("session_id")  # avoid duplicate kwarg at call site
        with self.assertRaises(ValueError):
            make_envelope("session.phase-changed", session_id="SESS-X",
                          **base)

    def test_invalid_session_id_too_short(self):
        base = _make_base_kwargs()
        base.pop("session_id")  # avoid duplicate kwarg at call site
        with self.assertRaises(ValueError):
            make_envelope("session.phase-changed", session_id="sess-x",
                          **base)


# ---------------------------------------------------------------------------
# make_envelope: actor validation
# ---------------------------------------------------------------------------


class TestActorValidation(unittest.TestCase):
    """actor.kind in operator|agent|service; id non-empty str."""

    def test_operator_actor_passes(self):
        env = make_envelope(
            "session.phase-changed", actor=_VALID_ACTOR,
            **{k: v for k, v in _make_base_kwargs().items() if k != "actor"},
        )
        self.assertEqual(env["actor"]["kind"], "operator")

    def test_agent_actor_passes(self):
        env = make_envelope("session.phase-changed", actor=_VALID_ACTOR_AGENT,
                            **{k: v for k, v in _make_base_kwargs().items() if k != "actor"})
        self.assertEqual(env["actor"]["kind"], "agent")

    def test_service_actor_passes(self):
        env = make_envelope("session.phase-changed", actor=_VALID_ACTOR_SERVICE,
                            **{k: v for k, v in _make_base_kwargs().items() if k != "actor"})
        self.assertEqual(env["actor"]["kind"], "service")

    def test_unknown_actor_kind_raises(self):
        with self.assertRaises(ValueError):
            make_envelope("session.phase-changed", actor={"kind": "alien", "id": "x"},
                          **{k: v for k, v in _make_base_kwargs().items() if k != "actor"})

    def test_empty_actor_id_raises(self):
        with self.assertRaises(ValueError):
            make_envelope("session.phase-changed", actor={"kind": "operator", "id": ""},
                          **{k: v for k, v in _make_base_kwargs().items() if k != "actor"})


# ---------------------------------------------------------------------------
# make_envelope: severity and caller_class
# ---------------------------------------------------------------------------


class TestSeverityAndCallerClass(unittest.TestCase):
    """severity valid enum or None; caller_class valid or None."""

    def test_valid_severity_passes(self):
        for sev in ("low", "medium", "high", "critical"):
            with self.subTest(sev=sev):
                env = make_envelope("session.phase-changed", severity=sev,
                                    **{k: v for k, v in _make_base_kwargs().items()
                                       if k != "severity"})
                self.assertEqual(env["severity"], sev)

    def test_none_severity_passes(self):
        env = make_envelope("session.phase-changed", severity=None,
                            **{k: v for k, v in _make_base_kwargs().items()
                               if k != "severity"})
        self.assertIsNone(env["severity"])

    def test_invalid_severity_raises(self):
        with self.assertRaises(ValueError):
            make_envelope("session.phase-changed", severity="extreme",
                          **{k: v for k, v in _make_base_kwargs().items()
                             if k != "severity"})

    def test_caller_class_operator_passes(self):
        env = make_envelope("session.phase-changed", caller_class="operator",
                            **{k: v for k, v in _make_base_kwargs().items()
                               if k != "caller_class"})
        self.assertEqual(env["caller_class"], "operator")

    def test_caller_class_alien_raises(self):
        with self.assertRaises(ValueError):
            make_envelope("session.phase-changed", caller_class="alien",
                          **{k: v for k, v in _make_base_kwargs().items()
                             if k != "caller_class"})

    def test_caller_class_none_passes(self):
        env = make_envelope("session.phase-changed", caller_class=None,
                            **{k: v for k, v in _make_base_kwargs().items()
                               if k != "caller_class"})
        self.assertIsNone(env["caller_class"])


# ---------------------------------------------------------------------------
# FileEventSink: dual-location rule
# ---------------------------------------------------------------------------


class TestFileEventSinkDualLocation(unittest.TestCase):
    """Session events → sessions/<sid>/events.jsonl;
    null-session → documenter/corpus-audit/events.jsonl; no stray files."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_session_event_lands_in_session_dir(self):
        sink = FileEventSink(self.root)
        env = make_envelope("session.phase-changed", **_make_base_kwargs())
        sink.append(env)
        expected = os.path.join(self.root, "sessions", "sess-phase1",
                                "events.jsonl")
        self.assertTrue(os.path.isfile(expected))

    def test_session_event_no_corpus_audit(self):
        sink = FileEventSink(self.root)
        env = make_envelope("session.phase-changed", **_make_base_kwargs())
        sink.append(env)
        audit_path = os.path.join(self.root, "documenter", "corpus-audit",
                                  "events.jsonl")
        self.assertFalse(os.path.isfile(audit_path))

    def test_no_stray_files_session(self):
        sink = FileEventSink(self.root)
        env = make_envelope("session.phase-changed", **_make_base_kwargs())
        sink.append(env)
        self.assertEqual(_walk_file_count(self.root), 1)

    def test_null_session_lands_in_corpus_audit(self):
        kwargs = _make_base_kwargs()
        kwargs["session_id"] = None
        sink = FileEventSink(self.root)
        env = make_envelope("session.phase-changed", **kwargs)
        sink.append(env)
        expected = os.path.join(self.root, "documenter", "corpus-audit",
                                "events.jsonl")
        self.assertTrue(os.path.isfile(expected))

    def test_null_session_no_session_dir(self):
        kwargs = _make_base_kwargs()
        kwargs["session_id"] = None
        sink = FileEventSink(self.root)
        env = make_envelope("session.phase-changed", **kwargs)
        sink.append(env)
        session_file = os.path.join(self.root, "sessions", "sess-phase1",
                                    "events.jsonl")
        self.assertFalse(os.path.isfile(session_file))

    def test_null_session_no_stray_files(self):
        kwargs = _make_base_kwargs()
        kwargs["session_id"] = None
        sink = FileEventSink(self.root)
        env = make_envelope("session.phase-changed", **kwargs)
        sink.append(env)
        self.assertEqual(_walk_file_count(self.root), 1)


# ---------------------------------------------------------------------------
# FileEventSink: append-only semantics
# ---------------------------------------------------------------------------


class TestFileEventSinkAppendOnly(unittest.TestCase):
    """Two appends → two lines; first line bytes unchanged after second append."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_two_appends_two_lines(self):
        sink = FileEventSink(self.root)
        env1 = make_envelope("session.phase-changed", **_make_base_kwargs())
        sink.append(env1)
        env2 = make_envelope("session.phase-changed", **_make_base_kwargs(),
                             event_id="evt-second01")
        sink.append(env2)
        lines = _read_lines(sink)
        self.assertEqual(len(lines), 2)

    def test_first_line_unchanged_after_second_append(self):
        sink = FileEventSink(self.root)
        env1 = make_envelope("session.phase-changed", **_make_base_kwargs())
        sink.append(env1)
        first_line_bytes = open(sink._path, "rb").read()
        env2 = make_envelope("session.phase-changed", **_make_base_kwargs(),
                             event_id="evt-second02")
        sink.append(env2)
        updated_bytes = open(sink._path, "rb").read()
        self.assertTrue(
            updated_bytes.startswith(first_line_bytes),
            "first line bytes must be unchanged",
        )


# ---------------------------------------------------------------------------
# FileEventSink: duplicate tolerance (at-least-once)
# ---------------------------------------------------------------------------


class TestFileEventSinkDuplicateTolerance(unittest.TestCase):
    """Same envelope twice → 2 lines on disk (consumer dedups by event_id)."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_same_event_id_twice_produces_two_lines(self):
        sink = FileEventSink(self.root)
        env = make_envelope("session.phase-changed", **_make_base_kwargs(),
                            event_id="evt-dup0001")
        sink.append(env)
        sink.append(env)
        lines = _read_lines(sink)
        self.assertEqual(len(lines), 2)


# ---------------------------------------------------------------------------
# FileEventSink: invalid envelope → ValueError, file untouched
# ---------------------------------------------------------------------------


class TestFileEventSinkInvalidEnvelope(unittest.TestCase):
    """Invalid envelope must raise ValueError and not create / not append."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_missing_schema_version_raises_value_error(self):
        sink = FileEventSink(self.root)
        fake_event = {
            "event_id": "evt-bad0001",
            "event_type": "session.phase-changed",
            "emitted_at": "2026-11-15T10:00:00Z",
            "session_id": "sess-phase1",
            "actor": {"kind": "operator", "id": "op-alice"},
            "severity": "low",
            "payload": {},
            # missing schema_version
        }
        with self.assertRaises(ValueError):
            sink.append(fake_event)

    def test_invalid_event_id_raises_value_error(self):
        sink = FileEventSink(self.root)
        env = make_envelope("session.phase-changed", **_make_base_kwargs(),
                            event_id="not-an-event-id")
        with self.assertRaises(ValueError):
            sink.append(env)

    def test_invalid_envelope_no_file_created(self):
        """When envelope is invalid the session directory file must not exist."""
        sink = FileEventSink(self.root)
        fake_event = {
            "event_id": "evt-bad0002",
            "event_type": "session.phase-changed",
            "emitted_at": "2026-11-15T10:00:00Z",
            "session_id": "sess-phase1",
            "actor": {"kind": "operator", "id": "op-alice"},
            "severity": "low",
            "payload": {},
        }
        with self.assertRaises(ValueError):
            sink.append(fake_event)
        session_file = os.path.join(self.root, "sessions", "sess-phase1",
                                    "events.jsonl")
        self.assertFalse(os.path.isfile(session_file))

    def test_invalid_envelope_line_count_unchanged(self):
        """If some valid events are already on disk, invalid append must not add lines."""
        sink = FileEventSink(self.root)
        env1 = make_envelope("session.phase-changed", **_make_base_kwargs())
        sink.append(env1)
        lines_before = _read_lines(sink)
        self.assertEqual(len(lines_before), 1)
        with self.assertRaises(ValueError):
            sink.append({"broken": True})
        lines_after = _read_lines(sink)
        self.assertEqual(len(lines_after), 1)


# ---------------------------------------------------------------------------
# FileEventSink: JSONL round-trip — compact valid JSON per line
# ---------------------------------------------------------------------------


class TestFileEventSinkJSONLRoundTrip(unittest.TestCase):
    """Each line is valid compact JSON (json.loads-able, no embedded newline)."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_each_line_is_valid_json(self):
        sink = FileEventSink(self.root)
        env1 = make_envelope("session.phase-changed", **_make_base_kwargs())
        sink.append(env1)
        env2 = make_envelope("session.phase-changed", **_make_base_kwargs(),
                             event_id="evt-round02")
        sink.append(env2)
        for i, line in enumerate(_read_lines(sink)):
            with self.subTest(line=i):
                obj = json.loads(line)
                self.assertIsInstance(obj, dict)

    def test_no_pretty_printing_in_lines(self):
        """Compact JSON: no newline inside the JSON string representation."""
        sink = FileEventSink(self.root)
        env = make_envelope("session.phase-changed", **_make_base_kwargs())
        sink.append(env)
        lines = _read_lines(sink)
        self.assertEqual(len(lines), 1)
        # Compact JSON must not contain a literal newline inside the value
        self.assertNotIn("\n", lines[0])

    def test_round_trip_preserves_all_keys(self):
        """json.loads(line) reconstructs all required envelope keys."""
        sink = FileEventSink(self.root)
        env = make_envelope("session.phase-changed", **_make_base_kwargs())
        sink.append(env)
        for line in _read_lines(sink):
            obj = json.loads(line)
            for key in ("schema_version", "event_id", "event_type",
                        "emitted_at", "session_id", "actor", "severity"):
                self.assertIn(key, obj, f"key {key} missing from round-trip")


if __name__ == "__main__":
    unittest.main()
