"""Comprehensive tests for the Documenter Service write branch (W2).

Covers:
  - adapters/applier: apply_unified_diff unit tests
  - adapters/lock: DelegateLock unit tests
  - core/write: propose_write, approve, apply_write, reconcile
  - Service-level: delegate(preview=False), approve, apply
  - stdout_events: documenter.approval event emission
  - diff_engine, trust, errors, pre_audit_gate, policy, registry
  - integration: full delegate -> approve -> apply lifecycle

Run with: python3 -m unittest tests.test_documenter_write
"""
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from documenter_service.adapters.applier import apply_unified_diff  # noqa: E402
from documenter_service.adapters.diff_engine import StdDiffEngine  # noqa: E402
from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry  # noqa: E402
from documenter_service.adapters.lock import DelegateLock  # noqa: E402
from documenter_service.adapters.stdout_events import (  # noqa: E402
    StdoutEventSink, MVP_EVENT_TYPES, EVENT_SCHEMAS)
from documenter_service.core.errors import StructuredError  # noqa: E402
from documenter_service.core import registry as reg  # noqa: E402
from documenter_service.core.policy import (  # noqa: E402
    check_tier2_authorized, operator_id_valid, match_operation, trust_rank)
from documenter_service.__main__ import Service  # noqa: E402
from documenter_service.core import write as core_write  # noqa: E402
from documenter_service.core.policy import Policy  # noqa: E402
from documenter_service.core.trust import check_invariant  # noqa: E402
from documenter_service.core.audit import pre_audit_gate  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures',
                        'documenter')
CORPUS = os.path.join(FIXTURES, 'corpus')


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

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


def _make_tier0_policy():
    """Create a Tier-0 Policy (no write intent)."""
    return Policy({
        "version": "0.2.0",
        "active_tier": 0,
        "allowed_operations": [],
        "audit_freshness": 30,
        "approval_expiry_window": 30,
        "max_diff_bytes": 524288,
    })


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


def _enable_operator_ingress(root):
    """Create the ADR-013 Operator Ingress readiness sentinel under root.

    Tier 2+ test corpora must opt into surface-readiness explicitly:
    check_tier2_authorized refuses (tier_interlock) while the sentinel is
    absent. Tests asserting the second interlock level omit this call.
    """
    sentinel = os.path.join(root, "documenter", ".operator_ingress_ready")
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


def _make_diff(change_type="update", trust_level="safe",
               target_id="alpha", doc_text=None):
    """Create a simple unified diff for a target document."""
    if doc_text is None:
        doc_text = "# Alpha\nid: alpha\nVersion: 1.0.0\nStatus: active\nchangelog-path: CHANGELOGS/alpha.md\n"
    old_lines = doc_text.split("\n")
    diff_lines = []
    for line in old_lines:
        if line == "changelog-path: CHANGELOGS/alpha.md":
            diff_lines.append("-changelog-path: CHANGELOGS/alpha.md")
            diff_lines.append("+changelog-path: CHANGELOGS/alpha.updated.md")
        else:
            diff_lines.append(" " + line)
    # Exclude trailing empty string from the diff (it gets stripped by normalize)
    effective_lines = old_lines
    if old_lines and old_lines[-1] == "":
        effective_lines = old_lines[:-1]
    hunk_header = "@@ -1," + str(len(effective_lines)) + " +1," + str(len(effective_lines)) + " @@\n"
    effective_diff = []
    for line in effective_lines:
        if line == "changelog-path: CHANGELOGS/alpha.md":
            effective_diff.append("-changelog-path: CHANGELOGS/alpha.md")
            effective_diff.append("+changelog-path: CHANGELOGS/alpha.updated.md")
        else:
            effective_diff.append(" " + line)
    diff_text = "--- a/index.md\n+++ b/index.md\n" + hunk_header + "\n".join(effective_diff) + "\n"
    return diff_text


def _encode_diff(diff_text):
    return base64.b64encode(diff_text.encode("utf-8")).decode("ascii")


def _make_audit_record(audit_id, issued_at=None, scope="*", findings=None,
                       has_remaining=False):
    now = issued_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "audit_id": audit_id,
        "issued_at": now,
        "scope": scope,
        "findings": findings or [],
        "scanned_ids": ["alpha", "beta", "gamma"],
        "has_remaining": has_remaining,
    }
# ---------------------------------------------------------------------------
# Test class: TestApplier
# ---------------------------------------------------------------------------

class TestApplier(unittest.TestCase):
    """Unit tests for apply_unified_diff (pure, no I/O)."""

    def test_simple_replacement(self):
        original = "# Title\nid: alpha\n\nHello world\n"
        diff = "@@ -1,4 +1,4 @@\n-# Title\n+xTitle\n id: alpha\n \n-Hello world\n+Hello there\n"
        result = apply_unified_diff(original, diff)
        self.assertIn("Hello there", result)
        self.assertNotIn("Hello world", result)

    def test_context_preservation(self):
        original = "line1\nline2\nline3\n"
        diff = "@@ -1,3 +1,3 @@\n line1\n-line2\n+line2_updated\n line3\n"
        result = apply_unified_diff(original, diff)
        self.assertIn("line1", result)
        self.assertIn("line3", result)

    def test_line_deletion(self):
        original = "keep\nremove_this\nkeep2\n"
        diff = "@@ -1,3 +1,2 @@\n keep\n-remove_this\n keep2\n"
        result = apply_unified_diff(original, diff)
        self.assertNotIn("remove_this", result)
        self.assertIn("keep\n", result)

    def test_line_insertion(self):
        original = "before\nafter\n"
        diff = "@@ -1,2 +1,3 @@\n before\n+inserted\n after\n"
        result = apply_unified_diff(original, diff)
        self.assertIn("inserted", result)

    def test_multiple_hunks(self):
        original = "a\nb\nc\nd\ne\n"
        diff1 = "@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n"
        diff2 = "@@ -4,2 +4,2 @@\n-d\n+D\n e\n"
        result = apply_unified_diff(original, diff1 + diff2)
        self.assertIn("B", result)
        self.assertIn("D", result)
        self.assertNotIn("b\n", result)
        self.assertNotIn("d\n", result)

    def test_empty_change_no_op(self):
        original = "content\n"
        diff = "@@ -1,1 +1,1 @@\n-content\n+content\n"
        result = apply_unified_diff(original, diff)
        self.assertEqual(result, original)

    def test_diff_mismatch_raises(self):
        original = "line1\nline2\n"
        diff = "@@ -1,2 +1,2 @@\n wrong_context\n line2\n+new1\n+new2\n"
        with self.assertRaises(StructuredError) as ctx:
            apply_unified_diff(original, diff)
        self.assertIn("does not apply cleanly", ctx.exception.message)
        self.assertEqual(ctx.exception.error_category, "unknown")

    def test_mismatched_context_raises(self):
        original = "hello\nworld\n"
        diff = "@@ -1,2 +1,2 @@\n goodbye\n world\n+world\n+new\n"
        with self.assertRaises(StructuredError) as ctx:
            apply_unified_diff(original, diff)
        self.assertIn("context mismatch", ctx.exception.message)

    def test_unparseable_hunk_raises(self):
        original = "a\n"
        diff = "@@ BAD HEADER @@\n+a\n"
        with self.assertRaises(StructuredError) as ctx:
            apply_unified_diff(original, diff)
        self.assertEqual(ctx.exception.error_category, "unknown")

    def test_extra_context_lines_exhausted(self):
        original = "a\n"
        diff = "@@ -1,1 +1,1 @@\n-a\n+b\n"
        result = apply_unified_diff(original, diff)
        self.assertEqual(result, "b\n")

    def test_empty_file(self):
        original = ""
        diff = "@@ -0,0 +1,1 @@\n+a\n"
        result = apply_unified_diff(original, diff)
        self.assertEqual(result, "a\n")

    def test_added_lines_in_order(self):
        original = ""
        diff = "@@ -0,0 +1,3 @@\n+a\n+b\n+c\n"
        result = apply_unified_diff(original, diff)
        self.assertEqual(result, "a\nb\nc\n")

    def test_only_removed_lines(self):
        original = "a\nb\nc\n"
        diff = "@@ -1,3 +0,0 @@\n-a\n-b\n-c\n"
        result = apply_unified_diff(original, diff)
        self.assertEqual(result, "")

    # -- regressions for the rewritten positional applier ---------------------

    def test_blank_context_line_inside_hunk(self):
        # normalize() rstrips, so a blank context line arrives as "" — it is
        # a blank context line, never an end marker (the original bug).
        original = "id: x\n\nStatus: active\n"
        diff = "@@ -1,3 +1,3 @@\n-id: x\n+id: y\n\n Status: active\n"
        result = apply_unified_diff(original, diff)
        self.assertEqual(result, "id: y\n\nStatus: active\n")

    def test_hunk_uses_declared_start_with_gap(self):
        # A hunk not starting at line 1 must apply AT its declared position,
        # copying the gap verbatim (the walker ignored old_start before).
        original = "l1\nl2\nl3\nl4\nl5\n"
        diff = "@@ -4,2 +4,2 @@\n-l4\n+L4\n l5\n"
        result = apply_unified_diff(original, diff)
        self.assertEqual(result, "l1\nl2\nl3\nL4\nl5\n")

    def test_two_hunks_with_gap(self):
        original = "a\nb\nc\nd\ne\nf\n"
        diff = ("@@ -2,1 +2,1 @@\n-b\n+B\n"
                "@@ -6,1 +6,1 @@\n-f\n+F\n")
        result = apply_unified_diff(original, diff)
        self.assertEqual(result, "a\nB\nc\nd\ne\nF\n")

    def test_overlapping_hunks_rejected(self):
        original = "a\nb\nc\n"
        diff = ("@@ -1,2 +1,2 @@\n-a\n+A\n b\n"
                "@@ -2,2 +2,2 @@\n-b\n+B\n c\n")
        with self.assertRaises(StructuredError) as ctx:
            apply_unified_diff(original, diff)
        self.assertEqual(ctx.exception.error_category, "unknown")
        self.assertIn("overlap", ctx.exception.message.lower())
        # Same hunks with a trailing newline (normalized-payload shape):
        # the verdict must not depend on the payload's final newline.
        with self.assertRaises(StructuredError) as ctx2:
            apply_unified_diff(original, diff + "\n")
        self.assertIn("overlap", ctx2.exception.message.lower())

    def test_pure_insertion_after_line_n(self):
        original = "a\nb\n"
        diff = "@@ -1,0 +2,1 @@\n+inserted\n"
        result = apply_unified_diff(original, diff)
        self.assertEqual(result, "a\ninserted\nb\n")

    def test_old_count_inconsistency_rejected(self):
        original = "a\nb\n"
        diff = "@@ -1,5 +1,1 @@\n-a\n+A\n"
        with self.assertRaises(StructuredError) as ctx:
            apply_unified_diff(original, diff)
        self.assertEqual(ctx.exception.error_category, "unknown")
        self.assertIn("declares 5", ctx.exception.message)

    def test_context_mismatch_beyond_position_rejected(self):
        # Line 2 exists but differs: strict verbatim comparison.
        original = "a\nb\n"
        diff = "@@ -2,1 +2,1 @@\n-WRONG\n+B\n"
        with self.assertRaises(StructuredError) as ctx:
            apply_unified_diff(original, diff)
        self.assertIn("mismatch", ctx.exception.message)

    def _build_diff(self, *args, **kwargs):
        """Helper to build a diff. Args: removed/added pairs. kwargs: before/after."""
        diff_lines = []
        changed = False
        for i in range(0, len(args), 2):
            if i + 1 < len(args):
                removed = args[i]
                added = args[i + 1]
                diff_lines.append("-" + removed)
                diff_lines.append("+" + added)
                changed = True
        if not changed:
            old = args[0] if args else "x"
            new = args[1] if len(args) > 1 else old
            diff_lines.append("-" + old)
            diff_lines.append("+" + new)
        if diff_lines:
            before_part = "a\n" if "before" in kwargs else ""
            after_part = "z\n" if "after" in kwargs else ""
            count = 3 + len(diff_lines) // 2
            return "@@ -1," + str(count) + " +1," + str(count) + " @@\n" + "\n".join(diff_lines) + "\n"
        return "@@ -1,1 +1,1 @@\n"


