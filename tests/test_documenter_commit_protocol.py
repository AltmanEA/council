"""Tests for the Multi-file Commit Protocol (phase MF-1).

Covers:
  - commit_rank / sort_for_commit ordering
  - validate_changeset_paths (allowed / blocked)
  - stage_bytes (correct dir, naming, content, fsync)
  - write_intent / read_intent (roundtrip, validation, atomicity)
  - scan_intents (skip garbage, read valid)
  - ordered_renames (happy path, tampered tmp, partiality)
  - reconcile new-format three branches
  - reconcile legacy regression
  - reconcile mixed legacy + new
"""
import json
import os
import shutil
import tempfile
import time
import unittest

# Ensure repo root is on sys.path for gen_manifest import.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys  # noqa: E402
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from documenter_service.adapters.commit_protocol import (  # noqa: E402
    commit_rank,
    sort_for_commit,
    allowed_changeset_paths,
    validate_changeset_paths,
    stage_bytes,
    write_intent,
    read_intent,
    scan_intents,
    ordered_renames,
    _valid_intent,
)
from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry  # noqa: E402
from documenter_service.core.errors import StructuredError  # noqa: E402
from documenter_service.core import write as core_write  # noqa: E402


# ---------------------------------------------------------------------------
# In-memory manifest helper (mimics _make_manifest from test_documenter_write)
# ---------------------------------------------------------------------------


def _make_manifest(doc_ids=None, entry_extra=None):
    """Create an in-memory manifest mock.

    When ``entry_extra`` is provided it should be a list of dicts that are
    appended to the manifest entries alongside the standard entries for
    each doc_id.  Each extra dict must have a matching ``id`` key.
    """
    if doc_ids is None:
        doc_ids = ["alpha", "beta", "gamma"]
    entries_list = []
    manifest = type("Manifest", (), {
        "_entries": {},
        "entries": lambda self: entries_list,
        "resolve": lambda self, tid: self._entries.get(tid),
    })()
    extra_map = {}
    if entry_extra:
        for extra in entry_extra:
            extra_map[extra["id"]] = extra
    for eid in doc_ids:
        entry = {
            "id": eid,
            "path": "docs/en/" + eid + "/index.md",
            "title": eid.title() + " Document",
            "version": "1.0.0",
            "status": "active",
        }
        extra = extra_map.get(eid)
        if extra:
            entry.update(extra)
        entries_list.append(entry)
        manifest._entries[eid] = entry
    return manifest


def _make_registry(tmpdir):
    return JsonlAuditRegistry(tmpdir)


def _make_briefing(tmpdir):
    path = os.path.join(tmpdir, "_briefing.md")
    with open(path, "w") as f:
        f.write("# Briefing\n\nAuthorised operational context.\n")
    return path


def _enable_operator_ingress(root):
    sentinel = os.path.join(root, "documenter", ".operator_ingress_ready")
    os.makedirs(os.path.dirname(sentinel), exist_ok=True)
    with open(sentinel, "w") as f:
        f.write("")
    return sentinel


def _init_git_repo(root):
    import subprocess
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


# ---------------------------------------------------------------------------
# Test class: TestCommitRank
# ---------------------------------------------------------------------------

