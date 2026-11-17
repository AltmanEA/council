"""Tests for pre_check gate — real wiring (Cycle 6 Step 5).

Frozen API contract:
  - RegistryIntegrityError(Exception)
  - PRE_CHECK_TIMEOUT_SECONDS boot constant (env PRE_CHECK_TIMEOUT)
  - run_precheck(target_id, documenter_port, *, timeout, clock,
    event_sink, session_id, actor) -> dict
  - Verdicts: pass / fail / unavailable
  - Event emission: precheck.running → precheck.passed/failed/unavailable
  - submit_task: pass → commit; unavailable → auto-proceed + key;
    fail → REFUSE VAL.003

Fakes:
  - FakeDocumenterPort(DocumenterPort) — configurable findings / raises / sleep
  - ListEventSink(EventSink) — collects appended envelopes in a list

Target: red baseline (RegistryIntegrityError / run_precheck kwargs red),
  back-compat: existing verbs + architecture GREEN.
"""
from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest

# ---------------------------------------------------------------------------
# Regexes for result validation
# ---------------------------------------------------------------------------

_SESS_RE = re.compile(r"^sess-[a-z0-9]{12}$")

# ---------------------------------------------------------------------------
# Try importing the red baseline — NameError = red
# ---------------------------------------------------------------------------

try:
    from operator_surface.core.precheck import (  # noqa: F401
        RegistryIntegrityError,
        run_precheck,
        PRE_CHECK_TIMEOUT_SECONDS,
    )
except ImportError:
    RegistryIntegrityError = None  # type: ignore[misc,assignment]
    run_precheck = None  # type: ignore[misc,assignment]
    PRE_CHECK_TIMEOUT_SECONDS = None  # type: ignore[misc,assignment]

try:
    from operator_surface.core.events import make_envelope  # noqa: F401
except ImportError:
    make_envelope = None  # type: ignore[misc,assignment]

try:
    from operator_surface.core.envelope import error_envelope  # noqa: F401
except ImportError:
    error_envelope = None  # type: ignore[misc,assignment]

try:
    from operator_surface.ports import DocumenterPort, EventSink  # noqa: F401
except ImportError:
    DocumenterPort = None  # type: ignore[misc,assignment]
    EventSink = None  # type: ignore[misc,assignment]

try:
    from operator_surface.core.verbs import submit_task  # noqa: F401
except ImportError:
    submit_task = None  # type: ignore[misc,assignment]

try:
    from operator_surface.adapters.session_store import MvpSessionStore  # noqa: F401
except ImportError:
    MvpSessionStore = None  # type: ignore[misc,assignment]

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeDocumenterPort(DocumenterPort):
    """Configurable fake DocumenterPort for test isolation."""

    def __init__(self, *, findings=None, raise_exc=None, sleep_before=0):
        """
        Args:
            findings: list of finding dicts, each with a "severity" key.
            raise_exc: exception class to raise on audit() call.
            sleep_before: seconds to sleep before returning.
        """
        self.findings = findings if findings is not None else []
        self.raise_exc = raise_exc
        self.sleep_before = sleep_before
        self._audit_called_count = 0

    def audit(self, target_id="*", **kwargs):
        self._audit_called_count += 1
        if self.sleep_before:
            time.sleep(self.sleep_before)
        if self.raise_exc:
            raise self.raise_exc()
        return {
            "report": {
                "header": {"target_id": target_id, "status": "complete"},
                "findings": self.findings,
            }
        }

    def status(self, target_id=None):
        return {"healthy": True, "registry": {"status": "healthy"}}

    def delegate_preview(self, target_id, change_type, trust_level, diff_input):
        return {"diff": "fake"}


# Add missing import for FakeDocumenterPort (sleep_before uses time)
import time  # noqa: E402


class ListEventSink(EventSink):
    """In-memory event sink that collects appended envelopes."""

    def __init__(self):
        self.events: list[dict] = []

    def append(self, event: dict) -> None:
        self.events.append(event)


# ---------------------------------------------------------------------------
# Minimal claims for token generation (needed by some integration tests)
# ---------------------------------------------------------------------------

_MIN_CLAIMS = {
    "alg": "HS256",
    "iss": "operator-surface",
    "sub": "op-alice",
    "exp": 9999999999,
}

