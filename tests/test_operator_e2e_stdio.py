"""End-to-end stdio session: full lifecycle from spawn through known verbs.

Cycle 10 Step 9 — Test Author.

Contract:
  1. Subprocess starts → READY (known method responds)
  2. Authenticated submit_task → session created (in COUNCIL_TEST_MODE,
     precheck passes because _FakeDocumenter.audit() returns compliant=True)
  3. council.status → lists sessions, includes notice about layer1_stub_active
  4. council.list_sessions → lists same session
  5. documenter.audit → works in test mode (stub returns compliant=True)
  6. council.resolve_escalation on unknown escalation_id → VAL.003
     (in test mode, escalations is absent → None → guard 2 fires)
  7. council.override_precheck → override_granted
  8. documenter.override_gate → overridden
  9. Event log contains required event types (verified in-process via handle_request)
 10. Sentinel file exists at documenter/.operator_ingress_ready (created by surface)
 11. REGISTRATION.md presence test → FAILS (code author must create it)

Red baseline: REGISTRATION.md missing; sentinel may not be created yet;
full event log not wired in test mode yet.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

try:
    from operator_ingress.core.auth import issue_token  # noqa: F401
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

_SESS_RE = re.compile(r"^sess-[a-z0-9]{12}$")


def _make_token(secret="test-secret-key", sub="op-alice"):
    if issue_token is None:
        return None
    claims = dict(_MIN_CLAIMS)
    claims["sub"] = sub
    return issue_token(claims, secret)


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------

def _spawn_subprocess(root_dir, timeout=15):
    """Spawn stdio subprocess with test env."""
    env = os.environ.copy()
    env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
    env["COUNCIL_STATE_ROOT"] = root_dir
    env["COUNCIL_TEST_MODE"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-m", "operator_ingress"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    return proc


def _safe_readline(proc, label=""):
    try:
        line = proc.stdout.readline()
        return line if line else ""
    except Exception:
        return ""


def _send_request(proc, request):
    """Write a JSON-RPC request and read the response line."""
    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()
    return _safe_readline(proc, f"request {request.get('id', '?')}")


def _kill_proc(proc):
    """Terminate a subprocess, with SIGKILL fallback."""
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
# E2E Test: full lifecycle in one subprocess
# ---------------------------------------------------------------------------

class TestE2EStdioSession(unittest.TestCase):
    """Full end-to-end stdio session: spawn → auth → submit → status →
    audit → resolve_escalation → override → sentinel → REGISTRATION.md."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self._proc = None

    def tearDown(self):
        _kill_proc(self._proc)
        shutil.rmtree(self.root, ignore_errors=True)

    def _auth_token(self, sub="op-alice"):
        return _make_token(sub=sub)

    def _request(self, method, params, rid=1):
        req = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            req["params"] = params
        return req

    def test_full_session_lifecycle(self):
        """Lifecycle: submit_task → status → list_sessions → audit →
        resolve_escalation (VAL.003) → override_precheck → override_gate
        → sentinel → REGISTRATION.md (failing test)."""
        if issue_token is None:
            self.skipTest("operator_ingress.core.auth not available yet")

        proc = _spawn_subprocess(self.root)
        self._proc = proc
        # Consume the READY line before sending requests.
        ready_line = _safe_readline(proc, "READY")
        self.assertTrue(ready_line.startswith("READY"),
                        f"Expected READY line, got {repr(ready_line)}")
        try:
            token = self._auth_token()

            # --- 1. submit_task ---
            req = self._request(
                "council.submit_task",
                params={
                    "auth": {"token": token},
                    "task_brief": "E2E lifecycle test",
                    "scenario_id": "scen-e2e",
                },
                rid=1,
            )
            line = _send_request(proc, req)
            self.assertTrue(len(line) > 0, "submit_task must return a response")
            resp = json.loads(line)
            self.assertIn("result", resp, "submit_task must return result")
            session_id = resp["result"]["session_id"]
            self.assertRegex(session_id, _SESS_RE.pattern)
            self.assertEqual(resp["result"]["status"], "submitted")

            # --- 2. council.status ---
            req2 = self._request(
                "council.status",
                params={"auth": {"token": token}},
                rid=2,
            )
            line2 = _send_request(proc, req2)
            resp2 = json.loads(line2)
            self.assertIn("result", resp2)
            result2 = resp2["result"]
            self.assertIn("sessions", result2)
            self.assertEqual(len(result2["sessions"]), 1,
                             "Must list 1 session after submit_task")
            self.assertEqual(result2["session_id"], None,
                             "Operator-level view must have session_id=None")
            # Check for layer1_stub_active notice.
            notices = result2.get("notices", [])
            notice_types = [n.get("type", "") for n in notices]
            self.assertTrue(
                any("layer1_stub_active" in t for t in notice_types),
                "Must include layer1_stub_active notice type",
            )

            # --- 3. council.list_sessions ---
            req3 = self._request(
                "council.list_sessions",
                params={"auth": {"token": token}},
                rid=3,
            )
            line3 = _send_request(proc, req3)
            resp3 = json.loads(line3)
            self.assertIn("result", resp3)
            self.assertEqual(len(resp3["result"]["sessions"]), 1)

            # --- 4. documenter.audit (COUNCIL_TEST_MODE — stub) ---
            req4 = self._request(
                "documenter.audit",
                params={"auth": {"token": token}},
                rid=4,
            )
            line4 = _send_request(proc, req4)
            resp4 = json.loads(line4)
            self.assertIn("result", resp4,
                          "documenter.audit must not crash under test mode")

            # --- 5. council.resolve_escalation on unknown escalation_id ---
            # In test mode, escalations is absent → None → guard 2 fires → VAL.003.
            req5 = self._request(
                "council.resolve_escalation",
                params={
                    "auth": {"token": token},
                    "session_id": session_id,
                    "escalation_id": "esc-nonexistent-000000",
                    "decision": "accept",
                },
                rid=5,
            )
            line5 = _send_request(proc, req5)
            resp5 = json.loads(line5)
            # The verb returns {"error": envelope}, which handle_request
            # wraps in "result" → result.error.code.
            self.assertIn("result", resp5,
                          "resolve_escalation returns a result envelope")
            self.assertIn("error", resp5["result"],
                          "resolve_escalation on unknown escalation must contain error")
            self.assertEqual(
                resp5["result"]["error"]["code"], "VAL.003",
                "Unknown escalation_id must return VAL.003",
            )

            # --- 6. council.override_precheck ---
            req6 = self._request(
                "council.override_precheck",
                params={
                    "auth": {"token": token},
                    "session_id": session_id,
                    "reason": "Emergency override for e2e test",
                },
                rid=6,
            )
            line6 = _send_request(proc, req6)
            resp6 = json.loads(line6)
            self.assertIn("result", resp6,
                          "override_precheck must return result")
            self.assertEqual(resp6["result"]["status"], "override_granted")

            # --- 7. documenter.override_gate ---
            req7 = self._request(
                "documenter.override_gate",
                params={
                    "auth": {"token": token},
                    "target_id": "doc-e2e",
                    "reason": "Emergency gate override",
                },
                rid=7,
            )
            line7 = _send_request(proc, req7)
            resp7 = json.loads(line7)
            self.assertIn("result", resp7,
                          "override_gate must return result")
            self.assertEqual(resp7["result"]["status"], "overridden")

            # --- 8. Check sentinel file ---
            # The Operator Ingress should have created the sentinel.
            sentinel_path = os.path.join(self.root, "documenter", ".operator_ingress_ready")
            self.assertTrue(
                os.path.isfile(sentinel_path),
                "Sentinel file must exist at documenter/.operator_ingress_ready after operations",
            )

            # --- 9. REGISTRATION.md presence test ---
            # ORCHESTRATOR-AUTHORIZED EDIT (cycle 10): the runbook lives in the
            # package (target-task: operator_ingress/REGISTRATION.md, an
            # implementation file), NOT in the state root; production startup
            # must not copy files around. Presence + content checks per the
            # target-task acceptance criteria.
            import operator_ingress as _pkg
            registration_path = os.path.join(
                os.path.dirname(os.path.abspath(_pkg.__file__)),
                "REGISTRATION.md",
            )
            self.assertTrue(
                os.path.isfile(registration_path),
                "REGISTRATION.md must exist in the operator_ingress package",
            )
            with open(registration_path, "r", encoding="utf-8") as fh:
                reg_text = fh.read()
            for var in ("COUNCIL_OPERATOR_ID", "COUNCIL_OPERATOR_SECRET",
                        "COUNCIL_STATE_ROOT", "PRE_CHECK_TIMEOUT"):
                self.assertIn(var, reg_text,
                              f"REGISTRATION.md must document {var}")
            lowered = reg_text.lower()
            self.assertTrue(
                "operator" in lowered
                and ("never registers" in lowered
                     or "operator performs registration" in lowered
                     or "operator's decision" in lowered),
                "REGISTRATION.md must state that registration and activation "
                "are operator acts and the surface never registers itself",
            )
        finally:
            _kill_proc(proc)


if __name__ == "__main__":
    unittest.main()