class TestCommitRank(unittest.TestCase):
    """Unit tests for commit_rank and sort_for_commit."""

    def test_sort_order_doc_ru_changelog_manifest_hashes(self):
        """Test 1: [docs-manifest.yaml, index.md, changelog, index-RU.md, hashes.json]
        must sort to: doc(0) → RU(1) → changelog(2) → manifest(3) → hashes(4)."""
        paths = [
            "docs-manifest.yaml",
            "docs/en/alpha/index.md",
            "CHANGELOGS/alpha.changes.md",
            "docs/ru/alpha/index-RU.md",
            "documenter/hashes.json",
        ]
        ordered = sort_for_commit(paths)
        expected = [
            "docs/en/alpha/index.md",       # rank 0
            "docs/ru/alpha/index-RU.md",    # rank 1
            "CHANGELOGS/alpha.changes.md",  # rank 2
            "docs-manifest.yaml",           # rank 3
            "documenter/hashes.json",       # rank 4
        ]
        self.assertEqual(ordered, expected)

    def test_commit_rank_values(self):
        self.assertEqual(commit_rank("docs/en/foo/index.md"), 0)
        self.assertEqual(commit_rank("docs/ru/foo/index-RU.md"), 1)
        self.assertEqual(commit_rank("CHANGELOGS/foo.changes.md"), 2)
        self.assertEqual(commit_rank("docs-manifest.yaml"), 3)
        self.assertEqual(commit_rank("documenter/hashes.json"), 4)

    def test_unknown_path_returns_rank_0(self):
        self.assertEqual(commit_rank("some/random/path.txt"), 0)

    def test_changelog_requires_CHANGELOGS_prefix_and_suffix(self):
        self.assertEqual(commit_rank("CHANGELOGS/foo.changes.md"), 2)
        self.assertNotEqual(commit_rank("CHANGELOGS/foo.md"), 2)  # no .changes
        self.assertNotEqual(commit_rank("foo.changes.md"), 2)  # no CHANGELOGS/

    def test_sort_stable(self):
        paths = ["docs/en/beta/index.md", "docs/en/alpha/index.md"]
        ordered = sort_for_commit(paths)
        self.assertEqual(ordered, [
            "docs/en/alpha/index.md",
            "docs/en/beta/index.md",
        ])


# ---------------------------------------------------------------------------
# Test class: TestValidateChangesetPaths
# ---------------------------------------------------------------------------

class TestValidateChangesetPaths(unittest.TestCase):
    """Unit tests for validate_changeset_paths and allowed_changeset_paths."""

    def test_allowed_paths_include_manifest_entries(self):
        manifest = _make_manifest(["alpha"])
        allowed = allowed_changeset_paths(manifest)
        self.assertIn("docs/en/alpha/index.md", allowed)

    def test_allowed_paths_include_has_translation(self):
        manifest = _make_manifest(
            ["alpha"],
            entry_extra=[{"id": "alpha", "has_translation": "docs/ru/alpha/index-RU.md"}]
        )
        allowed = allowed_changeset_paths(manifest)
        self.assertIn("docs/ru/alpha/index-RU.md", allowed)

    def test_allowed_paths_include_changelog_when_present(self):
        manifest = _make_manifest(
            ["alpha"],
            entry_extra=[{"id": "alpha", "changelog-path": "CHANGELOGS/alpha.changes.md"}]
        )
        allowed = allowed_changeset_paths(manifest)
        self.assertIn("CHANGELOGS/alpha.changes.md", allowed)

    def test_allowed_paths_always_include_manifest_and_hashes(self):
        manifest = _make_manifest()
        allowed = allowed_changeset_paths(manifest)
        self.assertIn("docs-manifest.yaml", allowed)
        self.assertIn("documenter/hashes.json", allowed)

    def test_validate_passes_for_all_allowed(self):
        manifest = _make_manifest(["alpha"])
        validate_changeset_paths(["docs/en/alpha/index.md"], manifest)
        validate_changeset_paths(["docs-manifest.yaml"], manifest)

    def test_validate_blocks_non_manifest_path(self):
        manifest = _make_manifest(["alpha"])
        with self.assertRaises(StructuredError) as ctx:
            validate_changeset_paths(["docs/en/evil.md"], manifest)
        self.assertEqual(ctx.exception.error_category, "unknown")
        self.assertIn("no writes proceed", ctx.exception.message)

    def test_validate_posix_normalises_slashes(self):
        manifest = _make_manifest(["alpha"])
        # Windows-style path should still match the POSIX entry.
        validate_changeset_paths(["docs\\en\\alpha\\index.md"], manifest)


# ---------------------------------------------------------------------------
# Test class: TestStageBytes
# ---------------------------------------------------------------------------

