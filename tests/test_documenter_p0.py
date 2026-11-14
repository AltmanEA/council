"""Regression tests for ADR-013 Tier 0 interlock (P0).

Covers:
  - T1: approve with Tier-0 policy → tier_interlock, state unchanged
  - T2: malformed operator_id takes priority over tier gate
  - T3: apply_write with Tier-0 policy → tier_interlock, file unchanged
  - T4: Dormancy matrix — all write-branch paths yield tier_interlock for Tier-0
  - T5: consume_token rejects approval_id as audit_mismatch
  - T6: apply_write rejects scan_cursor as approval_id (audit_mismatch)
  - T7: Full legit cycle still green with Tier-2 policy
  - T8: Tier 0 + budget=0 yields tier_interlock (tier gate precedes budget)

Run with: python3 -m unittest tests.test_documenter_p0
"""
import base64
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from documenter_service.adapters.diff_engine import StdDiffEngine  # noqa: E402
from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry  # noqa: E402
from documenter_service.adapters.stdout_events import StdoutEventSink  # noqa: E402
from documenter_service.core.errors import StructuredError  # noqa: E402
from documenter_service.core import registry as reg  # noqa: E402
from documenter_service.core import write as core_write  # noqa: E402
from documenter_service.core.policy import Policy  # noqa: E402
from documenter_service.core.patterns import apply_pattern_batch  # noqa: E402
from documenter_service.core.override import override_gate  # noqa: E402


# ---------------------------------------------------------------------------
# Helper factories (copied from test_documenter_write.py for isolation)
# ---------------------------------------------------------------------------

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'fixtures', 'documenter')


def _make_tier0_policy():
    """Create a Tier-0 Policy (no write intent, no briefing_ref)."""
    return Policy({
        "version": "0.2.0",
        "active_tier": 0,
        "allowed_operations": [],
        "audit_freshness": 30,
        "approval_expiry_window": 30,
        "max_diff_bytes": 524288,
    })


def _make_tier2_policy(briefing_path=None):
    """Create a Tier-2 Policy with a valid briefing_ref."""
    fields = {
        "version": "0.2.0",
        "active_tier": 2,
        "allowed_operations": [
            {
                "change_type": "update",
                "targets": ["alpha"],
                "trust_level": "safe",
            },
            {
                "change_type": "update",
                "targets": [],
                "trust_level": "review",
            },
        ],
        "briefing_ref": briefing_path or "_briefing.md",
        "audit_freshness": 30,
        "approval_expiry_window": 30,
        "max_diff_bytes": 524288,
        "lock_wait_timeout": 30,
    }
    return Policy(fields)


def _make_registry(tmpdir):
    return JsonlAuditRegistry(tmpdir)


def _make_briefing(tmpdir):
    """Create a briefing file at the expected path."""
    path = os.path.join(tmpdir, "_briefing.md")
    with open(path, "w") as f:
        f.write("# Briefing\n\nAuthorised operational context.\n")
    return path


def _enable_operator_surface(root):
    """Create the ADR-013 Operator Surface readiness sentinel under root."""
    sentinel = os.path.join(root, "documenter", ".operator_surface_ready")
    os.makedirs(os.path.dirname(sentinel), exist_ok=True)
    with open(sentinel, "w") as f:
        f.write("")
    return sentinel


def _init_git_repo(root: str) -> None:
    """Initialise ``root`` as a git repo (quietly)."""
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


