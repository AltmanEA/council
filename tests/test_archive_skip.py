"""Unit tests for the archive-exclusion filter in tools/check_all.py.

These tests verify that documents under docs/en/archive/ and docs/ru/archive/
are silently excluded from every check pass, per the archive convention
(documenter-service/index.md §Archive + §Audit tool, documentation-rules §2.6).

Pattern: copy the clean fixture corpus to a temp dir, inject archive and
non-archive docs with deliberate violations, then run check_all.main() and
assert on the --json findings.
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

import check_all
import gen_manifest

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures", "check_all")
CORPUS = os.path.join(FIXTURES, "corpus")
WORKROOT = None  # reused across methods in same test case


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _clean_root():
    """Fresh temp copy of the clean fixture corpus."""
    d = tempfile.mkdtemp()
    root = os.path.join(d, "repo")
    shutil.copytree(CORPUS, root)
    return root


def _write_doc(root, rel, text):
    abs_path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return abs_path


def _read_doc(root, rel):
    with open(os.path.join(root, *rel.split("/")), encoding="utf-8") as fh:
        return fh.read()


def _run(root, *argv):
    """Run the CLI; returns (exit_code, stdout_text, stderr_text)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = check_all.main(["--root", root] + list(argv))
    return rc, out.getvalue(), err.getvalue()


def _jsonl(root, *argv):
    rc, out, _ = _run(root, "--json", *argv)
    records = [json.loads(line) for line in out.splitlines() if line.strip()]
    return rc, records


def _touch_manifest(root):
    """Regenerate on-disk manifest so parity holds after corpus mutation."""
    assert gen_manifest.main(["--root", root, "--write"]) == 0


def _find(records, rule=None, severity=None):
    return [r for r in records
            if (rule is None or r["rule"] == rule)
            and (severity is None or r["severity"] == severity)]


# Archive document template with deliberate violations.
# Must include changelog-path so it parses into the manifest; the
# cross-ref violations remain so we can verify the filter works.
_ARCHIVE_DOC = """\
# Archived Document
id: archive-foo
Version: 0.1
Status: archive
Abstraction: reference
changelog-path: CHANGELOGS/beta.changes.md

## Superseded Purpose

This content is deliberately broken: it references a ghost file and a
non-existent section so we can verify the archive filter is active.

## Cross-References

- `docs/en/ghost/index.md` — missing file (high)
- See `beta/index.md#nope` — broken anchor (medium)
- See §Totally Absent Heading — unresolved ref (medium)
"""

# RU archived mirror with the same violations.
# No changelog-path required for RU docs (ru docs are not scanned by
# check_rule2_changelog); but the RU file still gets link-integrity
# scanning in check_link_integrity (docs/ru walk).  We reference a
# ghost docs/en file so that a docs-manifest-link high finding is
# produced — verifying that the archive filter must exclude RU files too.
_ARCHIVE_DOC_RU = """\
# Архивированный документ
id: archive-foo-ru
Version: 0.1
Status: archive
Abstraction: reference
has_translation: ru/archive/foo/index.md

## Цели

Этот контент намеренно сломан: ссылка на несуществующий файл.

## Cross-References

- `docs/en/ghost/index.md` — missing file (high)
"""

