"""Tests for Tier 3 pattern auto-apply (mvp-contract §4 row 4).

Covers:
  - pattern_metric: promotion metric over viewed diffs
  - record_viewed: append-only mark-as-viewed
  - check_quarantine: first-N quarantine gate
  - apply_pattern_batch: batch-level and per-item guards
  - Service-level: Service.pattern_auto_apply, Service.record_approval_viewed

Uses same tmp corpus + in-memory manifest + Policy objects as
tests/test_documenter_write.py; registry via JsonlAuditRegistry(tmpdir);
events via StdoutEventSink(io.StringIO()).
"""
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from documenter_service.adapters.diff_engine import StdDiffEngine  # noqa: E402
from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry  # noqa: E402
from documenter_service.adapters.stdout_events import StdoutEventSink  # noqa: E402
from documenter_service.core.errors import StructuredError  # noqa: E402
from documenter_service.core import registry as reg  # noqa: E402
from documenter_service.core.patterns import (  # noqa: E402
    pattern_metric,
    record_viewed,
    check_quarantine,
    apply_pattern_batch,
)
from documenter_service.core.policy import Policy  # noqa: E402
from documenter_service.__main__ import Service  # noqa: E402


# ---------------------------------------------------------------------------
# Helper factories (mirrors test_documenter_write.py patterns)
# ---------------------------------------------------------------------------


def _enable_operator_surface(root):
    """Create the ADR-013 Operator Surface readiness sentinel under root.

    Tier 2+ test corpora must opt into surface-readiness explicitly:
    check_tier2_authorized refuses (tier_interlock) while the sentinel is
    absent. Tests asserting the second interlock level omit this call.
    """
    sentinel = os.path.join(root, "documenter", ".operator_surface_ready")
    os.makedirs(os.path.dirname(sentinel), exist_ok=True)
    with open(sentinel, "w") as f:
        f.write("")
    return sentinel


def _init_git_repo(root: str) -> None:
    """Initialise ``root`` as a git repo (quietly).

    Called by tests that exercise the apply_write path so that the
    pre-change git snapshot guard passes.
    """
    subprocess.run(
        ["git", "init", "-q", root],
        capture_output=True, text=True, timeout=10, shell=False,
    )
    subprocess.run(
        ["git", "-C", root, "config", "user.email", "test@council.local"],
        capture_output=True, text=True, timeout=10, shell=False,
    )
    subprocess.run(
        ["git", "-C", root, "config", "user.name", "Test"],
        capture_output=True, text=True, timeout=10, shell=False,
    )
    subprocess.run(
        ["git", "-C", root, "add", "-A"],
        capture_output=True, text=True, timeout=10, shell=False,
    )
    subprocess.run(
        ["git", "-C", root, "commit", "-q", "-m", "fixture baseline"],
        capture_output=True, text=True, timeout=10, shell=False,
    )


def _make_tier3_policy(briefing_path=None, allowed_ops=None):
    """Create a Tier-3 Policy with a valid briefing_ref and pattern entry."""
    ops = allowed_ops or [
        {
            "type": "pattern",
            "pattern_id": "auto-bump-version",
            "pattern_description": "Auto-bump version metadata",
            "match_criteria": {
                "change_type": "update",
                "file_pattern": "CHANGELOGS/*.changes.md",
            },
            "trust_level": "safe",
        },
    ]
    fields = {
        "version": "0.2.0",
        "active_tier": 3,
        "allowed_operations": ops,
        "briefing_ref": briefing_path or "_briefing.md",
        "audit_freshness": 30,
        "approval_expiry_window": 30,
        "max_diff_bytes": 524288,
        "lock_wait_timeout": 30,
    }
    return Policy(fields)


def _make_manifest(doc_ids=None):
    """Create an in-memory manifest from corpus entries."""
    if doc_ids is None:
        doc_ids = ["alpha", "beta", "gamma"]
    entries_list = []
    manifest = type("Manifest", (), {
        "_entries": {},
        "entries": lambda self: entries_list,
        "resolve": lambda self, tid: self._entries.get(tid),
    })()
    for eid in doc_ids:
        entry = {
            "id": eid,
            "path": "docs/en/" + eid + "/index.md",
            "title": eid.title() + " Document",
            "version": "1.0.0",
            "status": "active",
        }
        entries_list.append(entry)
        manifest._entries[eid] = entry
    return manifest


def _make_registry(tmpdir):
    return JsonlAuditRegistry(tmpdir)


def _make_briefing(tmpdir):
    """Create a briefing file at the expected path."""
    path = os.path.join(tmpdir, "_briefing.md")
    with open(path, "w") as f:
        f.write("# Briefing\n\nAuthorised operational context.\n")
    return path


def _make_tier1_policy():
    """Create a Tier-1 Policy (no write intent)."""
    return Policy({
        "version": "0.2.0",
        "active_tier": 1,
        "allowed_operations": [],
        "audit_freshness": 30,
        "approval_expiry_window": 30,
        "max_diff_bytes": 524288,
    })