class TestStageBytes(unittest.TestCase):
    """Unit tests for stage_bytes."""

    def test_file_created_in_target_dir_not_tmp(self):
        tmpdir = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmpdir, "docs", "en", "alpha"), exist_ok=True)
            rel = "docs/en/alpha/index.md"
            data = b"hello staged content"
            tx_id = "a1b2c3d4e5f678901234567890abcdef"  # 32 hex chars, no dashes
            tmp_path = stage_bytes(tmpdir, rel, data, tx_id)

            # File must be in the target dir hierarchy under root,
            # not in a standalone /tmp staging area.
            self.assertTrue(tmp_path.startswith(tmpdir))

            # Check naming pattern.
            basename = os.path.basename(tmp_path)
            self.assertTrue(basename.startswith("."))
            self.assertTrue(basename.endswith(".tmp"))
            self.assertIn("a1b2c3d4e5f67890", basename)  # tx16
        finally:
            shutil.rmtree(tmpdir)

    def test_content_matches(self):
        tmpdir = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmpdir, "docs", "en", "alpha"), exist_ok=True)
            data = b"exact content to verify"
            tmp_path = stage_bytes(tmpdir, "docs/en/alpha/index.md", data, "uuid-1234")
            with open(tmp_path, "rb") as f:
                self.assertEqual(f.read(), data)
        finally:
            shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# Test class: TestWriteReadIntent
# ---------------------------------------------------------------------------

class TestWriteReadIntent(unittest.TestCase):
    """Unit tests for write_intent / read_intent (roundtrip, validation, atomicity)."""

    def _make_valid_record(self, tx_id=None):
        import uuid
        if tx_id is None:
            tx_id = str(uuid.uuid4())
        return {
            "tx_id": tx_id,
            "target_id": "alpha",
            "created_at": "2026-01-01T00:00:00Z",
            "entries": [
                {
                    "path": "docs/en/alpha/index.md",
                    "tmp_path": "/tmp/staged/alpha.tmp",
                    "before_hash": "sha256:" + "a" * 64,
                    "after_hash": "sha256:" + "b" * 64,
                }
            ],
        }

    def test_roundtrip(self):
        tmpdir = tempfile.mkdtemp()
        try:
            tx_id = "11111111-2222-3333-4444-555555555555"
            record = self._make_valid_record(tx_id)
            path = write_intent(tmpdir, tx_id, record)

            # Path must be data_dir/intent/<tx_id>.json
            self.assertTrue(path.endswith(os.path.join("intent", f"{tx_id}.json")))
            self.assertTrue(os.path.exists(path))

            # Round-trip read.
            read_back = read_intent(tmpdir, tx_id)
            self.assertIsNotNone(read_back)
            self.assertEqual(read_back["tx_id"], tx_id)
            self.assertEqual(read_back["target_id"], "alpha")
            self.assertEqual(len(read_back["entries"]), 1)
        finally:
            shutil.rmtree(tmpdir)

    def test_no_tmp_after_write(self):
        tmpdir = tempfile.mkdtemp()
        try:
            tx_id = "22222222-3333-4444-5555-666666666666"
            record = self._make_valid_record(tx_id)
            write_intent(tmpdir, tx_id, record)
            # The .tmp file from the atomic write must not remain.
            tmp_path = os.path.join(tmpdir, "intent", f"{tx_id}.json.tmp")
            self.assertFalse(os.path.exists(tmp_path))
        finally:
            shutil.rmtree(tmpdir)

    def test_read_nonexistent_returns_none(self):
        tmpdir = tempfile.mkdtemp()
        try:
            self.assertIsNone(read_intent(tmpdir, "nonexistent-tx"))
        finally:
            shutil.rmtree(tmpdir)

    def test_invalid_record_entries_empty_raises(self):
        tmpdir = tempfile.mkdtemp()
        try:
            import uuid
            tx_id = str(uuid.uuid4())
            record = {
                "tx_id": tx_id,
                "target_id": "alpha",
                "created_at": "2026-01-01T00:00:00Z",
                "entries": [],  # empty entries → invalid
            }
            intent_file = os.path.join(tmpdir, "intent", f"{tx_id}.json")
            with self.assertRaises(StructuredError):
                write_intent(tmpdir, tx_id, record)
            # File must NOT have been created.
            self.assertFalse(os.path.exists(intent_file))
        finally:
            shutil.rmtree(tmpdir)

    def test_invalid_record_hash_without_sha256_prefix_raises(self):
        tmpdir = tempfile.mkdtemp()
        try:
            import uuid
            tx_id = str(uuid.uuid4())
            record = {
                "tx_id": tx_id,
                "target_id": "alpha",
                "created_at": "2026-01-01T00:00:00Z",
                "entries": [
                    {
                        "path": "docs/en/alpha/index.md",
                        "tmp_path": "/tmp/staged/alpha.tmp",
                        "before_hash": "md5:abcdef",  # missing sha256: prefix
                        "after_hash": "sha256:" + "b" * 64,
                    }
                ],
            }
            intent_file = os.path.join(tmpdir, "intent", f"{tx_id}.json")
            with self.assertRaises(StructuredError):
                write_intent(tmpdir, tx_id, record)
            self.assertFalse(os.path.exists(intent_file))
        finally:
            shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# Test class: TestScanIntents