# ---------------------------------------------------------------------------
# Test class: TestLock
# ---------------------------------------------------------------------------

class TestLock(unittest.TestCase):
    """Unit tests for DelegateLock."""

    def test_lock_acquires_and_releases(self):
        tmpdir = tempfile.mkdtemp()
        try:
            with DelegateLock(tmpdir, wait_timeout=1):
                self.assertTrue(os.path.exists(os.path.join(tmpdir, ".delegate.lock")))
        finally:
            shutil.rmtree(tmpdir)
        self.assertTrue(True)  # no raise = success

    def test_lock_creates_directory(self):
        tmpdir = tempfile.mkdtemp()
        subdir = os.path.join(tmpdir, "sub")
        try:
            with DelegateLock(subdir, wait_timeout=1):
                self.assertTrue(os.path.isdir(subdir))
        finally:
            shutil.rmtree(tmpdir)

    def test_lock_timeout_raises(self):
        tmpdir = tempfile.mkdtemp()
        try:
            with DelegateLock(tmpdir, wait_timeout=30):
                with self.assertRaises(StructuredError) as ctx:
                    with DelegateLock(tmpdir, wait_timeout=0):
                        pass
                self.assertEqual(ctx.exception.error_category, "lock_conflict")
                self.assertEqual(ctx.exception.next_action, "preview_denied")
        finally:
            shutil.rmtree(tmpdir)

    def test_lock_owner_info(self):
        tmpdir = tempfile.mkdtemp()
        try:
            lock = DelegateLock(tmpdir, wait_timeout=1)
            with lock:
                self.assertIn("pid", lock._owner_info)
                self.assertIn("acquired_at", lock._owner_info)
                self.assertIsInstance(lock._owner_info["pid"], int)
        finally:
            shutil.rmtree(tmpdir)

    def test_unexpected_oserror_not_treated_as_conflict(self):
        """p.21: OSError other than EWOULDBLOCK/EAGAIN (e.g. ENOSPC) must
        escalate as 'unknown', not spin until lock_conflict timeout."""
        import errno as _errno
        from unittest import mock

        tmpdir = tempfile.mkdtemp()
        try:
            boom = OSError(_errno.ENOSPC, "No space left on device")
            with mock.patch("documenter_service.adapters.lock.fcntl.flock",
                            side_effect=boom):
                with self.assertRaises(StructuredError) as ctx:
                    with DelegateLock(tmpdir, wait_timeout=1):
                        pass
            self.assertEqual(ctx.exception.error_category, "unknown")
            self.assertEqual(ctx.exception.next_action, "escalate")
        finally:
            shutil.rmtree(tmpdir)

    def test_eagain_still_retries_then_conflict(self):
        """p.21: EAGAIN (plain OSError, not BlockingIOError) keeps the retry
        semantics → lock_conflict on timeout (not regression of p.21)."""
        import errno as _errno
        from unittest import mock

        tmpdir = tempfile.mkdtemp()
        try:
            boom = OSError(_errno.EAGAIN, "Resource temporarily unavailable")
            with mock.patch("documenter_service.adapters.lock.fcntl.flock",
                            side_effect=boom):
                with self.assertRaises(StructuredError) as ctx:
                    with DelegateLock(tmpdir, wait_timeout=0):
                        pass
            self.assertEqual(ctx.exception.error_category, "lock_conflict")
        finally:
            shutil.rmtree(tmpdir)

    def test_lock_truncates_file_on_release(self):
        tmpdir = tempfile.mkdtemp()
        lock_path = os.path.join(tmpdir, ".delegate.lock")
        lock = DelegateLock(tmpdir, wait_timeout=1)
        with lock:
            lock_content = open(lock_path).read()
            self.assertTrue(len(lock_content) > 0)
        self.assertTrue(open(lock_path).read() == "")

    def test_lock_never_raises_on_exit(self):
        tmpdir = tempfile.mkdtemp()
        lock = DelegateLock(tmpdir, wait_timeout=1)
        try:
            with lock:
                pass
            # Normal release should not raise
        except Exception:
            self.fail("DelegateLock.__exit__ raised unexpectedly")
        finally:
            shutil.rmtree(tmpdir)

    def test_lock_fd_closed_on_release(self):
        tmpdir = tempfile.mkdtemp()
        lock = DelegateLock(tmpdir, wait_timeout=1)
        with lock:
            fd_before = lock._fd
            self.assertIsNotNone(fd_before)
        self.assertIsNone(lock._fd)

    def test_lock_with_custom_clock(self):
        tmpdir = tempfile.mkdtemp()
        clock_time = [100.0]
        def fake_clock():
            return clock_time[0]
        try:
            with DelegateLock(tmpdir, wait_timeout=1, clock=fake_clock):
                pass
        finally:
            shutil.rmtree(tmpdir)

    def test_lock_custom_clock_timeout(self):
        tmpdir = tempfile.mkdtemp()
        try:
            call_count = [0]
            def fake_clock():
                call_count[0] += 1
                if call_count[0] <= 1:
                    return 100.0  # First call: sets deadline=110.0
                return 200.0     # Second call: 200.0 >= 110.0 → timeout
            with DelegateLock(tmpdir, wait_timeout=30):
                lock = DelegateLock(tmpdir, wait_timeout=10, clock=fake_clock)
                with self.assertRaises(StructuredError) as ctx:
                    with lock:
                        pass
                self.assertEqual(ctx.exception.error_category, "lock_conflict")
        finally:
            shutil.rmtree(tmpdir)

    def test_lock_pids_differ(self):
        tmpdir1 = tempfile.mkdtemp()
        tmpdir2 = tempfile.mkdtemp()
        try:
            lock1 = DelegateLock(tmpdir1, wait_timeout=1)
            lock2 = DelegateLock(tmpdir2, wait_timeout=1)
            with lock1:
                with lock2:
                    # Both locks acquired by same process share PID
                    # but owner info should differ in acquired_at timestamp
                    self.assertEqual(lock1._owner_info["pid"],
                                     lock2._owner_info["pid"])
                    self.assertIn("acquired_at", lock1._owner_info)
                    self.assertIn("acquired_at", lock2._owner_info)
        finally:
            shutil.rmtree(tmpdir1)
            shutil.rmtree(tmpdir2)

    def test_lock_default_timeout(self):
        tmpdir = tempfile.mkdtemp()
        try:
            with DelegateLock(tmpdir):  # default 30
                pass
        finally:
            shutil.rmtree(tmpdir)
