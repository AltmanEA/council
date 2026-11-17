"""Tests for solo-operator Tier 2+ activation changeset (AI-1).

Covers acceptance criteria 1-7 from target-task.md.
Run with: python3 -m unittest tests.test_solo_activation -v
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

try:
    from documenter_service.core.errors import StructuredError
except ImportError:
    StructuredError = None

try:
    from documenter_service.core.policy import PolicyError, validate_policy
except ImportError:
    PolicyError = None
    validate_policy = None

try:
    from documenter_service.core.write import (
        approve as write_approve, _apply_write_changeset,
    )
except ImportError:
    write_approve = None
    _apply_write_changeset = None

try:
    from operator_surface.core.approval import (
        ApprovalError, ApprovalRegistry, hash_diff,
    )
except ImportError:
    ApprovalError = None
    ApprovalRegistry = None
    hash_diff = None

try:
    from operator_surface.core.verbs import (
        documenter_approve, documenter_delegate, consume_precheck_override,
        override_precheck,
    )
except ImportError:
    documenter_approve = None
    documenter_delegate = None
    consume_precheck_override = None
    override_precheck = None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _policy(**over):
    """Build a minimal tier-2 policy dict with optional overrides."""
    base = {
        "documenter_policy": {
            "version": "0.2.0",
            "active_tier": 2,
            "allowed_operations": [],
            "briefing_ref": None,
            "audit_freshness": 30,
            "approval_expiry_window": 30,
        }
    }
    base["documenter_policy"].update(over)
    return base


def _enable_operator_surface(root):
    sentinel = os.path.join(root, "documenter", ".operator_surface_ready")
    os.makedirs(os.path.dirname(sentinel), exist_ok=True)
    with open(sentinel, "w") as f:
        f.write("")
    return sentinel


class TestPolicyFields(unittest.TestCase):
    """AC1: validate_policy accepts allow_solo_approval (bool) and
    min_approval_delay_seconds (int [60,86400]). Absent -> fail-closed."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        bp = os.path.join(self.tmpdir, "briefing.md")
        with open(bp, "w") as f:
            f.write("briefing")
        self.briefing = bp

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_allow_solo_approval_absent_defaults_false(self):
        """Absent field => fail-closed: solo still blocked."""
        if validate_policy is None or PolicyError is None:
            self.skipTest("policy module not yet implemented")
        p = _policy(briefing_ref=self.briefing, active_tier=1,
                    allowed_operations=[])
        result = validate_policy(p)
        self.assertEqual(result.get("allow_solo_approval"), False)

    def test_allow_solo_approval_true(self):
        if validate_policy is None or PolicyError is None:
            self.skipTest("policy module not yet implemented")
        p = _policy(briefing_ref=self.briefing, active_tier=1,
                    allowed_operations=[], allow_solo_approval=True)
        result = validate_policy(p)
        self.assertTrue(result.get("allow_solo_approval"))

    def test_allow_solo_approval_false(self):
        if validate_policy is None or PolicyError is None:
            self.skipTest("policy module not yet implemented")
        p = _policy(briefing_ref=self.briefing, active_tier=1,
                    allowed_operations=[], allow_solo_approval=False)
        result = validate_policy(p)
        self.assertFalse(result.get("allow_solo_approval"))

    def test_min_approval_delay_seconds_valid(self):
        if validate_policy is None or PolicyError is None:
            self.skipTest("policy module not yet implemented")
        for val in [60, 300, 3600, 86400]:
            p = _policy(briefing_ref=self.briefing, active_tier=1,
                        allowed_operations=[], min_approval_delay_seconds=val)
            result = validate_policy(p)
            self.assertEqual(result.get("min_approval_delay_seconds"), val)

    def test_min_approval_delay_seconds_too_low(self):
        if validate_policy is None or PolicyError is None:
            self.skipTest("policy module not yet implemented")
        p = _policy(briefing_ref=self.briefing, active_tier=1,
                    allowed_operations=[], min_approval_delay_seconds=59)
        with self.assertRaises(PolicyError) as ctx:
            validate_policy(p)
        self.assertIn("min_approval_delay_seconds", ctx.exception.reason.lower())

    def test_min_approval_delay_seconds_too_high(self):
        if validate_policy is None or PolicyError is None:
            self.skipTest("policy module not yet implemented")
        p = _policy(briefing_ref=self.briefing, active_tier=1,
                    allowed_operations=[], min_approval_delay_seconds=86401)
        with self.assertRaises(PolicyError) as ctx:
            validate_policy(p)
        self.assertIn("min_approval_delay_seconds", ctx.exception.reason.lower())

    def test_min_approval_delay_seconds_non_int(self):
        if validate_policy is None or PolicyError is None:
            self.skipTest("policy module not yet implemented")
        p = _policy(briefing_ref=self.briefing, active_tier=1,
                    allowed_operations=[], min_approval_delay_seconds=3.5)
        with self.assertRaises(PolicyError) as ctx:
            validate_policy(p)
        self.assertIn("min_approval_delay_seconds", ctx.exception.reason.lower())

    def test_min_approval_delay_seconds_string(self):
        if validate_policy is None or PolicyError is None:
            self.skipTest("policy module not yet implemented")
        p = _policy(briefing_ref=self.briefing, active_tier=1,
                    allowed_operations=[], min_approval_delay_seconds="300")
        with self.assertRaises(PolicyError) as ctx:
            validate_policy(p)
        self.assertIn("min_approval_delay_seconds", ctx.exception.reason.lower())

    def test_min_approval_delay_seconds_absent_defaults_zero(self):
        """Absent => strict default (zero delay): solo still blocked by
        allow_solo_approval."""
        if validate_policy is None or PolicyError is None:
            self.skipTest("policy module not yet implemented")
        p = _policy(briefing_ref=self.briefing, active_tier=1,
                    allowed_operations=[])
        result = validate_policy(p)
        self.assertEqual(result.get("min_approval_delay_seconds"), 0)

    def test_allow_solo_approval_non_bool_raises(self):
        if validate_policy is None or PolicyError is None:
            self.skipTest("policy module not yet implemented")
        p = _policy(briefing_ref=self.briefing, active_tier=1,
                    allowed_operations=[], allow_solo_approval="yes")
        with self.assertRaises(PolicyError) as ctx:
            validate_policy(p)
        self.assertIn("allow_solo_approval", ctx.exception.reason.lower())

    def test_allow_solo_approval_bool_is_false(self):
        """bool False is still False — but bool should be rejected since
        allow_solo_approval must be a plain bool (not int)."""
        if validate_policy is None or PolicyError is None:
            self.skipTest("policy module not yet implemented")
        # In Python bool is a subclass of int, so bool False is valid bool.
        # The field must be accepted as a bool.
        p = _policy(briefing_ref=self.briefing, active_tier=1,
                    allowed_operations=[], allow_solo_approval=False)
        result = validate_policy(p)
        self.assertFalse(result.get("allow_solo_approval"))