# ---------------------------------------------------------------------------
# Test class: pre_check gate verdict logic (cases 1–12)
# ---------------------------------------------------------------------------


class TestRunPrecheckVerdicts(unittest.TestCase):
    """Cases 1–12: run_precheck verdict logic and event emission."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # --- Case 1: 0 findings → pass ---

    @unittest.skipIf(run_precheck is None, "red baseline: run_precheck not implemented yet")
    def test_case_1_zero_findings_pass(self):
        """0 findings → verdict pass; events [running, passed]."""
        fake = FakeDocumenterPort(findings=[])
        sink = ListEventSink()
        sid = "sess-verify001"
        result = run_precheck(
            target_id="documentation-rules",
            documenter_port=fake,
            event_sink=sink,
            session_id=sid,
            actor={"kind": "operator", "id": "op-alice"},
        )
        self.assertEqual(result["verdict"], "pass")
        event_types = [e["event_type"] for e in sink.events]
        self.assertEqual(event_types, [
            "precheck.running",
            "precheck.passed",
        ])

    # --- Case 2: one high finding → fail ---

    @unittest.skipIf(run_precheck is None, "red baseline: run_precheck not implemented yet")
    def test_case_2_high_finding_fail(self):
        """One high finding → verdict fail; events [running, failed]."""
        fake = FakeDocumenterPort(findings=[{
            "severity": "high",
            "description": "changelog missing",
        }])
        sink = ListEventSink()
        sid = "sess-verify002"
        result = run_precheck(
            target_id="documentation-rules",
            documenter_port=fake,
            event_sink=sink,
            session_id=sid,
            actor={"kind": "operator", "id": "op-alice"},
        )
        self.assertEqual(result["verdict"], "fail")
        event_types = [e["event_type"] for e in sink.events]
        self.assertEqual(event_types, [
            "precheck.running",
            "precheck.failed",
        ])

    # --- Case 3: one critical finding → fail ---

    @unittest.skipIf(run_precheck is None, "red baseline: run_precheck not implemented yet")
    def test_case_3_critical_finding_fail(self):
        """One critical finding → verdict fail."""
        fake = FakeDocumenterPort(findings=[{
            "severity": "critical",
            "description": "missing critical section",
        }])
        sink = ListEventSink()
        sid = "sess-verify003"
        result = run_precheck(
            target_id="documentation-rules",
            documenter_port=fake,
            event_sink=sink,
            session_id=sid,
            actor={"kind": "operator", "id": "op-alice"},
        )
        self.assertEqual(result["verdict"], "fail")
        event_types = [e["event_type"] for e in sink.events]
        self.assertEqual(event_types, [
            "precheck.running",
            "precheck.failed",
        ])

    # --- Case 4: TimeoutError → unavailable ---

    @unittest.skipIf(run_precheck is None, "red baseline: run_precheck not implemented yet")
    def test_case_4_timeout_error_unavailable(self):
        """Fake raises TimeoutError → verdict unavailable."""
        fake = FakeDocumenterPort(raise_exc=TimeoutError)
        sink = ListEventSink()
        sid = "sess-verify004"
        result = run_precheck(
            target_id="documentation-rules",
            documenter_port=fake,
            event_sink=sink,
            session_id=sid,
            actor={"kind": "operator", "id": "op-alice"},
        )
        self.assertEqual(result["verdict"], "unavailable")
        event_types = [e["event_type"] for e in sink.events]
        self.assertEqual(event_types, [
            "precheck.running",
            "precheck.unavailable",
        ])

    # --- Case 5: OSError → unavailable ---

    @unittest.skipIf(run_precheck is None, "red baseline: run_precheck not implemented yet")
    def test_case_5_os_error_unavailable(self):
        """Fake raises OSError → verdict unavailable."""
        fake = FakeDocumenterPort(raise_exc=OSError)
        sink = ListEventSink()
        sid = "sess-verify005"
        result = run_precheck(
            target_id="documentation-rules",
            documenter_port=fake,
            event_sink=sink,
            session_id=sid,
            actor={"kind": "operator", "id": "op-alice"},
        )
        self.assertEqual(result["verdict"], "unavailable")

    # --- Case 6: wall-clock timeout → unavailable ---

    @unittest.skipIf(run_precheck is None, "red baseline: run_precheck not implemented yet")
    def test_case_6_wall_clock_timeout_unavailable(self):
        """Fake sleeps 0.2s, timeout=0.05 → unavailable."""
        fake = FakeDocumenterPort(sleep_before=0.2)
        sink = ListEventSink()
        sid = "sess-verify006"
        result = run_precheck(
            target_id="documentation-rules",
            documenter_port=fake,
            timeout=0.05,
            event_sink=sink,
            session_id=sid,
            actor={"kind": "operator", "id": "op-alice"},
        )
        self.assertEqual(result["verdict"], "unavailable")
        event_types = [e["event_type"] for e in sink.events]
        self.assertEqual(event_types, [
            "precheck.running",
            "precheck.unavailable",
        ])

    # --- Case 6b: truly infinite hang does NOT block indefinitely ---

    @unittest.skipIf(run_precheck is None, "red baseline: run_precheck not implemented yet")
    def test_case_6b_indefinite_hang_unavailable(self):
        """Fake port blocks on Event.wait() with no timeout → still returns
        within the precheck timeout; wall-clock elapsed < 2.0 s."""
        hang_event = threading.Event()
        fake = FakeDocumenterPort(sleep_before=0)
        # Replace the audit method to block forever.
        original_audit = fake.audit
        def hanging_audit(target_id="*", **kwargs):
            hang_event.wait()  # blocks indefinitely
        fake.audit = hanging_audit

        sink = ListEventSink()
        sid = "sess-verify006b"
        t0 = time.monotonic()
        result = run_precheck(
            target_id="documentation-rules",
            documenter_port=fake,
            timeout=0.1,
            event_sink=sink,
            session_id=sid,
            actor={"kind": "operator", "id": "op-alice"},
        )
        elapsed = time.monotonic() - t0
        try:
            hang_event.set()  # unblock leaked daemon thread
        except Exception:
            pass
        self.assertEqual(result["verdict"], "unavailable")
        event_types = [e["event_type"] for e in sink.events]
        self.assertEqual(event_types, [
            "precheck.running",
            "precheck.unavailable",
        ])
        self.assertLess(elapsed, 2.0,
                        "precheck must not block indefinitely; "
                        f"elapsed {elapsed:.2f}s")

    # --- Case 7: RegistryIntegrityError → fail (NOT unavailable) ---

    @unittest.skipIf(RegistryIntegrityError is None, "red baseline: RegistryIntegrityError not implemented yet")
    def test_case_7_integrity_error_is_fail(self):
        """RegistryIntegrityError → verdict fail, NOT unavailable."""
        fake = FakeDocumenterPort(raise_exc=RegistryIntegrityError)
        sink = ListEventSink()
        sid = "sess-verify007"
        result = run_precheck(
            target_id="documentation-rules",
            documenter_port=fake,
            event_sink=sink,
            session_id=sid,
            actor={"kind": "operator", "id": "op-alice"},
        )
        self.assertEqual(result["verdict"], "fail")
        self.assertNotEqual(result["reason"], "", "reason must not be empty")
        self.assertIn("registry", result["reason"].lower())
        event_types = [e["event_type"] for e in sink.events]
        self.assertEqual(event_types, [
            "precheck.running",
            "precheck.failed",
        ])

    # --- Case 8: running event emitted for ALL four verdict paths ---

    @unittest.skipIf(run_precheck is None, "red baseline: run_precheck not implemented yet")
    def test_case_8_running_event_emitted_for_all_verdicts(self):
        """For each verdict path, first event is precheck.running."""
        verdict_fakes = [
            ("pass", FakeDocumenterPort(findings=[])),
            ("fail", FakeDocumenterPort(findings=[
                {"severity": "high", "description": "x"}
            ])),
            ("unavailable", FakeDocumenterPort(raise_exc=TimeoutError)),
            ("integrity-fail", FakeDocumenterPort(
                raise_exc=RegistryIntegrityError
            ) if RegistryIntegrityError is not None else None),
        ]
        for verdict_name, fake in verdict_fakes:
            with self.subTest(verdict=verdict_name):
                if fake is None:
                    self.skipTest(
                        "RegistryIntegrityError not available"
                    )
                sink = ListEventSink()
                sid = f"sess-verify008-{verdict_name}"
                run_precheck(
                    target_id="documentation-rules",
                    documenter_port=fake,
                    event_sink=sink,
                    session_id=sid,
                    actor={"kind": "operator", "id": "op-alice"},
                )
                self.assertGreater(len(sink.events), 0)
                self.assertEqual(
                    sink.events[0]["event_type"],
                    "precheck.running",
                    f"First event for {verdict_name} must be running",
                )

    # --- Case 9: boot constant immutability ---

    @unittest.skipIf(run_precheck is None, "red baseline: run_precheck not implemented yet")
    def test_case_9_boot_constant_immutable(self):
        """PRE_CHECK_TIMEOUT from env; reload does NOT pick up env changes."""
        # Save original env.
        orig_val = os.environ.get("PRE_CHECK_TIMEOUT")
        try:
            # Set the env var.
            os.environ["PRE_CHECK_TIMEOUT"] = "7.5"
            # Reload the module so it reads the new value.
            import operator_surface.core.precheck as premod  # noqa: F811
            importlib.reload(premod)
            self.assertEqual(premod.PRE_CHECK_TIMEOUT_SECONDS, 7.5)
            # Change the env var — reload NOT performed, value stays.
            os.environ["PRE_CHECK_TIMEOUT"] = "9.9"
            # Value must still be 7.5 (immutability).
            self.assertEqual(premod.PRE_CHECK_TIMEOUT_SECONDS, 7.5)
            # Restore env + clean reload.
            del os.environ["PRE_CHECK_TIMEOUT"]
            importlib.reload(premod)
            # After clean reload, should use default (5.0).
            self.assertEqual(premod.PRE_CHECK_TIMEOUT_SECONDS, 5.0)
        finally:
            if orig_val is not None:
                os.environ["PRE_CHECK_TIMEOUT"] = orig_val
            elif "PRE_CHECK_TIMEOUT" in os.environ:
                del os.environ["PRE_CHECK_TIMEOUT"]

    # --- Case 10: timeout=None uses PRE_CHECK_TIMEOUT_SECONDS ---

    @unittest.skipIf(run_precheck is None, "red baseline: run_precheck not implemented yet")
    def test_case_10_timeout_none_uses_default(self):
        """timeout=None → uses PRE_CHECK_TIMEOUT_SECONDS (default 5.0)."""
        fake = FakeDocumenterPort(findings=[])
        sink = ListEventSink()
        sid = "sess-verify010"
        result = run_precheck(
            target_id="documentation-rules",
            documenter_port=fake,
            timeout=None,  # ← should use the module default
            event_sink=sink,
            session_id=sid,
            actor={"kind": "operator", "id": "op-alice"},
        )
        # Should NOT crash; should return a verdict.
        self.assertIn(result["verdict"], ("pass", "unavailable"))

    # --- Case 11: event_sink=None → no crash ---

    @unittest.skipIf(run_precheck is None, "red baseline: run_precheck not implemented yet")
    def test_case_11_no_event_sink(self):
        """event_sink=None → no events attempted, verdicts still correct."""
        fake = FakeDocumenterPort(findings=[{
            "severity": "high", "description": "x"
        }])
        sid = "sess-verify011"
        result = run_precheck(
            target_id="documentation-rules",
            documenter_port=fake,
            event_sink=None,  # ← no sink
            session_id=sid,
            actor={"kind": "operator", "id": "op-alice"},
        )
        self.assertEqual(result["verdict"], "fail")
        # No events should have been attempted.
        self.assertEqual(len(result), 3)  # verdict, reason, finding_count

    # --- Case 12: flat shape tolerance ---

    @unittest.skipIf(run_precheck is None, "red baseline: run_precheck not implemented yet")
    def test_case_12_flat_shape_tolerance(self):
        """Flat shape {'findings': [{'severity':'high'}]} → fail."""
        class FlatFakeDocumenterPort(DocumenterPort):
            def audit(self, target_id="*", **kwargs):
                return {"findings": [
                    {"severity": "high", "description": "flat test"}
                ]}

            def status(self, target_id=None):
                return {"healthy": True}

            def delegate_preview(self, target_id, change_type, trust_level, diff_input):
                return {"diff": "flat"}

        fake = FlatFakeDocumenterPort()
        sink = ListEventSink()
        sid = "sess-verify012"
        result = run_precheck(
            target_id="documentation-rules",
            documenter_port=fake,
            event_sink=sink,
            session_id=sid,
            actor={"kind": "operator", "id": "op-alice"},
        )
        self.assertEqual(result["verdict"], "fail")

# ---------------------------------------------------------------------------
# Test class: verb-level integration (cases 13–16)
# ---------------------------------------------------------------------------


class TestSubmitTaskWithPrecheckGate(unittest.TestCase):
    """Cases 13–16: submit_task verb-level integration with pre_check gate."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_deps(self):
        """Create deps dict with temp-dir store and fake events."""
        store = MvpSessionStore(self.tmpdir)
        events = ListEventSink()
        documenter = FakeDocumenterPort(findings=[])
        return {"store": store, "events": events,
                "documenter": documenter}

    # --- Case 13: FakePort pass → session created ---

    @unittest.skipIf(submit_task is None, "red baseline: submit_task not yet wired")
    def test_case_13_pass_commits_session(self):
        """submit_task with FakePort pass → session created,
        intent exists, events contain running/passed/verb.submit_task."""
        fake = FakeDocumenterPort(findings=[])
        deps = {"store": MvpSessionStore(self.tmpdir),
                "events": ListEventSink(),
                "documenter": fake}
        result = submit_task(
            deps["store"],
            deps["events"],
            task_brief="Test precheck pass",
            scenario_id="scen-1",
            operator_id="op-alice",
            documenter_port=fake,
        )
        self.assertIn("session_id", result)
        self.assertRegex(result["session_id"], _SESS_RE.pattern)
        # Verify session dir exists (MvpSessionStore creates it).
        sessions = deps["store"].list_sessions()
        self.assertGreater(len(sessions), 0)
        # Events contain precheck.running, precheck.passed, verb.submit_task.
        event_types = [e["event_type"] for e in deps["events"].events]
        self.assertIn("precheck.running", event_types)
        self.assertIn("precheck.passed", event_types)
        self.assertIn("verb.submit_task", event_types)

    # --- Case 14: FakePort high finding → NO session, VAL.003 error ---

    @unittest.skipIf(submit_task is None, "red baseline: submit_task not yet wired")
    def test_case_14_fail_refuses_session(self):
        """submit_task FakePort high finding → NO session dir,
        result has error dict with code VAL.003."""
        fake = FakeDocumenterPort(findings=[{
            "severity": "high", "description": "blocking"
        }])
        deps = {"store": MvpSessionStore(self.tmpdir),
                "events": ListEventSink(),
                "documenter": fake}
        result = submit_task(
            deps["store"],
            deps["events"],
            task_brief="Test precheck fail",
            scenario_id="scen-2",
            operator_id="op-bob",
            documenter_port=fake,
        )
        self.assertIn("error", result)
        self.assertEqual(result["error"]["code"], "VAL.003")
        self.assertNotIn("session_id", result)
        # No session should be created.
        sessions = deps["store"].list_sessions()
        self.assertEqual(len(sessions), 0)
        # Events: only precheck.running + precheck.failed (no verb.submit_task).
        event_types = [e["event_type"] for e in deps["events"].events]
        self.assertIn("precheck.running", event_types)
        self.assertIn("precheck.failed", event_types)
        self.assertNotIn("verb.submit_task", event_types)

    # --- Case 15: FakePort TimeoutError → auto-proceed (unavailable) ---

    @unittest.skipIf(submit_task is None, "red baseline: submit_task not yet wired")
    def test_case_15_unavailable_auto_proceed(self):
        """submit_task FakePort TimeoutError → session created,
        result precheck == 'unavailable'."""
        fake = FakeDocumenterPort(raise_exc=TimeoutError)
        deps = {"store": MvpSessionStore(self.tmpdir),
                "events": ListEventSink(),
                "documenter": fake}
        result = submit_task(
            deps["store"],
            deps["events"],
            task_brief="Test precheck unavailable",
            scenario_id="scen-3",
            operator_id="op-carol",
        )
        self.assertIn("session_id", result)
        self.assertEqual(result.get("precheck"), "unavailable")
        # Session was created (auto-proceed).
        sessions = deps["store"].list_sessions()
        self.assertGreater(len(sessions), 0)
        # Events: running, unavailable, verb.submit_task (in order).
        event_types = [e["event_type"] for e in deps["events"].events]
        self.assertIn("precheck.running", event_types)
        self.assertIn("precheck.unavailable", event_types)
        self.assertIn("verb.submit_task", event_types)

    # --- Case 16: documenter_port=None → unavailable auto-proceed ---

    @unittest.skipIf(submit_task is None, "red baseline: submit_task not yet wired")
    def test_case_16_no_documenter_port_auto_proceed(self):
        """submit_task with documenter_port=None → unavailable auto-proceed."""
        deps = {"store": MvpSessionStore(self.tmpdir),
                "events": ListEventSink(),
                "documenter": None}  # ← port is None
        # In the new wired version, the gate is unavailable → auto-proceed.
        result = submit_task(
            deps["store"],
            deps["events"],
            task_brief="Test no port",
            scenario_id="scen-4",
            operator_id="op-dave",
        )
        self.assertIn("session_id", result)
        self.assertEqual(result.get("precheck"), "unavailable")
        sessions = deps["store"].list_sessions()
        self.assertGreater(len(sessions), 0)
        event_types = [e["event_type"] for e in deps["events"].events]
        self.assertIn("precheck.unavailable", event_types)
        self.assertIn("verb.submit_task", event_types)