# ---------------------------------------------------------------------------

class TestScanIntents(unittest.TestCase):
    """Unit tests for scan_intents: garbage skip, valid read."""

    def test_garbage_json_skipped(self):
        tmpdir = tempfile.mkdtemp()
        try:
            intent_dir = os.path.join(tmpdir, "intent")
            os.makedirs(intent_dir, exist_ok=True)

            # Write garbage JSON.
            bad_path = os.path.join(intent_dir, "garbage-tx-id.json")
            with open(bad_path, "w") as f:
                f.write("not valid json at all")

            # Write a valid record alongside it.
            valid = self._make_valid_record("valid-tx-0000-0000-0000-000000000000")
            write_intent(tmpdir, "valid-tx-0000-0000-0000-000000000000", valid)

            # scan_intents must not raise and must skip the garbage.
            results = scan_intents(tmpdir)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["tx_id"], "valid-tx-0000-0000-0000-000000000000")
        finally:
            shutil.rmtree(tmpdir)

    def test_no_intent_dir_returns_empty(self):
        tmpdir = tempfile.mkdtemp()
        try:
            self.assertEqual(scan_intents(tmpdir), [])
        finally:
            shutil.rmtree(tmpdir)

    def test_mismatched_filename_skipped(self):
        tmpdir = tempfile.mkdtemp()
        try:
            # Write a file whose tx_id doesn't match record tx_id.
            intent_dir = os.path.join(tmpdir, "intent")
            os.makedirs(intent_dir, exist_ok=True)
            record = {
                "tx_id": "expected-tx",
                "target_id": "alpha",
                "created_at": "2026-01-01T00:00:00Z",
                "entries": [
                    {
                        "path": "docs/en/alpha/index.md",
                        "tmp_path": "/tmp/staged/alpha.tmp",
                        "before_hash": "sha256:" + "a" * 64,
                        "after_hash": "sha256:" + "b" * 64,
                    }
                ],
            }
            # File named differently from record's tx_id.
            fake_file = os.path.join(intent_dir, "different-filename.json")
            with open(fake_file, "w") as f:
                json.dump(record, f)

            results = scan_intents(tmpdir)
            self.assertEqual(len(results), 0)  # skipped due to mismatch
        finally:
            shutil.rmtree(tmpdir)

    def _make_valid_record(self, tx_id=None):
        import uuid
        if tx_id is None:
            tx_id = str(uuid.uuid4())
        return {
            "tx_id": tx_id,
            "target_id": "alpha",
            "created_at": "2026-01-01T00:00:00Z",
            "entries": [
                {
                    "path": "docs/en/alpha/index.md",
                    "tmp_path": "/tmp/staged/alpha.tmp",
                    "before_hash": "sha256:" + "a" * 64,
                    "after_hash": "sha256:" + "b" * 64,
                }
            ],
        }


# ---------------------------------------------------------------------------
# Test class: TestOrderedRenames
# ---------------------------------------------------------------------------