class TestSoloApprovalBlocked(unittest.TestCase):
    """AC2: allow_solo_approval False => self-approval (proposer==operator)
    is gate_failure (behavior preservation)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_self_approval_denied_when_solo_false(self):
        if write_approve is None:
            self.skipTest("write_approve not yet implemented")
        from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry
        from documenter_service.core.policy import Policy
        from documenter_service.adapters.stdout_events import StdoutEventSink
        from documenter_service.adapters.diff_engine import StdDiffEngine

        bp = os.path.join(self.tmpdir, "briefing.md")
        with open(bp, "w") as f:
            f.write("briefing")

        policy_dict = _policy(briefing_ref=bp, active_tier=2,
                              allowed_operations=[], allow_solo_approval=False)
        policy = Policy(policy_dict)
        _enable_operator_surface(self.tmpdir)

        registry = JsonlAuditRegistry(self.tmpdir)
        # Create an approval with proposer==operator (self-approval scenario).
        registry.issue_approval(
            approval_id="fake-id", target_ids=["alpha"],
            diff_hash="sha256:" + "a" * 64,
            proposer_id="op-alice", audit_id="aid-1")

        events = StdoutEventSink()

        with self.assertRaises(StructuredError) as ctx:
            write_approve(
                registry, policy, events, root=self.tmpdir,
                approval_id="fake-id", operator_id="op-alice")
        self.assertEqual(ctx.exception.error_category, "gate_failure")
        self.assertIn("self", ctx.exception.message.lower())


class TestSoloApproveAllowed(unittest.TestCase):
    """AC3: Solo approve when allow_solo_approval True + trust_level safe +
    ack token CONFIRMED_SOLE_REVIEWER. Missing/wrong token => gate_failure.
    Non-safe op => gate_failure. Bias-warning banner in response."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_solo_approve_with_token_and_safe(self):
        if write_approve is None:
            self.skipTest("write_approve not yet implemented")
        from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry
        from documenter_service.core.policy import Policy
        from documenter_service.adapters.stdout_events import StdoutEventSink

        bp = os.path.join(self.tmpdir, "briefing.md")
        with open(bp, "w") as f:
            f.write("briefing")

        policy_dict = _policy(briefing_ref=bp, active_tier=2,
                              allowed_operations=[
                                  {"change_type": "update", "targets": [],
                                   "trust_level": "safe"}
                              ], allow_solo_approval=True,
                              min_approval_delay_seconds=0)
        policy = Policy(policy_dict)
        _enable_operator_surface(self.tmpdir)

        registry = JsonlAuditRegistry(self.tmpdir)
        registry.issue_approval(
            approval_id="app-1", target_ids=["alpha"],
            diff_hash="sha256:" + "a" * 64,
            proposer_id="op-bot1", audit_id="aid-1",
            extra={"change_type": "update"})
        record = registry.find_approval("app-1")
        record["proposer_id"] = "op-bot1"
        registry.append("token_record", record)

        events = StdoutEventSink()
        result = write_approve(
            registry, policy, events, root=self.tmpdir,
            approval_id="app-1", operator_id="op-bot1",
            acknowledged="CONFIRMED_SOLE_REVIEWER")
        self.assertEqual(result["decision"], "approved")
        self.assertIn("bias_warning", result)

    def test_solo_approve_missing_token_gate_failure(self):
        """Missing ack token => gate_failure even when solo permitted."""
        if write_approve is None:
            self.skipTest("write_approve not yet implemented")
        from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry
        from documenter_service.core.policy import Policy
        from documenter_service.adapters.stdout_events import StdoutEventSink

        bp = os.path.join(self.tmpdir, "briefing.md")
        with open(bp, "w") as f:
            f.write("briefing")

        policy_dict = _policy(briefing_ref=bp, active_tier=2,
                              allowed_operations=[
                                  {"change_type": "update", "targets": [],
                                   "trust_level": "safe"}
                              ], allow_solo_approval=True,
                              min_approval_delay_seconds=0)
        policy = Policy(policy_dict)
        _enable_operator_surface(self.tmpdir)

        registry = JsonlAuditRegistry(self.tmpdir)
        registry.issue_approval(
            approval_id="app-1", target_ids=["alpha"],
            diff_hash="sha256:" + "a" * 64,
            proposer_id="op-bot1", audit_id="aid-1",
            extra={"change_type": "update"})
        record = registry.find_approval("app-1")
        record["proposer_id"] = "op-bot1"
        registry.append("token_record", record)

        events = StdoutEventSink()
        with self.assertRaises(StructuredError) as ctx:
            write_approve(
                registry, policy, events, root=self.tmpdir,
                approval_id="app-1", operator_id="op-bot1",
                acknowledged=None)
        self.assertEqual(ctx.exception.error_category, "gate_failure")
        self.assertIn("sole", ctx.exception.message.lower())

    def test_solo_approve_wrong_token_gate_failure(self):
        """Wrong ack token => gate_failure."""
        if write_approve is None:
            self.skipTest("write_approve not yet implemented")
        from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry
        from documenter_service.core.policy import Policy
        from documenter_service.adapters.stdout_events import StdoutEventSink

        bp = os.path.join(self.tmpdir, "briefing.md")
        with open(bp, "w") as f:
            f.write("briefing")

        policy_dict = _policy(briefing_ref=bp, active_tier=2,
                              allowed_operations=[
                                  {"change_type": "update", "targets": [],
                                   "trust_level": "safe"}
                              ], allow_solo_approval=True,
                              min_approval_delay_seconds=0)
        policy = Policy(policy_dict)
        _enable_operator_surface(self.tmpdir)

        registry = JsonlAuditRegistry(self.tmpdir)
        registry.issue_approval(
            approval_id="app-1", target_ids=["alpha"],
            diff_hash="sha256:" + "a" * 64,
            proposer_id="op-bot1", audit_id="aid-1",
            extra={"change_type": "update"})
        record = registry.find_approval("app-1")
        record["proposer_id"] = "op-bot1"
        registry.append("token_record", record)

        events = StdoutEventSink()
        with self.assertRaises(StructuredError) as ctx:
            write_approve(
                registry, policy, events, root=self.tmpdir,
                approval_id="app-1", operator_id="op-bot1",
                acknowledged="WRONG_TOKEN")
        self.assertEqual(ctx.exception.error_category, "gate_failure")

    def test_solo_approve_review_trust_gate_failure(self):
        """Non-safe (review) trust_level => gate_failure even with token."""
        if write_approve is None:
            self.skipTest("write_approve not yet implemented")
        from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry
        from documenter_service.core.policy import Policy
        from documenter_service.adapters.stdout_events import StdoutEventSink

        bp = os.path.join(self.tmpdir, "briefing.md")
        with open(bp, "w") as f:
            f.write("briefing")

        policy_dict = _policy(briefing_ref=bp, active_tier=2,
                              allowed_operations=[
                                  {"change_type": "update", "targets": [],
                                   "trust_level": "review"}
                              ], allow_solo_approval=True,
                              min_approval_delay_seconds=0)
        policy = Policy(policy_dict)
        _enable_operator_surface(self.tmpdir)

        registry = JsonlAuditRegistry(self.tmpdir)
        registry.issue_approval(
            approval_id="app-1", target_ids=["alpha"],
            diff_hash="sha256:" + "a" * 64,
            proposer_id="op-bot1", audit_id="aid-1",
            extra={"change_type": "update"})
        record = registry.find_approval("app-1")
        record["proposer_id"] = "op-bot1"
        registry.append("token_record", record)

        events = StdoutEventSink()
        with self.assertRaises(StructuredError) as ctx:
            write_approve(
                registry, policy, events, root=self.tmpdir,
                approval_id="app-1", operator_id="op-bot1",
                acknowledged="CONFIRMED_SOLE_REVIEWER")
        self.assertEqual(ctx.exception.error_category, "gate_failure")

    def test_solo_approve_bias_warning_banner(self):
        """Response contains a bias-warning banner string."""
        if write_approve is None:
            self.skipTest("write_approve not yet implemented")
        from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry
        from documenter_service.core.policy import Policy
        from documenter_service.adapters.stdout_events import StdoutEventSink

        bp = os.path.join(self.tmpdir, "briefing.md")
        with open(bp, "w") as f:
            f.write("briefing")

        policy_dict = _policy(briefing_ref=bp, active_tier=2,
                              allowed_operations=[
                                  {"change_type": "update", "targets": [],
                                   "trust_level": "safe"}
                              ], allow_solo_approval=True,
                              min_approval_delay_seconds=0)
        policy = Policy(policy_dict)
        _enable_operator_surface(self.tmpdir)

        registry = JsonlAuditRegistry(self.tmpdir)
        registry.issue_approval(
            approval_id="app-1", target_ids=["alpha"],
            diff_hash="sha256:" + "a" * 64,
            proposer_id="op-bot1", audit_id="aid-1",
            extra={"change_type": "update"})
        record = registry.find_approval("app-1")
        record["proposer_id"] = "op-bot1"
        registry.append("token_record", record)

        events = StdoutEventSink()
        result = write_approve(
            registry, policy, events, root=self.tmpdir,
            approval_id="app-1", operator_id="op-bot1",
            acknowledged="CONFIRMED_SOLE_REVIEWER")
        self.assertIn("bias_warning", result)


