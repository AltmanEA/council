"""Unit tests for the link-integrity step of tools/check_all.py.

Consensus sess-operator-surface-split O-3 (CI guard for the Phase 2 split
trigger, condition O-1(ii)):

  docs→manifest  — a docs/en (or docs/ru) document referencing a docs/...
                   path that does not exist or is not registered in
                   docs-manifest.yaml → HIGH (hard fail, exit 1; ADR-003
                   precedent for a prose invariant enforced by CI).
  code→docs      — comments/docstrings under scanned package directories
                   (LINK_INTEGRITY_CODE_DIRS; empty since the 2026-11-19
                   reconstruction deleted the Council service packages, so
                   this side is inert — kept as an extension point).

Every case runs the CLI (check_all.main) against a temp copy of the fixture
corpus tests/fixtures/check_all/corpus/ (same harness style as
tests/test_check_all.py); the shared fixture corpus is never modified.
"""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import check_all

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "fixtures", "check_all", "corpus")


def _clean_root():
    """Fresh temp copy of the clean fixture corpus."""
    d = tempfile.mkdtemp()
    root = os.path.join(d, "repo")
    shutil.copytree(CORPUS, root)
    return root


def _write(root, rel, text):
    abs_path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return abs_path


def _run(root, *argv):
    """Run the CLI; returns (exit_code, stdout_text, stderr_text)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = check_all.main(["--root", root] + list(argv))
    return rc, out.getvalue(), err.getvalue()


def _json_findings(root, *argv):
    rc, out, _ = _run(root, "--json", *argv)
    import json
    return rc, [json.loads(l) for l in out.splitlines() if l.strip()]


# Docs-side body appended to alpha/index.md; the token is a path the
# link-integrity regex matches (docs/en/... .md anchored on non-path chars).
def _append_ref(root, rel, line):
    abs_path = os.path.join(root, *rel.split("/"))
    with open(abs_path, encoding="utf-8") as fh:
        text = fh.read()
    with open(abs_path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n" + line + "\n")


class TestLinkIntegrityCleanCorpus(unittest.TestCase):
    def test_clean_fixture_corpus_no_link_findings(self):
        rc, findings = _json_findings(_clean_root(), "--rule", "link-integrity")
        self.assertEqual(rc, 0)
        self.assertEqual(findings, [])

    def test_registered_paths_pass(self):
        """A reference to a registered docs/en path stays clean."""
        root = _clean_root()
        _append_ref(root, "docs/en/alpha/index.md",
                    "See [beta](docs/en/beta/index.md) for details.")
        rc, findings = _json_findings(root, "--rule", "link-integrity")
        self.assertEqual(rc, 0)
        self.assertEqual([f for f in findings
                          if f["rule"] == "docs-manifest-link"], [])


class TestDocsToManifest(unittest.TestCase):
    """docs→manifest: HARD FAIL (high, exit 1) — O-3 first half."""

    def test_missing_file_reference_blocks(self):
        root = _clean_root()
        _append_ref(root, "docs/en/alpha/index.md",
                    "See docs/en/gamma/index.md for context.")
        rc, findings = _json_findings(root, "--rule", "link-integrity")
        self.assertEqual(rc, 1)
        hits = [f for f in findings if f["rule"] == "docs-manifest-link"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "high")
        self.assertEqual(hits[0]["file"], "docs/en/alpha/index.md")
        self.assertIn("docs/en/gamma/index.md", hits[0]["description"])
        self.assertIn("not a file under root", hits[0]["description"])

    def test_unregistered_existing_file_blocks(self):
        """A file that exists on disk but is absent from the manifest
        (rule-6 orphan is checked separately; link-integrity must catch the
        reference itself)."""
        root = _clean_root()
        _write(root, "docs/en/beta/extra.md", "# Extra\n")
        _append_ref(root, "docs/en/alpha/index.md",
                    "See docs/en/beta/extra.md for context.")
        rc, findings = _json_findings(root, "--rule", "link-integrity")
        self.assertEqual(rc, 1)
        hits = [f for f in findings if f["rule"] == "docs-manifest-link"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "high")
        self.assertIn("not registered in docs-manifest.yaml",
                      hits[0]["description"])

    def test_ru_reference_requires_registration(self):
        """docs/ru mirrors are covered: registered via has_translation in
        the manifest (regenerated from frontmatter, sole writer
        gen_manifest)."""
        root = _clean_root()
        # registered RU path: file present + alpha frontmatter has_translation
        _write(root, "docs/ru/alpha/index-RU.md",
               "# Документ\nid: alpha\nVersion: 1.0.0\nStatus: active\n"
               "Abstraction: protocol\nchangelog-path: "
               "CHANGELOGS/alpha.changes.md\n")
        alpha = os.path.join(root, "docs/en/alpha/index.md")
        with open(alpha, encoding="utf-8") as fh:
            text = fh.read()
        with open(alpha, "w", encoding="utf-8") as fh:
            fh.write(text.replace(
                "changelog-path: CHANGELOGS/alpha.changes.md",
                "changelog-path: CHANGELOGS/alpha.changes.md\n"
                "has_translation: docs/ru/alpha/index-RU.md", 1))
        import gen_manifest
        self.assertEqual(gen_manifest.main(["--root", root, "--write"]), 0)
        _append_ref(root, "docs/en/alpha/index.md",
                    "См. docs/ru/alpha/index-RU.md.")
        rc, findings = _json_findings(root, "--rule", "link-integrity")
        self.assertEqual(rc, 0)

        # missing file → blocks (never registered anywhere)
        _append_ref(root, "docs/en/alpha/index.md",
                    "См. docs/ru/beta/index-RU.md.")
        rc, findings = _json_findings(root, "--rule", "link-integrity")
        self.assertEqual(rc, 1)
        hits = [f for f in findings if f["rule"] == "docs-manifest-link"]
        self.assertEqual(len(hits), 1)
        self.assertIn("docs/ru/beta/index-RU.md", hits[0]["description"])

    def test_fenced_reference_is_ignored(self):
        root = _clean_root()
        _append_ref(root, "docs/en/alpha/index.md",
                    "```text\ndocs/en/nowhere/index.md\n```")
        rc, findings = _json_findings(root, "--rule", "link-integrity")
        self.assertEqual(rc, 0)
        self.assertEqual([f for f in findings
                          if f["rule"] == "docs-manifest-link"], [])

    def test_unparsable_manifest_skips_docs_side(self):
        """Missing/unparsable on-disk manifest → the check cannot judge
        registration: skip instead of failing closed (manifest-drift high
        from rule-6 owns the broken-manifest condition)."""
        root = _clean_root()
        _append_ref(root, "docs/en/alpha/index.md",
                    "See docs/en/gamma/index.md for context.")
        with open(os.path.join(root, "docs-manifest.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write("\t: : not yaml [\n")
        rc, findings = _json_findings(root, "--rule", "link-integrity")
        self.assertEqual(rc, 0)
        self.assertEqual([f for f in findings
                          if f["rule"] == "docs-manifest-link"], [])


class TestLiveCorpus(unittest.TestCase):
    """The real repository must stay clean under the new step."""

    REPO_ROOT = os.path.dirname(HERE)

    def test_live_repo_link_integrity_zero(self):
        rc, findings = _json_findings(self.REPO_ROOT, "--rule",
                                      "link-integrity")
        self.assertEqual(rc, 0)
        self.assertEqual(findings, [])

    def test_live_repo_link_integrity_strict_zero(self):
        rc, findings = _json_findings(self.REPO_ROOT, "--rule",
                                      "link-integrity", "--strict-links")
        self.assertEqual(rc, 0)
        self.assertEqual(findings, [])

    def test_full_scan_baseline_unchanged(self):
        """Regression guard: the new step adds no findings to the live
        baseline (28 low at the time of the O-3 implementation, operator
        may re-baseline; here we assert only the blocking count)."""
        rc, findings = _json_findings(self.REPO_ROOT)
        self.assertEqual(rc, 0)
        blocking = [f for f in findings
                    if f["severity"] in ("high", "medium")]
        self.assertEqual(blocking, [])


if __name__ == "__main__":
    unittest.main()
