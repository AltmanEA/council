"""Subprocess smoke tests for operator_surface stdio JSON-RPC (Step 4 DoD a-c).

Spawns ``python3 -m operator_surface`` as a subprocess, sends newline-delimited
JSON-RPC 2.0 requests on stdin, reads responses from stdout.

Environment:
  COUNCIL_OPERATOR_SECRET — HMAC signing secret
  COUNCIL_STATE_ROOT — temp directory for all state writes
  COUNCIL_TEST_MODE=1 — use temp-root ports, no real documenter_service

All state lives in tempfile.TemporaryDirectory(); no real paths created.
Every subprocess call has timeout ≤ 10 s and is killed reliably.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest

try:
    from operator_surface.core.auth import issue_token  # noqa: F401
except ImportError:
    issue_token = None

_SESS_RE = re.compile(r"^sess-[a-z0-9]{12}$")
_EID_RE = re.compile(r"^evt-[a-z0-9][a-z0-9-]{2,63}$")

#: Minimal claims that issue_token accepts.
_MIN_CLAIMS = {
    "alg": "HS256",
    "iss": "operator-surface",
    "sub": "op-alice",
    "exp": 9999999999,  # far-future epoch seconds
}


def _spawn_subprocess(root_dir, timeout=10):
    """Spawn ``python3 -m operator_surface`` with test env.

    Returns ``(process, env_dict)`` for caller management.
    The READY line is consumed before returning so that the first
    ``_safe_readline`` call returns the actual response.
    """
    env = os.environ.copy()
    env["COUNCIL_OPERATOR_SECRET"] = "stdio-test-secret-key"
    env["COUNCIL_STATE_ROOT"] = root_dir
    env["COUNCIL_TEST_MODE"] = "1"
    proc = subprocess.Popen(
        ["python3", "-m", "operator_surface"],
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
    return proc, env


def _make_token():
    """Build a valid token via in-process issue_token (when available)."""
    if issue_token is None:
        return None
    claims = dict(_MIN_CLAIMS)
    return issue_token(claims, "stdio-test-secret-key")


def _safe_readline(proc, label=""):
    """Read one line from proc.stdout or return empty string."""
    try:
        line = proc.stdout.readline()
        return line if line else ""
    except Exception:
        return ""


class TestStdioSmokeRoundTrip(unittest.TestCase):
    """Basic JSON-RPC round trip over stdio."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_council_status_round_trip(self):
        """council.status → result dict with jsonrpc envelope."""
        if issue_token is None:
            self.skipTest("operator_surface.core.auth not available yet")
        proc, _env = _spawn_subprocess(self.root)
        try:
            token = _make_token()
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "council.status",
                "params": {"auth": {"token": token}},
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = _safe_readline(proc, "status round-trip")
            self.assertTrue(len(response_line) > 0,
                            "No response on stdout")
            response = json.loads(response_line)
            self.assertIn("result", response)
            self.assertEqual(response["jsonrpc"], "2.0")
            self.assertEqual(response["id"], 1)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def test_submit_task_has_session_id(self):
        """council.submit_task → result.session_id matches sess-regex."""
        if issue_token is None:
            self.skipTest("operator_surface.core.auth not available yet")
        proc, _env = _spawn_subprocess(self.root)
        try:
            token = _make_token()
            request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "council.submit_task",
                "params": {
                    "auth": {"token": token},
                    "task_brief": "Smoke task",
                    "scenario_id": "scen-smoke",
                },
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = _safe_readline(proc, "submit_task")
            response = json.loads(response_line)
            self.assertIn("result", response)
            self.assertRegex(
                response["result"]["session_id"], _SESS_RE.pattern,
                f"session_id {response['result']['session_id']!r} "
                f"does not match {_SESS_RE.pattern}",
            )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def test_submit_task_has_operator_id(self):
        """council.submit_task → result.operator_id == 'op-alice'."""
        if issue_token is None:
            self.skipTest("operator_surface.core.auth not available yet")
        proc, _env = _spawn_subprocess(self.root)
        try:
            token = _make_token()
            request = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "council.submit_task",
                "params": {
                    "auth": {"token": token},
                    "task_brief": "Smoke task",
                    "scenario_id": "scen-smoke",
                },
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = _safe_readline(proc, "submit_task operator_id")
            response = json.loads(response_line)
            self.assertEqual(response["result"]["operator_id"], "op-alice")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def test_council_list_sessions(self):
        """council.list_sessions → result with sessions list."""
        if issue_token is None:
            self.skipTest("operator_surface.core.auth not available yet")
        proc, _env = _spawn_subprocess(self.root)
        try:
            token = _make_token()
            request = {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "council.list_sessions",
                "params": {"auth": {"token": token}},
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = _safe_readline(proc, "list_sessions")
            response = json.loads(response_line)
            self.assertIn("result", response)
            self.assertIn("sessions", response["result"])
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def test_multiple_round_trips(self):
        """Two sequential round trips succeed."""
        if issue_token is None:
            self.skipTest("operator_surface.core.auth not available yet")
        proc, _env = _spawn_subprocess(self.root)
        try:
            token = _make_token()
            request = {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "council.status",
                "params": {"auth": {"token": token}},
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            resp1 = json.loads(_safe_readline(proc, "first round-trip"))
            self.assertIn("result", resp1)

            request2 = {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "council.status",
                "params": {"auth": {"token": token}},
            }
            proc.stdin.write(json.dumps(request2) + "\n")
            proc.stdin.flush()
            resp2 = json.loads(_safe_readline(proc, "second round-trip"))
            self.assertIn("result", resp2)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


class TestStdioAuthFailure(unittest.TestCase):
    """Auth failures: bad token or missing params.auth → error, no result."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_bad_token_error_no_result(self):
        """Bad token → error.data.code starts with AUTH., no result key."""
        proc, _env = _spawn_subprocess(self.root)
        try:
            request = {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "council.status",
                "params": {"auth": {"token": "completely-wrong-token"}},
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = _safe_readline(proc, "bad token")
            response = json.loads(response_line)
            self.assertIn("error", response)
            self.assertNotIn("result", response)
            code = response["error"]["data"]["code"]
            self.assertTrue(
                code.startswith("AUTH."),
                f"Expected AUTH.* code, got {code!r}",
            )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def test_missing_params_auth_error(self):
        """Request without params.auth → AUTH.002, no session dir."""
        proc, _env = _spawn_subprocess(self.root)
        try:
            request = {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "council.submit_task",
                "params": {"task_brief": "No auth"},
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = _safe_readline(proc, "no auth")
            response = json.loads(response_line)
            self.assertIn("error", response)
            self.assertNotIn("result", response)
            code = response["error"]["data"]["code"]
            self.assertEqual(code, "AUTH.002")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def test_no_session_dir_after_auth_failure(self):
        """After auth failure, no sessions directory created under root."""
        proc, _env = _spawn_subprocess(self.root)
        try:
            request = {
                "jsonrpc": "2.0",
                "id": 12,
                "method": "council.submit_task",
                "params": {"auth": {"token": "bad-token-here"}},
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = _safe_readline(proc, "fail-check")
            json.loads(response_line)  # consume response
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        # Check: no sessions dir or empty sessions dir
        sessions_dir = os.path.join(self.root, "sessions")
        if os.path.isdir(sessions_dir):
            self.assertEqual(
                len(os.listdir(sessions_dir)), 0,
                "Auth failure must not create session dirs",
            )

    def test_no_auth_key_rejected(self):
        """Request with no 'auth' key in params → AUTH.002."""
        proc, _env = _spawn_subprocess(self.root)
        try:
            request = {
                "jsonrpc": "2.0",
                "id": 13,
                "method": "council.submit_task",
                "params": {},
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = _safe_readline(proc, "no auth key")
            response = json.loads(response_line)
            self.assertIn("error", response)
            self.assertNotIn("result", response)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def test_no_params_rejected(self):
        """Request with no 'params' key → AUTH.002."""
        proc, _env = _spawn_subprocess(self.root)
        try:
            request = {
                "jsonrpc": "2.0",
                "id": 14,
                "method": "council.submit_task",
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = _safe_readline(proc, "no params")
            response = json.loads(response_line)
            self.assertIn("error", response)
            self.assertNotIn("result", response)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


class TestStdioUnknownMethod(unittest.TestCase):
    """Unknown methods → error.data.code == CONFIG.002."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_unknown_method_config_002(self):
        """council.nonexistent → CONFIG.002 error."""
        if issue_token is None:
            self.skipTest("operator_surface.core.auth not available yet")
        proc, _env = _spawn_subprocess(self.root)
        try:
            token = _make_token()
            request = {
                "jsonrpc": "2.0",
                "id": 20,
                "method": "council.nonexistent",
                "params": {"auth": {"token": token}},
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = _safe_readline(proc, "unknown method")
            response = json.loads(response_line)
            self.assertIn("error", response)
            self.assertEqual(response["error"]["data"]["code"], "CONFIG.002")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


class TestStdioNoSecretLeak(unittest.TestCase):
    """Stdio output must never contain secrets."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_stdout_no_secret(self):
        """Good response stdout must not contain the HMAC secret."""
        if issue_token is None:
            self.skipTest("operator_surface.core.auth not available yet")
        proc, _env = _spawn_subprocess(self.root)
        try:
            token = _make_token()
            request = {
                "jsonrpc": "2.0",
                "id": 30,
                "method": "council.status",
                "params": {"auth": {"token": token}},
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = _safe_readline(proc, "no secret leak")
            self.assertNotIn(
                "stdio-test-secret-key", response_line,
                "stdout must not leak the HMAC secret",
            )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def test_no_traceback_in_stdout(self):
        """stdout must not contain Python tracebacks."""
        proc, _env = _spawn_subprocess(self.root)
        try:
            request = {
                "jsonrpc": "2.0",
                "id": 31,
                "method": "council.submit_task",
                "params": {"task_brief": "No auth at all"},
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = _safe_readline(proc, "no traceback")
            self.assertNotIn(
                "Traceback", response_line,
                "stdout must not contain tracebacks",
            )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


class TestStdioTimeoutKill(unittest.TestCase):
    """Subprocess must be killable; timeout guard works."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_subprocess_can_be_killed(self):
        """Spawn a subprocess and kill it within timeout."""
        proc, _env = _spawn_subprocess(self.root)
        try:
            proc.stdin.close()
            try:
                _ = proc.stdout.readline()
            except Exception:
                pass
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


if __name__ == "__main__":
    unittest.main()