def _make_diff(change_type="update", trust_level="safe",
               target_id="alpha", doc_text=None):
    """Create a simple unified diff for a target document."""
    if doc_text is None:
        doc_text = "# Alpha\nid: alpha\nVersion: 1.0.0\nStatus: active\nchangelog-path: CHANGELOGS/alpha.md\n"
    old_lines = doc_text.split("\n")
    effective_lines = old_lines
    if old_lines and old_lines[-1] == "":
        effective_lines = old_lines[:-1]
    hunk_header = "@@ -1," + str(len(effective_lines)) + " +1," + str(
        len(effective_lines)) + " @@\n"
    effective_diff = []
    for line in effective_lines:
        if "changelog-path: CHANGELOGS/alpha.md" in line:
            effective_diff.append(
                "-" + line)
            effective_diff.append("+" + line.replace(
                "changelog-path: CHANGELOGS/alpha.md",
                "changelog-path: CHANGELOGS/alpha.updated.md"))
        else:
            effective_diff.append(" " + line)
    diff_text = ("--- a/index.md\n+++ b/index.md\n" + hunk_header +
                 "\n".join(effective_diff) + "\n")
    return diff_text


def _encode_diff(diff_text):
    return base64.b64encode(diff_text.encode("utf-8")).decode("ascii")


def _make_manifest():
    """Create an in-memory manifest from corpus entries."""
    entries_list = []
    manifest = type("Manifest", (), {
        "_entries": {},
        "entries": lambda self: entries_list,
        "resolve": lambda self, tid: self._entries.get(tid),
    })()
    for eid in ["alpha", "beta", "gamma"]:
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


# ---------------------------------------------------------------------------
# T1: test_approve_tier0_denied_before_any_state_change
# ---------------------------------------------------------------------------

class TestTier0Approve(unittest.TestCase):
    """T1: approve with Tier-0 policy -> tier_interlock, state unchanged."""

    def test_approve_tier0_denied_before_any_state_change(self):
        tmpdir = tempfile.mkdtemp()
        try:
            root = os.path.join(tmpdir, "corpus")
            os.makedirs(root)
            registry = _make_registry(tmpdir)
            policy0 = _make_tier0_policy()  # no briefing_ref
            events = StdoutEventSink()

            # Issue an approval directly
            registry.issue_approval(
                approval_id="app-1",
                target_ids=["alpha"],
                diff_hash="sha256:" + "a" * 64,
                proposer_id="op-proposer",
                audit_id=None,
            )

            # approve with Tier-0 policy and no sentinel -> tier_interlock
            with self.assertRaises(StructuredError) as ctx:
                core_write.approve(
                    registry, policy0, events,
                    root=root,
                    approval_id="app-1", operator_id="op-user1")
            self.assertEqual(ctx.exception.error_category, "tier_interlock")

            # Approval decision must still be None
            approval = registry.find_approval("app-1")
            self.assertIsNone(approval["decision"])
        finally:
            shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# T2: test_approve_malformed_operator_id_precedes_tier_gate
# ---------------------------------------------------------------------------

class TestMalformedOperatorId(unittest.TestCase):
    """T2: malformed operator_id takes priority over tier gate."""

    def test_approve_malformed_operator_id_precedes_tier_gate(self):
        tmpdir = tempfile.mkdtemp()
        try:
            root = os.path.join(tmpdir, "corpus")
            os.makedirs(root)
            registry = _make_registry(tmpdir)
            policy0 = _make_tier0_policy()  # Tier-0, no briefing
            events = StdoutEventSink()

            # Issue an approval
            registry.issue_approval(
                approval_id="app-1",
                target_ids=["alpha"],
                diff_hash="sha256:" + "a" * 64,
                proposer_id="op-proposer",
                audit_id=None,
            )

            # Malformed operator_id -> "unknown", NOT "tier_interlock"
            with self.assertRaises(StructuredError) as ctx:
                core_write.approve(
                    registry, policy0, events,
                    root=root,
                    approval_id="app-1", operator_id="invalid")
            self.assertEqual(ctx.exception.error_category, "unknown")
        finally:
            shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# T3: test_apply_write_tier0_denied_file_unchanged
# ---------------------------------------------------------------------------