class TestMinDelay(unittest.TestCase):
    """AC4: Approve before min_approval_delay_seconds since created_at =>
    gate_failure; after => proceeds."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_approve_before_delay_gate_failure(self):
        if write_approve is None:
            self.skipTest("write_approve not yet implemented")
        from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry
        from documenter_service.core.policy import Policy
        from documenter_service.adapters.stdout_events import StdoutEventSink

        bp = os.path.join(self.tmpdir, "briefing.md")
        with open(bp, "w") as f:
            f.write("briefing")

        policy_dict = _policy(briefing_ref=bp, active_tier=2,
                              allowed_operations=[
                                  {"change_type": "update", "targets": [],
                                   "trust_level": "safe"}
                              ], allow_solo_approval=True,
                              min_approval_delay_seconds=600)
        policy = Policy(policy_dict)
        _enable_operator_surface(self.tmpdir)

        registry = JsonlAuditRegistry(self.tmpdir)
        registry.issue_approval(
            approval_id="app-1", target_ids=["alpha"],
            diff_hash="sha256:" + "a" * 64,
            proposer_id="op-bot1", audit_id="aid-1",
            extra={"change_type": "update"})
        record = registry.find_approval("app-1")
        record["proposer_id"] = "op-bot1"
        registry.append("token_record", record)

        events = StdoutEventSink()
        with self.assertRaises(StructuredError) as ctx:
            write_approve(
                registry, policy, events, root=self.tmpdir,
                approval_id="app-1", operator_id="op-bot1",
                acknowledged="CONFIRMED_SOLE_REVIEWER")
        self.assertEqual(ctx.exception.error_category, "gate_failure")
        self.assertIn("delay", ctx.exception.message.lower())

    def test_approve_after_delay_proceeds(self):
        """Manually backdate created_at so delay has elapsed."""
        if write_approve is None:
            self.skipTest("write_approve not yet implemented")
        from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry
        from documenter_service.core.policy import Policy
        from documenter_service.adapters.stdout_events import StdoutEventSink

        bp = os.path.join(self.tmpdir, "briefing.md")
        with open(bp, "w") as f:
            f.write("briefing")

        policy_dict = _policy(briefing_ref=bp, active_tier=2,
                              allowed_operations=[
                                  {"change_type": "update", "targets": [],
                                   "trust_level": "safe"}
                              ], allow_solo_approval=True,
                              min_approval_delay_seconds=600)
        policy = Policy(policy_dict)
        _enable_operator_surface(self.tmpdir)

        registry = JsonlAuditRegistry(self.tmpdir)
        registry.issue_approval(
            approval_id="app-1", target_ids=["alpha"],
            diff_hash="sha256:" + "a" * 64,
            proposer_id="op-bot1", audit_id="aid-1",
            extra={"change_type": "update"})
        # Backdate to 1200 seconds ago (> 600)
        old_time = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                 time.gmtime(time.time() - 1200))
        record = registry.find_approval("app-1")
        record["proposer_id"] = "op-bot1"
        record["created_at"] = old_time
        registry.append("token_record", record)

        events = StdoutEventSink()
        result = write_approve(
            registry, policy, events, root=self.tmpdir,
            approval_id="app-1", operator_id="op-bot1",
            acknowledged="CONFIRMED_SOLE_REVIEWER")
        self.assertEqual(result["decision"], "approved")


class TestApprovalRegistryPersistence(unittest.TestCase):
    """AC5: ApprovalRegistry persistence via JSONL + _precheck_override_consumed
    journal. Simulated process restart (new instance over same state_root)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_approvals_jsonl_written(self):
        if ApprovalRegistry is None:
            self.skipTest("ApprovalRegistry not yet implemented")
        intent_dir = os.path.join(self.tmpdir, "documenter", "intent")
        os.makedirs(intent_dir, exist_ok=True)
        reg = ApprovalRegistry(state_root=self.tmpdir)
        reg.register_request("req-1", hash_diff("diff"), "op-alice")
        app_file = os.path.join(intent_dir, "approvals.jsonl")
        self.assertTrue(os.path.isfile(app_file))
        with open(app_file) as f:
            lines = [l for l in f.readlines() if l.strip()]
        self.assertGreater(len(lines), 0)

    def test_approvals_survive_restart(self):
        if ApprovalRegistry is None:
            self.skipTest("ApprovalRegistry not yet implemented")
        intent_dir = os.path.join(self.tmpdir, "documenter", "intent")
        os.makedirs(intent_dir, exist_ok=True)
        reg1 = ApprovalRegistry(state_root=self.tmpdir)
        rid = reg1.register_request("req-1", hash_diff("diff"), "op-alice")
        rec1 = reg1.get("req-1")
        self.assertIsNotNone(rec1)
        self.assertEqual(rec1["proposer_operator_id"], "op-alice")
        self.assertEqual(rec1["state"], "pending")
        # New instance over same state_root
        reg2 = ApprovalRegistry(state_root=self.tmpdir)
        rec2 = reg2.get("req-1")
        self.assertIsNotNone(rec2)
        self.assertEqual(rec2["proposer_operator_id"], "op-alice")

    def test_precheck_override_journal_written(self):
        if override_precheck is None or consume_precheck_override is None:
            self.skipTest("override_precheck not yet implemented")
        os.makedirs(self.tmpdir, exist_ok=True)
        journal_path = os.path.join(self.tmpdir, "documenter",
                                    "precheck_override_journal.jsonl")
        store_mock = type("Store", (), {
            "append_record": lambda s, sid, r: None,
        })()
        events = type("Events", (), {"append": lambda s, e: None})()
        result = override_precheck(
            store_mock, session_id="sess-valid-id", reason="urgent",
            operator_id="op-alice", events=events,
            state_root=self.tmpdir)
        self.assertEqual(result.get("status"), "override_granted")
        self.assertTrue(os.path.isfile(journal_path))

    def test_precheck_override_refuse_reconsumption(self):
        if consume_precheck_override is None:
            self.skipTest("consume_precheck_override not yet implemented")
        os.makedirs(self.tmpdir, exist_ok=True)
        journal_path = os.path.join(self.tmpdir, "documenter",
                                    "precheck_override_journal.jsonl")
        # Simulate: write journal entry directly (since override_precheck
        # may need store_mock which we mock above)
        os.makedirs(os.path.dirname(journal_path), exist_ok=True)
        with open(journal_path, "w") as f:
            json.dump([{"session_id": "sess-1",
                        "operator_id": "op-alice",
                        "consumed_at": "2026-01-01T00:00:00Z"}], f)
        self.assertFalse(consume_precheck_override("sess-1", "op-alice"))