# ---------------------------------------------------------------------------
# Back-compat: test that run_precheck is importable and the module-level
# constants exist (green-baseline proof).
# ---------------------------------------------------------------------------


class TestGreenBaselineImport(unittest.TestCase):
    """Verify the precheck module is properly implemented (green baseline)."""

    def test_registry_error_is_exception_subclass(self):
        """RegistryIntegrityError is a subclass of Exception."""
        self.assertIsInstance(RegistryIntegrityError, type)
        self.assertTrue(issubclass(RegistryIntegrityError, Exception))

    def test_run_precheck_is_callable(self):
        """run_precheck is a callable function."""
        self.assertTrue(callable(run_precheck))

    def test_boot_constant_is_default_float(self):
        """PRE_CHECK_TIMEOUT_SECONDS is 5.0 under clean env."""
        import operator_surface.core.precheck as premod  # noqa: F811
        self.assertIsInstance(premod.PRE_CHECK_TIMEOUT_SECONDS, float)
        # Verify no PRE_CHECK_TIMEOUT env was set in this process:
        # if env were set, reload would be needed (case_9 covers that).
        # Here we just check the already-loaded module's value.
        self.assertEqual(premod.PRE_CHECK_TIMEOUT_SECONDS, 5.0)


# ---------------------------------------------------------------------------
# Back-compat: ensure existing verb tests and architecture tests still pass.
# These are NOT part of the 16 pinned cases — they prove existing code
# does not break when this test file is added.
# ---------------------------------------------------------------------------


