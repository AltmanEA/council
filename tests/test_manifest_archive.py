"""Unit tests for gen_manifest.py archive pass-through.

Verifies that archived documents (Status: archive in frontmatter) are
included in the manifest entries with their status preserved and their
path recorded — i.e., archive is NOT a drop condition for the manifest
generator (documenter-service/index.md §Archive, documentation-rules §2.6).
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import gen_manifest

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "check_all", "corpus")


def _clean_root():
    """Fresh temp copy of the clean fixture corpus."""
    d = tempfile.mkdtemp()
    root = os.path.join(d, "repo")
    shutil.copytree(FIXTURES, root)
    return root


def _write_doc(root, rel, text):
    abs_path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return abs_path


def _write_manifest_entry(root, rel, text):
    """Same as _write_doc but also touch the manifest."""
    _write_doc(root, rel, text)
    assert gen_manifest.main(["--root", root, "--write"]) == 0


def _find_entry(entries, path):
    """Find the manifest entry matching the given path."""
    for e in entries:
        if e["path"] == path:
            return e
    return None


# Archive document for manifest testing.
# Must include changelog-path so it parses into the manifest; status
# is 'archive' to exercise the pass-through behavior.
_ARCHIVE_DOC = """\
# Archived Document
id: archive-foo
Version: 0.1
Status: archive
Abstraction: reference
changelog-path: CHANGELOGS/beta.changes.md
"""


class TestManifestArchiveEntry(unittest.TestCase):
    """Test 4: gen_manifest.build_entries / --write emits an entry for
    docs/en/archive/foo/index.md with status exactly 'archive' and path
    the archive path (pass-through, not dropped)."""

    def test_archive_entry_present_with_status_archive(self):
        """An archived doc under docs/en/archive/ produces a manifest entry
        whose status is exactly 'archive' and whose path is the archive path."""
        root = _clean_root()
        _write_manifest_entry(root, "docs/en/archive/foo/index.md", _ARCHIVE_DOC)

        entries, errors = gen_manifest.build_entries(root)
        self.assertEqual(errors, [])

        entry = _find_entry(entries, "docs/en/archive/foo/index.md")
        self.assertIsNotNone(entry,
                             "Archive doc must produce a manifest entry")
        self.assertEqual(entry["status"], "archive")
        self.assertEqual(entry["id"], "archive-foo")
        self.assertEqual(entry["path"], "docs/en/archive/foo/index.md")

    def test_non_archive_entries_unchanged(self):
        """Existing non-archive docs in the fixture corpus are still present
        in the generated entries (no regression)."""
        root = _clean_root()

        entries, errors = gen_manifest.build_entries(root)
        self.assertEqual(errors, [])

        # beta is a known fixture entry
        entry = _find_entry(entries, "docs/en/beta/index.md")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["id"], "beta")
        self.assertEqual(entry["status"], "draft")

    def test_write_persists_archive_entry(self):
        """gen_manifest.main(['--write']) writes a manifest that includes the
        archive entry with status='archive'."""
        root = _clean_root()
        _write_manifest_entry(root, "docs/en/archive/foo/index.md", _ARCHIVE_DOC)

        manifest_path = os.path.join(root, "docs-manifest.yaml")
        self.assertTrue(os.path.exists(manifest_path))

        import yaml
        with open(manifest_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        archive_entries = [e for e in data["documents"]
                           if e["path"] == "docs/en/archive/foo/index.md"]
        self.assertEqual(len(archive_entries), 1)
        self.assertEqual(archive_entries[0]["status"], "archive")


if __name__ == "__main__":
    unittest.main()