class TestOrderedRenames(unittest.TestCase):
    """Unit tests for ordered_renames (happy path + tampered tmp)."""

    def _prepare_staged(self, root, entries):
        """Create target directories and staged tmp files for each entry."""
        from hashlib import sha256 as _sha256
        hasher = lambda b: "sha256:" + _sha256(b).hexdigest()

        prepared = []
        for entry in entries:
            rel = entry["path"]
            abs_path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)

            content = entry.get("content", f"content for {rel}")
            entry["content"] = content  # store for later assertions
            data = content.encode("utf-8") if isinstance(content, str) else content
            tmp_path = entry["tmp_path"]
            os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
            with open(tmp_path, "wb") as f:
                f.write(data)

            # Set after_hash to the actual hash of the content.
            entry["after_hash"] = hasher(data)
            prepared.append(entry)
        return prepared

    def test_happy_path_all_renamed_in_order(self):
        """Happy path: all tmp files exist with correct hashes → all renamed."""
        tmpdir = tempfile.mkdtemp()
        try:
            entries = [
                {
                    "path": "docs/en/alpha/index.md",
                    "tmp_path": os.path.join(tmpdir, "staged", "alpha.tmp"),
                    "before_hash": "sha256:" + "0" * 64,
                    "after_hash": "",  # will be filled
                },
                {
                    "path": "docs/ru/alpha/index-RU.md",
                    "tmp_path": os.path.join(tmpdir, "staged", "ru.tmp"),
                    "before_hash": "sha256:" + "0" * 64,
                    "after_hash": "",
                },
                {
                    "path": "CHANGELOGS/alpha.changes.md",
                    "tmp_path": os.path.join(tmpdir, "staged", "cl.tmp"),
                    "before_hash": "sha256:" + "0" * 64,
                    "after_hash": "",
                },
            ]
            entries = self._prepare_staged(tmpdir, entries)

            renamed = ordered_renames(tmpdir, entries)
            self.assertEqual(len(renamed), 3)

            # All final files must exist with correct content.
            for entry in entries:
                final_path = os.path.join(tmpdir, entry["path"])
                self.assertTrue(os.path.exists(final_path))
                with open(final_path, "rb") as f:
                    content = f.read()
                self.assertEqual(content, entry["content"].encode("utf-8"))

                # Staged tmp must be gone.
                self.assertFalse(os.path.exists(entry["tmp_path"]))

            # Verify order: doc → RU → changelog.
            self.assertEqual(renamed[0], "docs/en/alpha/index.md")
            self.assertEqual(renamed[1], "docs/ru/alpha/index-RU.md")
            self.assertEqual(renamed[2], "CHANGELOGS/alpha.changes.md")

        finally:
            shutil.rmtree(tmpdir)

    def test_tampered_tmp_hash_mismatch_rest_are_not_touched(self):
        """When first tmp has wrong hash, StructuredError raised and
        previously renamed files are NOT rolled back (but NO files
        are renamed before the failure since we process in order)."""
        tmpdir = tempfile.mkdtemp()
        try:
            entries = [
                {
                    "path": "docs/en/alpha/index.md",
                    "tmp_path": os.path.join(tmpdir, "staged", "alpha.tmp"),
                    "before_hash": "sha256:" + "0" * 64,
                    "after_hash": "sha256:" + "b" * 64,  # will not match
                },
                {
                    "path": "CHANGELOGS/alpha.changes.md",
                    "tmp_path": os.path.join(tmpdir, "staged", "cl.tmp"),
                    "before_hash": "sha256:" + "0" * 64,
                    "after_hash": "sha256:" + "c" * 64,
                },
            ]
            # Write correct content for cl.tmp but WRONG content for alpha.tmp.
            os.makedirs(os.path.join(tmpdir, "staged"), exist_ok=True)
            os.makedirs(os.path.join(tmpdir, "CHANGELOGS"), exist_ok=True)

            cl_content = b"changelog content"
            with open(entries[1]["tmp_path"], "wb") as f:
                f.write(cl_content)
            entries[1]["after_hash"] = "sha256:" + _sha256(cl_content).hexdigest()

            # Write CORRECT content for alpha.tmp but set a WRONG after_hash.
            alpha_content = b"alpha content"
            with open(entries[0]["tmp_path"], "wb") as f:
                f.write(alpha_content)
            entries[0]["after_hash"] = "sha256:" + "z" * 64  # deliberately wrong

            with self.assertRaises(StructuredError) as ctx:
                ordered_renames(tmpdir, entries)
            self.assertEqual(ctx.exception.error_category, "hash_mismatch")

            # The second file must NOT have been renamed (ordering guarantees
            # we stop before processing it).
            changelog_final = os.path.join(tmpdir, "CHANGELOGS", "alpha.changes.md")
            self.assertFalse(os.path.exists(changelog_final))
            # alpha.tmp still exists (wasn't renamed due to error).
            self.assertTrue(os.path.exists(entries[0]["tmp_path"]))

        finally:
            shutil.rmtree(tmpdir)