class TestProtectedPaths(unittest.TestCase):
    """AC6: _apply_write_changeset refuses protected paths
    docs-manifest.yaml and documenter_policy.yml."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmpdir, "documenter"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_changeset_refuses_docs_manifest_yaml(self):
        if _apply_write_changeset is None:
            self.skipTest("_apply_write_changeset not yet implemented")
        import subprocess
        from documenter_service.core.policy import Policy
        from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry
        from documenter_service.adapters.stdout_events import StdoutEventSink
        from documenter_service.adapters.diff_engine import StdDiffEngine

        bp = os.path.join(self.tmpdir, "briefing.md")
        with open(bp, "w") as f:
            f.write("briefing")
        policy = Policy(_policy(briefing_ref=bp, active_tier=2,
                                allowed_operations=[
                                    {"change_type": "update", "targets": [],
                                     "trust_level": "safe"}
                                ], allow_solo_approval=True))
        _enable_operator_surface(self.tmpdir)

        # Init git repo so _apply_write_changeset can capture git snapshot
        subprocess.run(["git", "init", "-q", self.tmpdir],
                       capture_output=True, timeout=10)
        subprocess.run(["git", "-C", self.tmpdir, "config", "user.email",
                        "test@council.local"], capture_output=True, timeout=10)
        subprocess.run(["git", "-C", self.tmpdir, "config", "user.name",
                        "Test"], capture_output=True, timeout=10)
        # Create the briefing file and a dummy index so there's something to commit
        with open(bp, "w") as f:
            f.write("briefing")
        subprocess.run(["git", "-C", self.tmpdir, "add", "-A"],
                       capture_output=True, timeout=10)
        subprocess.run(["git", "-C", self.tmpdir, "commit", "-q",
                        "-m", "baseline"], capture_output=True, timeout=10)

        manifest = type("Manifest", (), {
            "resolve": lambda self, t: {"path": "docs/en/" + t + "/index.md"}
            if t in ("alpha", "beta") else None,
            "entries": lambda self: [],
        })()

        registry = JsonlAuditRegistry(self.tmpdir)
        events = StdoutEventSink()
        engine = StdDiffEngine()

        approval = {
            "diff_hash": "sha256:" + "a" * 64,
            "decision": "approved",
            "target_ids": ["alpha"],
            "consumed": False,
            "consumed_at": None,
        }
        with self.assertRaises(StructuredError) as ctx:
            _apply_write_changeset(
                root=self.tmpdir, manifest=manifest, registry=registry,
                policy=policy, events=events, engine=engine,
                approval=approval, approval_id="app-1",
                operator_id="op-user1", text=b"diff",
                normalized=b"diff", diff_hash="sha256:" + "a" * 64,
                target_id="alpha", target_path=os.path.join(
                    self.tmpdir, "docs", "en", "alpha", "index.md"),
                target_path_rel="docs/en/alpha/index.md",
                changeset=[{"path": "docs-manifest.yaml",
                            "content_b64": b"aQ==".decode()}],
                data_dir=os.path.join(self.tmpdir, "documenter"),
                seams=None, sync_latency_budget_ms=30000,
                deadline=time.monotonic() + 30)
        self.assertIn("protected", ctx.exception.message.lower())

    def test_changeset_refuses_documenter_policy_yml(self):
        if _apply_write_changeset is None:
            self.skipTest("_apply_write_changeset not yet implemented")
        import subprocess
        from documenter_service.core.policy import Policy
        from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry
        from documenter_service.adapters.stdout_events import StdoutEventSink
        from documenter_service.adapters.diff_engine import StdDiffEngine

        bp = os.path.join(self.tmpdir, "briefing.md")
        with open(bp, "w") as f:
            f.write("briefing")
        policy = Policy(_policy(briefing_ref=bp, active_tier=2,
                                allowed_operations=[
                                    {"change_type": "update", "targets": [],
                                     "trust_level": "safe"}
                                ], allow_solo_approval=True))
        _enable_operator_surface(self.tmpdir)

        subprocess.run(["git", "init", "-q", self.tmpdir],
                       capture_output=True, timeout=10)
        subprocess.run(["git", "-C", self.tmpdir, "config", "user.email",
                        "test@council.local"], capture_output=True, timeout=10)
        subprocess.run(["git", "-C", self.tmpdir, "config", "user.name",
                        "Test"], capture_output=True, timeout=10)
        with open(bp, "w") as f:
            f.write("briefing")
        subprocess.run(["git", "-C", self.tmpdir, "add", "-A"],
                       capture_output=True, timeout=10)
        subprocess.run(["git", "-C", self.tmpdir, "commit", "-q",
                        "-m", "baseline"], capture_output=True, timeout=10)

        manifest = type("Manifest", (), {
            "resolve": lambda self, t: {"path": "docs/en/" + t + "/index.md"}
            if t in ("alpha",) else None,
            "entries": lambda self: [],
        })()

        registry = JsonlAuditRegistry(self.tmpdir)
        events = StdoutEventSink()
        engine = StdDiffEngine()

        approval = {
            "diff_hash": "sha256:" + "a" * 64,
            "decision": "approved",
            "target_ids": ["alpha"],
            "consumed": False,
            "consumed_at": None,
        }
        with self.assertRaises(StructuredError) as ctx:
            _apply_write_changeset(
                root=self.tmpdir, manifest=manifest, registry=registry,
                policy=policy, events=events, engine=engine,
                approval=approval, approval_id="app-1",
                operator_id="op-user1", text=b"diff",
                normalized=b"diff", diff_hash="sha256:" + "a" * 64,
                target_id="alpha", target_path=os.path.join(
                    self.tmpdir, "docs", "en", "alpha", "index.md"),
                target_path_rel="docs/en/alpha/index.md",
                changeset=[{"path": "documenter_policy.yml",
                            "content_b64": b"aQ==".decode()}],
                data_dir=os.path.join(self.tmpdir, "documenter"),
                seams=None, sync_latency_budget_ms=30000,
                deadline=time.monotonic() + 30)
        self.assertIn("protected", ctx.exception.message.lower())


class TestFailClosed(unittest.TestCase):
    """AC7: Absent fields => deny-solo behavior identical to today."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_absent_solo_fields_blocks_solo(self):
        """Without allow_solo_approval and min_approval_delay_seconds,
        self-approval should be denied (gate_failure)."""
        if write_approve is None:
            self.skipTest("write_approve not yet implemented")
        from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry
        from documenter_service.core.policy import Policy
        from documenter_service.adapters.stdout_events import StdoutEventSink

        bp = os.path.join(self.tmpdir, "briefing.md")
        with open(bp, "w") as f:
            f.write("briefing")

        # No allow_solo_approval, no min_approval_delay_seconds
        policy_dict = _policy(briefing_ref=bp, active_tier=2,
                              allowed_operations=[
                                  {"change_type": "update", "targets": [],
                                   "trust_level": "safe"}
                              ])
        policy = Policy(policy_dict)
        _enable_operator_surface(self.tmpdir)

        registry = JsonlAuditRegistry(self.tmpdir)
        registry.issue_approval(
            approval_id="app-1", target_ids=["alpha"],
            diff_hash="sha256:" + "a" * 64,
            proposer_id="op-bot1", audit_id="aid-1",
            extra={"change_type": "update"})
        record = registry.find_approval("app-1")
        record["proposer_id"] = "op-bot1"
        registry.append("token_record", record)

        events = StdoutEventSink()
        # Without the acknowledged param, self-approval should be denied
        # via the existing self-approval check (gate_failure).
        with self.assertRaises(StructuredError) as ctx:
            write_approve(
                registry, policy, events, root=self.tmpdir,
                approval_id="app-1", operator_id="op-bot1")
        self.assertIn(ctx.exception.error_category,
                      {"gate_failure", "approval_expired", "unknown"})


