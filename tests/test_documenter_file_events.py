"""Tests for FileEventSink — append-only JSONL persistence.

configuration-guide §Delivery Semantics: events persisted to
``documenter/corpus-audit/events.jsonl`` for operator replay.
consumers deduplicate by ``event_id``; the contract is append-only.

mvp-data-models §3: file persistence adds durable record alongside the
MVP stdout carrier.
"""
import json
import os
import shutil
import tempfile
import unittest
import sys

sys.path.insert(0, '.')

from documenter_service.adapters.file_events import FileEventSink  # noqa: E402
from documenter_service.adapters.stdout_events import (  # noqa: E402
    EVENT_SCHEMAS, MVP_EVENT_TYPES)
from documenter_service.core.errors import StructuredError  # noqa: E402


def _tmpdir():
    return tempfile.mkdtemp()


class TestFileEventSinkBasic(unittest.TestCase):
    """Basic emission and file persistence."""

    def setUp(self):
        self.tmp = _tmpdir()
        self.events_dir = os.path.join(self.tmp, "events")
        self.sink = FileEventSink(self.events_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_emit_creates_events_file(self):
        """emit() creates events.jsonl in events_dir."""
        self.sink.emit("documenter.issue", {
            "audit_id": "a1",
            "subject_id": "alpha",
            "severity": "low",
            "description": "test",
        })
        path = os.path.join(self.events_dir, "events.jsonl")
        self.assertTrue(os.path.exists(path))

    def test_emit_valid_json_line(self):
        """The written line is valid JSON with the expected keys."""
        self.sink.emit("documenter.issue", {
            "audit_id": "a1",
            "subject_id": "alpha",
            "severity": "low",
            "description": "test",
        })
        path = os.path.join(self.events_dir, "events.jsonl")
        with open(path, encoding="utf-8") as fh:
            line = fh.readline().strip()
        obj = json.loads(line)
        self.assertIn("event_id", obj)
        self.assertIn("emitted_at", obj)
        self.assertIn("event_type", obj)
        self.assertIn("payload", obj)
        self.assertEqual(obj["event_type"], "documenter.issue")
        self.assertEqual(obj["payload"]["audit_id"], "a1")
        self.assertEqual(obj["payload"]["subject_id"], "alpha")
        self.assertEqual(obj["payload"]["severity"], "low")
        self.assertEqual(obj["payload"]["description"], "test")

    def test_event_id_is_uuid(self):
        """event_id is a valid UUID4 string."""
        self.sink.emit("documenter.issue", {
            "audit_id": "a1",
            "subject_id": "alpha",
            "severity": "low",
            "description": "test",
        })
        path = os.path.join(self.events_dir, "events.jsonl")
        with open(path, encoding="utf-8") as fh:
            line = fh.readline().strip()
        obj = json.loads(line)
        # UUID4 pattern: 8-4-4-4-12 hex digits
        import uuid
        uuid.UUID(obj["event_id"], version=4)  # raises if not valid

    def test_emitted_at_is_iso8601(self):
        """emitted_at is a valid ISO 8601 UTC timestamp."""
        self.sink.emit("documenter.issue", {
            "audit_id": "a1",
            "subject_id": "alpha",
            "severity": "low",
            "description": "test",
        })
        path = os.path.join(self.events_dir, "events.jsonl")
        with open(path, encoding="utf-8") as fh:
            line = fh.readline().strip()
        obj = json.loads(line)
        ts = obj["emitted_at"]
        self.assertTrue(ts.endswith("Z"))
        # Should be parseable
        from datetime import datetime
        datetime.fromisoformat(ts.replace("Z", "+00:00"))

    def test_payload_keys_match_schema(self):
        """payload contains exactly the keys defined by EVENT_SCHEMAS."""
        self.sink.emit("documenter.issue", {
            "audit_id": "a1",
            "subject_id": "alpha",
            "severity": "low",
            "description": "test",
        })
        path = os.path.join(self.events_dir, "events.jsonl")
        with open(path, encoding="utf-8") as fh:
            line = fh.readline().strip()
        obj = json.loads(line)
        expected_keys = EVENT_SCHEMAS["documenter.issue"]
        self.assertEqual(frozenset(obj["payload"].keys()), expected_keys)


class TestFileEventSinkAppendOnly(unittest.TestCase):
    """Append-only behavior: each emit adds a new line."""

    def setUp(self):
        self.tmp = _tmpdir()
        self.events_dir = os.path.join(self.tmp, "events")
        self.sink = FileEventSink(self.events_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_two_emits_two_lines(self):
        """Two emits → two lines in events.jsonl (append-only)."""
        self.sink.emit("documenter.issue", {
            "audit_id": "a1",
            "subject_id": "alpha",
            "severity": "low",
            "description": "first",
        })
        self.sink.emit("documenter.issue", {
            "audit_id": "a2",
            "subject_id": "beta",
            "severity": "medium",
            "description": "second",
        })
        path = os.path.join(self.events_dir, "events.jsonl")
        with open(path, encoding="utf-8") as fh:
            lines = [l for l in fh.read().splitlines() if l.strip()]
        self.assertEqual(len(lines), 2)
        # Different event_ids (each emit generates a new uuid4)
        objs = [json.loads(l) for l in lines]
        self.assertNotEqual(objs[0]["event_id"], objs[1]["event_id"])

    def test_different_event_types(self):
        """Events of different types are each appended."""
        self.sink.emit("documenter.issue", {
            "audit_id": "a1",
            "subject_id": "alpha",
            "severity": "low",
            "description": "test",
        })
        self.sink.emit("precheck.passed", {
            "audit_id": "a1",
            "target_id": "alpha",
        })
        path = os.path.join(self.events_dir, "events.jsonl")
        with open(path, encoding="utf-8") as fh:
            lines = [l for l in fh.read().splitlines() if l.strip()]
        self.assertEqual(len(lines), 2)
        objs = [json.loads(l) for l in lines]
        self.assertEqual(objs[0]["event_type"], "documenter.issue")
        self.assertEqual(objs[1]["event_type"], "precheck.passed")


class TestFileEventSinkValidation(unittest.TestCase):
    """Validation errors are raised by parent before any file write."""

    def setUp(self):
        self.tmp = _tmpdir()
        self.events_dir = os.path.join(self.tmp, "events")
        self.sink = FileEventSink(self.events_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unknown_event_type_raises(self):
        """Unknown event_type → StructuredError, file NOT created."""
        with self.assertRaises(StructuredError) as ctx:
            self.sink.emit("unknown.type", {"foo": "bar"})
        self.assertEqual(ctx.exception.error_category, "unknown")
        path = os.path.join(self.events_dir, "events.jsonl")
        self.assertFalse(os.path.exists(path))

    def test_tier2_event_type_raises(self):
        """Event type in EVENT_SCHEMAS but outside MVP_EVENT_TYPES → tier_interlock."""
        # precheck.overridden is declared in EVENT_SCHEMAS but not in MVP_EVENT_TYPES
        with self.assertRaises(StructuredError) as ctx:
            self.sink.emit("precheck.overridden", {
                "reason": "test",
                "operator_id": "op-user",
            })
        self.assertEqual(ctx.exception.error_category, "tier_interlock")
        path = os.path.join(self.events_dir, "events.jsonl")
        self.assertFalse(os.path.exists(path))

    def test_unknown_payload_key_rejected(self):
        """Payload with an unknown key → StructuredError (VAL.001)."""
        with self.assertRaises(StructuredError) as ctx:
            self.sink.emit("documenter.issue", {
                "audit_id": "a1",
                "subject_id": "alpha",
                "severity": "low",
                "description": "test",
                "extra_field": "should_not_be_here",
            })
        self.assertEqual(ctx.exception.error_category, "unknown")
        # File should not contain a bad line
        path = os.path.join(self.events_dir, "events.jsonl")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
            self.assertFalse("extra_field" in content)

    def test_missing_payload_key_rejected(self):
        """Payload missing a required key → StructuredError."""
        with self.assertRaises(StructuredError) as ctx:
            self.sink.emit("documenter.issue", {
                "audit_id": "a1",
                "subject_id": "alpha",
                # "severity" missing!
                "description": "test",
            })
        self.assertEqual(ctx.exception.error_category, "unknown")

    def test_invalid_severity_rejected(self):
        """Invalid severity value → StructuredError."""
        with self.assertRaises(StructuredError) as ctx:
            self.sink.emit("documenter.issue", {
                "audit_id": "a1",
                "subject_id": "alpha",
                "severity": "extreme",
                "description": "test",
            })
        self.assertEqual(ctx.exception.error_category, "unknown")


class TestFileEventSinkDirectoryCreation(unittest.TestCase):
    """FileEventSink creates missing directories."""

    def setUp(self):
        self.tmp = _tmpdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_creates_nested_events_dir(self):
        """events_dir and its parents are created on first emit."""
        events_dir = os.path.join(self.tmp, "deep", "nested", "events")
        sink = FileEventSink(events_dir)
        sink.emit("documenter.issue", {
            "audit_id": "a1",
            "subject_id": "alpha",
            "severity": "low",
            "description": "test",
        })
        path = os.path.join(events_dir, "events.jsonl")
        self.assertTrue(os.path.exists(path))

    def test_multiple_emits_same_file(self):
        """Multiple emits from different sinks append to the same file."""
        events_dir = os.path.join(self.tmp, "events")
        s1 = FileEventSink(events_dir)
        s2 = FileEventSink(events_dir)
        s1.emit("documenter.issue", {
            "audit_id": "a1",
            "subject_id": "alpha",
            "severity": "low",
            "description": "from-sink-1",
        })
        s2.emit("documenter.issue", {
            "audit_id": "a2",
            "subject_id": "beta",
            "severity": "medium",
            "description": "from-sink-2",
        })
        path = os.path.join(events_dir, "events.jsonl")
        with open(path, encoding="utf-8") as fh:
            lines = [l for l in fh.read().splitlines() if l.strip()]
        self.assertEqual(len(lines), 2)


# ---------------------------------------------------------------------------
# Persistence degradation (fix plan p.22, decision E0.3): OSError during the
# durable write degrades to a stderr warning; the event still reaches the
# stream and validation errors still raise.
# ---------------------------------------------------------------------------

class TestFileEventSinkPersistenceDegrades(unittest.TestCase):

    def setUp(self):
        self.tmp = _tmpdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _payload(self):
        return {"audit_id": "a1", "subject_id": "alpha",
                "severity": "low", "description": "degraded"}

    def _patch_open_fail(self, exc):
        """Make os.open fail for the persistence write only."""
        from unittest import mock
        real_open = os.open

        def fake_open(path, flags, *a, **kw):
            if str(path).endswith("events.jsonl"):
                raise exc
            return real_open(path, flags, *a, **kw)

        return mock.patch("documenter_service.adapters.file_events.os.open",
                          side_effect=fake_open)

    def test_oserror_does_not_raise_stream_still_receives(self):
        import io as _io
        import errno as _errno
        sink = FileEventSink(os.path.join(self.tmp, "events"),
                             stream=_io.StringIO())
        with self._patch_open_fail(OSError(_errno.EACCES, "Permission denied")):
            sink.emit("documenter.issue", self._payload())  # must not raise
        out = sink._stream.getvalue()
        self.assertIn("documenter.issue", out)  # event reached the stream

    def test_stderr_warning_emitted_by_default(self):
        import io as _io
        import errno as _errno
        sink = FileEventSink(os.path.join(self.tmp, "events"),
                             stream=_io.StringIO())
        from unittest import mock
        with self._patch_open_fail(OSError(_errno.EACCES, "Permission denied")):
            with mock.patch("sys.stderr", new_callable=_io.StringIO) as err:
                sink.emit("documenter.issue", self._payload())
        self.assertIn("WARNING", err.getvalue())
        self.assertIn("event persistence failed", err.getvalue())

    def test_stderr_warning_suppressed_at_error_level(self):
        import io as _io
        import errno as _errno
        os.environ["DOCUMENTER_LOG_LEVEL"] = "error"
        try:
            sink = FileEventSink(os.path.join(self.tmp, "events"),
                                 stream=_io.StringIO())
            from unittest import mock
            with self._patch_open_fail(
                    OSError(_errno.EACCES, "Permission denied")):
                with mock.patch("sys.stderr", new_callable=_io.StringIO) as err:
                    sink.emit("documenter.issue", self._payload())
            self.assertNotIn("event persistence failed", err.getvalue())
        finally:
            del os.environ["DOCUMENTER_LOG_LEVEL"]

    def test_validation_error_still_raises(self):
        """Degradation applies to persistence only — schema violations keep
        raising StructuredError (fail-loud for validation preserved)."""
        sink = FileEventSink(os.path.join(self.tmp, "events"),
                             stream=__import__("io").StringIO())
        with self.assertRaises(StructuredError):
            sink.emit("documenter.issue", {"bogus": 1})


if __name__ == "__main__":
    unittest.main()