# ---------------------------------------------------------------------------
# Test class: TestProposeWrite
# ---------------------------------------------------------------------------

class TestProposeWrite(unittest.TestCase):
    """Unit tests for propose_write (core/write.py)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.corpus = os.path.join(self.tmpdir, "corpus")
        os.makedirs(os.path.join(self.corpus, "docs", "en", "alpha"))
        _enable_operator_ingress(self.corpus)
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        with open(alpha_path, "w") as f:
            f.write("# Alpha\nid: alpha\nVersion: 1.0.0\nStatus: active\nchangelog-path: CHANGELOGS/alpha.md\n")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_propose_write_requires_approval(self):
        manifest = _make_manifest()
        reg_obj = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()
        diff_text = _make_diff()
        encoded = _encode_diff(diff_text)

        record = _make_audit_record("aid-1")
        reg_obj.append("audit_record", record)

        result = core_write.propose_write(
            self.corpus, manifest, reg_obj, policy, events, engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded, audit_id="aid-1", preview=False,
            proposer_id="op-bot1"
        )

        self.assertTrue(result["approval_required"])
        self.assertIn("approval_id", result)
        self.assertIn("diff_hash", result)
        self.assertEqual(result["next_action"], "await_approval")

    def test_propose_write_no_file_written(self):
        manifest = _make_manifest()
        reg_obj = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()
        diff_text = _make_diff()
        encoded = _encode_diff(diff_text)

        record = _make_audit_record("aid-1")
        reg_obj.append("audit_record", record)

        core_write.propose_write(
            self.corpus, manifest, reg_obj, policy, events, engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded, audit_id="aid-1", preview=False,
            proposer_id="op-bot1"
        )

        with open(os.path.join(self.corpus, "docs", "en", "alpha", "index.md")) as f:
            content = f.read()
        self.assertIn("changelog-path: CHANGELOGS/alpha.md", content)

    def test_propose_write_preview_true_raises(self):
        manifest = _make_manifest()
        reg_obj = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()

        with self.assertRaises(StructuredError) as ctx:
            core_write.propose_write(
                self.corpus, manifest, reg_obj, policy, events, engine,
                target_id="alpha", change_type="update", trust_level="safe",
                diff_input="dGVzdA==", audit_id="aid-1", preview=True,
            proposer_id="op-bot1"
        )
        self.assertEqual(ctx.exception.error_category, "unknown")

    def test_propose_write_tier_interlock(self):
        manifest = _make_manifest()
        reg_obj = _make_registry(self.tmpdir)
        policy = _make_tier0_policy()
        events = StdoutEventSink()
        engine = StdDiffEngine()

        with self.assertRaises(StructuredError) as ctx:
            core_write.propose_write(
                self.corpus, manifest, reg_obj, policy, events, engine,
                target_id="alpha", change_type="update", trust_level="safe",
                diff_input="dGVzdA==", audit_id="aid-1", preview=False,
            proposer_id="op-bot1"
        )
        self.assertEqual(ctx.exception.error_category, "tier_interlock")

    def test_propose_write_policy_none_raises(self):
        manifest = _make_manifest()
        reg_obj = _make_registry(self.tmpdir)
        events = StdoutEventSink()
        engine = StdDiffEngine()

        with self.assertRaises(StructuredError) as ctx:
            core_write.propose_write(
                self.corpus, manifest, reg_obj, None, events, engine,
                target_id="alpha", change_type="update", trust_level="safe",
                diff_input="dGVzdA==", audit_id="aid-1", preview=False,
            proposer_id="op-bot1"
        )
        self.assertEqual(ctx.exception.error_category, "tier_interlock")

    def test_propose_write_corrupt_registry_raises(self):
        manifest = _make_manifest()
        reg_obj = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()

        with self.assertRaises(StructuredError) as ctx:
            # Force corrupt status by writing bad data
            with open(reg_obj.path, "w") as f:
                f.write("not valid json\n")
            core_write.propose_write(
                self.corpus, manifest, reg_obj, policy, events, engine,
                target_id="alpha", change_type="update", trust_level="safe",
                diff_input="dGVzdA==", audit_id="aid-1", preview=False,
            proposer_id="op-bot1"
        )
        self.assertEqual(ctx.exception.error_category, "gate_failure")

    def test_propose_write_no_audit_id_raises(self):
        manifest = _make_manifest()
        reg_obj = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()

        with self.assertRaises(StructuredError) as ctx:
            core_write.propose_write(
                self.corpus, manifest, reg_obj, policy, events, engine,
                target_id="alpha", change_type="update", trust_level="safe",
                diff_input="dGVzdA==", audit_id=None, preview=False,
            proposer_id="op-bot1"
        )
        self.assertEqual(ctx.exception.error_category, "audit_mismatch")
        self.assertEqual(ctx.exception.next_action, "rerun_audit")

    def test_propose_write_unknown_target_raises(self):
        manifest = _make_manifest()
        reg_obj = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()
        diff_text = _make_diff()
        encoded = _encode_diff(diff_text)

        record = _make_audit_record("aid-1")
        reg_obj.append("audit_record", record)

        with self.assertRaises(StructuredError) as ctx:
            core_write.propose_write(
                self.corpus, manifest, reg_obj, policy, events, engine,
                target_id="nonexistent", change_type="update", trust_level="safe",
                diff_input=encoded, audit_id="aid-1", preview=False,
            proposer_id="op-bot1"
        )
        self.assertEqual(ctx.exception.error_category, "unknown")

    def test_propose_write_not_in_allowed_ops_raises(self):
        manifest = _make_manifest()
        reg_obj = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        # Override policy to not allow this target
        policy._fields["allowed_operations"] = [{
            "change_type": "split",
            "targets": ["beta"],
            "trust_level": "review",
        }]
        events = StdoutEventSink()
        engine = StdDiffEngine()
        diff_text = _make_diff()
        encoded = _encode_diff(diff_text)

        record = _make_audit_record("aid-1")
        reg_obj.append("audit_record", record)

        with self.assertRaises(StructuredError) as ctx:
            core_write.propose_write(
                self.corpus, manifest, reg_obj, policy, events, engine,
                target_id="alpha", change_type="update", trust_level="safe",
                diff_input=encoded, audit_id="aid-1", preview=False,
            proposer_id="op-bot1"
        )
        self.assertEqual(ctx.exception.error_category, "gate_failure")

    def test_propose_write_trust_mismatch_raises(self):
        manifest = _make_manifest()
        reg_obj = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()

        # Create a diff that changes a line non-mechanically
        diff_text = _make_diff(change_type="update", trust_level="safe")
        encoded = _encode_diff(diff_text)

        record = _make_audit_record("aid-1")
        reg_obj.append("audit_record", record)

        # Use review trust_level for a safe-requested change — should pass
        # because requested(rev) >= derived(safe)
        result = core_write.propose_write(
            self.corpus, manifest, reg_obj, policy, events, engine,
            target_id="alpha", change_type="update", trust_level="review",
            diff_input=encoded, audit_id="aid-1", preview=False,
            proposer_id="op-bot1"
        )
        self.assertTrue(result["approval_required"])

    def test_propose_write_issues_approval_in_registry(self):
        manifest = _make_manifest()
        reg_obj = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()
        diff_text = _make_diff()
        encoded = _encode_diff(diff_text)

        record = _make_audit_record("aid-1")
        reg_obj.append("audit_record", record)

        result = core_write.propose_write(
            self.corpus, manifest, reg_obj, policy, events, engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded, audit_id="aid-1", preview=False,
            proposer_id="op-bot1"
        )

        approval = reg_obj.find_approval(result["approval_id"])
        self.assertIsNotNone(approval)
        self.assertEqual(approval["diff_hash"], result["diff_hash"])
        self.assertIsNone(approval["decision"])

    def test_propose_write_proposer_id_stored(self):
        manifest = _make_manifest()
        reg_obj = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()
        diff_text = _make_diff()
        encoded = _encode_diff(diff_text)

        record = _make_audit_record("aid-1")
        reg_obj.append("audit_record", record)

        result = core_write.propose_write(
            self.corpus, manifest, reg_obj, policy, events, engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded, audit_id="aid-1", proposer_id="op-user1",
            preview=False)

        approval = reg_obj.find_approval(result["approval_id"])
        self.assertIsNotNone(approval)
        self.assertEqual(approval["proposer_id"], "op-user1")
        self.assertEqual(approval["diff_hash"], result["diff_hash"])
        self.assertIsNone(approval["decision"])

    def test_propose_write_expires_in_min(self):
        manifest = _make_manifest()
        reg_obj = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()
        diff_text = _make_diff()
        encoded = _encode_diff(diff_text)

        record = _make_audit_record("aid-1")
        reg_obj.append("audit_record", record)

        result = core_write.propose_write(
            self.corpus, manifest, reg_obj, policy, events, engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded, audit_id="aid-1", preview=False,
            proposer_id="op-bot1"
        )
        self.assertEqual(result["expires_in_min"], 30)

    def test_propose_write_no_policy_fallback_expiry(self):
        manifest = _make_manifest()
        reg_obj = _make_registry(self.tmpdir)
        # policy is None → tier_interlock blocks → test with a policy that has no approval_expiry_window
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        del policy._fields["approval_expiry_window"]
        events = StdoutEventSink()
        engine = StdDiffEngine()
        diff_text = _make_diff()
        encoded = _encode_diff(diff_text)

        record = _make_audit_record("aid-1")
        reg_obj.append("audit_record", record)

        result = core_write.propose_write(
            self.corpus, manifest, reg_obj, policy, events, engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded, audit_id="aid-1", preview=False,
            proposer_id="op-bot1"
        )
        self.assertEqual(result["expires_in_min"], 30)  # DEFAULTS fallback


# ---------------------------------------------------------------------------
# Test class: TestApprove
# ---------------------------------------------------------------------------

class TestApprove(unittest.TestCase):
    """Unit tests for approve (core/write.py)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = os.path.join(self.tmpdir, "corpus")
        os.makedirs(self.root, exist_ok=True)
        _enable_operator_ingress(self.root)
        self.registry = _make_registry(self.tmpdir)
        self.policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        self.events = StdoutEventSink()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _issue_approval(self, approval_id, diff_hash="sha256:" + "a" * 64,
                        proposer_id="op-bot1", target_id="alpha"):
        self.registry.issue_approval(
            approval_id=approval_id,
            target_ids=[target_id] if target_id else [],
            diff_hash=diff_hash,
            proposer_id=proposer_id,
            audit_id="aid-1",
        )
        return self.registry.find_approval(approval_id)

    def test_approve_success(self):
        approval_id = "app-1"
        self._issue_approval(approval_id, proposer_id="op-other")
        result = core_write.approve(
            self.registry, self.policy, self.events,
            root=self.root,
            approval_id=approval_id, operator_id="op-user1")
        self.assertEqual(result["decision"], "approved")
        self.assertEqual(result["next_action"], "await_approval")
        self.assertEqual(result["approval_id"], approval_id)

    def test_approve_self_approval_denied(self):
        approval_id = "app-1"
        self._issue_approval(approval_id, proposer_id="op-user1")
        with self.assertRaises(StructuredError) as ctx:
            core_write.approve(
                self.registry, self.policy, self.events,
                root=self.root,
                approval_id=approval_id, operator_id="op-user1")
        self.assertEqual(ctx.exception.error_category, "gate_failure")
        self.assertIn("self-approval denied", ctx.exception.message)

    def test_approve_unknown_approval_id(self):
        with self.assertRaises(StructuredError) as ctx:
            core_write.approve(
                self.registry, self.policy, self.events,
                root=self.root,
                approval_id="nonexistent", operator_id="op-user1")
        self.assertEqual(ctx.exception.error_category, "audit_mismatch")

    def test_approve_malformed_operator_id(self):
        approval_id = "app-1"
        self._issue_approval(approval_id, proposer_id="op-other")
        with self.assertRaises(StructuredError) as ctx:
            core_write.approve(
                self.registry, self.policy, self.events,
                root=self.root,
                approval_id=approval_id, operator_id="invalid")
        self.assertEqual(ctx.exception.error_category, "unknown")

    def test_approve_token_replay(self):
        approval_id = "app-1"
        self._issue_approval(approval_id, proposer_id="op-other")
        core_write.approve(
            self.registry, self.policy, self.events,
            root=self.root,
            approval_id=approval_id, operator_id="op-user1")
        with self.assertRaises(StructuredError) as ctx:
            core_write.approve(
                self.registry, self.policy, self.events,
                root=self.root,
                approval_id=approval_id, operator_id="op-user2")
        self.assertEqual(ctx.exception.error_category, "token_replay")

    def test_approve_emits_event(self):
        approval_id = "app-1"
        self._issue_approval(approval_id, proposer_id="op-other")
        stream = io.StringIO()
        events = StdoutEventSink(stream)
        core_write.approve(
            self.registry, self.policy, events,
            root=self.root,
            approval_id=approval_id, operator_id="op-user1")
        stream.seek(0)
        event_line = stream.readline().strip()
        event = json.loads(event_line)
        self.assertEqual(event["event_type"], "documenter.approval")
        self.assertEqual(event["payload"]["decision"], "approved")
        self.assertEqual(event["payload"]["approval_id"], approval_id)

    def test_approve_unattributed_proposal_denied(self):
        """approve an approval with proposer_id=None → gate_failure
        (unattributed proposals are rejected — fail-closed)."""
        approval_id = "app-1"
        # Issue approval directly with proposer_id=None (bypassing the
        # helper which now defaults to "op-bot1")
        self.registry.issue_approval(
            approval_id=approval_id,
            target_ids=["alpha"],
            diff_hash="sha256:" + "a" * 64,
            proposer_id=None,
            audit_id="aid-1",
        )
        with self.assertRaises(StructuredError) as ctx:
            core_write.approve(
                self.registry, self.policy, self.events,
                root=self.root,
                approval_id=approval_id, operator_id="op-user1")
        self.assertEqual(ctx.exception.error_category, "gate_failure")
        self.assertIn("unattributed", ctx.exception.message)

    def test_approve_expired_raises(self):
        approval_id = "app-1"
        self._issue_approval(approval_id, proposer_id="op-other")
        # Manually backdate created_at
        record = self.registry.find_approval(approval_id)
        record["created_at"] = "2020-01-01T00:00:00Z"
        self.registry.append("token_record", record)
        with self.assertRaises(StructuredError) as ctx:
            core_write.approve(
                self.registry, self.policy, self.events,
                root=self.root,
                approval_id=approval_id, operator_id="op-user1")
        self.assertEqual(ctx.exception.error_category, "approval_expired")

    def test_approve_expiry_window_from_policy(self):
        approval_id = "app-1"
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        policy._fields["approval_expiry_window"] = 0
        self._issue_approval(approval_id, proposer_id="op-other")
        record = self.registry.find_approval(approval_id)
        record["created_at"] = "2020-01-01T00:00:00Z"
        self.registry.append("token_record", record)
        with self.assertRaises(StructuredError) as ctx:
            core_write.approve(
                self.registry, policy, self.events,
                root=self.root,
                approval_id=approval_id, operator_id="op-user1")
        self.assertEqual(ctx.exception.error_category, "approval_expired")

    def test_approve_resolves_in_registry(self):
        approval_id = "app-1"
        self._issue_approval(approval_id, proposer_id="op-other")
        core_write.approve(
            self.registry, self.policy, self.events,
            root=self.root,
            approval_id=approval_id, operator_id="op-user1")
        approval = self.registry.find_approval(approval_id)
        self.assertEqual(approval["decision"], "approved")
        self.assertEqual(approval["resolved_by"], "op-user1")
        self.assertIsNotNone(approval.get("resolved_at"))

    def test_approve_different_operator_id_formats(self):
        valid_id = "op-abc"
        self.assertTrue(operator_id_valid(valid_id))
        invalid_id = "op-"  # too short
        self.assertFalse(operator_id_valid(invalid_id))
        invalid_id2 = "op-A1"  # uppercase
        self.assertFalse(operator_id_valid(invalid_id2))

    def test_approve_next_action_await_approval(self):
        approval_id = "app-1"
        self._issue_approval(approval_id, proposer_id="op-other")
        result = core_write.approve(
            self.registry, self.policy, self.events,
            root=self.root,
            approval_id=approval_id, operator_id="op-user1")
        self.assertEqual(result["next_action"], "await_approval")

    def test_approve_event_contains_diff_hash(self):
        approval_id = "app-1"
        diff_hash = "sha256:" + "b" * 64
        self._issue_approval(approval_id, diff_hash=diff_hash, proposer_id="op-other")
        stream = io.StringIO()
        events = StdoutEventSink(stream)
        core_write.approve(
            self.registry, self.policy, events,
            root=self.root,
            approval_id=approval_id, operator_id="op-user1")
        stream.seek(0)
        event = json.loads(stream.readline().strip())
        self.assertEqual(event["payload"]["diff_hash"], diff_hash)

    def test_approve_operator_id_regex_format(self):
        """Test various valid/invalid operator_id formats."""
        self.assertTrue(operator_id_valid("op-abc"))
        self.assertTrue(operator_id_valid("op-abc123"))
        self.assertTrue(operator_id_valid("op-a1-b2"))
        self.assertFalse(operator_id_valid(""))
        self.assertFalse(operator_id_valid("op-"))
        self.assertFalse(operator_id_valid("op-a"))
        self.assertFalse(operator_id_valid("op-a_"))
        self.assertFalse(operator_id_valid("Op-a1"))
