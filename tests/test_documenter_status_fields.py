"""Tests for status() staged_files and override_counter fields.

mvp-interfaces §3 — registry table fields:
  staged_files — array of {target_id, staged_at} from unresolved intent_records;
  override_counter — count of token_record entries with token_type=override_gate.
"""
import shutil
import tempfile
import time
import unittest

import sys
sys.path.insert(0, '.')

from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry  # noqa: E402
from documenter_service.core import registry as reg  # noqa: E402
from documenter_service.core.status import status as status_core  # noqa: E402


def _tmpdir():
    return tempfile.mkdtemp()


def _registry(tmp, clock=None):
    return JsonlAuditRegistry(tmp, clock=clock)


class TestStatusStagedFiles(unittest.TestCase):

    def setUp(self):
        self.tmp = _tmpdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unresolved_intent_appears_in_staged_files(self):
        """An unresolved intent_record → staged_files contains {target_id, staged_at}."""
        r = _registry(self.tmp)
        now = r.now()
        r.append("intent_record", {
            "target_ids": ["alpha"],
            "staged_at": now,
            "per_file_sha256": {"alpha": "sha256:" + "0" * 64},
            "resolved": False,
        })
        out = status_core(r, None)
        staged = out["registry"]["staged_files"]
        self.assertEqual(len(staged), 1)
        self.assertEqual(staged[0]["target_id"], "alpha")
        self.assertEqual(staged[0]["staged_at"], now)

    def test_resolved_intent_not_in_staged_files(self):
        """A resolved intent_record does NOT appear in staged_files."""
        r = _registry(self.tmp)
        r.append("intent_record", {
            "target_ids": ["alpha"],
            "staged_at": r.now(),
            "per_file_sha256": {"alpha": "sha256:" + "0" * 64},
            "resolved": True,
        })
        out = status_core(r, None)
        self.assertEqual(out["registry"]["staged_files"], [])

    def test_multiple_targets_per_intent(self):
        """An intent with multiple target_ids → multiple staged_files entries."""
        r = _registry(self.tmp)
        now = r.now()
        r.append("intent_record", {
            "target_ids": ["alpha", "beta"],
            "staged_at": now,
            "per_file_sha256": {"alpha": "sha256:" + "0" * 64,
                                "beta": "sha256:" + "1" * 64},
            "resolved": False,
        })
        out = status_core(r, None)
        staged = out["registry"]["staged_files"]
        self.assertEqual(len(staged), 2)
        targets = {s["target_id"] for s in staged}
        self.assertEqual(targets, {"alpha", "beta"})
        for s in staged:
            self.assertEqual(s["staged_at"], now)

    def test_dedup_latest_wins(self):
        """Two unresolved intents for the same target → only the latest remains."""
        r = _registry(self.tmp)
        now1 = "2026-01-01T00:00:00Z"
        now2 = "2026-01-02T00:00:00Z"
        r.append("intent_record", {
            "target_ids": ["alpha"],
            "staged_at": now1,
            "per_file_sha256": {"alpha": "sha256:" + "0" * 64},
            "resolved": False,
        })
        r.append("intent_record", {
            "target_ids": ["alpha"],
            "staged_at": now2,
            "per_file_sha256": {"alpha": "sha256:" + "9" * 64},
            "resolved": False,
        })
        out = status_core(r, None)
        staged = out["registry"]["staged_files"]
        self.assertEqual(len(staged), 1)
        self.assertEqual(staged[0]["staged_at"], now2)