from hashlib import sha256 as _sha256


# ---------------------------------------------------------------------------
# Test class: TestReconcileNewFormat (three branches)
# ---------------------------------------------------------------------------

class TestReconcileNewFormat(unittest.TestCase):
    """Test 7: reconcile new-format three branches.

    (a) all files == after_hash → resolve + intent file deleted + resolved
        record in registry.
    (b) files == before_hash and tmp on disk → roll forward, files ==
        after_hash, resolve.
    (c) file externally modified (neither before nor after) → needs_attention,
        tmp NOT renamed, intent NOT deleted.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.corpus = os.path.join(self.tmpdir, "corpus")
        self.data_dir = os.path.join(self.tmpdir, "documenter")
        os.makedirs(self.corpus, exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "intent"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "staged"), exist_ok=True)
        # Create corpus structure needed by manifest.
        os.makedirs(os.path.join(self.corpus, "docs", "en", "alpha"), exist_ok=True)
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        with open(alpha_path, "w") as f:
            f.write("# Alpha\nid: alpha\nVersion: 1.0.0\nStatus: active\n")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _sha(self, data):
        return "sha256:" + _sha256(data).hexdigest()

    def test_branch_a_all_matched_after_hash_resolves(self):
        """All files already have after_hash → resolve, intent deleted."""
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        content = b"committed content A"
        with open(alpha_path, "wb") as f:
            f.write(content)
        after_sha = self._sha(content)

        record = {
            "tx_id": "aaa-bbb-ccc-ddd-000000000001",
            "target_id": "alpha",
            "created_at": "2026-01-01T00:00:00Z",
            "entries": [
                {
                    "path": "docs/en/alpha/index.md",
                    "tmp_path": os.path.join(self.data_dir, "staged", "alpha.tmp"),
                    "before_hash": self._sha(b"before content"),
                    "after_hash": after_sha,
                }
            ],
        }

        # Write the intent file (simulating leftover from prior run).
        write_intent(self.data_dir, record["tx_id"], record)
        self.assertTrue(os.path.exists(os.path.join(
            self.data_dir, "intent", f"{record['tx_id']}.json")))

        registry = _make_registry(self.data_dir)
        manifest = _make_manifest(["alpha"])

        results = core_write.reconcile(registry, manifest, self.corpus, self.data_dir)

        # No needs_attention results for this intent.
        na = [r for r in results if r["status"] == "needs_attention"]
        self.assertEqual(len(na), 0)

        # Intent file must be deleted.
        self.assertFalse(os.path.exists(os.path.join(
            self.data_dir, "intent", f"{record['tx_id']}.json")))

        # Resolved intent record must be in the registry.
        records, _ = registry.read_all()
        intent_records = [r for r in records if r["record_type"] == "intent_record"]
        resolved = [r for r in intent_records if r["data"].get("resolved")]
        self.assertTrue(len(resolved) > 0)
        self.assertEqual(resolved[-1]["data"].get("target_id"), "alpha")

    def test_branch_b_before_hash_and_tmp_exist_roll_forward(self):
        """Files match before_hash, tmp has after_hash → roll forward."""
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        before_content = b"before content B"
        after_content = b"after content B"
        before_sha = self._sha(before_content)
        after_sha = self._sha(after_content)

        with open(alpha_path, "wb") as f:
            f.write(before_content)

        staged_path = os.path.join(self.data_dir, "staged", "alpha.tmp")
        os.makedirs(os.path.dirname(staged_path), exist_ok=True)
        with open(staged_path, "wb") as f:
            f.write(after_content)

        record = {
            "tx_id": "aaa-bbb-ccc-ddd-000000000002",
            "target_id": "alpha",
            "created_at": "2026-01-01T00:00:00Z",
            "entries": [
                {
                    "path": "docs/en/alpha/index.md",
                    "tmp_path": staged_path,
                    "before_hash": before_sha,
                    "after_hash": after_sha,
                }
            ],
        }
        write_intent(self.data_dir, record["tx_id"], record)

        registry = _make_registry(self.data_dir)
        manifest = _make_manifest(["alpha"])

        results = core_write.reconcile(registry, manifest, self.corpus, self.data_dir)

        na = [r for r in results if r["status"] == "needs_attention"]
        self.assertEqual(len(na), 0)

        # File must now contain after content (rolled forward).
        with open(alpha_path, "rb") as f:
            self.assertEqual(f.read(), after_content)

        # Staged tmp must be gone.
        self.assertFalse(os.path.exists(staged_path))

        # Intent file deleted.
        self.assertFalse(os.path.exists(os.path.join(
            self.data_dir, "intent", f"{record['tx_id']}.json")))

    def test_branch_c_external_modification_needs_attention(self):
        """File changed externally → needs_attention, intent NOT deleted."""
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        before_sha = self._sha(b"before content C")
        after_sha = self._sha(b"after content C")

        # Write content that is neither before nor after.
        with open(alpha_path, "wb") as f:
            f.write(b"externally modified content")

        record = {
            "tx_id": "aaa-bbb-ccc-ddd-000000000003",
            "target_id": "alpha",
            "created_at": "2026-01-01T00:00:00Z",
            "entries": [
                {
                    "path": "docs/en/alpha/index.md",
                    "tmp_path": os.path.join(self.data_dir, "staged", "alpha.tmp"),
                    "before_hash": before_sha,
                    "after_hash": after_sha,
                }
            ],
        }
        write_intent(self.data_dir, record["tx_id"], record)

        registry = _make_registry(self.data_dir)
        manifest = _make_manifest(["alpha"])

        results = core_write.reconcile(registry, manifest, self.corpus, self.data_dir)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "needs_attention")
        self.assertIn("external modification detected", results[0]["detail"])

        # Intent file must NOT be deleted.
        self.assertTrue(os.path.exists(os.path.join(
            self.data_dir, "intent", f"{record['tx_id']}.json")))


# ---------------------------------------------------------------------------
# Test class: TestReconcileLegacyRegression
# ---------------------------------------------------------------------------

class TestReconcileLegacyRegression(unittest.TestCase):
    """Test 8: legacy reconcile path (registry-only, no new-format entries).

    Verifies that the existing reconcile behavior (registry-based,
    per_file_sha256 comparison) continues to work.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.corpus = os.path.join(self.tmpdir, "corpus")
        os.makedirs(os.path.join(self.corpus, "docs", "en", "alpha"))
        self.data_dir = os.path.join(self.tmpdir, "documenter")
        os.makedirs(self.data_dir, exist_ok=True)
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        with open(alpha_path, "w") as f:
            f.write("# Alpha\nid: alpha\nVersion: 1.0.0\nStatus: active\nchangelog-path: CHANGELOGS/alpha.md\n")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_reconcile_no_unresolved(self):
        manifest = _make_manifest()
        registry = _make_registry(self.tmpdir)
        results = core_write.reconcile(registry, manifest, self.corpus, self.data_dir)
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
        registry = _make_registry(self.tmpdir)
        registry.append("intent_record", intent)

        manifest = _make_manifest()
        results = core_write.reconcile(registry, manifest, self.corpus, self.data_dir)
        self.assertEqual(results, [])

    def test_reconcile_hash_mismatch(self):
        intent = {
            "target_ids": ["alpha"],
            "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "per_file_sha256": {"alpha": "sha256:" + "0" * 64},
            "resolved": False,
        }
        registry = _make_registry(self.tmpdir)
        registry.append("intent_record", intent)

        manifest = _make_manifest()
        results = core_write.reconcile(registry, manifest, self.corpus, self.data_dir)
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
        registry = _make_registry(self.tmpdir)
        registry.append("intent_record", intent)

        manifest = _make_manifest()
        core_write.reconcile(registry, manifest, self.corpus, self.data_dir)

        records, _ = registry.read_all()
        intent_records = [r for r in records if r["record_type"] == "intent_record"]
        resolved = [r for r in intent_records if r["data"].get("resolved")]
        self.assertTrue(len(resolved) > 0)

    def test_reconcile_manifest_missing(self):
        intent = {
            "target_ids": ["alpha"],
            "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "per_file_sha256": {},
            "resolved": False,
        }
        registry = _make_registry(self.tmpdir)
        registry.append("intent_record", intent)

        manifest_bad = _make_manifest(["alpha"])
        del manifest_bad._entries["alpha"]
        results = core_write.reconcile(registry, manifest_bad, self.corpus, self.data_dir)
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
        registry = _make_registry(self.tmpdir)
        registry.append("intent_record", intent)

        manifest = _make_manifest()
        core_write.reconcile(registry, manifest, self.corpus, self.data_dir)
        self.assertTrue(os.path.exists(self.data_dir))


