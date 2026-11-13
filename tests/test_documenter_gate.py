"""Tests for the pre-audit gate, trust invariant, and tier interlock.

test_pre_audit_gate (mvp-contract §3.1: rules 1–5 each produce the canonical
error_category), test_tier_interlock (mvp-interfaces §2 preview, §4 enums),
trust classification matrix (index.md §Trust Classification).
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from documenter_service.adapters.worker_stub import InterlockedWorkerStub  # noqa: E402
from documenter_service.core.audit import pre_audit_gate  # noqa: E402
from documenter_service.core.errors import (ERROR_CATEGORIES, NEXT_ACTIONS,  # noqa: E402
                                            StructuredError)
from documenter_service.core.trust import (CHANGE_TYPES, STATIC_FLOORS,  # noqa: E402
                                           TRUST_LEVELS, check_invariant,
                                           derive_trust)

NOW = "2026-11-13T12:00:00Z"
T0 = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)


def _record(**over):
    data = {
        "audit_id": "aud-1",
        "issued_at": "2026-11-13T11:50:00Z",
        "scope": "*",
        "findings": [],
        "scanned_ids": ["alpha"],
        "has_remaining": False,
        "scan_cursor": None,
    }
    data.update(over)
    return data


class TestPreAuditGate(unittest.TestCase):
    """Pure function, no filesystem (mvp-contract §3.1)."""

    def test_all_rules_pass(self):
        self.assertIsNone(pre_audit_gate(_record(), "alpha", NOW, 30))

    def test_rule1_missing_audit_id(self):
        err = pre_audit_gate(None, "alpha", NOW, 30)
        self.assertEqual(err.error_category, "audit_mismatch")
        self.assertEqual(err.next_action, "rerun_audit")

    def test_rule2_stale_audit(self):
        stale = _record(issued_at="2026-11-13T11:00:00Z")  # 60 min old
        err = pre_audit_gate(stale, "alpha", NOW, 30)
        self.assertEqual(err.error_category, "audit_mismatch")
        self.assertIn("audit_freshness", err.message)

    def test_rule2_boundary_exactly_at_window_passes(self):
        edge = _record(issued_at=(T0 - timedelta(minutes=30)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"))
        self.assertIsNone(pre_audit_gate(edge, "alpha", NOW, 30))
        past = _record(issued_at=(T0 - timedelta(minutes=30, seconds=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"))
        self.assertIsNotNone(pre_audit_gate(past, "alpha", NOW, 30))

    def test_rule3_scope_not_covering_target(self):
        err = pre_audit_gate(_record(scope="beta"), "alpha", NOW, 30)
        self.assertEqual(err.error_category, "audit_mismatch")
        # exact-match scope covers; '*' covers anything
        self.assertIsNone(pre_audit_gate(_record(scope="alpha"), "alpha", NOW, 30))
        self.assertIsNone(pre_audit_gate(_record(scope="*"), "anything", NOW, 30))

    def test_rule4_blocking_high_finding(self):
        rec = _record(findings=[{"subject_id": "alpha", "severity": "high",
                                 "description": "d", "suggested_action": "a"}])
        err = pre_audit_gate(rec, "alpha", NOW, 30)
        self.assertEqual(err.error_category, "blocking_finding")
        self.assertEqual(err.next_action, "resolve_finding")

    def test_rule4_critical_blocks_and_medium_does_not(self):
        crit = _record(findings=[{"subject_id": "alpha", "severity": "critical",
                                  "description": "d", "suggested_action": "a"}])
        self.assertEqual(pre_audit_gate(crit, "alpha", NOW, 30).error_category,
                         "blocking_finding")
        med = _record(findings=[{"subject_id": "alpha", "severity": "medium",
                                 "description": "d", "suggested_action": "a"}])
        self.assertIsNone(pre_audit_gate(med, "alpha", NOW, 30))
        # high finding on ANOTHER subject does not block this target
        other = _record(findings=[{"subject_id": "beta", "severity": "high",
                                   "description": "d", "suggested_action": "a"}])
        self.assertIsNone(pre_audit_gate(other, "alpha", NOW, 30))

    def test_rule5_incomplete_scan(self):
        err = pre_audit_gate(_record(has_remaining=True,
                                     scan_cursor="tok"), "alpha", NOW, 30)
        self.assertEqual(err.error_category, "blocking_finding")
        self.assertEqual(err.next_action, "rescan_to_completion")

    def test_freshness_zero_disables_gate(self):
        self.assertIsNone(pre_audit_gate(None, "alpha", NOW, 0))


class TestTrustClassification(unittest.TestCase):
    """requested >= derived over the full change_type × trust_level matrix."""

    def test_static_floor_matrix(self):
        self.assertEqual(derive_trust("update")[0], "safe")
        self.assertIn("static floor", derive_trust("update")[1])
        for ctype in ("split", "create_ru", "custom"):
            self.assertEqual(derive_trust(ctype)[0], "review")

    def test_invariant_matrix(self):
        for ctype in CHANGE_TYPES:
            floor = STATIC_FLOORS[ctype]
            for requested in TRUST_LEVELS:
                if floor == "review" and requested == "safe":
                    with self.assertRaises(StructuredError) as ctx:
                        check_invariant(ctype, requested)
                    self.assertEqual(ctx.exception.error_category,
                                     "trust_mismatch")
                else:
                    derived, _ = check_invariant(ctype, requested)
                    self.assertEqual(derived, floor)

    def test_unknown_enums_are_defects(self):
        with self.assertRaises(StructuredError) as ctx:
            derive_trust("rewrite-everything")
        self.assertEqual(ctx.exception.error_category, "unknown")
        with self.assertRaises(StructuredError) as ctx:
            check_invariant("update", "yolo")
        self.assertEqual(ctx.exception.error_category, "unknown")


class TestTierInterlock(unittest.TestCase):
    def test_worker_stub_any_call(self):
        worker = InterlockedWorkerStub()
        for call in (lambda: worker.execute({}),
                     lambda: worker.execute({"target_ids": ["x"]})):
            with self.assertRaises(StructuredError) as ctx:
                call()
            self.assertEqual(ctx.exception.error_category, "tier_interlock")
            self.assertEqual(ctx.exception.next_action, "preview_denied")

    def test_error_enums_closed(self):
        # Closed enums from mvp-interfaces §4, verbatim.
        self.assertEqual(set(ERROR_CATEGORIES), {
            "audit_mismatch", "blocking_finding", "tier_interlock",
            "approval_expired", "approval_invalidated", "hash_mismatch",
            "trust_mismatch", "token_replay", "lock_conflict", "gate_failure",
            "unknown"})
        self.assertEqual(set(NEXT_ACTIONS), {
            "preview_only", "await_approval", "rerun_audit", "resolve_finding",
            "rescan_to_completion", "preview_denied", "escalate"})

    def test_structured_error_rejects_unknown_category(self):
        with self.assertRaises(ValueError):
            StructuredError("not-a-category", "boom")

    def test_delegate_preview_false_and_absent_denied(self):
        # Same refusal via the composition root for preview=False/None.
        from documenter_service.__main__ import Service
        svc = Service(FIXTURE_CORPUS_FOR_DELEGATE)
        for bad_preview in (False, None):
            with self.assertRaises(StructuredError) as ctx:
                svc.delegate(target_id="alpha", change_type="update",
                             trust_level="review", diff_input="eA==",
                             preview=bad_preview)
            self.assertEqual(ctx.exception.error_category, "tier_interlock")
            self.assertEqual(ctx.exception.next_action, "preview_denied")

    def test_reserved_intent_record_never_written(self):
        from documenter_service import ports
        from documenter_service.core import registry as reg
        self.assertEqual(ports.INTENT_RECORD_TYPE, "intent_record")
        self.assertIn(reg.INTENT_RECORD, reg.RECORD_TYPES)  # readable ...
        # ... but no MVP source file ever APPENDS it (schema reserved only).
        pkg = os.path.join(REPO_ROOT, "documenter_service")
        for dirpath, _dirs, files in os.walk(pkg):
            for name in files:
                if name.endswith(".py"):
                    with open(os.path.join(dirpath, name),
                              encoding="utf-8") as fh:
                        src = fh.read()
                    self.assertNotIn(
                        'append(reg.INTENT_RECORD', src,
                        f"intent_record append found in {name}")


FIXTURE_CORPUS_FOR_DELEGATE = os.path.join(
    REPO_ROOT, "tests", "fixtures", "documenter", "corpus")


if __name__ == "__main__":
    unittest.main()
