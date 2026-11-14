"""Tests for changeset create operations (missing before_hash sentinel).

Covers:
  A.  Create: changeset creates a file that does not exist on disk
      → propose with before_hash="missing", apply succeeds, file created.
  B.  Create + seam crash at before_rename → reconcile rolls forward
      the create (branch-2: current_sha == before_hash == "missing").
  C.  Scope guard: changeset touching a non-target file → unknown.
  D.  changeset_paths in approval record (Task C).

Run with: python3 -m pytest tests/test_documenter_changeset_create.py -q
"""
import base64
import hashlib
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

from documenter_service.adapters.diff_engine import StdDiffEngine  # noqa: E402
from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry  # noqa: E402
from documenter_service.adapters.stdout_events import StdoutEventSink  # noqa: E402
from documenter_service.core.errors import StructuredError  # noqa: E402
from documenter_service.core import write as core_write  # noqa: E402


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures',
                        'documenter')
CORPUS_FIXTURES = os.path.join(FIXTURES, 'corpus')


def _enable_operator_surface(root: str) -> str:
    """Create the ADR-013 Operator Surface readiness sentinel."""
    sentinel = os.path.join(root, "documenter", ".operator_surface_ready")
    os.makedirs(os.path.dirname(sentinel), exist_ok=True)
    with open(sentinel, "w") as f:
        f.write("")
    return sentinel


def _init_git_repo(root: str) -> None:
    """Initialise root as a git repo (quietly)."""
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


def _make_manifest():
    """Create an in-memory manifest with alpha and beta (scope tests need beta tracked but not in alpha scope).

    alpha's changelog-path points to CHANGELOGS/new.changes.md (a file that will NOT
    exist on disk during tests — this is the create scenario where before_hash="missing").
    """
    entries_list = []
    manifest = type("Manifest", (), {
        "_entries": {},
        "entries": lambda self: entries_list,
        "resolve": lambda self, tid: self._entries.get(tid),
    })()
    entry = {
        "id": "alpha",
        "path": "docs/en/alpha/index.md",
        "title": "Alpha Document",
        "version": "1.0.0",
        "status": "active",
        "changelog-path": "CHANGELOGS/new.changes.md",
    }
    entries_list.append(entry)
    manifest._entries["alpha"] = entry
    # Beta: tracked in manifest but OUTSIDE alpha's scope.
    manifest._entries["beta"] = {
        "id": "beta",
        "path": "docs/en/beta/index.md",
        "title": "Beta Document",
        "version": "1.0.0",
        "status": "active",
        "changelog-path": "CHANGELOGS/beta.changes.md",
    }
    entries_list.append(manifest._entries["beta"])
    return manifest


def _make_registry(tmpdir):
    return JsonlAuditRegistry(tmpdir)


def _make_tier2_policy(briefing_path=None):
    fields = {
        "version": "0.2.0",
        "active_tier": 2,
        "allowed_operations": [
            {"change_type": "update", "targets": ["alpha"], "trust_level": "safe"},
            {"change_type": "update", "targets": [], "trust_level": "review"},
        ],
        "briefing_ref": briefing_path or "_briefing.md",
        "audit_freshness": 30,
        "approval_expiry_window": 30,
        "max_diff_bytes": 524288,
        "lock_wait_timeout": 30,
    }
    return type("Policy", (), {"_fields": fields, "get": lambda s, k, d=None: s._fields.get(k, d)})()


def _make_audit_record(audit_id="aid-1", issued_at=None):
    now = issued_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "audit_id": audit_id,
        "issued_at": now,
        "scope": "*",
        "findings": [],
        "scanned_ids": ["alpha", "beta", "gamma"],
        "has_remaining": False,
    }


def _make_diff(doc_text=None):
    if doc_text is None:
        doc_text = "# Alpha\nid: alpha\nVersion: 1.0.0\nStatus: active\nchangelog-path: CHANGELOGS/alpha.md\n"
    old_lines = doc_text.split("\n")
    effective_lines = old_lines[:-1] if old_lines and old_lines[-1] == "" else old_lines
    hunk_header = "@@ -1," + str(len(effective_lines)) + " +1," + str(len(effective_lines)) + " @@\n"
    effective_diff = []
    for line in effective_lines:
        if "changelog-path: CHANGELOGS/alpha.md" in line:
            effective_diff.append("-" + line)
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


