"""AI-1b: public-surface plumbing of the solo approval acknowledgment token.

Core `write.approve()` accepts `acknowledged` (AI-1), but no public path
passed it: CLI `--approve` and the MCP `approve` tool. Without plumbing the
solo operator could not complete an approval after activation (fail-closed
deny). These tests pin the public contract:

  CLI:  --approve --approval-id <id> [--acknowledge <token>]
  MCP:  tools/call approve {"approval_id": ..., "acknowledge": <token>}

Solo configuration used throughout: allow_solo_approval true, one safe
`update` entry (targets []) and one review `create_ru` entry; delay left
absent (0) so token/trust behavior is isolated from the timer.

Run with: python3 -m unittest tests.test_solo_ack_plumbing
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import yaml  # noqa: E402

# Reuse the established CLI/MCP subprocess helpers (no fixture copying).
from tests.test_documenter_cli_tier2 import (  # noqa: E402
    _run_cli,
    _make_corpus,
    _diff_for_alpha,
)
from tests.test_documenter_mcp import _run_mcp  # noqa: E402

ACK = "CONFIRMED_SOLE_REVIEWER"


def _write_solo_policy(tmpdir):
    """Tier 2 policy with solo enabled; safe update + review create_ru."""
    fields = {
        "version": "0.2.0",
        "active_tier": 2,
        "allowed_operations": [
            {"change_type": "update", "targets": [], "trust_level": "safe"},
            {"change_type": "create_ru", "targets": [], "trust_level": "review"},
        ],
        "briefing_ref": os.path.join(tmpdir, "_briefing.md"),
        "audit_freshness": 30,
        "approval_expiry_window": 30,
        "max_diff_bytes": 524288,
        "lock_wait_timeout": 5,
        "allow_solo_approval": True,
    }
    with open(os.path.join(tmpdir, "_briefing.md"), "w") as f:
        f.write("# Briefing\n\nSolo pilot context.\n")
    p = os.path.join(tmpdir, "pol.yml")
    with open(p, "w") as f:
        yaml.safe_dump({"documenter_policy": fields}, f)
    return p


def _propose(tmpdir, corpus, policy_path, data_dir, *,
             change_type="update", trust_level="safe"):
    """audit + delegate-write as op-solo; returns (audit_id, approval_id)."""
    env = {
        "DOCUMENTER_POLICY_PATH": policy_path,
        "DOCUMENTER_DATA_DIR": data_dir,
    }
    resp, rc = _run_cli(["--audit", "--root", corpus, "--target", "*",
                         "--json"], env_extra=env)
    assert rc == 0, f"audit failed: {resp}"
    audit_id = resp["audit_id"]

    resp, rc = _run_cli([
        "--delegate-write", "--root", corpus,
        "--target", "alpha",
        "--change-type", change_type,
        "--trust-level", trust_level,
        "--diff-base64", _diff_for_alpha(),
        "--audit-id", audit_id,
        "--json"],
        env_extra={**env, "COUNCIL_OPERATOR_ID": "op-solo"})
    assert rc == 0, f"delegate-write failed: {resp}"
    return audit_id, resp["approval_id"]


class TestCLIAcknowledgePlumbing(unittest.TestCase):
    """CLI --approve --acknowledge: solo approve requires the token."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.corpus = _make_corpus(self.tmpdir)
        self.policy = _write_solo_policy(self.tmpdir)
        self.data_dir = os.path.join(self.tmpdir, "state")
        self.env = {
            "DOCUMENTER_POLICY_PATH": self.policy,
            "DOCUMENTER_DATA_DIR": self.data_dir,
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _approve(self, approval_id, extra_argv=()):
        return _run_cli(
            ["--approve", "--root", self.corpus,
             "--approval-id", approval_id, "--json", *extra_argv],
            env_extra={**self.env, "COUNCIL_OPERATOR_ID": "op-solo"})

    def test_solo_approve_without_ack_denied(self):
        """No --acknowledge → gate_failure (core token check stands)."""
        _, approval_id = _propose(self.tmpdir, self.corpus, self.policy,
                                  self.data_dir)
        resp, rc = self._approve(approval_id)
        self.assertEqual(rc, 2)
        self.assertEqual(resp["error_category"], "gate_failure")

    def test_solo_approve_with_ack_succeeds(self):
        """--acknowledge CONFIRMED_SOLE_REVIEWER → approved + bias_warning."""
        _, approval_id = _propose(self.tmpdir, self.corpus, self.policy,
                                  self.data_dir)
        resp, rc = self._approve(approval_id,
                                 extra_argv=["--acknowledge", ACK])
        self.assertEqual(rc, 0, f"expected approved, got {resp}")
        self.assertEqual(resp["decision"], "approved")
        self.assertIn("bias_warning", resp)
        self.assertTrue(resp["bias_warning"])

    def test_solo_approve_wrong_ack_denied(self):
        """--acknowledge with wrong value → gate_failure."""
        _, approval_id = _propose(self.tmpdir, self.corpus, self.policy,
                                  self.data_dir)
        resp, rc = self._approve(approval_id,
                                 extra_argv=["--acknowledge", "WRONG"])
        self.assertEqual(rc, 2)
        self.assertEqual(resp["error_category"], "gate_failure")

    def test_solo_approve_non_safe_change_type_denied(self):
        """create_ru (review floor) proposal + correct token → gate_failure.

        E2E proof the safe-only rule uses the PERSISTED change_type through
        the public CLI path, not a hard-coded 'update'.
        """
        _, approval_id = _propose(self.tmpdir, self.corpus, self.policy,
                                  self.data_dir,
                                  change_type="create_ru",
                                  trust_level="review")
        resp, rc = self._approve(approval_id, extra_argv=["--acknowledge", ACK])
        self.assertEqual(rc, 2)
        self.assertEqual(resp["error_category"], "gate_failure")


class TestMCPAcknowledgePlumbing(unittest.TestCase):
    """MCP tools/call approve accepts 'acknowledge' and forwards it.

    Proposals are created through the CLI (same data_dir), approvals are
    taken through the MCP surface — proving the token travels end to end.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.corpus = _make_corpus(self.tmpdir)
        self.policy = _write_solo_policy(self.tmpdir)
        self.data_dir = os.path.join(self.tmpdir, "state")
        self.env = {
            "DOCUMENTER_POLICY_PATH": self.policy,
            "DOCUMENTER_DATA_DIR": self.data_dir,
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _approve_via_mcp(self, approval_id, acknowledge=None):
        args = {"approval_id": approval_id}
        if acknowledge is not None:
            args["acknowledge"] = acknowledge
        responses, _, rc = _run_mcp(
            ["--root", self.corpus],
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "approve", "arguments": args}}],
            env_extra={**self.env, "COUNCIL_OPERATOR_ID": "op-solo"})
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        return responses[0]

    def test_mcp_approve_ack_accepted(self):
        """acknowledge is a schema-valid argument; correct token approves."""
        _, approval_id = _propose(self.tmpdir, self.corpus, self.policy,
                                  self.data_dir)
        resp = self._approve_via_mcp(approval_id, ACK)
        self.assertFalse(resp["result"].get("isError"),
                         f"expected approval, got {resp}")
        payload = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(payload["decision"], "approved")
        self.assertIn("bias_warning", payload)

    def test_mcp_approve_wrong_ack_denied(self):
        """Wrong acknowledge value → isError gate_failure (core rule)."""
        _, approval_id = _propose(self.tmpdir, self.corpus, self.policy,
                                  self.data_dir)
        resp = self._approve_via_mcp(approval_id, "NOPE")
        self.assertTrue(resp["result"].get("isError"))
        payload = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(payload["error_category"], "gate_failure")

    def test_mcp_approve_without_ack_denied(self):
        """Missing acknowledge for a solo approval → isError gate_failure."""
        _, approval_id = _propose(self.tmpdir, self.corpus, self.policy,
                                  self.data_dir)
        resp = self._approve_via_mcp(approval_id)
        self.assertTrue(resp["result"].get("isError"))
        payload = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(payload["error_category"], "gate_failure")


if __name__ == "__main__":
    unittest.main()
