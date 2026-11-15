"""Additional tests for the Documenter registry: approval lifecycle, intent
helpers, and metrics (Task W1, Part A).

Appends to existing test_documenter_registry.py — import-compatible with the
original.  Run with: python3 -m unittest tests.test_documenter_registry.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from documenter_service.adapters.jsonl_registry import (  # noqa: E402
    JsonlAuditRegistry, REGISTRY_FILENAME)
from documenter_service.core import registry as reg  # noqa: E402
from documenter_service.core.errors import StructuredError  # noqa: E402


def _tmpdir():
    return tempfile.mkdtemp()


def _registry(tmp, clock=None):
    return JsonlAuditRegistry(os.path.join(tmp, "state"), clock=clock)


def _valid_sha256():
    return "sha256:" + "a" * 64


class TestApprovalLifecycle(unittest.TestCase):
    """Approval token_record lifecycle: issue → find → resolve → chain intact."""

    def setUp(self):
        self.tmp = _tmpdir()
        self.r = _registry(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- issue validation --

    def test_issue_approval_empty_id(self):
        with self.assertRaises(StructuredError) as ctx:
            self.r.issue_approval(
                approval_id="", target_ids=["alpha"],
                diff_hash=_valid_sha256(), proposer_id="agent-1",
                audit_id="aud-1")
        self.assertEqual(ctx.exception.error_category, "unknown")

    def test_issue_approval_non_string_id(self):
        with self.assertRaises(StructuredError) as ctx:
            self.r.issue_approval(
                approval_id=123, target_ids=["alpha"],
                diff_hash=_valid_sha256(), proposer_id="agent-1",
                audit_id="aud-1")
        self.assertEqual(ctx.exception.error_category, "unknown")

    def test_issue_approval_bad_diff_hash(self):
        with self.assertRaises(StructuredError) as ctx:
            self.r.issue_approval(
                approval_id="ap-1", target_ids=["alpha"],
                diff_hash="not-a-hash", proposer_id="agent-1",
                audit_id="aud-1")
        self.assertEqual(ctx.exception.error_category, "unknown")

    def test_issue_approval_missing_prefix(self):
        with self.assertRaises(StructuredError) as ctx:
            self.r.issue_approval(
                approval_id="ap-1", target_ids=["alpha"],
                diff_hash="abcd" * 16,  # 64 hex chars but no prefix
                proposer_id="agent-1", audit_id="aud-1")
        self.assertEqual(ctx.exception.error_category, "unknown")

    def test_issue_approval_uppercase_hex_rejected(self):
        with self.assertRaises(StructuredError) as ctx:
            self.r.issue_approval(
                approval_id="ap-1", target_ids=["alpha"],
                diff_hash="sha256:" + "A" * 64,
                proposer_id="agent-1", audit_id="aud-1")
        self.assertEqual(ctx.exception.error_category, "unknown")

    # -- successful issue --

    def test_issue_approval_returns_data(self):
        data = self.r.issue_approval(
            approval_id="ap-1", target_ids=["alpha"],
            diff_hash=_valid_sha256(), proposer_id="agent-1",
            audit_id="aud-1")
        self.assertEqual(data["token_type"], reg.APPROVAL_ID)
        self.assertEqual(data["token_value"], "ap-1")
        self.assertEqual(data["bound_to"]["audit_id"], "aud-1")
        self.assertEqual(data["bound_to"]["target_id"], "alpha")
        self.assertFalse(data["consumed"])
        self.assertIsNone(data["consumed_at"])
        self.assertEqual(data["diff_hash"], _valid_sha256())
        self.assertEqual(data["proposer_id"], "agent-1")
        self.assertIn("created_at", data)
        self.assertIsNone(data["decision"])
        self.assertIsNone(data["resolved_at"])

    def test_issue_approval_multi_target(self):
        data = self.r.issue_approval(
            approval_id="ap-multi", target_ids=["alpha", "beta"],
            diff_hash=_valid_sha256(), proposer_id="agent-1",
            audit_id="aud-1")
        self.assertEqual(data["target_ids"], ["alpha", "beta"])
        # bound_to target_id is comma-joined for multi
        self.assertEqual(data["bound_to"]["target_id"], "alpha,beta")

    def test_issue_approval_single_target(self):
        data = self.r.issue_approval(
            approval_id="ap-single", target_ids=["alpha"],
            diff_hash=_valid_sha256(), proposer_id="agent-1",
            audit_id="aud-1")
        self.assertEqual(data["bound_to"]["target_id"], "alpha")
        self.assertEqual(data["target_ids"], ["alpha"])

    # -- find --

    def test_find_approval_roundtrip(self):
        self.r.issue_approval(
            approval_id="ap-1", target_ids=["alpha"],
            diff_hash=_valid_sha256(), proposer_id="agent-1",
            audit_id="aud-1")
        found = self.r.find_approval("ap-1")
        self.assertIsNotNone(found)
        self.assertEqual(found["token_value"], "ap-1")
        self.assertEqual(found["token_type"], reg.APPROVAL_ID)
        self.assertEqual(found["diff_hash"], _valid_sha256())
        self.assertEqual(found["proposer_id"], "agent-1")
        self.assertIn("created_at", found)

    def test_find_approval_not_found(self):
        self.assertIsNone(self.r.find_approval("nonexistent"))

    def test_find_approval_latest_of_multiple(self):
        self.r.issue_approval(
            approval_id="ap-1", target_ids=["alpha"],
            diff_hash=_valid_sha256(), proposer_id="agent-1",
            audit_id="aud-1")
        self.r.issue_approval(
            approval_id="ap-2", target_ids=["alpha"],
            diff_hash=_valid_sha256(), proposer_id="agent-2",
            audit_id="aud-1")
        self.assertEqual(self.r.find_approval("ap-1")["proposer_id"], "agent-1")
        self.assertEqual(self.r.find_approval("ap-2")["proposer_id"], "agent-2")

    # -- resolve --

    def test_resolve_approved(self):
        self.r.issue_approval(
            approval_id="ap-1", target_ids=["alpha"],
            diff_hash=_valid_sha256(), proposer_id="agent-1",
            audit_id="aud-1")
        resolved = self.r.resolve_approval(
            "ap-1", decision="approved", operator_id="op-abc123")
        self.assertEqual(resolved["decision"], "approved")
        self.assertEqual(resolved["resolved_by"], "op-abc123")
        self.assertIn("resolved_at", resolved)

    def test_resolve_rejected(self):
        self.r.issue_approval(
            approval_id="ap-1", target_ids=["alpha"],
            diff_hash=_valid_sha256(), proposer_id="agent-1",
            audit_id="aud-1")
        resolved = self.r.resolve_approval(
            "ap-1", decision="rejected", operator_id="op-abc123")
        self.assertEqual(resolved["decision"], "rejected")

    def test_resolve_unknown_approval(self):
        with self.assertRaises(StructuredError) as ctx:
            self.r.resolve_approval(
                "unknown-id", decision="approved", operator_id="op-abc123")
        self.assertEqual(ctx.exception.error_category, "audit_mismatch")

    def test_resolve_already_resolved_replay(self):
        self.r.issue_approval(
            approval_id="ap-1", target_ids=["alpha"],
            diff_hash=_valid_sha256(), proposer_id="agent-1",
            audit_id="aud-1")
        self.r.resolve_approval(
            "ap-1", decision="approved", operator_id="op-abc123")
        with self.assertRaises(StructuredError) as ctx:
            self.r.resolve_approval(
                "ap-1", decision="approved", operator_id="op-abc456")
        self.assertEqual(ctx.exception.error_category, "token_replay")

    def test_resolve_bad_decision(self):
        self.r.issue_approval(
            approval_id="ap-1", target_ids=["alpha"],
            diff_hash=_valid_sha256(), proposer_id="agent-1",
            audit_id="aud-1")
        with self.assertRaises(StructuredError) as ctx:
            self.r.resolve_approval(
                "ap-1", decision="pending", operator_id="op-abc123")
        self.assertEqual(ctx.exception.error_category, "unknown")

    def test_resolve_bad_operator_id(self):
        self.r.issue_approval(
            approval_id="ap-1", target_ids=["alpha"],
            diff_hash=_valid_sha256(), proposer_id="agent-1",
            audit_id="aud-1")
        with self.assertRaises(StructuredError) as ctx:
            self.r.resolve_approval(
                "ap-1", decision="approved", operator_id="not-valid")
        self.assertEqual(ctx.exception.error_category, "unknown")

    # -- created_at present at issue --

    def test_issue_contains_created_at(self):
        data = self.r.issue_approval(
            approval_id="ap-1", target_ids=["alpha"],
            diff_hash=_valid_sha256(), proposer_id=None,
            audit_id=None)
        self.assertIn("created_at", data)
        self.assertTrue(data["created_at"].endswith("Z"))

    # -- approval_is_expired boundaries --

    def test_approval_is_expired_boundaries(self):
        t0 = "2026-11-13T12:00:00Z"
        approval = {"created_at": t0}
        # 29 min 59s → not expired
        now_29m = "2026-11-13T12:29:59Z"
        self.assertFalse(reg.approval_is_expired(approval, now_29m, 30))
        # exactly 30 min → expired (> 30*60 seconds)
        now_30m = "2026-11-13T12:30:00Z"
        self.assertTrue(reg.approval_is_expired(approval, now_30m, 30))
        # 31 min → expired
        now_31m = "2026-11-13T12:31:00Z"
        self.assertTrue(reg.approval_is_expired(approval, now_31m, 30))
        # 1 min → not expired
        now_1m = "2026-11-13T12:01:00Z"
        self.assertFalse(reg.approval_is_expired(approval, now_1m, 30))

    def test_approval_is_expired_no_created_at(self):
        self.assertTrue(reg.approval_is_expired({}, "2026-11-13T12:30:00Z", 30))

    def test_resolve_after_expiry_is_caller_checked(self):
        """The registry resolve method does NOT check expiry.  Test helper only."""
        self.r.issue_approval(
            approval_id="ap-1", target_ids=["alpha"],
            diff_hash=_valid_sha256(), proposer_id="agent-1",
            audit_id="aud-1")
        # Even at arbitrary time, resolve succeeds (expiry checked by caller)
        resolved = self.r.resolve_approval(
            "ap-1", decision="approved", operator_id="op-abc123")
        self.assertEqual(resolved["decision"], "approved")

    # -- pending_approvals / unresolved_intents / metrics --

    def test_pending_approvals(self):
        self.r.issue_approval(
            approval_id="ap-1", target_ids=["alpha"],
            diff_hash=_valid_sha256(), proposer_id="a", audit_id="aud")
        self.r.issue_approval(
            approval_id="ap-2", target_ids=["beta"],
            diff_hash=_valid_sha256(), proposer_id="a", audit_id="aud")
        self.r.resolve_approval(
            "ap-1", decision="approved", operator_id="op-abc")
        # pending_approvals via registry_metrics
        metrics = self.r.registry_metrics()
        self.assertEqual(metrics["pending_approvals"], 1)

    def test_unresolved_intents(self):
        r = self.r
        r.append(reg.INTENT_RECORD, {"target_ids": ["alpha"], "resolved": False})
        r.append(reg.INTENT_RECORD, {"target_ids": ["beta"], "resolved": False})
        r.append(reg.INTENT_RECORD, {"target_ids": ["alpha"], "resolved": True})
        result = r.unresolved_intents()
        # The resolved copy is the latest record for the alpha intent, so the
        # original unresolved record no longer counts (append-only lifecycle).
        self.assertEqual(len(result), 1)
        self.assertIn("beta", result[0]["target_ids"])
        # find_intent() applies the same latest-per-intent rule.
        self.assertIsNone(r.find_intent("alpha"))
        self.assertIsNotNone(r.find_intent("beta"))

    def test_find_intent(self):
        r = self.r
        r.append(reg.INTENT_RECORD, {"target_ids": ["alpha", "beta"], "resolved": False})
        r.append(reg.INTENT_RECORD, {"target_ids": ["alpha"], "resolved": True})
        self.assertIsNotNone(r.find_intent("alpha"))
        self.assertIsNone(r.find_intent("nonexistent"))

    def test_registry_metrics(self):
        self.r.issue_approval(
            approval_id="ap-1", target_ids=["alpha"],
            diff_hash=_valid_sha256(), proposer_id="a", audit_id="aud")
        self.r.issue_approval(
            approval_id="ap-2", target_ids=["beta"],
            diff_hash=_valid_sha256(), proposer_id="a", audit_id="aud")
        self.r.resolve_approval(
            "ap-1", decision="approved", operator_id="op-abc")
        self.r.append(reg.INTENT_RECORD, {"target_ids": ["alpha"], "resolved": False})
        self.r.append(reg.INTENT_RECORD, {"target_ids": ["gamma"], "resolved": True})
        metrics = self.r.registry_metrics()
        self.assertEqual(metrics["pending_approvals"], 1)  # ap-2 still pending
        self.assertEqual(metrics["unresolved_intents"], 1)

    # -- chain integrity after lifecycle --

    def test_chain_healthy_after_approval_lifecycle(self):
        self.r.issue_approval(
            approval_id="ap-1", target_ids=["alpha"],
            diff_hash=_valid_sha256(), proposer_id="a", audit_id="aud")
        self.r.resolve_approval(
            "ap-1", decision="approved", operator_id="op-abc")
        records, status = self.r.read_all()
        self.assertEqual(status, "healthy")
        self.assertEqual(len(records), 2)  # issue + resolve
        self.assertEqual(records[0]["record_type"], reg.TOKEN_RECORD)
        self.assertEqual(records[1]["record_type"], reg.TOKEN_RECORD)
        self.assertEqual(records[1]["data"]["decision"], "approved")


if __name__ == "__main__":
    unittest.main()