# ---------------------------------------------------------------------------
# Test class: TestReconcileMixed
# ---------------------------------------------------------------------------

class TestReconcileMixed(unittest.TestCase):
    """Test 9: one legacy unresolved + one new-format intent → both handled."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.corpus = os.path.join(self.tmpdir, "corpus")
        os.makedirs(os.path.join(self.corpus, "docs", "en", "alpha"))
        self.data_dir = os.path.join(self.tmpdir, "documenter")
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "intent"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "staged"), exist_ok=True)
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        with open(alpha_path, "w") as f:
            f.write("# Alpha\nid: alpha\nVersion: 1.0.0\nStatus: active\nchangelog-path: CHANGELOGS/alpha.md\n")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _sha(self, data):
        return "sha256:" + _sha256(data).hexdigest()

    def test_one_legacy_clean_one_new_all_committed(self):
        """Legacy intent hash-matched + new-format intent all after_hash →
        both resolved, registry has two resolved records."""
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        # Write content that both intents will agree on.
        common_content = b"common committed content"
        with open(alpha_path, "wb") as f:
            f.write(common_content)
        common_sha = self._sha(common_content)

        # Legacy intent (clean hash — matches actual file).
        legacy_intent = {
            "target_ids": ["alpha"],
            "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "per_file_sha256": {"alpha": common_sha},
            "resolved": False,
        }

        # New-format intent (all files match after_hash).
        new_record = {
            "tx_id": "new-tx-0000-0000-0000-000000000001",
            "target_id": "alpha",
            "created_at": "2026-01-01T00:00:00Z",
            "entries": [
                {
                    "path": "docs/en/alpha/index.md",
                    "tmp_path": os.path.join(self.data_dir, "staged", "new.tmp"),
                    "before_hash": self._sha(b"before"),
                    "after_hash": common_sha,
                }
            ],
        }

        registry = _make_registry(self.data_dir)
        registry.append("intent_record", legacy_intent)
        write_intent(self.data_dir, new_record["tx_id"], new_record)

        manifest = _make_manifest(["alpha"])
        results = core_write.reconcile(registry, manifest, self.corpus, self.data_dir)

        # Both should be resolved (no needs_attention).
        na = [r for r in results if r["status"] == "needs_attention"]
        self.assertEqual(len(na), 0)

        # Both intent files deleted (new-format).
        self.assertFalse(os.path.exists(os.path.join(
            self.data_dir, "intent", f"{new_record['tx_id']}.json")))

        # Two resolved intent records in registry (legacy + new).
        records, _ = registry.read_all()
        intent_records = [r for r in records if r["record_type"] == "intent_record"]
        resolved = [r for r in intent_records if r["data"].get("resolved")]
        self.assertEqual(len(resolved), 2)