class TestApplyWriteTier0(unittest.TestCase):
    """T3: apply_write with Tier-0 policy -> tier_interlock, file unchanged."""

    def test_apply_write_tier0_denied_file_unchanged(self):
        tmpdir = tempfile.mkdtemp()
        try:
            corpus = os.path.join(tmpdir, "corpus")
            os.makedirs(os.path.join(corpus, "docs", "en", "alpha"))
            alpha_path = os.path.join(corpus, "docs", "en", "alpha",
                                     "index.md")
            with open(alpha_path, "w") as f:
                f.write("# Alpha\nid: alpha\nVersion: 1.0.0\n"
                        "Status: active\nchangelog-path: CHANGELOGS/alpha.md\n")
            _init_git_repo(corpus)

            manifest = _make_manifest()
            registry = _make_registry(tmpdir)
            policy0 = _make_tier0_policy()  # Tier-0
            events = StdoutEventSink()
            engine = StdDiffEngine()

            # Issue approval and resolve it
            registry.issue_approval(
                approval_id="app-1",
                target_ids=["alpha"],
                diff_hash="sha256:" + "a" * 64,
                proposer_id="op-proposer",
                audit_id="aid-1",
            )
            # Manually set decision=approved (simulating a prior approve that
            # somehow succeeded in the legacy path — not possible now but
            # tests the gate)
            approval = registry.find_approval("app-1")
            approval["decision"] = "approved"
            registry.append(reg.TOKEN_RECORD, approval)

            # apply_write with Tier-0 policy -> tier_interlock
            encoded = _encode_diff(_make_diff())
            with self.assertRaises(StructuredError) as ctx:
                core_write.apply_write(
                    corpus, manifest, registry, policy0, events, engine,
                    approval_id="app-1", operator_id="op-user1",
                    diff_input=encoded,
                    data_dir=os.path.join(tmpdir, "documenter"))
            self.assertEqual(ctx.exception.error_category, "tier_interlock")

            # File must be unchanged
            with open(alpha_path) as f:
                content = f.read()
            self.assertIn("changelog-path: CHANGELOGS/alpha.md", content)
        finally:
            shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# T4: test_dormancy_preserved_matrix
# ---------------------------------------------------------------------------

class TestDormancyMatrix(unittest.TestCase):
    """T4: Dormancy matrix — all write-branch paths yield tier_interlock."""

    def test_dormancy_preserved_matrix(self):
        tmpdir = tempfile.mkdtemp()
        try:
            # Tier-0 policy, root without sentinel
            policy0 = _make_tier0_policy()
            root = os.path.join(tmpdir, "corpus")
            os.makedirs(root)
            registry = _make_registry(tmpdir)
            events = StdoutEventSink()
            manifest = _make_manifest()
            engine = StdDiffEngine()
            encoded = _encode_diff(_make_diff())

            # 4a: propose_write -> tier_interlock
            with self.assertRaises(StructuredError) as ctx:
                core_write.propose_write(
                    root, manifest, registry, policy0, events, engine,
                    target_id="alpha", change_type="update",
                    trust_level="safe", diff_input=encoded, audit_id="aid-1",
                    preview=False,
            proposer_id="op-bot1"
        )
            self.assertEqual(ctx.exception.error_category, "tier_interlock")

            # 4b: approve -> tier_interlock
            with self.assertRaises(StructuredError) as ctx:
                core_write.approve(
                    registry, policy0, events,
                    root=root,
                    approval_id="app-x", operator_id="op-user1")
            self.assertEqual(ctx.exception.error_category, "tier_interlock")

            # 4c: apply_write -> tier_interlock
            manifest = _make_manifest()
            with self.assertRaises(StructuredError) as ctx:
                core_write.apply_write(
                    root, manifest, registry, policy0, events, engine,
                    approval_id="app-x", operator_id="op-user1",
                    diff_input=encoded,
                    data_dir=os.path.join(tmpdir, "documenter"))
            self.assertEqual(ctx.exception.error_category, "tier_interlock")

            # 4d: apply_pattern_batch -> tier_interlock
            with self.assertRaises(StructuredError) as ctx:
                apply_pattern_batch(
                    root, manifest, registry, policy0, events, engine,
                    pattern_id="p1", proposals=[], operator_id="op-user1")
            self.assertEqual(ctx.exception.error_category, "tier_interlock")

            # 4e: override_gate -> tier_interlock
            with self.assertRaises(StructuredError) as ctx:
                override_gate(
                    root, os.path.join(tmpdir, "documenter"), registry,
                    policy0, events,
                    target_id="alpha",
                    diff_hash="sha256:" + "a" * 64,
                    reason="x", operator_id="op-user1")
            self.assertEqual(ctx.exception.error_category, "tier_interlock")
        finally:
            shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# T5: test_consume_token_approval_id_rejected
