"""Crash integrity: SIGKILL mid-flight + malformed trailing bytes + stale intent.

Cycle 10 Step 9 — Test Author.

Contract (D): store cold start tolerates:
  (i) truncated final line in session.jsonl / intent.jsonl (malformed trailing
      JSON silently skipped — reader returns valid records only, no exception)
  (ii) stale intent record without session commit — list_sessions/get_session
        unaffected, no crash

Tests both levels: subprocess SIGKILL AND direct store-level tests.
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


def _make_token(secret="crash-test-secret", sub="op-alice"):
    if issue_token is None:
        return None
    claims = dict(_MIN_CLAIMS)
    claims["sub"] = sub
    return issue_token(claims, secret)


# ---------------------------------------------------------------------------
# Subprocess helper (mirror test_operator_stdio)
# ---------------------------------------------------------------------------

def _spawn_subprocess(root_dir, timeout=10):
    """Spawn `python3 -m operator_ingress` with test env.

    The READY line is consumed before returning so that the first
    ``_safe_readline`` call returns the actual response.
    """
    env = os.environ.copy()
    env["COUNCIL_OPERATOR_SECRET"] = "crash-test-secret"
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
# Test cases
# ---------------------------------------------------------------------------

class TestCrashIntegritySIGKILL(unittest.TestCase):
    """SIGKILL mid-flight: kill the stdio subprocess after sending a request."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_sigkill_mid_flight(self):
        """Kill subprocess after sending request; restart must cold-start OK."""
        if issue_token is None:
            self.skipTest("operator_ingress.core.auth not available yet")
        proc = _spawn_subprocess(self.root)
        try:
            token = _make_token(sub="op-alice")
            request = {
                "jsonrpc": "2.0",
                "id": 100,
                "method": "council.submit_task",
                "params": {
                    "auth": {"token": token},
                    "task_brief": "Crash test",
                    "scenario_id": "scen-crash",
                },
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            # Read first response (may or may not arrive before kill).
            _safe_readline(proc, "pre-kill response")
            # Kill immediately with SIGKILL (cannot be caught/ignored).
            proc.kill()
            # Wait for process to terminate.
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

            # --- Now restart the server on the SAME state root ---
            proc2 = _spawn_subprocess(self.root)
            try:
                token2 = _make_token(sub="op-bob")
                request2 = {
                    "jsonrpc": "2.0",
                    "id": 101,
                    "method": "council.status",
                    "params": {"auth": {"token": token2}},
                }
                proc2.stdin.write(json.dumps(request2) + "\n")
                proc2.stdin.flush()
                response_line = _safe_readline(proc2, "post-restart status")
                self.assertTrue(
                    len(response_line) > 0,
                    "After SIGKILL+restart, server must respond to status",
                )
                response = json.loads(response_line)
                self.assertIn("result", response,
                              "council.status must return result after restart")
                self.assertIn("sessions", response["result"])
                # Session from pre-SIGKILL should be readable (or absent if
                # SIGKILL interrupted the write — either way: no crash).
            finally:
                _kill_subprocess(proc2)
        finally:
            _kill_subprocess(proc)

    def test_sigkill_then_submit(self):
        """After SIGKILL kill and restart, submit_task still works."""
        if issue_token is None:
            self.skipTest("operator_ingress.core.auth not available yet")
        proc = _spawn_subprocess(self.root)
        try:
            token = _make_token(sub="op-alice")
            request = {
                "jsonrpc": "2.0",
                "id": 200,
                "method": "council.submit_task",
                "params": {
                    "auth": {"token": token},
                    "task_brief": "Pre-kill task",
                    "scenario_id": "scen-crash2",
                },
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            _safe_readline(proc, "pre-kill response 2")
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

            # Restart and verify it's healthy.
            proc2 = _spawn_subprocess(self.root)
            try:
                token2 = _make_token(sub="op-bob")
                request2 = {
                    "jsonrpc": "2.0",
                    "id": 201,
                    "method": "council.submit_task",
                    "params": {
                        "auth": {"token": token2},
                        "task_brief": "Post-kill task",
                        "scenario_id": "scen-crash3",
                    },
                }
                proc2.stdin.write(json.dumps(request2) + "\n")
                proc2.stdin.flush()
                response_line = _safe_readline(proc2, "post-restart submit")
                self.assertTrue(len(response_line) > 0,
                                "After restart, submit_task must respond")
                response = json.loads(response_line)
                self.assertIn("result", response,
                              "submit_task must return result after restart")
            finally:
                _kill_subprocess(proc2)
        finally:
            _kill_subprocess(proc)


class TestCrashIntegrityStoreLevel(unittest.TestCase):
    """Store-level: malformed trailing bytes in session.jsonl / intent.jsonl."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_malformed_trailing_line_session_jsonl(self):
        """Truncated/malformed JSON as the FIRST line in session.jsonl: cold start
        must skip it silently — valid sessions still readable, no exception.

        The store's read path uses readline() + json.loads; if the first line
        is malformed, json.loads raises — list_sessions must catch that and
        skip the session (no crash).
        """
        from operator_ingress.adapters.session_store import MvpSessionStore

        store = MvpSessionStore(self.root)

        # Create a valid session first.
        store.create_session("sess-good1")

        # Now write a session with ONLY a malformed first line (truncated).
        session_path = os.path.join(
            self.root, "sessions", "sess-bad1", "session.jsonl"
        )
        os.makedirs(os.path.dirname(session_path), exist_ok=True)
        with open(session_path, "w", encoding="utf-8") as fh:
            fh.write("MALFORMED TRUNCATED {NOT JSON\n")

        # list_sessions should NOT crash — returns only valid sessions.
        sessions = store.list_sessions()
        session_ids = {s["session_id"] for s in sessions}
        self.assertIn("sess-good1", session_ids,
                       "Valid session must be listed")
        self.assertNotIn("sess-bad1", session_ids,
                          "Malformed session must be silently skipped")

    def test_malformed_trailing_line_intent_jsonl(self):
        """Truncated JSON in intent.jsonl: append_record + get_session must
        not crash; list_sessions unaffected."""
        from operator_ingress.adapters.session_store import MvpSessionStore

        store = MvpSessionStore(self.root)
        store.create_session("sess-good2")

        # Append a valid record then a malformed trailing line.
        store.append_record("sess-good2", {
            "verb": "council.submit_task",
            "operator_id": "op-alice",
        })
        intent_path = os.path.join(
            self.root, "sessions", "sess-good2", "intent.jsonl"
        )
        with open(intent_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"verb": "council.status"}) + "\n")
            fh.write("{incomplete json\n")

        # list_sessions must not crash.
        sessions = store.list_sessions()
        self.assertGreater(len(sessions), 0,
                           "list_sessions must return valid sessions")

        # get_session must return the valid session dict.
        session = store.get_session("sess-good2")
        self.assertIsNotNone(session, "get_session must return valid session")
        self.assertEqual(session["session_id"], "sess-good2")

    def test_stale_intent_without_session(self):
        """Intent record exists but no corresponding session: list_sessions
        / get_session unaffected, no crash, no roll-forward."""
        from operator_ingress.adapters.session_store import MvpSessionStore

        store = MvpSessionStore(self.root)

        # Write an intent record for a session that does NOT exist.
        intent_path = os.path.join(
            self.root, "sessions", "sess-stale999", "intent.jsonl"
        )
        os.makedirs(os.path.dirname(intent_path), exist_ok=True)
        with open(intent_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "verb": "documenter.delegate",
                "operator_id": "op-alice",
            }) + "\n")

        # list_sessions: no session named sess-stale999 (no crash).
        sessions = store.list_sessions()
        session_ids = {s["session_id"] for s in sessions}
        self.assertNotIn("sess-stale999", session_ids,
                          "Stale session must not appear in list_sessions")

        # get_session: must return None, not crash.
        session = store.get_session("sess-stale999")
        self.assertIsNone(session,
                          "get_session for non-existent session must return None")


if __name__ == "__main__":
    unittest.main()