class TestStatusOverrideCounter(unittest.TestCase):

    def setUp(self):
        self.tmp = _tmpdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_override_gate_token_counted(self):
        """token_record with token_type=override_gate increments the counter."""
        r = _registry(self.tmp)
        r.append("token_record", {
            "token_type": "override_gate",
            "token_value": "ov-1",
            "bound_to": {"audit_id": "a1", "target_id": "alpha"},
            "consumed": True,
            "consumed_at": r.now(),
        })
        out = status_core(r, None)
        self.assertEqual(out["registry"]["override_counter"], 1)

    def test_two_override_gate_tokens(self):
        """Two override_gate tokens → override_counter == 2."""
        r = _registry(self.tmp)
        r.append("token_record", {
            "token_type": "override_gate",
            "token_value": "ov-1",
            "bound_to": {"audit_id": "a1", "target_id": "alpha"},
            "consumed": True,
            "consumed_at": r.now(),
        })
        r.append("token_record", {
            "token_type": "override_gate",
            "token_value": "ov-2",
            "bound_to": {"audit_id": "a1", "target_id": "beta"},
            "consumed": True,
            "consumed_at": r.now(),
        })
        out = status_core(r, None)
        self.assertEqual(out["registry"]["override_counter"], 2)

    def test_approval_token_not_counted(self):
        """token_record with token_type=approval_id does NOT increment counter."""
        r = _registry(self.tmp)
        r.append("token_record", {
            "token_type": "approval_id",
            "token_value": "appr-1",
            "bound_to": {"audit_id": "a1", "target_id": "alpha"},
            "consumed": False,
        })
        out = status_core(r, None)
        self.assertEqual(out["registry"]["override_counter"], 0)

    def test_mixed_tokens(self):
        """Mixed tokens: only override_gate counts."""
        r = _registry(self.tmp)
        r.append("token_record", {
            "token_type": "approval_id",
            "token_value": "appr-1",
            "bound_to": {"audit_id": "a1", "target_id": "alpha"},
            "consumed": False,
        })
        r.append("token_record", {
            "token_type": "override_gate",
            "token_value": "ov-1",
            "bound_to": {"audit_id": "a1", "target_id": "alpha"},
            "consumed": True,
            "consumed_at": r.now(),
        })
        r.append("token_record", {
            "token_type": "approval_id",
            "token_value": "appr-2",
            "bound_to": {"audit_id": "a1", "target_id": "beta"},
            "consumed": False,
        })
        out = status_core(r, None)
        self.assertEqual(out["registry"]["override_counter"], 1)


class TestStatusEmptyRegistry(unittest.TestCase):

    def setUp(self):
        self.tmp = _tmpdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_registry_staged_files(self):
        """Empty registry → staged_files == []."""
        r = _registry(self.tmp)
        out = status_core(r, None)
        self.assertEqual(out["registry"]["staged_files"], [])

    def test_empty_registry_override_counter(self):
        """Empty registry → override_counter == 0."""
        r = _registry(self.tmp)
        out = status_core(r, None)
        self.assertEqual(out["registry"]["override_counter"], 0)

    def test_audit_record_no_effect(self):
        """audit_record does not affect staged_files or override_counter."""
        r = _registry(self.tmp)
        r.append("audit_record", {
            "audit_id": "a1",
            "scope": "*",
            "findings": [],
            "scanned_ids": [],
            "has_remaining": False,
            "scan_cursor": None,
            "issued_at": r.now(),
        })
        out = status_core(r, None)
        self.assertEqual(out["registry"]["staged_files"], [])
        self.assertEqual(out["registry"]["override_counter"], 0)


class TestStatusIntegrity(unittest.TestCase):
    """Ensure no fields were added or removed from the response shape."""

    def setUp(self):
        self.tmp = _tmpdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_response_has_required_fields(self):
        """status() returns exactly the §3 table fields."""
        r = _registry(self.tmp)
        out = status_core(r, None)
        top_keys = set(out.keys())
        self.assertIn("active_tier", top_keys)
        self.assertIn("registry", top_keys)
        self.assertIn("scan_status", top_keys)
        self.assertIn("tier_interlock", top_keys)
        reg_keys = set(out["registry"].keys())
        self.assertIn("staged_files", reg_keys)
        self.assertIn("override_counter", reg_keys)
        self.assertIn("status", reg_keys)
        self.assertIn("last_audit", reg_keys)
        # staged_files is a list, override_counter is an int
        self.assertIsInstance(out["registry"]["staged_files"], list)
        self.assertIsInstance(out["registry"]["override_counter"], int)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Pending scan detection (point 23: pending = any unclosed scan)