# ---------------------------------------------------------------------------

class TestConsumeToken(unittest.TestCase):
    """T5: approve_id rejected as scan_cursor on consume."""

    def test_consume_token_approval_id_rejected(self):
        tmpdir = tempfile.mkdtemp()
        try:
            registry = _make_registry(tmpdir)

            # Issue an approval_id token
            registry.issue_approval(
                approval_id="app-1",
                target_ids=["alpha"],
                diff_hash="sha256:" + "b" * 64,
                proposer_id="op-proposer",
                audit_id=None,
            )

            # consume_token with approval_id -> audit_mismatch
            with self.assertRaises(StructuredError) as ctx:
                registry.consume_token("app-1", "alpha")
            self.assertEqual(ctx.exception.error_category, "audit_mismatch")
            self.assertIn("not a scan_cursor", ctx.exception.message)

            # Now test a legit scan_cursor cycle
            registry.issue_token(
                "scan_cursor", "tok-1",
                {"audit_id": "a1", "target_id": "alpha"})
            result = registry.consume_token("tok-1", "alpha")
            self.assertTrue(result["consumed"])
        finally:
            shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# T6: test_apply_with_scan_cursor_as_approval_id
# ---------------------------------------------------------------------------

class TestScanCursorAsApprovalId(unittest.TestCase):
    """T6: apply_write with scan_cursor as approval_id -> audit_mismatch."""

    def test_apply_with_scan_cursor_as_approval_id(self):
        tmpdir = tempfile.mkdtemp()
        try:
            corpus = os.path.join(tmpdir, "corpus")
            os.makedirs(os.path.join(corpus, "docs", "en", "alpha"))
            alpha_path = os.path.join(corpus, "docs", "en", "alpha",
                                     "index.md")
            with open(alpha_path, "w") as f:
                f.write("# Alpha\nid: alpha\n")
            _init_git_repo(corpus)

            manifest = _make_manifest()
            registry = _make_registry(tmpdir)
            policy = _make_tier2_policy(_make_briefing(tmpdir))
            events = StdoutEventSink()
            engine = StdDiffEngine()

            # Issue a scan_cursor token
            registry.issue_token(
                "scan_cursor", "cur-1",
                {"audit_id": "a1", "target_id": "alpha"})

            # Enable operator surface (sentinel) — Tier-2 policy requires it
            _enable_operator_surface(corpus)

            # apply_write with scan_cursor as approval_id -> audit_mismatch
            encoded = _encode_diff(_make_diff())
            with self.assertRaises(StructuredError) as ctx:
                core_write.apply_write(
                    corpus, manifest, registry, policy, events, engine,
                    approval_id="cur-1", operator_id="op-user1",
                    diff_input=encoded,
                    data_dir=os.path.join(tmpdir, "documenter"))
            self.assertEqual(ctx.exception.error_category, "audit_mismatch")
        finally:
            shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# T7: test_legit_cycle_still_green
# ---------------------------------------------------------------------------

