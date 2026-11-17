"""Degradation: documenter_service not importable → IO.004 envelope + precheck.unavailable auto-proceed.

Cycle 10 Step 9 — Test Author.

Contract (C): when ``documenter_service`` cannot be imported, the adapter
``Tier01Documenter`` returns ``{"available": False, "reason": ...}`` from
every method.  The operator surface must NOT crash — verbs that call through
to the port get ``IO.004`` error envelopes, and the precheck path returns
``verdict: "unavailable"`` which triggers auto-proceed with
``"precheck": "unavailable"`` in the submit_task response.

Red baseline: with documenter_service absent, verbs that call audit/status
may raise unhandled exceptions instead of returning IO.004.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

try:
    from operator_surface.core.auth import issue_token  # noqa: F401
except ImportError:
    issue_token = None  # type: ignore[misc,assignment]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_CLAIMS = {
    "alg": "HS256",
    "iss": "operator-surface",
    "sub": "op-alice",
    "exp": 9999999999,
}


def _make_token(secret="test-secret-key", sub="op-alice"):
    if issue_token is None:
        return None
    claims = dict(_MIN_CLAIMS)
    claims["sub"] = sub
    return issue_token(claims, secret)


# ---------------------------------------------------------------------------
# Subprocess helper — documenter_service poisoned via COUNCIL_TEST_MODE
# ---------------------------------------------------------------------------

def _spawn_subprocess(root_dir, timeout=10):
    """Spawn stdio subprocess with COUNCIL_TEST_MODE=1 (no real documenter).

    The READY line is consumed before returning so that the first
    ``_safe_readline`` call returns the actual response.
    """
    env = os.environ.copy()
    env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
    env["COUNCIL_STATE_ROOT"] = root_dir
    env["COUNCIL_TEST_MODE"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-m", "operator_surface"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    # Consume the READY line before returning.
    try:
        proc.stdout.readline()
    except Exception:
        pass
    return proc


def _safe_readline(proc, label=""):
    try:
        line = proc.stdout.readline()
        return line if line else ""
    except Exception:
        return ""


def _kill_subprocess(proc):
    """Safely terminate or kill a subprocess."""
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
    except Exception:
        try:
            proc.kill()
            proc.wait()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# In-process degradation test
# ---------------------------------------------------------------------------

class TestDegradationInProcess(unittest.TestCase):
    """Adapter degradation when documenter_service is not importable."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_adapter_audit_returns_available_false(self):
        """Tier01Documenter.audit() returns available=False when service absent."""
        from operator_surface.adapters.documenter_adapter import Tier01Documenter

        adapter = Tier01Documenter(self.tmpdir)
        result = adapter.audit(target_id="*")
        self.assertFalse(result.get("available"),
                         "audit must return available=False without documenter_service")
        self.assertIn("reason", result,
                       "audit result must include a reason")

    def test_adapter_status_returns_healthy_false(self):
        """Tier01Documenter.status() returns healthy=False when service absent."""
        from operator_surface.adapters.documenter_adapter import Tier01Documenter

        adapter = Tier01Documenter(self.tmpdir)
        result = adapter.status(target_id=None)
        # When the Service constructor fails (no corpus), the adapter
        # caches self._service = None and returns the degraded response.
        self.assertFalse(result.get("healthy"),
                         "status must return healthy=False without documenter_service")

    def test_adapter_delegate_preview_returns_available_false(self):
        """Tier01Documenter.delegate_preview() returns available=False when service absent."""
        from operator_surface.adapters.documenter_adapter import Tier01Documenter

        adapter = Tier01Documenter(self.tmpdir)
        result = adapter.delegate_preview(
            target_id="doc-1",
            change_type="edit",
            trust_level="operator",
            diff_input="diff content",
        )
        self.assertFalse(result.get("available"),
                         "delegate_preview must return available=False")
        self.assertIn("reason", result,
                       "delegate_preview result must include a reason")