# Non-archive doc with the same violations (for comparison)
_NON_ARCHIVE_DOC = """\
# Non-Archive Violating Document
id: rogue
Version: 0.1
Status: draft
Abstraction: reference
changelog-path: CHANGELOGS/beta.changes.md

## Purpose

This document is NOT under archive but has the same violations.

## Cross-References

- `docs/en/ghost/index.md` — missing file (high)
- See `beta/index.md#nope` — broken anchor (medium)
- See §Totally Absent Heading — unresolved ref (medium)
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestArchiveExclusionEn(unittest.TestCase):
    """Test 1: An archived doc under docs/en/archive/ with deliberately
    non-compliant content produces ZERO findings attributable to that file."""

    def test_archive_doc_no_findings(self):
        root = _clean_root()
        # Create archive doc with violations
        _write_doc(root, "docs/en/archive/foo/index.md", _ARCHIVE_DOC)
        _touch_manifest(root)
        rc, records = _jsonl(root)
        # The archive file must NOT appear in any finding
        archive_findings = [r for r in records
                            if r["file"].startswith("docs/en/archive/")]
        self.assertEqual(archive_findings, [])
        # But there may be findings from other files — we don't care;
        # the archive file itself must be clean.


class TestArchiveExclusionRu(unittest.TestCase):
    """Test 2: An RU archived mirror under docs/ru/archive/ also produces
    zero findings attributable to that file."""

    def test_ru_archive_no_findings(self):
        root = _clean_root()
        # Create RU archive dir and doc
        _write_doc(root, "docs/ru/archive/foo/index.md", _ARCHIVE_DOC_RU)
        _touch_manifest(root)
        rc, records = _jsonl(root)
        ru_archive_findings = [r for r in records
                                if r["file"].startswith("docs/ru/archive/")]
        self.assertEqual(ru_archive_findings, [])


class TestArchiveExclusionVsNonArchive(unittest.TestCase):
    """Test 3: A NON-archived doc with the same violations STILL produces
    findings.  This proves the filter is scoped to the archive prefix, not
    globally disabling the checks."""

    def test_non_archive_violations_still_reported(self):
        root = _clean_root()
        # Archive doc (violations)
        _write_doc(root, "docs/en/archive/foo/index.md", _ARCHIVE_DOC)
        # Non-archive doc with the same violations
        _write_doc(root, "docs/en/rogue/index.md", _NON_ARCHIVE_DOC)
        _touch_manifest(root)
        rc, records = _jsonl(root)
        # Archive file: zero findings
        archive_findings = [r for r in records
                            if r["file"].startswith("docs/en/archive/")]
        self.assertEqual(archive_findings, [])
        # Non-archive file: must have at least one finding (high: missing-reference)
        rogue_findings = [r for r in records
                          if r["file"].startswith("docs/en/rogue/")]
        self.assertTrue(rogue_findings,
                        "Non-archive doc with violations must still produce findings")
        # Verify at least one high finding from the non-archive file
        rogue_high = _find(rogue_findings, severity="high")
        self.assertTrue(rogue_high,
                        "Non-archive doc should produce at least one high-severity finding")


class TestArchivePrefixPredicate(unittest.TestCase):
    """Test 5: The archive prefix predicate matches docs/en/archive/ exactly;
    files merely containing 'archive' elsewhere in their path are NOT excluded.
    Guards against substring matching."""

    def test_archive_substring_not_excluded(self):
        """A file under docs/en/archive-notes/ (contains 'archive' but is not
        under docs/en/archive/) must NOT be excluded from audit."""
        root = _clean_root()
        # "archive-notes" folder — NOT under docs/en/archive/ prefix
        _write_doc(root, "docs/en/archive-notes/index.md", _NON_ARCHIVE_DOC)
        _touch_manifest(root)
        rc, records = _jsonl(root)
        archive_notes_findings = [r for r in records
                                   if r["file"].startswith("docs/en/archive-notes/")]
        self.assertTrue(archive_notes_findings,
                        "docs/en/archive-notes/index.md must NOT be excluded")

    def test_archive_in_filename_not_excluded(self):
        """A file named archived-notes.md under docs/en/service-contract/
        must NOT be excluded from audit."""
        root = _clean_root()
        # Put non-archive doc with archive in filename under service-contract
        _write_doc(root, "docs/en/service-contract/archived-notes.md",
                   _NON_ARCHIVE_DOC)
        _touch_manifest(root)
        rc, records = _jsonl(root)
        archived_findings = [r for r in records
                              if r["file"] == "docs/en/service-contract/archived-notes.md"]
        self.assertTrue(archived_findings,
                        "docs/en/service-contract/archived-notes.md must NOT be excluded")


class TestArchivePrefixExcluded(unittest.TestCase):
    """Test that docs/en/archive/ IS correctly excluded (basic sanity)."""

    def test_en_archive_is_excluded(self):
        root = _clean_root()
        _write_doc(root, "docs/en/archive/foo/index.md", _ARCHIVE_DOC)
        _touch_manifest(root)
        rc, records = _jsonl(root)
        en_archive_findings = [r for r in records
                                if r["file"].startswith("docs/en/archive/")]
        self.assertEqual(en_archive_findings, [])


class TestArchivePrefixExcludedRu(unittest.TestCase):
    """Test that docs/ru/archive/ IS correctly excluded (basic sanity)."""

    def test_ru_archive_is_excluded(self):
        root = _clean_root()
        _write_doc(root, "docs/ru/archive/foo/index.md", _ARCHIVE_DOC_RU)
        _touch_manifest(root)
        rc, records = _jsonl(root)
        ru_archive_findings = [r for r in records
                                if r["file"].startswith("docs/ru/archive/")]
        self.assertEqual(ru_archive_findings, [])


if __name__ == "__main__":
    unittest.main()