class TestLegitCycle(unittest.TestCase):
    """T7: Full legit cycle still green with Tier-2 policy."""

    def test_legit_cycle_still_green(self):
        tmpdir = tempfile.mkdtemp()
        try:
            corpus = os.path.join(tmpdir, "corpus")
            os.makedirs(os.path.join(corpus, "docs", "en", "alpha"))
            alpha_path = os.path.join(corpus, "docs", "en", "alpha",
                                     "index.md")
            with open(alpha_path, "w") as f:
                f.write("# Alpha\nid: alpha\nVersion: 1.0.0\n"
                        "Status: active\nchangelog-path: CHANGELOGS/alpha.md\n")
            _init_git_repo(corpus)

            manifest = _make_manifest()
            registry = _make_registry(tmpdir)
            policy = _make_tier2_policy(_make_briefing(tmpdir))
            events = StdoutEventSink()
            engine = StdDiffEngine()

            # Enable operator surface (sentinel) — Tier-2 policy requires it
            _enable_operator_surface(corpus)

            # Seed audit record
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            registry.append(reg.AUDIT_RECORD, {
                "audit_id": "aid-1",
                "issued_at": now_iso,
                "scope": "*",
                "findings": [],
                "scanned_ids": ["alpha", "beta", "gamma"],
                "has_remaining": False,
            })

            # propose_write
            diff_text = _make_diff()
            encoded = _encode_diff(diff_text)
            prop_result = core_write.propose_write(
                corpus, manifest, registry, policy, events, engine,
                target_id="alpha", change_type="update",
                trust_level="safe", diff_input=encoded, audit_id="aid-1",
                preview=False,
            proposer_id="op-bot1"
        )

            self.assertTrue(prop_result["approval_required"])
            approval_id = prop_result["approval_id"]

            # approve (with Tier-2 policy + sentinel present)
            core_write.approve(
                registry, policy, events,
                root=corpus,
                approval_id=approval_id, operator_id="op-user1")

            # apply_write
            result = core_write.apply_write(
                corpus, manifest, registry, policy, events, engine,
                approval_id=approval_id, operator_id="op-user1",
                diff_input=encoded,
                data_dir=os.path.join(tmpdir, "documenter"))

            self.assertTrue(result["applied"])
            self.assertEqual(result["target_id"], "alpha")
            self.assertEqual(result["next_action"], "write_applied")
        finally:
            shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# T8: budget check must not preempt the tier gate (plan 2b, item 8d)
# ---------------------------------------------------------------------------

class TestBudgetAfterTierGate(unittest.TestCase):
    """Tier 0 + sync_latency_budget_ms=0 -> tier_interlock, never gate_failure."""

    def test_propose_write_tier0_budget_zero_yields_tier_interlock(self):
        tmpdir = tempfile.mkdtemp()
        try:
            root = os.path.join(tmpdir, "corpus")
            os.makedirs(root)
            registry = _make_registry(tmpdir)
            policy0 = _make_tier0_policy()
            events = StdoutEventSink()
            manifest = _make_manifest()
            engine = StdDiffEngine()
            encoded = _encode_diff(_make_diff())
            with self.assertRaises(StructuredError) as ctx:
                core_write.propose_write(
                    root, manifest, registry, policy0, events, engine,
                    target_id="alpha", change_type="update",
                    trust_level="safe", diff_input=encoded, audit_id="aid-1",
                    preview=False, sync_latency_budget_ms=0,
            proposer_id="op-bot1"
        )
            self.assertEqual(ctx.exception.error_category, "tier_interlock")
        finally:
            shutil.rmtree(tmpdir)

    def test_apply_write_tier0_budget_zero_yields_tier_interlock(self):
        tmpdir = tempfile.mkdtemp()
        try:
            root = os.path.join(tmpdir, "corpus")
            os.makedirs(root)
            registry = _make_registry(tmpdir)
            policy0 = _make_tier0_policy()
            events = StdoutEventSink()
            manifest = _make_manifest()
            engine = StdDiffEngine()
            encoded = _encode_diff(_make_diff())
            with self.assertRaises(StructuredError) as ctx:
                core_write.apply_write(
                    root, manifest, registry, policy0, events, engine,
                    approval_id="app-x", operator_id="op-user1",
                    diff_input=encoded,
                    data_dir=os.path.join(tmpdir, "documenter"),
                    sync_latency_budget_ms=0)
            self.assertEqual(ctx.exception.error_category, "tier_interlock")
        finally:
            shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