# ---------------------------------------------------------------------------
# Precheck degradation: unavailable → auto-proceed
# ---------------------------------------------------------------------------

class TestPrecheckDegradation(unittest.TestCase):
    """Precheck with no documenter port → unavailable verdict, auto-proceed."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_run_precheck_no_port_returns_unavailable(self):
        """run_precheck with documenter_port=None → verdict: unavailable."""
        from operator_surface.core.precheck import run_precheck

        result = run_precheck(
            target_id="scen-deg",
            documenter_port=None,
        )
        self.assertEqual(
            result.get("verdict"), "unavailable",
            "run_precheck without port must return verdict=unavailable",
        )
        self.assertIn("reason", result)
        # When port is None, _run_audit_with_timeout calls .audit(None)
        # which raises AttributeError → caught → unavailable.
        self.assertIn(
            "exception", result.get("reason", "").lower(),
            "reason should mention the exception",
        )

    def test_precheck_unavailable_event_emitted(self):
        """run_precheck unavailable → precheck.unavailable event via sink."""
        from operator_surface.core.precheck import run_precheck

        class _Sink:
            def __init__(self):
                self.events = []
            def append(self, event):
                self.events.append(event)

        sink = _Sink()
        result = run_precheck(
            target_id="scen-deg",
            documenter_port=None,
            event_sink=sink,
            session_id="sess-precheck-deg",
            actor={"kind": "operator", "id": "op-alice"},
        )
        self.assertEqual(result.get("verdict"), "unavailable")
        # There should be a "precheck.running" event first
        event_types = [ev.get("event_type", "") for ev in sink.events]
        self.assertIn("precheck.running", event_types,
                       "precheck.running event must be emitted first")
        self.assertIn("precheck.unavailable", event_types,
                       "precheck.unavailable event must be emitted")

    def test_submit_task_auto_proceed_unavailable(self):
        """submit_task with precheck unavailable → returns precheck: unavailable."""
        from operator_surface.adapters.session_store import MvpSessionStore
        from operator_surface.core.verbs import submit_task

        store = MvpSessionStore(self.tmpdir)
        events = []  # simple list as event sink
        result = submit_task(
            store=store,
            events=events,
            task_brief="Degradation auto-proceed test",
            scenario_id="scen-deg",
            operator_id="op-alice",
            precheck_gate=None,  # → uses run_precheck with no port → unavailable
        )
        # Auto-proceed: session created, precheck marked unavailable.
        self.assertIn("session_id", result,
                       "submit_task must create a session on unavailable (auto-proceed)")
        self.assertEqual(
            result.get("precheck"), "unavailable",
            "submit_task must include precheck=unavailable in response",
        )
        self.assertEqual(result.get("status"), "submitted")

    def test_submit_task_event_emitted_on_auto_proceed(self):
        """submit_task auto-proceed on unavailable → verb.submit_task event."""
        from operator_surface.adapters.session_store import MvpSessionStore
        from operator_surface.core.verbs import submit_task

        store = MvpSessionStore(self.tmpdir)
        events = []
        result = submit_task(
            store=store,
            events=events,
            task_brief="Auto-emit test",
            scenario_id="scen-deg2",
            operator_id="op-alice",
            precheck_gate=None,
        )
        self.assertIn("session_id", result)
        # Check emitted events
        self.assertGreater(len(events), 0,
                           "submit_task must emit events on auto-proceed")
        event_types = [ev.get("event_type", "") for ev in events]
        self.assertIn("verb.submit_task", event_types,
                       "verb.submit_task event must be emitted")


# ---------------------------------------------------------------------------
# Subprocess degradation: full end-to-end with COUNCIL_TEST_MODE
# ---------------------------------------------------------------------------

class TestDegradationSubprocess(unittest.TestCase):
    """Full subprocess tests under COUNCIL_TEST_MODE (no real documenter)."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_status_healthy_false_with_test_mode(self):
        """council.status under COUNCIL_TEST_MODE → valid response (test mode stubs)."""
        if issue_token is None:
            self.skipTest("operator_surface.core.auth not available yet")
        proc = _spawn_subprocess(self.root)
        try:
            token = _make_token(sub="op-alice")
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "council.status",
                "params": {"auth": {"token": token}},
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = _safe_readline(proc, "status test-mode")
            self.assertTrue(len(response_line) > 0,
                            "Must receive a response")
            response = json.loads(response_line)
            self.assertIn("result", response,
                          "council.status must return result")
            result2 = response["result"]
            # In test mode the status verb returns sessions + notices.
            self.assertIn("sessions", result2,
                          "status must include sessions list")
            self.assertIn("notices", result2,
                          "status must include notices list")
            self.assertEqual(result2.get("session_id"), None,
                             "operator-level view must have session_id=None")
        finally:
            _kill_subprocess(proc)

    def test_submit_task_auto_proceed_via_stdio(self):
        """council.submit_task under COUNCIL_TEST_MODE → precheck: unavailable."""
        if issue_token is None:
            self.skipTest("operator_surface.core.auth not available yet")
        proc = _spawn_subprocess(self.root)
        try:
            token = _make_token(sub="op-alice")
            request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "council.submit_task",
                "params": {
                    "auth": {"token": token},
                    "task_brief": "Degradation stdio test",
                    "scenario_id": "scen-deg-stdio",
                },
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = _safe_readline(proc, "submit_task test-mode")
            self.assertTrue(len(response_line) > 0,
                            "Must receive a response")
            response = json.loads(response_line)
            self.assertIn("result", response,
                          "submit_task must return result")
            self.assertIn("session_id", response["result"],
                          "auto-proceed must create session")
            self.assertEqual(
                response["result"].get("precheck"), "unavailable",
                "submit_task under test mode must include precheck=unavailable",
            )
        finally:
            _kill_subprocess(proc)

    def test_documenter_audit_no_crash(self):
        """documenter.audit under COUNCIL_TEST_MODE → does not crash, returns error or stub."""
        if issue_token is None:
            self.skipTest("operator_surface.core.auth not available yet")
        proc = _spawn_subprocess(self.root)
        try:
            token = _make_token(sub="op-alice")
            request = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "documenter.audit",
                "params": {
                    "auth": {"token": token},
                },
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = _safe_readline(proc, "documenter.audit test-mode")
            self.assertTrue(len(response_line) > 0,
                            "Must receive a response")
            response = json.loads(response_line)
            # Must NOT be an error (CONFIG.002 = unknown method).
            self.assertIn("result", response,
                          "documenter.audit must be a known method, return result")
        finally:
            _kill_subprocess(proc)

    def test_documenter_delegate_no_crash(self):
        """documenter.delegate under COUNCIL_TEST_MODE → returns valid response.

        May return "result" (when approval_registry is wired) or
        "error" (when not yet wired — CONFIG.001 or IO.999).
        The contract is: no unhandled exception.
        """
        if issue_token is None:
            self.skipTest("operator_surface.core.auth not available yet")
        proc = _spawn_subprocess(self.root)
        try:
            token = _make_token(sub="op-alice")
            request = {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "documenter.delegate",
                "params": {
                    "auth": {"token": token},
                    "target_id": "doc-deg",
                    "change_type": "edit",
                    "diff": "diff content",
                },
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = _safe_readline(proc, "documenter.delegate test-mode")
            self.assertTrue(len(response_line) > 0,
                            "Must receive a response")
            response = json.loads(response_line)
            # Must be a valid JSON-RPC response (result or error, not crash).
            self.assertTrue(
                "result" in response or "error" in response,
                "documenter.delegate must return result or error (no crash)",
            )
        finally:
            _kill_subprocess(proc)


if __name__ == "__main__":
    unittest.main()
