"""Unit tests for --core-root cross-root link resolution in check_all.py.

Each test covers exactly one acceptance criterion (AC-1 .. AC-7) from the
dual-root isolation task (sess-dist-isolated-install-2026-11-22).

Tests build minimal temp corpora (frontmatter + docs) so that unrelated rules
don't fire.  Every case invokes the CLI via the `_run` helper which calls
`check_all.main()` in-process, mirroring the style of tests/test_check_all.py.

Baseline (before implementation): tests that exercise --core-root fail because
argparse rejects the unknown flag (exit 2).  This is the expected red state.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import check_all
import gen_manifest

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures", "check_all")
CORPUS = os.path.join(FIXTURES, "corpus")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_root():
    """Fresh temp copy of the clean fixture corpus."""
    d = tempfile.mkdtemp()
    root = os.path.join(d, "repo")
    shutil.copytree(CORPUS, root)
    return root


def _write_doc(root, rel, text):
    """Write *text* to <root>/rel (creates parent dirs as needed)."""
    abs_path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return abs_path


def _read_doc(root, rel):
    with open(os.path.join(root, *rel.split("/")), encoding="utf-8") as fh:
        return fh.read()


def _run(root, *argv):
    """Run the CLI; returns (exit_code, stdout_text, stderr_text).

    Catches SystemExit (e.g. argparse --core-root unknown flag -> exit 2)
    so the test harness sees a regular return value instead of an unhandled
    SystemExit that unittest would report as ERROR.
    """
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            rc = check_all.main(["--root", root] + list(argv))
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else 2
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


def _make_core_corpus(core_root):
    """Create a minimal core corpus at *core_root* with docs/en/foo/index.md.

    The core has a single doc 'foo' plus its changelog and manifest so it is
    a well-formed corpus in its own right.
    """
    docs_en = os.path.join(core_root, "docs", "en")
    os.makedirs(docs_en, exist_ok=True)

    _write_doc(core_root, "docs/en/foo/index.md",
               "# Foo Core\n"
               "id: foo\n"
               "Version: 1.0.0\n"
               "Status: draft\n"
               "Abstraction: reference\n"
               "changelog-path: CHANGELOGS/core.changes.md\n\n"
               "## Purpose\n\n"
               "Core framework document. Referenced from the host.\n")

    _write_doc(core_root, "CHANGELOGS/core.changes.md",
               "# Changelog\n\n## 2026-01-01\n\nInitial.\n")

    _write_doc(core_root, "docs-manifest.yaml",
               "path: .\n"
               "version: 1.0.0\n"
               "documents:\n"
               "  - path: docs/en/foo/index.md\n"
               "    id: foo\n"
               "    version: 1.0.0\n"
               "    status: draft\n"
               "    abstraction: reference\n")

    return core_root


# Minimal host alpha doc referencing docs/en/foo/index.md
_HOST_ALPHA_BODY = (
    "# Alpha Document\n"
    "id: alpha\n"
    "Version: 1.0.0\n"
    "Status: active\n"
    "Abstraction: protocol\n"
    "changelog-path: CHANGELOGS/alpha.changes.md\n"
    "references: [beta, foo]\n\n"
    "## Purpose\n\n"
    "Host document referencing a core doc.\n\n"
    "## Cross-References\n\n"
    "- `beta`\n"
    "- `foo`\n\n"
    "## Details\n\n"
    "See `docs/en/foo/index.md` for the core spec.\n"
)


# ---------------------------------------------------------------------------
# AC-1: core-root resolves missing host reference -> NO finding
# ---------------------------------------------------------------------------

class TestAC1CoreResolvesMissingRef(unittest.TestCase):
    """AC-1: With --root R --core-root C, a host doc referencing docs/en/foo/
    index.md (exists only at C/docs/en/foo/index.md) produces NO
    missing-reference / link-integrity finding for that reference."""

    def test_no_missing_reference_with_core_root(self):
        host = _clean_root()
        core = _make_core_corpus(tempfile.mkdtemp())

        _write_doc(host, "docs/en/alpha/index.md", _HOST_ALPHA_BODY)
        _touch_manifest(host)

        rc, out, err = _run(host, "--core-root", core, "--severity", "medium")
        rc_json, records = _jsonl(host, "--core-root", core)

        # No missing-reference finding for foo
        missing_refs = _find(records, rule="missing-reference")
        self.assertFalse(missing_refs,
                         f"expected no missing-reference but got: {[r['description'] for r in missing_refs]}")

        # No link-integrity docs->manifest failure for the foo path
        link_issues = _find(records, rule="docs-manifest-link")
        self.assertFalse(link_issues,
                         f"expected no docs-manifest-link but got: {[r['description'] for r in link_issues]}")

        # No broken anchor or unresolved-reference for the core path
        broken = _find(records, rule="broken-anchor")
        self.assertFalse(broken, f"expected no broken-anchor: {[r['description'] for r in broken]}")
        unresolved = _find(records, rule="unresolved-reference")
        self.assertFalse(unresolved, f"expected no unresolved-reference: {[r['description'] for r in unresolved]}")

        # Clean -> exit 0 (medium severity only, no findings)
        self.assertEqual(rc_json, 0, "expected exit 0 (clean), got " + str(rc_json))


# ---------------------------------------------------------------------------
# AC-2: without --core-root the same ref DOES produce high-severity finding
# ---------------------------------------------------------------------------

class TestAC2RegressionWithoutCoreRoot(unittest.TestCase):
    """AC-2: Without --core-root the same reference DOES produce the existing
    high-severity missing-file finding (regression guard)."""

    def test_high_missing_reference_without_core_root(self):
        host = _clean_root()

        _write_doc(host, "docs/en/alpha/index.md", _HOST_ALPHA_BODY)
        _touch_manifest(host)

        rc, out, err = _run(host)
        rc_json, records = _jsonl(host)

        # Should have a missing-reference for docs/en/foo/index.md
        missing_refs = _find(records, rule="missing-reference", severity="high")
        self.assertTrue(missing_refs,
                        f"expected high missing-reference but got: {records}")
        self.assertTrue(any("foo" in h["description"] for h in missing_refs),
                        f"expected 'foo' in description, got: {[h['description'] for h in missing_refs]}")

        # Also link-integrity docs->manifest failure
        link_issues = _find(records, rule="docs-manifest-link", severity="high")
        self.assertTrue(link_issues,
                        f"expected docs-manifest-link finding but got: {records}")

        # high finding -> exit 2
        self.assertEqual(rc_json, 2)


# ---------------------------------------------------------------------------
# AC-3: core corpus NOT merged into host audit
# ---------------------------------------------------------------------------

class TestAC3CoreNotMerged(unittest.TestCase):
    """AC-3: Core corpus is NOT merged into the host audit corpus: core docs
    are not subject to host manifest-parity checks, do not appear in the host
    docs list, and are not reported as orphans of the host manifest."""

    def test_core_docs_not_in_host_orphans(self):
        host = _clean_root()
        core = _make_core_corpus(tempfile.mkdtemp())

        _write_doc(host, "docs/en/alpha/index.md", _HOST_ALPHA_BODY)
        _touch_manifest(host)

        rc, out, err = _run(host, "--core-root", core)
        rc_json, records = _jsonl(host, "--core-root", core)

        # Must succeed to validate the assertions below
        self.assertEqual(rc_json, 0,
                         "expected clean audit, got exit " + str(rc_json))

        # No orphan for the core doc "foo"
        orphans = _find(records, rule="orphan")
        self.assertFalse(any("docs/en/foo/" in o["file"] for o in orphans),
                         f"core doc should not be host orphan: {orphans}")

        # No manifest-drift related to core files
        drift = _find(records, rule="manifest-drift")
        self.assertFalse(any("docs/en/foo/" in d["file"] for d in drift),
                         f"core doc should not trigger drift: {drift}")

        # Core doc should not appear in any finding as a host file
        for r in records:
            self.assertFalse(
                r["file"].startswith("docs/en/foo/"),
                f"core doc {r['file']} should not appear in host audit")


    def test_core_docs_not_subject_to_host_manifest_parity(self):
        """Even if core has a stale manifest, it must not affect the host audit."""
        host = _clean_root()
        core = _make_core_corpus(tempfile.mkdtemp())

        # Mess up the core manifest (drift)
        core_manifest = os.path.join(core, "docs-manifest.yaml")
        with open(core_manifest, "a", encoding="utf-8") as fh:
            fh.write("\n# drift\n")

        _write_doc(host, "docs/en/alpha/index.md", _HOST_ALPHA_BODY)
        _touch_manifest(host)

        rc_json, records = _jsonl(host, "--core-root", core)

        # Must succeed
        self.assertEqual(rc_json, 0,
                         "expected clean audit, got exit " + str(rc_json))

        # Host manifest should be clean (no drift from core)
        drift = _find(records, rule="manifest-drift")
        self.assertFalse(drift,
                         f"host manifest drift from core should not appear: {drift}")


# ---------------------------------------------------------------------------
# AC-4: precedence - host wins over core when same path exists in both
# ---------------------------------------------------------------------------

class TestAC4HostPrecedence(unittest.TestCase):
    """AC-4: Precedence: if the same relative path exists under BOTH roots,
    resolution uses the audited root's (host) copy; the core copy is ignored
    for that token."""

    def test_host_resolves_first_when_path_exists_both_roots(self):
        host = _clean_root()
        core = _make_core_corpus(tempfile.mkdtemp())

        # Host also has docs/en/foo/index.md (different content)
        _write_doc(host, "docs/en/foo/index.md",
                   "# Foo Host\n"
                   "id: foo-host\n"
                   "Version: 1.0.0\n"
                   "Status: draft\n"
                   "Abstraction: reference\n"
                   "changelog-path: CHANGELOGS/foo.changes.md\n\n"
                   "## Purpose\n\n"
                   "Host copy of foo.\n")
        _write_doc(host, "CHANGELOGS/foo.changes.md",
                   "# Changelog\n\n## 2026-01-01\n\nHost version.\n")

        # Host alpha references docs/en/foo/index.md (resolves to host)
        _write_doc(host, "docs/en/alpha/index.md", _HOST_ALPHA_BODY)
        _touch_manifest(host)

        rc_json, records = _jsonl(host, "--core-root", core)

        # No missing-reference - it resolves within host
        missing_refs = _find(records, rule="missing-reference")
        self.assertFalse(missing_refs,
                         f"expected no missing-reference (host should win): {records}")

        # No broken-anchor
        broken = _find(records, rule="broken-anchor")
        self.assertFalse(broken, f"expected no broken-anchor: {records}")

        # Clean result
        self.assertEqual(rc_json, 0)


# ---------------------------------------------------------------------------
# AC-5: --core-root given but docs/en does not exist -> clear error (exit 2)
# ---------------------------------------------------------------------------

class TestAC5InvalidCoreRoot(unittest.TestCase):
    """AC-5: If --core-root is given but <core-root>/docs/en does not exist,
    the tool exits with a clear error message naming --core-root (same error
    style as the existing "no docs/en directory under --root" error)."""

    def test_core_root_no_docs_en_exits_2(self):
        host = _clean_root()
        nonexistent = os.path.join(tempfile.mkdtemp(), "nonexistent_core")

        rc, out, err = _run(host, "--core-root", nonexistent)

        # Exit 2 for invalid core root
        self.assertEqual(rc, 2)

        # Error message should mention the flag name
        combined = err + out
        self.assertIn("--core-root", combined,
                      f"error should mention --core-root: {combined}")

    def test_core_root_broken_symlink_exits_2(self):
        host = _clean_root()
        core_tmp = tempfile.mkdtemp()
        broken_link = os.path.join(core_tmp, "broken_link")
        os.symlink("/nonexistent/path", broken_link)

        rc, out, err = _run(host, "--core-root", broken_link)

        self.assertEqual(rc, 2)
        self.assertIn("--core-root", err + out,
                      f"error should mention --core-root: {err}")


# ---------------------------------------------------------------------------
# AC-6: --root only (no --core-root): existing behaviour unchanged
# ---------------------------------------------------------------------------

class TestAC6BackwardCompatibility(unittest.TestCase):
    """AC-6: --root only (no --core-root): existing behaviour unchanged."""

    def test_clean_corpus_still_clean_without_core_root(self):
        root = _clean_root()
        rc, out, _ = _run(root)
        self.assertEqual(rc, 0, "clean corpus should exit 0")
        self.assertEqual(out, "", "clean corpus should produce silent output")

    def test_known_broken_ref_still_reported_without_core_root(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee `docs/en/ghost/index.md` for details.\n")
        _touch_manifest(root)
        rc, out, err = _run(root)
        rc_json, records = _jsonl(root)
        self.assertEqual(rc_json, 2)
        missing_refs = _find(records, rule="missing-reference", severity="high")
        self.assertTrue(any("ghost" in h["description"] for h in missing_refs))

    def test_severity_filter_still_works(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee [x](beta/index.md#nope).\n")
        _touch_manifest(root)
        rc_med, records_med = _jsonl(root, "--severity", "medium")
        self.assertEqual(rc_med, 1)
        self.assertTrue(records_med)
        rc_high, records_high = _jsonl(root, "--severity", "high")
        self.assertEqual(rc_high, 0)
        self.assertEqual(records_high, [])


# ---------------------------------------------------------------------------
# AC-7: exit-code semantics unchanged: 0 clean, 1 findings, 2 errors
# ---------------------------------------------------------------------------

class TestAC7ExitCodeSemantics(unittest.TestCase):
    """AC-7: Exit-code semantics unchanged: 0 = clean, 1 = findings at/above
    threshold, 2 = scan/usage errors."""

    def test_clean_exit_0(self):
        root = _clean_root()
        rc, _, _ = _run(root)
        self.assertEqual(rc, 0)

    def test_findings_exit_1(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee [x](beta/index.md#nope).\n")
        _touch_manifest(root)
        rc, out, _ = _run(root, "--severity", "medium")
        self.assertEqual(rc, 1, f"expected exit 1, got {rc}: {out}")

    def test_high_finding_exit_2(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee `docs/en/ghost/index.md` for details.\n")
        _touch_manifest(root)
        rc, _, _ = _run(root)
        self.assertEqual(rc, 2)

    def test_scan_error_exit_2(self):
        tmp = tempfile.mkdtemp()
        rc, _, err = _run(tmp)
        self.assertEqual(rc, 2)
        self.assertIn("docs/en", err.lower() or "error should mention docs/en")

    def test_core_root_invalid_exit_2(self):
        host = _clean_root()
        rc, out, err = _run(host, "--core-root", "/nonexistent/path")
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