# ---------------------------------------------------------------------------


class TestStatusPendingUnclosed(unittest.TestCase):
    """status() must report has_pending=True when ANY audit_id has a
    latest record with has_remaining=True, even if a newer audit completed.
    (mvp-interfaces §3, AGENTS §23)"""

    def setUp(self):
        self.tmp = _tmpdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unclosed_scan_shows_pending(self):
        """audit_record#1 has_remaining=True, audit_record#2 has_remaining=False
        → status has_pending=True, pending=record#1."""
        r = _registry(self.tmp)
        now1 = "2026-01-01T00:00:00Z"
        now2 = "2026-01-02T00:00:00Z"
        # Unclosed scan.
        r.append("audit_record", {
            "audit_id": "A",
            "scope": "*",
            "findings": [{"subject_id": "manifest", "severity": "high",
                          "description": "manifest drift",
                          "suggested_action": "regenerate"}],
            "scanned_ids": ["alpha"],
            "has_remaining": True,
            "scan_cursor": "cursor-A",
            "issued_at": now1,
        })
        # New completed scan.
        r.append("audit_record", {
            "audit_id": "B",
            "scope": "*",
            "findings": [],
            "scanned_ids": ["alpha", "beta"],
            "has_remaining": False,
            "scan_cursor": None,
            "issued_at": now2,
        })
        out = status_core(r, None)
        self.assertTrue(out["scan_status"]["has_pending_scan"])
        self.assertEqual(out["scan_status"]["pending_scan_cursor"], "cursor-A")
        # Pending should be record A (the unclosed one).
        self.assertIsNotNone(out["scan_status"]["blocking_operator"])
        self.assertIn("audit_id='A'", out["scan_status"]["blocking_operator"])

    def test_closing_scan_clears_pending(self):
        """After completing an unclosed scan (has_remaining=False) for the same
        audit_id → has_pending=False."""
        r = _registry(self.tmp)
        now1 = "2026-01-01T00:00:00Z"
        now2 = "2026-01-02T00:00:00Z"
        # Unclosed scan.
        r.append("audit_record", {
            "audit_id": "A",
            "scope": "*",
            "findings": [],
            "scanned_ids": ["alpha"],
            "has_remaining": True,
            "scan_cursor": "cursor-A",
            "issued_at": now1,
        })
        # Complete the same audit.
        r.append("audit_record", {
            "audit_id": "A",
            "scope": "*",
            "findings": [],
            "scanned_ids": ["alpha", "beta"],
            "has_remaining": False,
            "scan_cursor": None,
            "issued_at": now2,
        })
        out = status_core(r, None)
        self.assertFalse(out["scan_status"]["has_pending_scan"])
        self.assertIsNone(out["scan_status"]["pending_scan_cursor"])
        self.assertIsNone(out["scan_status"]["blocking_operator"])

    def test_multiple_unclosed_selects_most_recent(self):
        """Two unclosed scans → pending = most recent (by issued_at)."""
        r = _registry(self.tmp)
        r.append("audit_record", {
            "audit_id": "A",
            "scope": "*",
            "findings": [],
            "scanned_ids": ["alpha"],
            "has_remaining": True,
            "scan_cursor": "cursor-A",
            "issued_at": "2026-01-01T00:00:00Z",
        })
        r.append("audit_record", {
            "audit_id": "B",
            "scope": "*",
            "findings": [],
            "scanned_ids": ["alpha", "beta"],
            "has_remaining": True,
            "scan_cursor": "cursor-B",
            "issued_at": "2026-01-02T00:00:00Z",
        })
        out = status_core(r, None)
        self.assertTrue(out["scan_status"]["has_pending_scan"])
        self.assertEqual(out["scan_status"]["pending_scan_cursor"], "cursor-B")
        self.assertIn("audit_id='B'", out["scan_status"]["blocking_operator"])

    def test_no_audit_records_no_pending(self):
        """Empty registry → has_pending=False."""
        r = _registry(self.tmp)
        out = status_core(r, None)
        self.assertFalse(out["scan_status"]["has_pending_scan"])