# ---------------------------------------------------------------------------
# Test class: TestChangesetCreateOperations
# ---------------------------------------------------------------------------

class TestChangesetCreateOperations(unittest.TestCase):
    """Tests for changeset create operations (missing before_hash sentinel)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.corpus = os.path.join(self.tmpdir, "corpus")
        os.makedirs(os.path.join(self.corpus, "documenter"))
        _enable_operator_surface(self.corpus)

        os.makedirs(os.path.join(self.corpus, "docs", "en", "alpha"))
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        self.alpha_content = (
            "# Alpha\nid: alpha\nVersion: 1.0.0\nStatus: active\n"
            "changelog-path: CHANGELOGS/alpha.md\n")
        with open(alpha_path, "w") as f:
            f.write(self.alpha_content)

        os.makedirs(os.path.join(self.corpus, "CHANGELOGS"))
        with open(os.path.join(self.corpus, "CHANGELOGS", "alpha.changes.md"), "w") as f:
            f.write("## Alpha Changelog\n\nOriginal content.\n")

        with open(os.path.join(self.corpus, "documenter", "hashes.json"), "w") as f:
            f.write('{"state": "ok"}\n')

        _init_git_repo(self.corpus)

        self.data_dir = os.path.join(self.tmpdir, "documenter")
        self.briefing = os.path.join(self.tmpdir, "_briefing.md")
        with open(self.briefing, "w") as f:
            f.write("# Briefing\n\nAuthorised operational context.\n")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    # -- Test A: Create new file in changeset --------------------------------

    def test_create_new_file_in_changeset(self):
        """Case A: changeset creates a file that does NOT exist on disk.

        Propose → approve → apply → file created, intents closed.
        """
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(self.briefing)
        events = StdoutEventSink()
        engine = StdDiffEngine()

        registry.append("audit_record", _make_audit_record("aid-1"))

        # Changeset: create a NEW file (does not exist on disk)
        new_content = b"## New Changelog\n\nCreated by changeset.\n"
        changeset = [
            {"path": "CHANGELOGS/new.changes.md",
             "content_b64": base64.b64encode(new_content).decode("ascii")},
        ]

        diff_text = _make_diff(doc_text=self.alpha_content)
        encoded = _encode_diff(diff_text)

        # Propose
        prop_result = core_write.propose_write(
            self.corpus, manifest, registry, policy, events, engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded, audit_id="aid-1", changeset=changeset)

        self.assertTrue(prop_result["approval_required"])
        self.assertEqual(prop_result["next_action"], "await_approval")
        approval_id = prop_result["approval_id"]

        # Verify: new file NOT created yet
        self.assertFalse(os.path.exists(
            os.path.join(self.corpus, "CHANGELOGS", "new.changes.md")))

        # Verify digest was stored
        approval_data = registry.find_approval(approval_id)
        self.assertIsNotNone(approval_data.get("changeset_digest"))

        # Approve
        core_write.approve(registry, policy, events,
                           root=self.corpus,
                           approval_id=approval_id, operator_id="op-user1")

        # Apply
        result = core_write.apply_write(
            self.corpus, manifest, registry, policy, events, engine,
            approval_id=approval_id, operator_id="op-user1",
            diff_input=encoded, data_dir=self.data_dir,
            changeset=changeset)

        self.assertTrue(result["applied"])
        self.assertEqual(result["target_id"], "alpha")

        # Verify new file created
        self.assertTrue(os.path.exists(
            os.path.join(self.corpus, "CHANGELOGS", "new.changes.md")))
        with open(os.path.join(self.corpus, "CHANGELOGS", "new.changes.md")) as f:
            self.assertEqual(f.read(), new_content.decode("utf-8"))

        # Verify cleanup: intent file removed, approval consumed
        intent_file = os.path.join(self.data_dir, "intent", f"intent_{approval_id}.json")
        self.assertFalse(os.path.exists(intent_file))

        approval = registry.find_approval(approval_id)
        self.assertTrue(approval.get("consumed"))

    # -- Test A.2: Create + seam crash before_rename → reconcile ------------

    def test_create_seam_crash_before_rename_reconcile(self):
        """Case A.2: Crash at before_rename seam → reconcile rolls forward
        the create operation (branch-2: current_sha == before_hash == "missing").
        """
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(self.briefing)
        events = StdoutEventSink()
        engine = StdDiffEngine()

        registry.append("audit_record", _make_audit_record("aid-1"))

        new_content = b"## New Changelog\n\nCreated by changeset.\n"
        changeset = [
            {"path": "CHANGELOGS/new.changes.md",
             "content_b64": base64.b64encode(new_content).decode("ascii")},
        ]

        diff_text = _make_diff(doc_text=self.alpha_content)
        encoded = _encode_diff(diff_text)

        prop_result = core_write.propose_write(
            self.corpus, manifest, registry, policy, events, engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded, audit_id="aid-1", changeset=changeset)
        approval_id = prop_result["approval_id"]

        core_write.approve(registry, policy, events,
                           root=self.corpus,
                           approval_id=approval_id, operator_id="op-user1")

        # Simulate crash at before_rename: manually stage files and create intent
        import uuid as _uuid
        tx_id = _uuid.uuid4().hex

        from documenter_service.adapters import commit_protocol as _cp
        from documenter_service.adapters.applier import apply_unified_diff
        from hashlib import sha256 as _sha256

        # Stage the new file
        staged_new_tmp = _cp.stage_bytes(
            self.corpus, "CHANGELOGS/new.changes.md", new_content, tx_id)

        # Read source and apply diff for target
        with open(os.path.join(self.corpus, "docs", "en", "alpha", "index.md"), "rb") as f:
            source_bytes = f.read()
        staged_new_text = apply_unified_diff(
            source_bytes.decode("utf-8"), diff_text)
        staged_target_tmp = _cp.stage_bytes(
            self.corpus, "docs/en/alpha/index.md", staged_new_text.encode("utf-8"), tx_id)

        staged_new_sha = "sha256:" + _sha256(new_content).hexdigest()
        staged_target_sha = "sha256:" + _sha256(
            staged_new_text.encode("utf-8")).hexdigest()
        source_sha = "sha256:" + _sha256(source_bytes).hexdigest()

        staged_entries = [
            {"path": "docs/en/alpha/index.md",
             "tmp_path": staged_target_tmp,
             "before_hash": source_sha,
             "after_hash": staged_target_sha},
            {"path": "CHANGELOGS/new.changes.md",
             "tmp_path": staged_new_tmp,
             "before_hash": core_write.BEFORE_HASH_MISSING,
             "after_hash": staged_new_sha},
        ]

        intent_record = {
            "tx_id": tx_id,
            "target_id": "alpha",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "entries": staged_entries,
        }

        # Verify intent structure is valid
        self.assertTrue(_cp._valid_intent(intent_record))

        _cp.write_intent(self.data_dir, tx_id, intent_record)

        # Reconcile should roll forward the create (branch-2)
        results = core_write.reconcile(
            registry, manifest, self.corpus, self.data_dir,
            sha256_func=lambda b: "sha256:" + _sha256(b).hexdigest())

        self.assertEqual(results, [])

        # Verify: new file was created by roll-forward
        self.assertTrue(os.path.exists(
            os.path.join(self.corpus, "CHANGELOGS", "new.changes.md")))
        with open(os.path.join(self.corpus, "CHANGELOGS", "new.changes.md")) as f:
            self.assertEqual(f.read(), new_content.decode("utf-8"))

        # Verify intent cleaned up
        intent_files = ([f for f in os.listdir(os.path.join(self.data_dir, "intent"))
                        if f.endswith(".json")]
                        if os.path.isdir(os.path.join(self.data_dir, "intent")) else [])
        self.assertFalse(intent_files)

    # -- Test B: Scope guard rejects non-target path ------------------------

    def test_scope_guard_rejects_non_target(self):
        """Case B: Changeset touches a file outside the target scope.

        Target is alpha, but changeset includes docs/en/beta/index.md →
        propose fails with StructuredError("unknown").
        """
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(self.briefing)
        events = StdoutEventSink()
        engine = StdDiffEngine()

        registry.append("audit_record", _make_audit_record("aid-1"))

        # Beta file does NOT exist in the manifest's allowed scope for alpha,
        # even though the manifest itself has "beta" as a doc_id we could add.
        # Here we use a path that is NOT in the scope of target "alpha".
        changeset = [
            {"path": "docs/en/beta/index.md",
             "content_b64": base64.b64encode(b"beta content").decode("ascii")},
        ]

        diff_text = _make_diff(doc_text=self.alpha_content)
        encoded = _encode_diff(diff_text)

        with self.assertRaises(StructuredError) as ctx:
            core_write.propose_write(
                self.corpus, manifest, registry, policy, events, engine,
                target_id="alpha", change_type="update", trust_level="safe",
                diff_input=encoded, audit_id="aid-1", changeset=changeset)

        self.assertEqual(ctx.exception.error_category, "unknown")
        self.assertIn("outside the target scope", ctx.exception.message)
        self.assertIn("beta", ctx.exception.message)
        self.assertIn("alpha", ctx.exception.message)

    def test_scope_guard_rejects_foreign_changelog_same_dir(self):
        """A sibling document's changelog in CHANGELOGS/ is NOT in alpha's
        scope even though it shares the CHANGELOGS/ directory (exact-path
        allow-list, not directory prefixes)."""
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(self.briefing)
        events = StdoutEventSink()
        engine = StdDiffEngine()
        registry.append("audit_record", _make_audit_record("aid-1"))

        changeset = [
            {"path": "CHANGELOGS/beta.changes.md",
             "content_b64": base64.b64encode(b"beta log").decode("ascii")},
        ]
        diff_text = _make_diff(doc_text=self.alpha_content)
        encoded = _encode_diff(diff_text)

        with self.assertRaises(StructuredError) as ctx:
            core_write.propose_write(
                self.corpus, manifest, registry, policy, events, engine,
                target_id="alpha", change_type="update", trust_level="safe",
                diff_input=encoded, audit_id="aid-1", changeset=changeset)
        self.assertEqual(ctx.exception.error_category, "unknown")
        self.assertIn("outside the target scope", ctx.exception.message)

    # -- Test B.2: Scope guard allows docs-manifest.yaml --------------------

    def test_scope_guard_allows_manifest(self):
        """Case B.2: Changeset including docs-manifest.yaml passes scope gate."""
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(self.briefing)
        events = StdoutEventSink()
        engine = StdDiffEngine()

        registry.append("audit_record", _make_audit_record("aid-1"))

        # docs-manifest.yaml is always allowed
        changeset = [
            {"path": "docs-manifest.yaml",
             "content_b64": base64.b64encode(b"{}").decode("ascii")},
        ]

        diff_text = _make_diff(doc_text=self.alpha_content)
        encoded = _encode_diff(diff_text)

        # This should NOT raise unknown from scope guard.
        # It may fail later for other reasons (e.g., operation not allowed),
        # but the scope check itself passes.
        try:
            core_write.propose_write(
                self.corpus, manifest, registry, policy, events, engine,
                target_id="alpha", change_type="update", trust_level="safe",
                diff_input=encoded, audit_id="aid-1", changeset=changeset)
        except StructuredError as exc:
            # Should NOT be from scope guard
            self.assertNotEqual(exc.error_category, "unknown",
                                "scope guard should pass for docs-manifest.yaml")
            self.assertNotIn("outside the target scope", exc.message)

    # -- Test B.3: Scope guard allows changelog -----------------------------

    def test_scope_guard_allows_changelog(self):
        """Case B.3: Changeset including the target's changelog passes scope gate.
        
        Since manifest entry has changelog-path="CHANGELOGS/new.changes.md",
        this path is within the target scope of "alpha".
        """
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(self.briefing)
        events = StdoutEventSink()
        engine = StdDiffEngine()

        registry.append("audit_record", _make_audit_record("aid-1"))

        changeset = [
            {"path": "CHANGELOGS/new.changes.md",
             "content_b64": base64.b64encode(b"changelog content").decode("ascii")},
        ]

        diff_text = _make_diff(doc_text=self.alpha_content)
        encoded = _encode_diff(diff_text)

        try:
            core_write.propose_write(
                self.corpus, manifest, registry, policy, events, engine,
                target_id="alpha", change_type="update", trust_level="safe",
                diff_input=encoded, audit_id="aid-1", changeset=changeset)
        except StructuredError as exc:
            self.assertNotEqual(exc.error_category, "unknown",
                                "scope guard should pass for target changelog")
            self.assertNotIn("outside the target scope", exc.message)

    # -- Test C: changeset_paths in approval record -------------------------

    def test_changeset_paths_in_approval(self):
        """Case C: propose_write stores changeset_paths in approval extra dict.
        
        After propose, registry.find_approval(approval_id).get("changeset_paths")
        returns the sorted list of normalized changeset paths (excluding target).
        """
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(self.briefing)
        events = StdoutEventSink()
        engine = StdDiffEngine()

        registry.append("audit_record", _make_audit_record("aid-1"))

        new_content = b"## New Changelog\n\nCreated by changeset.\n"
        hashes_content = b'{"state": "ok"}\n'
        changeset = [
            {"path": "CHANGELOGS/new.changes.md",
             "content_b64": base64.b64encode(new_content).decode("ascii")},
            {"path": "documenter/hashes.json",
             "content_b64": base64.b64encode(hashes_content).decode("ascii")},
        ]

        diff_text = _make_diff(doc_text=self.alpha_content)
        encoded = _encode_diff(diff_text)

        prop_result = core_write.propose_write(
            self.corpus, manifest, registry, policy, events, engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded, audit_id="aid-1", changeset=changeset)

        self.assertTrue(prop_result["approval_required"])
        approval_id = prop_result["approval_id"]

        # Verify changeset_paths in approval record
        approval_data = registry.find_approval(approval_id)
        self.assertIsNotNone(approval_data.get("changeset_paths"))
        self.assertEqual(
            approval_data["changeset_paths"],
            sorted(["CHANGELOGS/new.changes.md", "documenter/hashes.json"])
        )

    # -- Test A.3: Create a file that already exists → hash_mismatch ----------

    def test_create_file_already_exists(self):
        """Case A.3: changeset tries to create a file that already exists on
        disk. The propose gets before_hash=actual_sha256 (not "missing"),
        but we force the scenario: the digest expects "missing" because the
        proposal was made when the file was absent, then the file appeared
        between propose and apply.

        More reliably: propose for a create when the file exists → the before_hash
        is the actual sha, so apply succeeds (it's NOT a create in that case).
        Instead, we test the scenario: propose (create), approve, then create the
        file before apply → apply detects before_hash mismatch → approval_invalidated
        because the digest no longer matches.
        """
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        policy = _make_tier2_policy(self.briefing)
        events = StdoutEventSink()
        engine = StdDiffEngine()

        registry.append("audit_record", _make_audit_record("aid-1"))

        # CHANGELOGS/new.changes.md does NOT exist → create scenario
        new_content = b"## New Changelog\n\nCreated by changeset.\n"
        changeset = [
            {"path": "CHANGELOGS/new.changes.md",
             "content_b64": base64.b64encode(new_content).decode("ascii")},
        ]

        diff_text = _make_diff(doc_text=self.alpha_content)
        encoded = _encode_diff(diff_text)

        prop_result = core_write.propose_write(
            self.corpus, manifest, registry, policy, events, engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded, audit_id="aid-1", changeset=changeset)
        approval_id = prop_result["approval_id"]

        # Approve
        core_write.approve(registry, policy, events,
                           root=self.corpus,
                           approval_id=approval_id, operator_id="op-user1")

        # Now create the file BEFORE apply → before_hash in digest was "missing"
        # but at apply time the file exists → the recomputed before_hash differs
        # → recomputed digest != stored digest → approval_invalidated.
        with open(os.path.join(self.corpus, "CHANGELOGS", "new.changes.md"), "w") as f:
            f.write("someone else created this")

        with self.assertRaises(StructuredError) as ctx:
            core_write.apply_write(
                self.corpus, manifest, registry, policy, events, engine,
                approval_id=approval_id, operator_id="op-user1",
                diff_input=encoded, data_dir=self.data_dir,
                changeset=changeset)

        self.assertEqual(ctx.exception.error_category, "approval_invalidated")
        self.assertIn("changed since approval", ctx.exception.message)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