# ---------------------------------------------------------------------------
# Test class: TestApplyWrite
# ---------------------------------------------------------------------------

class TestApplyWrite(unittest.TestCase):
    """Unit tests for apply_write (core/write.py)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.corpus = os.path.join(self.tmpdir, "corpus")
        os.makedirs(os.path.join(self.corpus, "docs", "en", "alpha"))
        _enable_operator_ingress(self.corpus)
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        with open(alpha_path, "w") as f:
            f.write("# Alpha\nid: alpha\nVersion: 1.0.0\nStatus: active\nchangelog-path: CHANGELOGS/alpha.md\n")
        _init_git_repo(self.corpus)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _full_cycle(self, target_id="alpha", change_type="update",
                    trust_level="safe", doc_text=None):
        """Run propose_write + approve + apply_write."""
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()
        diff_text = _make_diff(change_type=change_type, trust_level=trust_level,
                               target_id=target_id, doc_text=doc_text)
        encoded = _encode_diff(diff_text)

        record = _make_audit_record("aid-1")
        registry.append("audit_record", record)

        # propose_write
        prop_result = core_write.propose_write(
            self.corpus, manifest, registry, policy, events, engine,
            target_id=target_id, change_type=change_type,
            trust_level=trust_level, diff_input=encoded, audit_id="aid-1",
            proposer_id="op-bot1"
        )

        # approve
        approval_id = prop_result["approval_id"]
        core_write.approve(registry, policy, events,
                           root=self.corpus,
                           approval_id=approval_id, operator_id="op-user1")

        # apply_write
        result = core_write.apply_write(
            self.corpus, manifest, registry, policy, events, engine,
            approval_id=approval_id, operator_id="op-user1",
            diff_input=encoded, data_dir=os.path.join(self.tmpdir, "documenter"))

        return result, encoded

    def test_apply_write_success(self):
        result, diff_input = self._full_cycle()
        self.assertTrue(result["applied"])
        self.assertEqual(result["target_id"], "alpha")
        self.assertEqual(result["next_action"], "write_applied")
        self.assertIn("diff_hash", result)

    def test_apply_write_modifies_file(self):
        result, diff_input = self._full_cycle()
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        with open(alpha_path) as f:
            content = f.read()
        self.assertIn("changelog-path: CHANGELOGS/alpha.updated.md", content)
        self.assertNotIn("changelog-path: CHANGELOGS/alpha.md\n", content)

    def test_apply_write_unknown_approval(self):
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()

        with self.assertRaises(StructuredError) as ctx:
            core_write.apply_write(
                self.corpus, manifest, registry, policy, events, engine,
                approval_id="nonexistent", operator_id="op-user1",
                diff_input="dGVzdA==")
        self.assertEqual(ctx.exception.error_category, "audit_mismatch")

    def test_apply_write_not_approved(self):
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()
        approval_id = "app-1"
        diff_hash = "sha256:" + "c" * 64
        registry.issue_approval(
            approval_id=approval_id, target_ids=["alpha"],
            diff_hash=diff_hash, proposer_id="op-other", audit_id="aid-1")

        with self.assertRaises(StructuredError) as ctx:
            core_write.apply_write(
                self.corpus, manifest, registry, policy, events, engine,
                approval_id=approval_id, operator_id="op-user1",
                diff_input="dGVzdA==")
        self.assertEqual(ctx.exception.error_category, "gate_failure")

    def test_apply_write_hash_mismatch(self):
        """Approved diff_hash tampered in the registry → apply refuses with
        'approval_invalidated'.  The category assertion is checked OUTSIDE
        the assertRaises context — inside the with-block it never executes
        when the exception is raised (false-green bug fixed per fix plan p.29).
        The approval is NOT consumed before apply here (no prior successful
        apply), so the refusal comes from the diff-hash check, not token_replay.
        """
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()

        record = _make_audit_record("aid-1")
        registry.append("audit_record", record)
        diff_text = _make_diff()
        encoded = _encode_diff(diff_text)

        prop_result = core_write.propose_write(
            self.corpus, manifest, registry, policy, events, engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded, audit_id="aid-1",
            proposer_id="op-bot1",
        )
        approval_id = prop_result["approval_id"]
        core_write.approve(registry, policy, events, root=self.corpus,
                           approval_id=approval_id, operator_id="op-user1")

        # Tamper with the approval's diff_hash in the registry.
        approval = registry.find_approval(approval_id)
        self.assertIsNotNone(approval, "approval must exist before tampering")
        approval["diff_hash"] = "sha256:" + "z" * 64
        registry.append("token_record", dict(approval))

        with self.assertRaises(StructuredError) as ctx:
            core_write.apply_write(
                self.corpus, manifest, registry, policy, events, engine,
                approval_id=approval_id, operator_id="op-user1",
                diff_input=encoded)
        self.assertEqual(ctx.exception.error_category, "approval_invalidated")

    def test_apply_write_expired_approval(self):
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()
        approval_id = "app-1"
        diff_hash = "sha256:" + "d" * 64
        registry.issue_approval(
            approval_id=approval_id, target_ids=["alpha"],
            diff_hash=diff_hash, proposer_id="op-other", audit_id="aid-1")
        # Set decision=approved and backdate
        record = registry.find_approval(approval_id)
        record["decision"] = "approved"
        record["created_at"] = "2020-01-01T00:00:00Z"
        registry.append("token_record", record)

        with self.assertRaises(StructuredError) as ctx:
            core_write.apply_write(
                self.corpus, manifest, registry, policy, events, engine,
                approval_id=approval_id, operator_id="op-user1",
                diff_input="dGVzdA==")
        self.assertEqual(ctx.exception.error_category, "approval_expired")

    def test_apply_write_source_hash_mismatch(self):
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()

        # Create proposal
        record = _make_audit_record("aid-1")
        registry.append("audit_record", record)

        diff_text = _make_diff()
        encoded = _encode_diff(diff_text)

        prop_result = core_write.propose_write(
            self.corpus, manifest, registry, policy, events, engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded, audit_id="aid-1",
            proposer_id="op-bot1"
        )

        approval_id = prop_result["approval_id"]
        core_write.approve(registry, policy, events,
                           root=self.corpus,
                           approval_id=approval_id, operator_id="op-user1")

        # Use after_intent seam to tamper with staged file before hash check
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        staged_tampered = []
        def tamper_staged():
            staged_tampered.append(True)
            staged_dir = os.path.dirname(alpha_path)
            for fname in os.listdir(staged_dir):
                if fname.startswith(".index.md.") and fname.endswith(".tmp"):
                    staged_path = os.path.join(staged_dir, fname)
                    with open(staged_path, "w") as sf:
                        sf.write("tampered content\n")
                    return

        with self.assertRaises(StructuredError) as ctx:
            core_write.apply_write(
                self.corpus, manifest, registry, policy, events, engine,
                approval_id=approval_id, operator_id="op-user1",
                diff_input=encoded,
                data_dir=os.path.join(self.tmpdir, "documenter"),
                seams={"after_intent": tamper_staged})
        self.assertEqual(ctx.exception.error_category, "hash_mismatch")
        self.assertTrue(staged_tampered)

    def test_apply_write_staged_file_created(self):
        result, diff_input = self._full_cycle()
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        with open(alpha_path) as f:
            content = f.read()
        self.assertIn("changelog-path: CHANGELOGS/alpha.updated.md", content)

    def test_apply_write_uses_data_dir(self):
        data_dir = os.path.join(self.tmpdir, "documenter")
        result, diff_input = self._full_cycle()
        self.assertTrue(os.path.exists(data_dir))

    def test_apply_write_intent_record_appended(self):
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()
        record = _make_audit_record("aid-1")
        registry.append("audit_record", record)
        diff_text = _make_diff()
        encoded = _encode_diff(diff_text)

        prop_result = core_write.propose_write(
            self.corpus, manifest, registry, policy, events, engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded, audit_id="aid-1",
            proposer_id="op-bot1"
        )
        approval_id = prop_result["approval_id"]
        core_write.approve(registry, policy, events,
                           root=self.corpus,
                           approval_id=approval_id, operator_id="op-user1")

        core_write.apply_write(
            self.corpus, manifest, registry, policy, events, engine,
            approval_id=approval_id, operator_id="op-user1",
            diff_input=encoded,
            data_dir=os.path.join(self.tmpdir, "documenter"))

        records, _ = registry.read_all()
        intent_records = [r for r in records if r["record_type"] == "intent_record"]
        self.assertTrue(len(intent_records) >= 2)

    def test_apply_write_seam_after_stage(self):
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()
        record = _make_audit_record("aid-1")
        registry.append("audit_record", record)
        diff_text = _make_diff()
        encoded = _encode_diff(diff_text)

        prop_result = core_write.propose_write(
            self.corpus, manifest, registry, policy, events, engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded, audit_id="aid-1",
            proposer_id="op-bot1"
        )
        approval_id = prop_result["approval_id"]
        core_write.approve(registry, policy, events,
                           root=self.corpus,
                           approval_id=approval_id, operator_id="op-user1")

        hit = []
        seams = {"after_stage": lambda: hit.append(True)}
        core_write.apply_write(
            self.corpus, manifest, registry, policy, events, engine,
            approval_id=approval_id, operator_id="op-user1",
            diff_input=encoded, seams=seams,
            data_dir=os.path.join(self.tmpdir, "documenter"))
        self.assertTrue(hit)

    def test_apply_write_seam_after_intent(self):
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()
        record = _make_audit_record("aid-1")
        registry.append("audit_record", record)
        diff_text = _make_diff()
        encoded = _encode_diff(diff_text)

        prop_result = core_write.propose_write(
            self.corpus, manifest, registry, policy, events, engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded, audit_id="aid-1",
            proposer_id="op-bot1"
        )
        approval_id = prop_result["approval_id"]
        core_write.approve(registry, policy, events,
                           root=self.corpus,
                           approval_id=approval_id, operator_id="op-user1")

        hit = []
        seams = {"after_intent": lambda: hit.append(True)}
        core_write.apply_write(
            self.corpus, manifest, registry, policy, events, engine,
            approval_id=approval_id, operator_id="op-user1",
            diff_input=encoded, seams=seams,
            data_dir=os.path.join(self.tmpdir, "documenter"))
        self.assertTrue(hit)

    def test_apply_write_seam_before_rename(self):
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()
        record = _make_audit_record("aid-1")
        registry.append("audit_record", record)
        diff_text = _make_diff()
        encoded = _encode_diff(diff_text)

        prop_result = core_write.propose_write(
            self.corpus, manifest, registry, policy, events, engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded, audit_id="aid-1",
            proposer_id="op-bot1"
        )
        approval_id = prop_result["approval_id"]
        core_write.approve(registry, policy, events,
                           root=self.corpus,
                           approval_id=approval_id, operator_id="op-user1")

        hit = []
        seams = {"before_rename": lambda: hit.append(True)}
        core_write.apply_write(
            self.corpus, manifest, registry, policy, events, engine,
            approval_id=approval_id, operator_id="op-user1",
            diff_input=encoded, seams=seams,
            data_dir=os.path.join(self.tmpdir, "documenter"))
        self.assertTrue(hit)

    def test_apply_write_source_changed_between_propose_and_apply(self):
        """OCC: source file changed between propose and apply → hash_mismatch.

        The approval carries source_sha256 from propose; when apply reads
        the source file, if the hash differs it must raise hash_mismatch
        and NOT modify the target file.
        """
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()
        record = _make_audit_record("aid-1")
        registry.append("audit_record", record)
        diff_text = _make_diff()
        encoded = _encode_diff(diff_text)

        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha",
                                  "index.md")

        # propose_write → approval with source_sha256
        prop_result = core_write.propose_write(
            self.corpus, manifest, registry, policy, events, engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded, audit_id="aid-1",
            proposer_id="op-bot1"
        )
        approval_id = prop_result["approval_id"]

        # approve
        core_write.approve(registry, policy, events,
                           root=self.corpus,
                           approval_id=approval_id, operator_id="op-user1")

        # Read the original content
        with open(alpha_path) as f:
            original_content = f.read()

        # Tamper with the source file between approve and apply
        with open(alpha_path, "w") as f:
            f.write(original_content + "# injected line\n")

        with self.assertRaises(StructuredError) as ctx:
            core_write.apply_write(
                self.corpus, manifest, registry, policy, events, engine,
                approval_id=approval_id, operator_id="op-user1",
                diff_input=encoded,
                data_dir=os.path.join(self.tmpdir, "documenter"))
        self.assertEqual(ctx.exception.error_category, "hash_mismatch")

        # The file must NOT have been modified by the diff.
        with open(alpha_path) as f:
            content = f.read()
        # Should still contain the injected line, NOT the diff result.
        self.assertIn("injected line", content)

    def test_apply_write_approval_without_source_sha256(self):
        """Legacy approval without source_sha256 → approval_invalidated.

        When issue_approval is called directly (without extra) and the
        approval reaches apply_write at Tier 2, the missing source_sha256
        must trigger approval_invalidated.
        """
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(_make_briefing(self.tmpdir))
        events = StdoutEventSink()
        engine = StdDiffEngine()

        # Issue approval WITHOUT source_sha256 (simulating a legacy path).
        approval_id = "app-no-source"
        diff_hash = "sha256:" + "a" * 64
        registry.issue_approval(
            approval_id=approval_id,
            target_ids=["alpha"],
            diff_hash=diff_hash,
            proposer_id="op-proposer",
            audit_id="aid-1",
            extra=None,  # no source_sha256
        )
        # Mark as approved.
        record = registry.find_approval(approval_id)
        record["decision"] = "approved"
        registry.append(reg.TOKEN_RECORD, record)

        encoded = _encode_diff(_make_diff())
        with self.assertRaises(StructuredError) as ctx:
            core_write.apply_write(
                self.corpus, manifest, registry, policy, events, engine,
                approval_id=approval_id, operator_id="op-user1",
                diff_input=encoded,
                data_dir=os.path.join(self.tmpdir, "documenter"))
        self.assertEqual(ctx.exception.error_category, "approval_invalidated")


# ---------------------------------------------------------------------------
# Test class: TestReconcile
# ---------------------------------------------------------------------------

class TestReconcile(unittest.TestCase):
    """Unit tests for reconcile (core/write.py)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.corpus = os.path.join(self.tmpdir, "corpus")
        os.makedirs(os.path.join(self.corpus, "docs", "en", "alpha"))
        _enable_operator_ingress(self.corpus)
        with open(os.path.join(self.corpus, "docs", "en", "alpha", "index.md"), "w") as f:
            f.write("# Alpha\nid: alpha\nVersion: 1.0.0\nStatus: active\nchangelog-path: CHANGELOGS/alpha.md\n")
        _init_git_repo(self.corpus)
        self.data_dir = os.path.join(self.tmpdir, "documenter")
        self.manifest = _make_manifest()
        self.registry = _make_registry(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_reconcile_no_unresolved(self):
        results = core_write.reconcile(self.registry, self.manifest,
                                        self.corpus, self.data_dir)
        self.assertEqual(results, [])

    def test_reconcile_clean_hash(self):
        import hashlib
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        with open(alpha_path, "rb") as f:
            expected_sha = "sha256:" + hashlib.sha256(f.read()).hexdigest()
        intent = {
            "target_ids": ["alpha"],
            "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "per_file_sha256": {"alpha": expected_sha},
            "resolved": False,
        }
        self.registry.append("intent_record", intent)

        results = core_write.reconcile(self.registry, self.manifest,
                                        self.corpus, self.data_dir)
        self.assertEqual(results, [])

    def test_reconcile_clean_hash_include_resolved(self):
        import hashlib
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        with open(alpha_path, "rb") as f:
            expected_sha = "sha256:" + hashlib.sha256(f.read()).hexdigest()
        intent = {
            "target_ids": ["alpha"],
            "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "per_file_sha256": {"alpha": expected_sha},
            "resolved": False,
        }
        self.registry.append("intent_record", intent)

        results = core_write.reconcile(
            self.registry, self.manifest, self.corpus, self.data_dir,
            include_resolved=True)
        self.assertEqual([r["status"] for r in results], ["reconciled"])

    def test_reconcile_idempotent_with_include_resolved(self):
        import hashlib
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        with open(alpha_path, "rb") as f:
            expected_sha = "sha256:" + hashlib.sha256(f.read()).hexdigest()
        intent = {
            "target_ids": ["alpha"],
            "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "per_file_sha256": {"alpha": expected_sha},
            "resolved": False,
        }
        self.registry.append("intent_record", intent)

        first = core_write.reconcile(
            self.registry, self.manifest, self.corpus, self.data_dir,
            include_resolved=True)
        self.assertEqual([r["status"] for r in first], ["reconciled"])
        second = core_write.reconcile(
            self.registry, self.manifest, self.corpus, self.data_dir,
            include_resolved=True)
        self.assertEqual(second, [])

    def test_reconcile_hash_mismatch(self):
        intent = {
            "target_ids": ["alpha"],
            "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "per_file_sha256": {"alpha": "sha256:" + "0" * 64},
            "resolved": False,
        }
        self.registry.append("intent_record", intent)

        results = core_write.reconcile(self.registry, self.manifest,
                                        self.corpus, self.data_dir)
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["status"], "needs_attention")
        self.assertIn("hash mismatch", results[0]["detail"])

    def test_reconcile_resolved_intent_appended(self):
        import hashlib
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        with open(alpha_path, "rb") as f:
            expected_sha = "sha256:" + hashlib.sha256(f.read()).hexdigest()

        intent = {
            "target_ids": ["alpha"],
            "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "per_file_sha256": {"alpha": expected_sha},
            "resolved": False,
        }
        self.registry.append("intent_record", intent)

        core_write.reconcile(self.registry, self.manifest,
                              self.corpus, self.data_dir)

        records, _ = self.registry.read_all()
        intent_records = [r for r in records if r["record_type"] == "intent_record"]
        resolved = [r for r in intent_records if r["data"].get("resolved")]
        self.assertTrue(len(resolved) > 0)

    def test_reconcile_manifest_missing(self):
        manifest_bad = _make_manifest(["alpha"])
        del manifest_bad._entries["alpha"]
        intent = {
            "target_ids": ["alpha"],
            "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "per_file_sha256": {},
            "resolved": False,
        }
        self.registry.append("intent_record", intent)

        results = core_write.reconcile(self.registry, manifest_bad,
                                        self.corpus, self.data_dir)
        self.assertTrue(len(results) > 0)
        self.assertIn("not found", results[0]["detail"])

    def test_reconcile_uses_data_dir(self):
        import hashlib
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        with open(alpha_path, "rb") as f:
            expected_sha = "sha256:" + hashlib.sha256(f.read()).hexdigest()
        intent = {
            "target_ids": ["alpha"],
            "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "per_file_sha256": {"alpha": expected_sha},
            "resolved": False,
        }
        self.registry.append("intent_record", intent)

        core_write.reconcile(self.registry, self.manifest,
                              self.corpus, self.data_dir)
        self.assertTrue(os.path.exists(self.data_dir))