class TestSoloApprovalFailClosed(unittest.TestCase):
    """AC3 fail-closed: two security gaps that must deny solo approval.

    A) Non-safe change_type: the solo path must check the actual
       proposal's change_type, not hardcode "update".
    B) Min-delay on missing/unparseable created_at: must deny, not pass through.

    Note: approval_is_expired (step 4) also fails-closed on missing/malformed
    created_at, so tests 2 and 3 patch it to reach the solo path and verify
    the min_delay gate itself rejects these cases.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_solo_approve_non_safe_proposal_denied(self):
        """A proposal with change_type='create_ru' (trust floor 'review')
        must be denied by solo path, not silently approved because the
        current code hardcodes change_type='update' on the solo path."""
        if write_approve is None:
            self.skipTest("write_approve not yet implemented")
        from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry
        from documenter_service.core.policy import Policy
        from documenter_service.adapters.stdout_events import StdoutEventSink

        bp = os.path.join(self.tmpdir, "briefing.md")
        with open(bp, "w") as f:
            f.write("briefing")

        policy_dict = _policy(
            briefing_ref=bp, active_tier=2,
            allowed_operations=[
                {"change_type": "update", "targets": [], "trust_level": "safe"},
                {"change_type": "create_ru", "targets": [], "trust_level": "review"},
            ],
            allow_solo_approval=True,
            min_approval_delay_seconds=0  # no delay, isolate change_type check
        )
        policy = Policy(policy_dict)
        _enable_operator_surface(self.tmpdir)

        registry = JsonlAuditRegistry(self.tmpdir)
        registry.issue_approval(
            approval_id="app-1", target_ids=["alpha"],
            diff_hash="sha256:" + "a" * 64,
            proposer_id="op-bot1", audit_id="aid-1",
            extra={"change_type": "create_ru"})  # non-safe: trust_level = "review"
        record = registry.find_approval("app-1")
        record["proposer_id"] = "op-bot1"
        registry.append("token_record", record)

        events = StdoutEventSink()
        with self.assertRaises(StructuredError) as ctx:
            write_approve(
                registry, policy, events, root=self.tmpdir,
                approval_id="app-1", operator_id="op-bot1",
                acknowledged="CONFIRMED_SOLE_REVIEWER")
        self.assertEqual(ctx.exception.error_category, "gate_failure")

    def test_solo_approve_missing_created_at_denied(self):
        """Approval with created_at absent — must deny solo approval.
        The min_delay gate must not silently pass through when the
        field is missing (fail-open is a security defect)."""
        if write_approve is None:
            self.skipTest("write_approve not yet implemented")
        from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry
        from documenter_service.core.policy import Policy
        from documenter_service.adapters.stdout_events import StdoutEventSink

        bp = os.path.join(self.tmpdir, "briefing.md")
        with open(bp, "w") as f:
            f.write("briefing")

        policy_dict = _policy(
            briefing_ref=bp, active_tier=2,
            allowed_operations=[
                {"change_type": "update", "targets": [], "trust_level": "safe"}
            ],
            allow_solo_approval=True,
            min_approval_delay_seconds=60  # requires delay check
        )
        policy = Policy(policy_dict)
        _enable_operator_surface(self.tmpdir)

        registry = JsonlAuditRegistry(self.tmpdir)
        registry.issue_approval(
            approval_id="app-1", target_ids=["alpha"],
            diff_hash="sha256:" + "a" * 64,
            proposer_id="op-bot1", audit_id="aid-1",
            extra={"change_type": "update"})
        record = registry.find_approval("app-1")
        record["proposer_id"] = "op-bot1"
        del record["created_at"]  # remove the auto-set created_at
        registry.append("token_record", record)

        events = StdoutEventSink()
        # approval_is_expired fails-closed on missing created_at; patch
        # at the source module so the locally-imported name inside
        # approve() is replaced when it does `from ..core.registry import`.
        with mock.patch(
            "documenter_service.core.registry.approval_is_expired",
            return_value=False,
        ):
            with self.assertRaises(StructuredError) as ctx:
                write_approve(
                    registry, policy, events, root=self.tmpdir,
                    approval_id="app-1", operator_id="op-bot1",
                    acknowledged="CONFIRMED_SOLE_REVIEWER")
            self.assertEqual(ctx.exception.error_category, "gate_failure")

    def test_solo_approve_unparseable_created_at_denied(self):
        """Approval with created_at = 'not-a-date' — must deny solo
        approval. Unparseable timestamps must not bypass the min_delay
        gate (the current `except (ValueError, TypeError): pass` is
        a fail-open defect)."""
        if write_approve is None:
            self.skipTest("write_approve not yet implemented")
        from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry
        from documenter_service.core.policy import Policy
        from documenter_service.adapters.stdout_events import StdoutEventSink

        bp = os.path.join(self.tmpdir, "briefing.md")
        with open(bp, "w") as f:
            f.write("briefing")

        policy_dict = _policy(
            briefing_ref=bp, active_tier=2,
            allowed_operations=[
                {"change_type": "update", "targets": [], "trust_level": "safe"}
            ],
            allow_solo_approval=True,
            min_approval_delay_seconds=60  # requires delay check
        )
        policy = Policy(policy_dict)
        _enable_operator_surface(self.tmpdir)

        registry = JsonlAuditRegistry(self.tmpdir)
        registry.issue_approval(
            approval_id="app-1", target_ids=["alpha"],
            diff_hash="sha256:" + "a" * 64,
            proposer_id="op-bot1", audit_id="aid-1",
            extra={"change_type": "update"})
        record = registry.find_approval("app-1")
        record["proposer_id"] = "op-bot1"
        record["created_at"] = "not-a-date"  # unparseable timestamp
        registry.append("token_record", record)

        events = StdoutEventSink()
        # approval_is_expired fails-closed on unparseable created_at;
        # patch at the source module so the locally-imported name inside
        # approve() is replaced when it does `from ..core.registry import`.
        with mock.patch(
            "documenter_service.core.registry.approval_is_expired",
            return_value=False,
        ):
            with self.assertRaises(StructuredError) as ctx:
                write_approve(
                    registry, policy, events, root=self.tmpdir,
                    approval_id="app-1", operator_id="op-bot1",
                    acknowledged="CONFIRMED_SOLE_REVIEWER")
            self.assertEqual(ctx.exception.error_category, "gate_failure")


    def test_solo_approve_missing_change_type_denied(self):
        """Approval record created WITHOUT change_type — must deny solo
        approval. The current code falls back to ``"update"`` via
        ``approval.get("change_type") or "update"`` (fail-open); per
        ADR-002 zero silent defaults, a missing change_type MUST be
        denied."""
        if write_approve is None:
            self.skipTest("write_approve not yet implemented")
        from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry
        from documenter_service.core.policy import Policy
        from documenter_service.adapters.stdout_events import StdoutEventSink

        bp = os.path.join(self.tmpdir, "briefing.md")
        with open(bp, "w") as f:
            f.write("briefing")

        policy_dict = _policy(
            briefing_ref=bp, active_tier=2,
            allowed_operations=[
                {"change_type": "update", "targets": [],
                 "trust_level": "safe"}
            ],
            allow_solo_approval=True,
            min_approval_delay_seconds=0  # no delay, isolate change_type check
        )
        policy = Policy(policy_dict)
        _enable_operator_surface(self.tmpdir)

        registry = JsonlAuditRegistry(self.tmpdir)
        # Bare issue_approval: no extra dict, so no change_type in the record.
        registry.issue_approval(
            approval_id="app-1", target_ids=["alpha"],
            diff_hash="sha256:" + "a" * 64,
            proposer_id="op-bot1", audit_id="aid-1")
        record = registry.find_approval("app-1")
        record["proposer_id"] = "op-bot1"
        registry.append("token_record", record)

        events = StdoutEventSink()
        with self.assertRaises(StructuredError) as ctx:
            write_approve(
                registry, policy, events, root=self.tmpdir,
                approval_id="app-1", operator_id="op-bot1",
                acknowledged="CONFIRMED_SOLE_REVIEWER")
        self.assertEqual(ctx.exception.error_category, "gate_failure")


if __name__ == "__main__":
    unittest.main()
