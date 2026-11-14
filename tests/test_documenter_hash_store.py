"""Tests for the Hash Store adapter and its wiring in Service / CLI.

Covers: persistence format, stability, change detection, corruption recovery,
bak rotation, atomicity, verify(), rebuild(), and CLI --rebuild-hashes.
"""
import io
import json
import os
import shutil
import tempfile
import unittest

import sys
from contextlib import redirect_stdout
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

from documenter_service.__main__ import Service, main  # noqa: E402
from documenter_service.adapters.hash_store import HashStore  # noqa: E402
from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry  # noqa: E402
from documenter_service.adapters.stdout_events import StdoutEventSink  # noqa: E402
from documenter_service.core.errors import StructuredError  # noqa: E402

FIXTURE_CORPUS = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tests", "fixtures", "documenter", "corpus")


def _make_service(root, tmp_dir=None):
    """Create a Service with an isolated temp data dir and memory events."""
    if tmp_dir is None:
        tmp_dir = tempfile.mkdtemp()
    os.environ["DOCUMENTER_DATA_DIR"] = os.path.join(tmp_dir, "state")
    svc = Service(root,
                  events=StdoutEventSink(io.StringIO()))
    return svc


class TestHashStoreFormat(unittest.TestCase):
    """Test 1: after audit(), hashes.json exists with valid structure."""

    def test_format(self):
        _, root = _make_corpus()
        tmp_dir = tempfile.mkdtemp()
        try:
            svc = _make_service(root, tmp_dir=tmp_dir)
            svc.audit(target_id="*")
            hash_path = svc.hash_store._path
            self.assertTrue(os.path.isfile(hash_path),
                            "hashes.json should exist after audit")
            with open(hash_path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data["version"], 1)
            self.assertIsInstance(data["entries"], dict)
            self.assertGreater(len(data["entries"]), 0)
            for path, entry in data["entries"].items():
                # path should be relative (manifest-relative)
                self.assertFalse(os.path.isabs(path),
                                 f"path {path!r} should be relative")
                lh = entry["last_hash"]
                self.assertTrue(
                    lh.startswith("sha256:"),
                    f"last_hash should start with sha256: got {lh!r}")
                hex_part = lh[7:]
                self.assertEqual(len(hex_part), 64)
                self.assertTrue(all(c in "0123456789abcdef" for c in hex_part))
                lm = entry["last_modified"]
                self.assertTrue(
                    lm.endswith("Z"),
                    f"last_modified should end with Z, got {lm!r}")
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestHashStoreStability(unittest.TestCase):
    """Test 2: re-running audit() doesn't change the store (no duplicate history)."""

    def test_stability(self):
        _, root = _make_corpus()
        tmp_dir = tempfile.mkdtemp()
        try:
            svc = _make_service(root, tmp_dir=tmp_dir)
            svc.audit(target_id="*")
            hash_path = svc.hash_store._path
            with open(hash_path, encoding="utf-8") as fh:
                before_data = json.load(fh)

            # Run audit again
            svc.audit(target_id="*")
            with open(hash_path, encoding="utf-8") as fh:
                after_data = json.load(fh)

            self.assertEqual(after_data, before_data,
                             "hash store should be identical after re-audit")
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestHashStoreChange(unittest.TestCase):
    """Test 3: modifying a file between audits updates hash and appends old to history."""

    def test_change(self):
        _, root = _make_corpus()
        tmp_dir = tempfile.mkdtemp()
        try:
            svc = _make_service(root, tmp_dir=tmp_dir)
            svc.audit(target_id="*")
            hash_path = svc.hash_store._path
            with open(hash_path, encoding="utf-8") as fh:
                before_data = json.load(fh)

            # Get an entry path and modify the file
            alpha_path = None
            for p, e in before_data["entries"].items():
                if "alpha" in p:
                    alpha_path = p
                    old_hash = e["last_hash"]
                    break
            self.assertIsNotNone(alpha_path, "alpha entry should exist")

            # Modify the alpha file
            abs_alpha = os.path.join(root, alpha_path)
            with open(abs_alpha, "a", encoding="utf-8") as fh:
                fh.write("\n# appended line\n")

            # Re-run audit
            svc.audit(target_id="*")
            with open(hash_path, encoding="utf-8") as fh:
                after_data = json.load(fh)

            updated = after_data["entries"].get(alpha_path, {})
            new_hash = updated.get("last_hash")
            self.assertNotEqual(new_hash, old_hash,
                                "hash should have changed")
            history = updated.get("history", [])
            self.assertGreater(len(history), 0,
                               "history should have an old hash entry")
            self.assertEqual(history[0]["hash"], old_hash,
                             "history[0].hash should be the old hash")
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestHashStoreCorruptFile(unittest.TestCase):
    """Test 4: garbage in hashes.json → audit doesn't crash, recovers."""

    def test_corrupt_file(self):
        _, root = _make_corpus()
        tmp_dir = tempfile.mkdtemp()
        try:
            svc = _make_service(root, tmp_dir=tmp_dir)
            svc.audit(target_id="*")
            hash_path = svc.hash_store._path

            # Overwrite with garbage
            with open(hash_path, "w", encoding="utf-8") as fh:
                fh.write("THIS IS GARBAGE NOT JSON\n" * 10)

            # audit should NOT crash
            resp = svc.audit(target_id="*")
            self.assertEqual(resp["coverage"]["status"], "complete")

            # File should be recovered
            with open(hash_path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data["version"], 1)
            self.assertGreater(len(data["entries"]), 0)

            # Next audit should also work
            resp2 = svc.audit(target_id="*")
            self.assertEqual(resp2["coverage"]["status"], "complete")
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestHashStoreBakRotation(unittest.TestCase):
    """Test 5: after second save, hashes.json.bak exists with previous content."""

    def test_bak_rotation(self):
        _, root = _make_corpus()
        tmp_dir = tempfile.mkdtemp()
        try:
            svc = _make_service(root, tmp_dir=tmp_dir)
            svc.audit(target_id="*")
            hash_path = svc.hash_store._path
            bak_path = svc.hash_store._bak_path

            self.assertFalse(os.path.exists(bak_path),
                             "bak should not exist after first save")

            # Modify a file to force a different hash
            alpha_path = None
            for p in svc.hash_store.load()["entries"]:
                if "alpha" in p:
                    alpha_path = os.path.join(root, p)
                    break
            self.assertIsNotNone(alpha_path)
            with open(alpha_path, "a", encoding="utf-8") as fh:
                fh.write("\n# second mutation\n")

            # Second audit triggers second save
            svc.audit(target_id="*")
            self.assertTrue(os.path.exists(bak_path),
                            "bak should exist after second save")

            # Verify bak contains previous content (version 1, entries present)
            with open(bak_path, encoding="utf-8") as fh:
                bak_data = json.load(fh)
            self.assertEqual(bak_data["version"], 1)
            self.assertGreater(len(bak_data["entries"]), 0)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestHashStoreAtomicity(unittest.TestCase):
    """Test 6: no temp files left after save."""

    def test_atomicity(self):
        _, root = _make_corpus()
        tmp_dir = tempfile.mkdtemp()
        try:
            svc = _make_service(root, tmp_dir=tmp_dir)
            svc.audit(target_id="*")
            data_dir = svc.hash_store.data_dir

            # Check no *.tmp files remain
            tmp_files = [f for f in os.listdir(data_dir) if f.endswith(".tmp")]
            self.assertEqual(tmp_files, [],
                             f"no .tmp files should remain, found: {tmp_files}")
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestHashStoreVerify(unittest.TestCase):
    """Test 7: verify() returns None, 'stale', or 'missing' correctly."""

    def test_verify(self):
        _, root = _make_corpus()
        tmp_dir = tempfile.mkdtemp()
        try:
            svc = _make_service(root, tmp_dir=tmp_dir)
            svc.audit(target_id="*")

            # Verify a known good entry → None
            result = svc.hash_store.verify(svc.manifest, "alpha")
            self.assertIsNone(result, "should match after audit")

            # External file change → "stale"
            alpha_md = os.path.join(root, "docs", "en", "alpha", "index.md")
            with open(alpha_md, "a", encoding="utf-8") as fh:
                fh.write("\n# external modification\n")
            result = svc.hash_store.verify(svc.manifest, "alpha")
            self.assertEqual(result, "stale",
                             "should be stale after external change")

            # Unknown target_id → "missing"
            result = svc.hash_store.verify(svc.manifest, "nonexistent")
            self.assertEqual(result, "missing",
                             "should be missing for unknown target")
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestHashStoreRebuild(unittest.TestCase):
    """Test 8: rebuild() restores all entries; non-existent paths don't appear.

    Scenario: audit → modify file → rebuild → old hash appears in history.
    The rebuild reads old entries (with their last_hash), sees the file has
    changed, and preserves the old hash in the new entry's history.
    """

    def test_rebuild(self):
        _, root = _make_corpus()
        tmp_dir = tempfile.mkdtemp()
        try:
            svc = _make_service(root, tmp_dir=tmp_dir)
            svc.audit(target_id="*")
            hash_path = svc.hash_store._path

            # Record current entries
            with open(hash_path, encoding="utf-8") as fh:
                before_data = json.load(fh)
            old_entries = dict(before_data["entries"])

            # Modify a file on disk BEFORE deleting and rebuilding.
            # The rebuild will compare new content against old_entries's
            # last_hash and preserve the old hash in history.
            alpha_md = os.path.join(root, "docs", "en", "alpha", "index.md")
            with open(alpha_md, "a", encoding="utf-8") as fh:
                fh.write("\n# before rebuild\n")

            # Delete hashes.json and rebuild — should pick up old entries'
            # last_hash from disk (the file has changed → old hash in history)
            os.unlink(hash_path)
            self.assertFalse(os.path.exists(hash_path))

            # Load still returns empty because the file is gone, so we need
            # to manually restore old entries. Actually, rebuild starts from
            # load() which returns empty when file is missing. To test history
            # preservation through rebuild, we must keep the file and modify
            # the disk content BEFORE calling rebuild, so load() can read
            # old entries and compare them against new disk hashes.
            #
            # Fix: don't delete the file — just modify the disk content.
            # Re-read: actually the scenario is: modify disk → rebuild (without
            # deleting) → old hash should be in history because load() returns
            # the old entries and the rebuild notices the hash changed.

            # Let me restructure: first, let the store exist, modify disk,
            # then call rebuild (which reads old entries, sees hash diff).
            # But we already modified it above and deleted. So let's do it
            # properly:

            # First audit created entries with hash A.
            # Now: modify disk → files differ → rebuild should put A in history.
            # But we deleted hashes.json. So we need to NOT delete it.
            #
            # Restructured test:
            svc2 = _make_service(root, tmp_dir=tmp_dir)

            # Second audit (no file change yet) → stable, entries same
            svc2.audit(target_id="*")
            hash_path2 = svc2.hash_store._path
            with open(hash_path2, encoding="utf-8") as fh:
                data_after_2 = json.load(fh)
            old_hash = data_after_2["entries"].get(
                "docs/en/alpha/index.md", {}).get("last_hash")

            # Now modify disk
            alpha_md2 = os.path.join(root, "docs", "en", "alpha", "index.md")
            with open(alpha_md2, "a", encoding="utf-8") as fh:
                fh.write("\n# before rebuild v2\n")

            # Rebuild without deleting: load() returns old entries,
            # disk hash differs → old hash goes to history
            rebuilt2 = svc2.hash_store.rebuild(svc2.manifest)
            alpha_hash2 = rebuilt2["entries"].get(
                "docs/en/alpha/index.md", {})
            history2 = alpha_hash2.get("history", [])
            self.assertGreater(len(history2), 0,
                               "history should have old hash from rebuild")
            self.assertEqual(history2[0]["hash"], old_hash,
                             "history[0] should be the old hash")

            # Non-existent paths: remove a file and rebuild → no entry for it
            os.unlink(alpha_md2)
            # Get a gamma entry
            gamma_path_in_store = "docs/en/gamma/index.md"
            os.unlink(os.path.join(root, gamma_path_in_store))

            rebuilt3 = svc2.hash_store.rebuild(svc2.manifest)
            self.assertNotIn(gamma_path_in_store, rebuilt3["entries"],
                             "deleted file should not appear in rebuilt entries")

        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestServiceAuditWiring(unittest.TestCase):
    """Test 9: Service.audit updates hash_store; CLI --rebuild-hashes works."""

    def test_audit_updates_hash_store(self):
        _, root = _make_corpus()
        tmp_dir = tempfile.mkdtemp()
        try:
            svc = _make_service(root, tmp_dir=tmp_dir)
            self.assertFalse(os.path.isfile(svc.hash_store._path),
                             "hashes.json should not exist before audit")
            svc.audit(target_id="*")
            self.assertTrue(os.path.isfile(svc.hash_store._path))
            with open(svc.hash_store._path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertGreater(len(data["entries"]), 0)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_cli_rebuild_hashes_json(self):
        _, root = _make_corpus()
        tmp_dir = tempfile.mkdtemp()
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = main(["--root", root, "--rebuild-hashes", "--json"])
            self.assertEqual(rc, 0)
            result = json.loads(out.getvalue().strip())
            self.assertIn("rebuilt_entries", result)
            self.assertIn("path", result)
            self.assertGreater(result["rebuilt_entries"], 0)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestHashStoreCorruptJSON(unittest.TestCase):
    """Test 10: bit-flip / structural corruption → cache miss, not crash."""

    def test_corrupt_structures(self):
        _, root = _make_corpus()
        tmp_dir = tempfile.mkdtemp()
        try:
            svc = _make_service(root, tmp_dir=tmp_dir)

            corrupt_jsons = [
                # version: 2 (wrong version)
                '{"version": 2, "entries": {}}',
                # entries is a list, not dict
                '{"version": 1, "entries": []}',
                # last_hash missing
                '{"version": 1, "entries": {"path": {"last_modified": "2026-01-01T00:00:00Z"}}}',
                # history not a list
                '{"version": 1, "entries": {"path": {"last_hash": "sha256:' + "a"*64 + '", "last_modified": "2026-01-01T00:00:00Z", "history": "bad"}}}',
                # hash not sha256:<64hex>
                '{"version": 1, "entries": {"path": {"last_hash": "md5:abc", "last_modified": "2026-01-01T00:00:00Z", "history": []}}}',
            ]
            for corrupt in corrupt_jsons:
                hash_path = svc.hash_store._path
                os.makedirs(svc.hash_store.data_dir, exist_ok=True)
                with open(hash_path, "w", encoding="utf-8") as fh:
                    fh.write(corrupt)

                # load should return empty (cache miss)
                data = svc.hash_store.load()
                self.assertEqual(data, {"version": 1, "entries": {}},
                                 f"should treat corrupt JSON as cache miss: {corrupt[:60]}")

                # audit should not crash
                resp = svc.audit(target_id="*")
                self.assertEqual(resp["coverage"]["status"], "complete",
                                 f"audit should complete despite corrupt store: {corrupt[:60]}")
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_corpus():
    """Copy the fixture corpus to a temp dir and return (temp_root, corpus_root)."""
    root = tempfile.mkdtemp()
    dst = os.path.join(root, "corpus")
    shutil.copytree(FIXTURE_CORPUS, dst)
    return root, dst



if __name__ == "__main__":
    unittest.main()