# ---------------------------------------------------------------------------
# Test class: TestServiceWriteBranch (Service-level delegate/approve/apply)
# ---------------------------------------------------------------------------

class TestServiceWriteBranch(unittest.TestCase):
    """Service wiring: preview parity, write-branch guards, apply ingress."""

    DOC = ("# Alpha\nid: alpha\nVersion: 1.0.0\nStatus: active\n"
           "changelog-path: CHANGELOGS/alpha.md\n")

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.corpus = os.path.join(self.tmpdir, "corpus")
        os.makedirs(os.path.join(self.corpus, "docs", "en", "alpha"))
        _enable_operator_ingress(self.corpus)
        with open(os.path.join(self.corpus, "docs", "en", "alpha",
                               "index.md"), "w") as f:
            f.write(self.DOC)
        _init_git_repo(self.corpus)
        self.data_dir = os.path.join(self.tmpdir, "state")
        self.policy_path = os.path.join(self.tmpdir, "pol.yml")
        self.briefing = _make_briefing(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _write_policy(self, tier=2):
        import yaml
        ops = ([{"change_type": "update", "targets": ["alpha"],
                 "trust_level": "safe"}] if tier >= 2 else [])
        doc = {"documenter_policy": {
            "version": "0.2.0", "active_tier": tier,
            "allowed_operations": ops,
            "audit_freshness": 30, "approval_expiry_window": 30,
            "max_diff_bytes": 524288, "lock_wait_timeout": 5,
            "briefing_ref": self.briefing if tier >= 2 else None}}
        with open(self.policy_path, "w") as f:
            yaml.safe_dump(doc, f)

    def _service(self, env_extra=None):
        env = dict(os.environ)
        env["DOCUMENTER_POLICY_PATH"] = self.policy_path
        env["DOCUMENTER_DATA_DIR"] = self.data_dir
        env.pop("COUNCIL_OPERATOR_ID", None)
        if env_extra:
            env.update(env_extra)
        return Service(self.corpus, env=env,
                       registry=JsonlAuditRegistry(self.data_dir),
                       manifest=_make_manifest(),
                       events=StdoutEventSink(io.StringIO()))

    def _diff(self):
        return _encode_diff(_make_diff(doc_text=self.DOC))

    def _seed_audit(self, svc, audit_id="aid-1"):
        svc.registry.append("audit_record", _make_audit_record(audit_id))

    def test_preview_false_policy_low_tier_interlock(self):
        self._write_policy(tier=1)
        svc = self._service(env_extra={"COUNCIL_OPERATOR_ID": "op-test"})
        self._seed_audit(svc)
        with self.assertRaises(StructuredError) as ctx:
            svc.delegate(target_id="alpha", change_type="update",
                         trust_level="safe", diff_input=self._diff(),
                         preview=False, audit_id="aid-1")
        self.assertEqual(ctx.exception.error_category, "tier_interlock")

    def test_preview_false_happy_then_apply_via_delegate(self):
        self._write_policy(tier=2)
        svc = self._service(env_extra={"COUNCIL_OPERATOR_ID": "op-test"})
        self._seed_audit(svc)
        diff = self._diff()
        prop = svc.delegate(target_id="alpha", change_type="update",
                            trust_level="safe", diff_input=diff,
                            preview=False, audit_id="aid-1")
        self.assertEqual(prop["next_action"], "await_approval")
        self.assertTrue(prop["approval_required"])
        # still unapplied
        with open(os.path.join(self.corpus, "docs", "en", "alpha",
                               "index.md")) as f:
            self.assertIn("CHANGELOGS/alpha.md\n", f.read())
        # approve out-of-band (different principal than apply ingress test)
        appr = svc.approve(prop["approval_id"], operator_id="op-approver")
        self.assertEqual(appr["decision"], "approved")
        # apply through delegate(preview=False, approval_id=...) WITHOUT
        # authenticated ingress → unknown (target_id is not a principal)
        svc_nop = self._service()
        svc_nop.registry = svc.registry
        with self.assertRaises(StructuredError) as ctx:
            svc_nop.delegate(target_id="alpha", change_type="update",
                             trust_level="safe", diff_input=diff,
                             preview=False, audit_id="aid-1",
                             approval_id=prop["approval_id"])
        self.assertEqual(ctx.exception.error_category, "unknown")
        # now with authenticated ingress
        svc2 = self._service(env_extra={"COUNCIL_OPERATOR_ID": "op-approver2"})
        svc2.registry = svc.registry
        result = svc2.delegate(target_id="alpha", change_type="update",
                               trust_level="safe", diff_input=diff,
                               preview=False, audit_id="aid-1",
                               approval_id=prop["approval_id"])
        self.assertEqual(result["next_action"], "write_applied")
        self.assertTrue(result["applied"])
        with open(os.path.join(self.corpus, "docs", "en", "alpha",
                               "index.md")) as f:
            self.assertIn("CHANGELOGS/alpha.updated.md", f.read())

    def test_preview_true_path_unchanged(self):
        """Regression: preview path byte-compatible with pre-W2 behavior."""
        self._write_policy(tier=1)
        svc = self._service()
        resp = svc.delegate(target_id="alpha", change_type="update",
                            trust_level="safe", diff_input=self._diff(),
                            preview=True)
        self.assertEqual(resp["next_action"], "preview_only")
        self.assertNotIn("approval_required", resp)


# ---------------------------------------------------------------------------
# P.11: match_operation strictest + propose_write policy floor
# ---------------------------------------------------------------------------


class TestMatchOperationStrictest(unittest.TestCase):
    """match_operation returns the STRICTEST (highest trust_level) match."""

    def test_wildcard_first_specific_second_returns_specific_stricter(self):
        """Wildcard safe first, target-specific review second → review."""
        policy = Policy({
            "version": "0.2.0",
            "active_tier": 2,
            "allowed_operations": [
                {"change_type": "update", "targets": [], "trust_level": "safe"},
                {"change_type": "update", "targets": ["alpha"], "trust_level": "review"},
            ],
            "briefing_ref": "_b.md",
            "audit_freshness": 30, "approval_expiry_window": 30,
            "max_diff_bytes": 524288, "lock_wait_timeout": 30,
        })
        result = match_operation(policy, change_type="update", target_id="alpha")
        self.assertEqual(result["trust_level"], "review")
        self.assertEqual(result["targets"], ["alpha"])

    def test_specific_first_wildcard_second_returns_specific_stricter(self):
        """Target-specific review first, wildcard safe second → review."""
        policy = Policy({
            "version": "0.2.0",
            "active_tier": 2,
            "allowed_operations": [
                {"change_type": "update", "targets": ["alpha"], "trust_level": "review"},
                {"change_type": "update", "targets": [], "trust_level": "safe"},
            ],
            "briefing_ref": "_b.md",
            "audit_freshness": 30, "approval_expiry_window": 30,
            "max_diff_bytes": 524288, "lock_wait_timeout": 30,
        })
        result = match_operation(policy, change_type="update", target_id="alpha")
        self.assertEqual(result["trust_level"], "review")
        self.assertEqual(result["targets"], ["alpha"])

    def test_wildcard_earlier_same_trust_returns_earlier(self):
        """Both safe, wildcard first → first (safe) returned."""
        policy = Policy({
            "version": "0.2.0",
            "active_tier": 2,
            "allowed_operations": [
                {"change_type": "update", "targets": [], "trust_level": "safe"},
                {"change_type": "update", "targets": ["alpha"], "trust_level": "safe"},
            ],
            "briefing_ref": "_b.md",
            "audit_freshness": 30, "approval_expiry_window": 30,
            "max_diff_bytes": 524288, "lock_wait_timeout": 30,
        })
        result = match_operation(policy, change_type="update", target_id="alpha")
        self.assertEqual(result["trust_level"], "safe")
        self.assertEqual(result["targets"], [])  # wildcard first

    def test_no_match_returns_none(self):
        """No matching entry → None."""
        policy = Policy({
            "version": "0.2.0",
            "active_tier": 2,
            "allowed_operations": [
                {"change_type": "update", "targets": [], "trust_level": "safe"},
            ],
            "briefing_ref": "_b.md",
            "audit_freshness": 30, "approval_expiry_window": 30,
            "max_diff_bytes": 524288, "lock_wait_timeout": 30,
        })
        self.assertIsNone(match_operation(policy, change_type="split", target_id="alpha"))


class TestProposeWritePolicyFloor(unittest.TestCase):
    """propose_write rejects trust_level below policy entry floor (P.11b)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.corpus = os.path.join(self.tmpdir, "docs")
        os.makedirs(self.corpus)
        # Create the alpha fixture document (matches _make_diff expectations)
        alpha_dir = os.path.join(self.corpus, "en", "alpha")
        os.makedirs(alpha_dir)
        with open(os.path.join(alpha_dir, "index.md"), "w") as f:
            f.write("# Alpha\nid: alpha\nVersion: 1.0.0\nStatus: active\nchangelog-path: CHANGELOGS/alpha.md\n")
        # Briefing
        self.briefing_path = os.path.join(self.tmpdir, "_briefing.md")
        with open(self.briefing_path, "w") as f:
            f.write("# Briefing\n\nAuthorised operational context.\n")
        # _enable_operator_ingress
        _enable_operator_ingress(self.tmpdir)
        _init_git_repo(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_manifest(self):
        return _make_manifest(["alpha"])

    def _make_audit_record(self):
        return _make_audit_record("aud-1", scope="*")

    def test_floor_safe_below_review_proposal_rejected(self):
        """Tier2 policy with [alpha review] first, wildcard safe second.
        propose_write(safe) → StructuredError trust_mismatch (even mechanical diff).
        """
        # Use policy where [targets ["alpha"] review] is FIRST, wildcard safe is second.
        policy = Policy({
            "version": "0.2.0",
            "active_tier": 2,
            "allowed_operations": [
                {"change_type": "update", "targets": ["alpha"], "trust_level": "review"},
                {"change_type": "update", "targets": [], "trust_level": "safe"},
            ],
            "briefing_ref": self.briefing_path,
            "audit_freshness": 30, "approval_expiry_window": 30,
            "max_diff_bytes": 524288, "lock_wait_timeout": 30,
        })
        manifest = self._make_manifest()
        registry = _make_registry(os.path.join(self.tmpdir, "state"))
        registry.append("audit_record", self._make_audit_record())
        engine = StdDiffEngine()
        events = StdoutEventSink(sys.stderr)

        diff_text = _make_diff()
        diff_b64 = _encode_diff(diff_text)

        # safe → rejected (policy floor = review)
        with self.assertRaises(StructuredError) as ctx:
            core_write.propose_write(
                self.tmpdir, manifest, registry, policy, events, engine,
                target_id="alpha", change_type="update",
                trust_level="safe", diff_input=diff_b64,
                audit_id="aud-1", proposer_id="op-bot1",
        )
        self.assertEqual(ctx.exception.error_category, "trust_mismatch")
        self.assertIn("policy entry floor", ctx.exception.message)

    def test_floor_review_proposal_passes(self):
        """Same policy but review → passes (not below floor)."""
        policy = Policy({
            "version": "0.2.0",
            "active_tier": 2,
            "allowed_operations": [
                {"change_type": "update", "targets": ["alpha"], "trust_level": "review"},
                {"change_type": "update", "targets": [], "trust_level": "safe"},
            ],
            "briefing_ref": self.briefing_path,
            "audit_freshness": 30, "approval_expiry_window": 30,
            "max_diff_bytes": 524288, "lock_wait_timeout": 30,
        })
        manifest = self._make_manifest()
        registry = _make_registry(os.path.join(self.tmpdir, "state"))
        registry.append("audit_record", self._make_audit_record())
        engine = StdDiffEngine()
        events = StdoutEventSink(sys.stderr)

        diff_text = _make_diff()
        diff_b64 = _encode_diff(diff_text)

        # review → passes (equal to floor)
        result = core_write.propose_write(
            self.tmpdir, manifest, registry, policy, events, engine,
            target_id="alpha", change_type="update",
            trust_level="review", diff_input=diff_b64,
            audit_id="aud-1", proposer_id="op-bot1",
        )
        self.assertEqual(result["next_action"], "await_approval")
        self.assertTrue(result["approval_required"])

    def test_regression_existing_tier2_policy_safe_passes(self):
        """Existing _make_tier2_policy: [alpha safe] first, [wildcard review] second.
        propose(safe) → passes because strictest for alpha == safe.
        """
        policy = _make_tier2_policy(self.briefing_path)
        manifest = self._make_manifest()
        registry = _make_registry(os.path.join(self.tmpdir, "state"))
        registry.append("audit_record", self._make_audit_record())
        engine = StdDiffEngine()
        events = StdoutEventSink(sys.stderr)

        diff_text = _make_diff()
        diff_b64 = _encode_diff(diff_text)

        # Regression: safe is still accepted because strictest for alpha is safe.
        result = core_write.propose_write(
            self.tmpdir, manifest, registry, policy, events, engine,
            target_id="alpha", change_type="update",
            trust_level="safe", diff_input=diff_b64,
            audit_id="aud-1", proposer_id="op-bot1",
        )
        self.assertEqual(result["next_action"], "await_approval")
        self.assertTrue(result["approval_required"])