def _make_simple_diff(doc_text):
    """Create a diff that bumps the Version line by one."""
    old_lines = doc_text.split("\n")
    # Count of original lines (exclude trailing empty from count)
    effective_orig = list(old_lines)
    if effective_orig and effective_orig[-1] == "":
        effective_orig = effective_orig[:-1]
    hunk_header = "@@ -1," + str(len(effective_orig)) + " +1," + str(len(effective_orig)) + " @@\n"
    diff_entries = []
    for line in old_lines:
        if line.startswith("Version: "):
            parts = line.split(": ", 1)[1].split(".")
            parts[-1] = str(int(parts[-1]) + 1)
            diff_entries.append("-" + line)
            diff_entries.append("+Version: " + ".".join(parts))
        else:
            diff_entries.append(" " + line)
    return "--- a/index.md\n+++ b/index.md\n" + hunk_header + "\n".join(diff_entries) + "\n"


def _encode_diff(diff_text):
    return base64.b64encode(diff_text.encode("utf-8")).decode("ascii")


class TestPatternMetric(unittest.TestCase):
    """Tests for pattern_metric — promotion metric over viewed diffs."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.registry = _make_registry(self.tmpdir)
        self.pattern_id = "auto-bump-version"
        self.now = "2026-01-15T12:00:00Z"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _make_approval(self, approval_id, created_at, decision, viewed=False,
                       pattern_id=None):
        """Helper to create an approval token_record."""
        data = {
            "token_type": reg.APPROVAL_ID,
            "token_value": approval_id,
            "bound_to": {"audit_id": "aid-1", "target_id": "alpha"},
            "consumed": False,
            "consumed_at": None,
            "target_ids": ["alpha"],
            "diff_hash": "sha256:" + "a" * 63 + "0",
            "proposer_id": "op-user1",
            "created_at": created_at,
            "decision": decision,  # None = pending, "approved", "rejected"
            "resolved_at": self.now if decision else None,
            "resolved_by": "op-user2" if decision else None,
        }
        if pattern_id is not None:
            data["pattern_id"] = pattern_id
        if viewed:
            data["viewed"] = True
        self.registry.append(reg.TOKEN_RECORD, data)
        return data

    def test_empty_returns_zeros(self):
        result = pattern_metric(
            self.registry, pattern_id=self.pattern_id, now_iso=self.now)
        self.assertEqual(result["viewed"], 0)
        self.assertEqual(result["approved"], 0)
        self.assertEqual(result["rejected"], 0)
        self.assertEqual(result["approval_rate"], 0.0)
        self.assertFalse(result["promotable"])

    def test_approval_rate_counts_only_viewed(self):
        # Seed: 1 viewed approved, 1 unviewed approved, 1 viewed rejected
        self._make_approval("app-1", self.now, "approved", viewed=True,
                            pattern_id=self.pattern_id)
        self._make_approval("app-2", self.now, "approved", viewed=False,
                            pattern_id=self.pattern_id)
        self._make_approval("app-3", self.now, "rejected", viewed=True,
                            pattern_id=self.pattern_id)

        result = pattern_metric(
            self.registry, pattern_id=self.pattern_id, now_iso=self.now)
        self.assertEqual(result["viewed"], 2)  # only viewed
        self.assertEqual(result["approved"], 1)
        self.assertEqual(result["rejected"], 1)
        self.assertEqual(result["approval_rate"], 0.5)
        self.assertFalse(result["promotable"])

    def test_promotable_at_90_exact(self):
        # 9 viewed approved, 1 viewed rejected → 0.9 → promotable
        for i in range(9):
            self._make_approval(
                f"app-{i}", self.now, "approved", viewed=True,
                pattern_id=self.pattern_id)
        self._make_approval("app-9", self.now, "rejected", viewed=True,
                            pattern_id=self.pattern_id)
        result = pattern_metric(
            self.registry, pattern_id=self.pattern_id, now_iso=self.now)
        self.assertEqual(result["approved"], 9)
        self.assertEqual(result["rejected"], 1)
        self.assertEqual(result["approval_rate"], 0.9)
        self.assertTrue(result["promotable"])

    def test_not_promotable_at_89(self):
        # 8 approved, 1 rejected → 0.8 → not promotable
        for i in range(8):
            self._make_approval(
                f"app-{i}", self.now, "approved", viewed=True,
                pattern_id=self.pattern_id)
        self._make_approval("app-8", self.now, "rejected", viewed=True,
                            pattern_id=self.pattern_id)
        result = pattern_metric(
            self.registry, pattern_id=self.pattern_id, now_iso=self.now)
        self.assertGreater(result["approval_rate"], 0.8)
        self.assertLess(result["approval_rate"], 0.9)
        self.assertFalse(result["promotable"])

    def test_different_pattern_id_excluded(self):
        self._make_approval("app-1", self.now, "approved", viewed=True,
                            pattern_id="other-pattern")
        self._make_approval("app-2", self.now, "approved", viewed=True,
                            pattern_id=self.pattern_id)
        result = pattern_metric(
            self.registry, pattern_id=self.pattern_id, now_iso=self.now)
        self.assertEqual(result["approved"], 1)
        self.assertEqual(result["viewed"], 1)

    def test_pending_not_counted(self):
        self._make_approval("app-1", self.now, None, viewed=True,
                            pattern_id=self.pattern_id)
        result = pattern_metric(
            self.registry, pattern_id=self.pattern_id, now_iso=self.now)
        self.assertEqual(result["approved"], 0)
        self.assertEqual(result["rejected"], 0)

    def test_window_excludes_old_records(self):
        # 14 days = 20160 min; record older than that is excluded
        old_time = "2025-12-30T12:00:00Z"  # 16 days ago
        self._make_approval("app-old", old_time, "approved", viewed=True,
                            pattern_id=self.pattern_id)
        self._make_approval("app-new", self.now, "approved", viewed=True,
                            pattern_id=self.pattern_id)
        result = pattern_metric(
            self.registry, pattern_id=self.pattern_id, now_iso=self.now)
        self.assertEqual(result["viewed"], 1)
        self.assertEqual(result["approved"], 1)

    def test_window_boundary_20160_min_exact(self):
        # Record exactly at the window boundary (20160 min ago) is INCLUDED
        # because the comparison is "created_dt < cutoff"
        cutoff = datetime.fromisoformat(
            self.now.replace("Z", "+00:00")) - timedelta(minutes=20160)
        boundary_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        self._make_approval("app-boundary", boundary_iso, "approved",
                            viewed=True, pattern_id=self.pattern_id)
        result = pattern_metric(
            self.registry, pattern_id=self.pattern_id, now_iso=self.now)
        self.assertEqual(result["viewed"], 1)
        self.assertTrue(result["promotable"])

    def test_window_boundary_20159_min_included(self):
        cutoff = datetime.fromisoformat(
            self.now.replace("Z", "+00:00")) - timedelta(minutes=20159)
        boundary_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        self._make_approval("app-recent", boundary_iso, "approved",
                            viewed=True, pattern_id=self.pattern_id)
        result = pattern_metric(
            self.registry, pattern_id=self.pattern_id, now_iso=self.now)
        self.assertEqual(result["viewed"], 1)
        self.assertTrue(result["promotable"])

    def test_non_approval_records_excluded(self):
        self.registry.append(reg.AUDIT_RECORD, {"audit_id": "aid-1"})
        result = pattern_metric(
            self.registry, pattern_id=self.pattern_id, now_iso=self.now)
        self.assertEqual(result["viewed"], 0)


class TestRecordViewed(unittest.TestCase):
    """Tests for record_viewed — append-only mark-as-viewed."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.registry = _make_registry(self.tmpdir)
        self.approval_id = "app-view-1"
        self.registry.issue_approval(
            approval_id=self.approval_id,
            target_ids=["alpha"],
            diff_hash="sha256:" + "a" * 64,
            proposer_id="op-user1",
            audit_id="aid-1",
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_appends_copy_with_viewed_true(self):
        # Before: viewed key absent
        before = self.registry.find_approval(self.approval_id)
        self.assertNotIn("viewed", before)

        result = record_viewed(self.registry, approval_id=self.approval_id)
        self.assertTrue(result.get("viewed"))

        # After: still has the original (approval not modified)
        after = self.registry.find_approval(self.approval_id)
        self.assertTrue(after.get("viewed"))

    def test_uses_latest_record(self):
        # Record viewed once, then resolve
        record_viewed(self.registry, approval_id=self.approval_id)
        self.registry.resolve_approval(
            self.approval_id, decision="approved", operator_id="op-user2")
        latest = self.registry.find_approval(self.approval_id)
        self.assertTrue(latest.get("viewed"))

    def test_unknown_approval_id_raises(self):
        from documenter_service.core.errors import StructuredError
        with self.assertRaises(StructuredError) as ctx:
            record_viewed(self.registry, approval_id="nonexistent")
        self.assertEqual(ctx.exception.error_category, "audit_mismatch")


class TestCheckQuarantine(unittest.TestCase):
    """Tests for check_quarantine — first-N quarantine gate."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.registry = _make_registry(self.tmpdir)
        self.pattern_id = "auto-bump-version"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_quarantine_when_count_below_n(self):
        result = check_quarantine(self.registry, self.pattern_id, quarantine_n=3)
        self.assertTrue(result)  # 0 < 3 → in quarantine

    def test_quarantine_exits_when_count_reaches_n(self):
        from documenter_service.core.registry import TOKEN_RECORD
        for i in range(3):
            self.registry.append(TOKEN_RECORD, {
                "token_type": "pattern_usage",
                "token_value": f"target-{i}",
                "bound_to": {"audit_id": None, "target_id": f"target-{i}"},
                "pattern_id": self.pattern_id,
                "applied_at": "2026-01-15T12:00:00Z",
                "approved_by": None,
                "auto": True,
            })
        result = check_quarantine(self.registry, self.pattern_id, quarantine_n=3)
        self.assertFalse(result)  # 3 >= 3 → out of quarantine

    def test_quarantine_different_pattern_ignored(self):
        from documenter_service.core.registry import TOKEN_RECORD
        self.registry.append(TOKEN_RECORD, {
            "token_type": "pattern_usage",
            "token_value": "t1",
            "bound_to": {"audit_id": None, "target_id": "t1"},
            "pattern_id": "other-pattern",
            "applied_at": "2026-01-15T12:00:00Z",
            "approved_by": None,
        })
        result = check_quarantine(self.registry, self.pattern_id, quarantine_n=3)
        self.assertTrue(result)  # 0 for our pattern


if __name__ == "__main__":
    unittest.main()


class TestApplyPatternBatch(unittest.TestCase):
    """Tests for apply_pattern_batch — batch-level and per-item guards."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.corpus = os.path.join(self.tmpdir, "corpus")
        os.makedirs(os.path.join(self.corpus, "docs", "en", "alpha"))
        _enable_operator_surface(self.corpus)
        os.makedirs(os.path.join(self.corpus, "docs", "en", "beta"))
        self.alpha_path = os.path.join(
            self.corpus, "docs", "en", "alpha", "index.md")
        self.beta_path = os.path.join(
            self.corpus, "docs", "en", "beta", "index.md")
        self.doc_template = (
            "# {name}\nid: {id}\nVersion: 1.0.0\nStatus: active\n"
            "changelog-path: CHANGELOGS/{id}.changes.md\n"
        )
        with open(self.alpha_path, "w") as f:
            f.write(self.doc_template.format(name="Alpha", id="alpha"))
        with open(self.beta_path, "w") as f:
            f.write(self.doc_template.format(name="Beta", id="beta"))

        _init_git_repo(self.corpus)

        self.briefing_path = _make_briefing(self.tmpdir)

        self.manifest = _make_manifest()
        self.registry = _make_registry(self.tmpdir)
        self.events = StdoutEventSink()
        self.engine = StdDiffEngine()
        self.pattern_id = "auto-bump-version"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _make_tier3_policy_with_path(self, allowed_ops=None):
        ops = allowed_ops or [
            {
                "type": "pattern",
                "pattern_id": self.pattern_id,
                "pattern_description": "Auto-bump version metadata",
                "match_criteria": {
                    "change_type": "update",
                    "file_pattern": "docs/en/*/index.md",
                },
                "trust_level": "safe",
            },
        ]
        return Policy({
            "version": "0.2.0",
            "active_tier": 3,
            "allowed_operations": ops,
            "briefing_ref": self.briefing_path,
            "audit_freshness": 30,
            "approval_expiry_window": 30,
            "max_diff_bytes": 524288,
            "lock_wait_timeout": 30,
        })

    def _make_proposals(self, doc_path, diff_text, target_id, audit_id="aid-1"):
        """Create proposal items from a diff."""
        encoded = _encode_diff(diff_text)
        return [{
            "target_id": target_id,
            "change_type": "update",
            "trust_level": "safe",
            "diff_input": encoded,
            "audit_id": audit_id,
        }]

    def test_tier_gate_tier2_policy(self):
        """tier 2 policy + pattern entry → tier_interlock."""
        policy = self._make_tier3_policy_with_path()
        policy._fields["active_tier"] = 2  # downgrade to tier 2
        alpha_diff = _make_simple_diff(
            self.doc_template.format(name="Alpha", id="alpha"))
        proposals = self._make_proposals(self.alpha_path, alpha_diff, "alpha")
        with self.assertRaises(StructuredError) as ctx:
            apply_pattern_batch(
                self.corpus, self.manifest, self.registry, policy,
                self.events, self.engine,
                pattern_id=self.pattern_id,
                proposals=proposals,
                operator_id="op-user1",
            )
        self.assertEqual(ctx.exception.error_category, "tier_interlock")

    def test_tier_gate_tier3_no_briefing_file(self):
        """tier 3 policy with missing briefing file → tier_interlock."""
        policy = self._make_tier3_policy_with_path()
        policy._fields["briefing_ref"] = "nonexistent_briefing.md"
        alpha_diff = _make_simple_diff(
            self.doc_template.format(name="Alpha", id="alpha"))
        proposals = self._make_proposals(self.alpha_path, alpha_diff, "alpha")
        with self.assertRaises(StructuredError) as ctx:
            apply_pattern_batch(
                self.corpus, self.manifest, self.registry, policy,
                self.events, self.engine,
                pattern_id=self.pattern_id,
                proposals=proposals,
                operator_id="op-user1",
            )
        self.assertEqual(ctx.exception.error_category, "tier_interlock")

    def test_pattern_missing_from_policy(self):
        """pattern missing from policy → gate_failure."""
        policy = self._make_tier3_policy_with_path()
        policy._fields["allowed_operations"] = []  # no pattern entries
        alpha_diff = _make_simple_diff(
            self.doc_template.format(name="Alpha", id="alpha"))
        proposals = self._make_proposals(self.alpha_path, alpha_diff, "alpha")
        with self.assertRaises(StructuredError) as ctx:
            apply_pattern_batch(
                self.corpus, self.manifest, self.registry, policy,
                self.events, self.engine,
                pattern_id=self.pattern_id,
                proposals=proposals,
                operator_id="op-user1",
            )
        self.assertEqual(ctx.exception.error_category, "gate_failure")
        self.assertIn("not authorized by policy", ctx.exception.message)

    def test_application_limit_reached(self):
        """application_limit reached → gate_failure (seed N pattern_usage records)."""
        policy = Policy({
            "version": "0.2.0",
            "active_tier": 3,
            "allowed_operations": [
                {
                    "type": "pattern",
                    "pattern_id": self.pattern_id,
                    "pattern_description": "Auto-bump version metadata",
                    "match_criteria": {
                        "change_type": "update",
                        "file_pattern": "docs/en/*/index.md",
                    },
                    "trust_level": "safe",
                    "application_limit": 2,
                },
            ],
            "briefing_ref": self.briefing_path,
            "audit_freshness": 30,
            "approval_expiry_window": 30,
            "max_diff_bytes": 524288,
            "lock_wait_timeout": 30,
        })
        # Seed 2 pattern_usage records (already at limit)
        from documenter_service.core.registry import TOKEN_RECORD
        for i in range(2):
            self.registry.append(TOKEN_RECORD, {
                "token_type": "pattern_usage",
                "token_value": f"target-{i}",
                "bound_to": {"audit_id": None, "target_id": f"target-{i}"},
                "pattern_id": self.pattern_id,
                "applied_at": "2026-01-15T12:00:00Z",
                "approved_by": None,
                "auto": True,
            })
        proposals = self._make_proposals(
            self.alpha_path,
            _make_simple_diff(self.doc_template.format(name="Alpha", id="alpha")),
            "alpha",
        )
        with self.assertRaises(StructuredError) as ctx:
            apply_pattern_batch(
                self.corpus, self.manifest, self.registry, policy,
                self.events, self.engine,
                pattern_id=self.pattern_id,
                proposals=proposals,
                operator_id="op-user1",
            )
        self.assertEqual(ctx.exception.error_category, "gate_failure")
        self.assertIn("application limit reached", ctx.exception.message)

    def test_expires_at_past(self):
        """expires_at in the past → gate_failure."""
        policy = Policy({
            "version": "0.2.0",
            "active_tier": 3,
            "allowed_operations": [
                {
                    "type": "pattern",
                    "pattern_id": self.pattern_id,
                    "pattern_description": "Auto-bump version metadata",
                    "match_criteria": {
                        "change_type": "update",
                        "file_pattern": "docs/en/*/index.md",
                    },
                    "trust_level": "safe",
                    "expires_at": "2020-01-01T00:00:00Z",
                },
            ],
            "briefing_ref": self.briefing_path,
            "audit_freshness": 30,
            "approval_expiry_window": 30,
            "max_diff_bytes": 524288,
            "lock_wait_timeout": 30,
        })
        proposals = self._make_proposals(
            self.alpha_path,
            _make_simple_diff(self.doc_template.format(name="Alpha", id="alpha")),
            "alpha",
        )
        with self.assertRaises(StructuredError) as ctx:
            apply_pattern_batch(
                self.corpus, self.manifest, self.registry, policy,
                self.events, self.engine,
                pattern_id=self.pattern_id,
                proposals=proposals,
                operator_id="op-user1",
            )
        self.assertEqual(ctx.exception.error_category, "gate_failure")
        self.assertIn("expired", ctx.exception.message)

    def test_invalid_canonical_diff_template_regex(self):
        """invalid canonical_diff_template regex → unknown."""
        policy = Policy({
            "version": "0.2.0",
            "active_tier": 3,
            "allowed_operations": [
                {
                    "type": "pattern",
                    "pattern_id": self.pattern_id,
                    "pattern_description": "Auto-bump version metadata",
                    "match_criteria": {
                        "change_type": "update",
                        "file_pattern": "docs/en/*/index.md",
                    },
                    "trust_level": "safe",
                    "canonical_diff_template": {
                        "changed_line_regex": "[invalid(regex",
                        "expected_hunk_count": 1,
                    },
                },
            ],
            "briefing_ref": self.briefing_path,
            "audit_freshness": 30,
            "approval_expiry_window": 30,
            "max_diff_bytes": 524288,
            "lock_wait_timeout": 30,
        })
        proposals = self._make_proposals(
            self.alpha_path,
            _make_simple_diff(self.doc_template.format(name="Alpha", id="alpha")),
            "alpha",
        )
        with self.assertRaises(StructuredError) as ctx:
            apply_pattern_batch(
                self.corpus, self.manifest, self.registry, policy,
                self.events, self.engine,
                pattern_id=self.pattern_id,
                proposals=proposals,
                operator_id="op-user1",
            )
        self.assertEqual(ctx.exception.error_category, "unknown")

    def test_happy_path_tier3_two_items_applied(self):
        """2 items applied, digest applied_count==2, pattern_usage records appended."""
        # Pre-seed 3 pattern_usage records so quarantine is exited (quarantine_n=3).
        from documenter_service.core.registry import TOKEN_RECORD
        for i in range(3):
            self.registry.append(TOKEN_RECORD, {
                "token_type": "pattern_usage",
                "token_value": f"pre-seed-{i}",
                "bound_to": {"audit_id": None, "target_id": f"pre-seed-{i}"},
                "pattern_id": self.pattern_id,
                "applied_at": "2026-01-15T12:00:00Z",
                "approved_by": None,
                "auto": True,
            })

        # Build diffs that bump version numbers
        alpha_diff = _make_simple_diff(
            self.doc_template.format(name="Alpha", id="alpha"))
        beta_diff = _make_simple_diff(
            self.doc_template.format(name="Beta", id="beta"))

        # The file_pattern "docs/en/*/index.md" covers both targets
        policy = self._make_tier3_policy_with_path()

        proposals = self._make_proposals(self.alpha_path, alpha_diff, "alpha") + \
            self._make_proposals(self.beta_path, beta_diff, "beta")

        result = apply_pattern_batch(
            self.corpus, self.manifest, self.registry, policy,
            self.events, self.engine,
            pattern_id=self.pattern_id,
            proposals=proposals,
            operator_id="op-user1",
        )

        self.assertEqual(result["applied_count"], 2)
        self.assertEqual(len(result["results"]), 2)
        self.assertFalse(result["quarantine_active"])
        self.assertEqual(result["next_action"], "write_applied")

        # Check files changed on disk
        with open(self.alpha_path) as f:
            alpha_content = f.read()
        self.assertIn("Version: 1.0.1", alpha_content)
        self.assertNotIn("Version: 1.0.0\n", alpha_content)

        with open(self.beta_path) as f:
            beta_content = f.read()
        self.assertIn("Version: 1.0.1", beta_content)

        # Check pattern_usage records appended (3 pre-seeded + 2 applied = 5).
        records, _ = self.registry.read_all()
        usage_records = [
            r for r in records
            if r["record_type"] == reg.TOKEN_RECORD
            and r["data"].get("token_type") == "pattern_usage"
            and r["data"].get("pattern_id") == self.pattern_id
        ]
        self.assertEqual(len(usage_records), 5)
        # Newly applied items: approved_by=operator_id, auto=False.
        applied_records = [
            ur for ur in usage_records
            if not ur["data"]["token_value"].startswith("pre-seed-")
        ]
        self.assertEqual(len(applied_records), 2)
        for ur in applied_records:
            self.assertEqual(ur["data"].get("approved_by"), "op-user1")
            self.assertFalse(ur["data"].get("auto"))
        # Pre-seeded items: approved_by=None, auto=True.
        pre_records = [
            ur for ur in usage_records
            if ur["data"]["token_value"].startswith("pre-seed-")
        ]
        self.assertEqual(len(pre_records), 3)
        for ur in pre_records:
            self.assertIsNone(ur["data"].get("approved_by"))
            self.assertTrue(ur["data"].get("auto"))

    def test_quarantine_first_n_require_approval(self):
        """Pre-seed 3 pattern_usage → quarantine exits immediately.
        Subsequent items apply directly (auto: True).
        """
        policy = Policy({
            "version": "0.2.0",
            "active_tier": 3,
            "allowed_operations": [
                {
                    "type": "pattern",
                    "pattern_id": self.pattern_id,
                    "pattern_description": "Auto-bump version metadata",
                    "match_criteria": {
                        "change_type": "update",
                        "file_pattern": "docs/en/*/index.md",
                    },
                    "trust_level": "safe",
                },
            ],
            "briefing_ref": self.briefing_path,
            "audit_freshness": 30,
            "approval_expiry_window": 30,
            "max_diff_bytes": 524288,
            "lock_wait_timeout": 30,
        })

        # Pre-seed 3 pattern_usage records so quarantine exits immediately
        # (count 3 >= quarantine_n 3).
        from documenter_service.core.registry import TOKEN_RECORD
        for i in range(3):
            self.registry.append(TOKEN_RECORD, {
                "token_type": "pattern_usage",
                "token_value": f"pre-seed-{i}",
                "bound_to": {"audit_id": None, "target_id": f"pre-seed-{i}"},
                "pattern_id": self.pattern_id,
                "applied_at": "2026-01-15T12:00:00Z",
                "approved_by": None,
                "auto": True,
            })

        # Helper that creates a diff based on CURRENT file content.
        def make_versioned_proposal():
            """Read current file, bump version, create proposal."""
            with open(self.alpha_path) as f:
                current = f.read()
            diff_text = _make_simple_diff(current)
            encoded = _encode_diff(diff_text)
            return [{"target_id": "alpha", "change_type": "update",
                     "trust_level": "safe", "diff_input": encoded,
                     "audit_id": "aid-1"}]

        # Item 1: quarantine already exited → auto-apply.
        proposals = make_versioned_proposal()
        result = apply_pattern_batch(
            self.corpus, self.manifest, self.registry, policy,
            self.events, self.engine,
            pattern_id=self.pattern_id,
            proposals=proposals,
            operator_id="op-user1",
        )
        self.assertEqual(result["results"][0]["status"], "applied")
        self.assertEqual(result["applied_count"], 1)
        self.assertFalse(result["quarantine_active"])

        # Verify file changed.
        with open(self.alpha_path) as f:
            self.assertIn("Version: 1.0.1", f.read())

        # Item 2: still out of quarantine → apply.
        proposals = make_versioned_proposal()
        result = apply_pattern_batch(
            self.corpus, self.manifest, self.registry, policy,
            self.events, self.engine,
            pattern_id=self.pattern_id,
            proposals=proposals,
            operator_id="op-user1",
        )
        self.assertEqual(result["results"][0]["status"], "applied")
        self.assertFalse(result["quarantine_active"])

        # Item 3: still out of quarantine → apply.
        proposals = make_versioned_proposal()
        result = apply_pattern_batch(
            self.corpus, self.manifest, self.registry, policy,
            self.events, self.engine,
            pattern_id=self.pattern_id,
            proposals=proposals,
            operator_id="op-user1",
        )
        self.assertEqual(result["results"][0]["status"], "applied")

        # Verify we now have 6 pattern_usage records (pre-seed 3 + 3 applied).
        self.assertFalse(
            check_quarantine(self.registry, self.pattern_id, quarantine_n=3))

        # Item 4: still out of quarantine → apply.
        proposals = make_versioned_proposal()
        result = apply_pattern_batch(
            self.corpus, self.manifest, self.registry, policy,
            self.events, self.engine,
            pattern_id=self.pattern_id,
            proposals=proposals,
            operator_id="op-user1",
        )
        self.assertFalse(result["quarantine_active"])

    def test_per_item_failure_second_item(self):
        """bad diff_input on second item → status failed, unknown; first still applied."""
        # Pre-seed 3 pattern_usage records so quarantine is already exited.
        from documenter_service.core.registry import TOKEN_RECORD
        for i in range(3):
            self.registry.append(TOKEN_RECORD, {
                "token_type": "pattern_usage",
                "token_value": f"pre-seed-{i}",
                "bound_to": {"audit_id": None, "target_id": f"pre-seed-{i}"},
                "pattern_id": self.pattern_id,
                "applied_at": "2026-01-15T12:00:00Z",
                "approved_by": None,
                "auto": True,
            })

        policy = self._make_tier3_policy_with_path()

        alpha_diff = _make_simple_diff(
            self.doc_template.format(name="Alpha", id="alpha"))
        beta_diff = _make_simple_diff(
            self.doc_template.format(name="Beta", id="beta"))

        # Corrupt the second diff
        proposals = self._make_proposals(self.alpha_path, alpha_diff, "alpha")
        proposals.append({
            "target_id": "beta",
            "change_type": "update",
            "trust_level": "safe",
            "diff_input": "!!NOT_BASE64!!",
            "audit_id": "aid-1",
        })

        result = apply_pattern_batch(
            self.corpus, self.manifest, self.registry, policy,
            self.events, self.engine,
            pattern_id=self.pattern_id,
            proposals=proposals,
            operator_id="op-user1",
        )

        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(result["results"][0]["status"], "applied")
        self.assertEqual(result["results"][1]["status"], "failed")

    def test_batch_limit_guards_all_items(self):
        """batch-level guard aborts ALL (limit reached even if items fine)."""
        policy = Policy({
            "version": "0.2.0",
            "active_tier": 3,
            "allowed_operations": [
                {
                    "type": "pattern",
                    "pattern_id": self.pattern_id,
                    "pattern_description": "Auto-bump version metadata",
                    "match_criteria": {
                        "change_type": "update",
                        "file_pattern": "docs/en/*/index.md",
                    },
                    "trust_level": "safe",
                    "application_limit": 1,  # Already at limit
                },
            ],
            "briefing_ref": self.briefing_path,
            "audit_freshness": 30,
            "approval_expiry_window": 30,
            "max_diff_bytes": 524288,
            "lock_wait_timeout": 30,
        })

        # Seed 1 pattern_usage record (already at limit)
        from documenter_service.core.registry import TOKEN_RECORD
        self.registry.append(TOKEN_RECORD, {
            "token_type": "pattern_usage",
            "token_value": "target-0",
            "bound_to": {"audit_id": None, "target_id": "target-0"},
            "pattern_id": self.pattern_id,
            "applied_at": "2026-01-15T12:00:00Z",
            "approved_by": None,
            "auto": True,
        })

        alpha_diff = _make_simple_diff(
            self.doc_template.format(name="Alpha", id="alpha"))
        beta_diff = _make_simple_diff(
            self.doc_template.format(name="Beta", id="beta"))

        proposals = self._make_proposals(self.alpha_path, alpha_diff, "alpha") + \
            self._make_proposals(self.beta_path, beta_diff, "beta")

        with self.assertRaises(StructuredError) as ctx:
            apply_pattern_batch(
                self.corpus, self.manifest, self.registry, policy,
                self.events, self.engine,
                pattern_id=self.pattern_id,
                proposals=proposals,
                operator_id="op-user1",
            )
        self.assertEqual(ctx.exception.error_category, "gate_failure")


class TestServicePattern(unittest.TestCase):
    """Tests for Service-level thin: Service.pattern_auto_apply,
    Service.record_approval_viewed."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.corpus = os.path.join(self.tmpdir, "corpus")
        os.makedirs(os.path.join(self.corpus, "docs", "en", "alpha"))
        _enable_operator_surface(self.corpus)
        self.alpha_path = os.path.join(
            self.corpus, "docs", "en", "alpha", "index.md")
        self.doc_text = (
            "# Alpha\nid: alpha\nVersion: 1.0.0\nStatus: active\n"
            "changelog-path: CHANGELOGS/alpha.changes.md\n"
        )
        with open(self.alpha_path, "w") as f:
            f.write(self.doc_text)
        _make_briefing(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_service_pattern_auto_apply_tier1_interlock(self):
        """Service.pattern_auto_apply tier1 default repo policy → tier_interlock."""
        # Create a Service pointing at a directory with no policy (or tier 0/1)
        svc_root = os.path.join(self.tmpdir, "no_policy")
        os.makedirs(svc_root, exist_ok=True)
        svc = Service(svc_root)
        # No policy file at all → load_policy_safe returns (None, PolicyError)
        # → tier_interlock via check_tier3_authorized
        with self.assertRaises(StructuredError) as ctx:
            svc.pattern_auto_apply(
                pattern_id="test-pattern",
                proposals=[{
                    "target_id": "alpha",
                    "change_type": "update",
                    "trust_level": "safe",
                    "diff_input": _encode_diff("test diff"),
                    "audit_id": "aid-1",
                }],
                operator_id="op-user1",
            )
        self.assertEqual(ctx.exception.error_category, "tier_interlock")

    def test_service_record_approval_viewed(self):
        """Service.record_approval_viewed delegates to core.patterns.record_viewed."""
        svc_root = os.path.join(self.tmpdir, "with_policy")
        os.makedirs(svc_root, exist_ok=True)
        briefing_path = _make_briefing(svc_root)
        os.makedirs(os.path.join(svc_root, "docs", "en", "alpha"))
        self.doc_template = (
            "# Alpha\nid: alpha\nVersion: 1.0.0\nStatus: active\n"
            "changelog-path: CHANGELOGS/alpha.changes.md\n"
        )
        with open(os.path.join(svc_root, "docs", "en", "alpha", "index.md"),
                  "w") as f:
            f.write(self.doc_template.format(name="Alpha", id="alpha"))

        # Create a policy file
        policy_path = os.path.join(svc_root, "documenter_policy.yml")
        with open(policy_path, "w") as f:
            f.write(f"""documenter_policy:
  version: "0.2.0"
  active_tier: 3
  allowed_operations:
    - type: pattern
      pattern_id: test
      pattern_description: Test pattern
      match_criteria:
        change_type: update
        file_pattern: "*"
      trust_level: safe
  briefing_ref: "{briefing_path}"
  audit_freshness: 30
  approval_expiry_window: 30
  max_diff_bytes: 524288
  lock_wait_timeout: 30
""")

        svc = Service(svc_root)

        # Issue an approval in the service's registry
        approval_id = "app-svc-view-1"
        svc.registry.issue_approval(
            approval_id=approval_id,
            target_ids=["alpha"],
            diff_hash="sha256:" + "b" * 64,
            proposer_id="op-user1",
            audit_id="aid-1",
        )

        result = svc.record_approval_viewed(approval_id=approval_id)
        self.assertTrue(result.get("viewed"))

        # Verify the approval record now has viewed=True
        approval = svc.registry.find_approval(approval_id)
        self.assertTrue(approval.get("viewed"))