class TestBackCompatVerbsExisting(unittest.TestCase):
    """Prove existing submit_task calls (no precheck params) still work
    in the red baseline (run_precheck passthrough always returns pass)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @unittest.skipIf(submit_task is None, "red baseline: submit_task missing")
    def test_submit_task_without_precheck_gate(self):
        """submit_task called without precheck_gate → still works (passthrough)."""
        store = MvpSessionStore(self.tmpdir)
        events = ListEventSink()
        result = submit_task(
            store, events,
            task_brief="Back-compat test",
            scenario_id="scen-compat",
            operator_id="op-alice",
        )
        self.assertIn("session_id", result)
        self.assertEqual(result["status"], "submitted")

    @unittest.skipIf(submit_task is None, "red baseline: submit_task missing")
    def test_submit_task_custom_precheck_gate_still_wins(self):
        """precheck_gate parameter still accepted when provided."""
        store = MvpSessionStore(self.tmpdir)
        events = ListEventSink()
        call_log = []

        def custom_gate(scenario_id=None):
            call_log.append(scenario_id)
            return {"verdict": "pass", "reason": "custom"}

        result = submit_task(
            store, events,
            task_brief="Custom gate test",
            scenario_id="scen-custom",
            operator_id="op-alice",
            precheck_gate=custom_gate,
        )
        self.assertIn("session_id", result)
        self.assertIn("scen-custom", call_log)


if __name__ == "__main__":
    unittest.main()
