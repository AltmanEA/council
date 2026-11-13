"""Unit tests for tools/bump_version.py (Stage D, plan sess-doc-reliability-algo).

Runs the version writer against fixture corpora under
tests/fixtures/bump_version/ (copied into tempdirs; the live repo root and the
live docs-manifest.yaml are never touched).
"""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import bump_version
import gen_manifest

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "bump_version")
CORPUS = os.path.join(FIXTURES, "corpus")
BROKEN = os.path.join(FIXTURES, "broken")


def _copy_corpus():
    """Copy fixture corpus to a temp dir and generate its manifest."""
    d = tempfile.mkdtemp()
    root = os.path.join(d, "repo")
    shutil.copytree(CORPUS, root)
    assert gen_manifest.main(["--root", root, "--write"]) == 0
    return root


def _snapshot(root):
    """Map of repo-relative path -> raw bytes for every file under root."""
    out = {}
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            abs_path = os.path.join(dirpath, name)
            rel = os.path.relpath(abs_path, root).replace("\\", "/")
            with open(abs_path, "rb") as fh:
                out[rel] = fh.read()
    return out


def _run(root, *argv):
    """Run bump_version.main; returns (rc, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = bump_version.main(["--root", root, *argv])
    return rc, out.getvalue(), err.getvalue()


def _read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _doc_path(root, doc_id):
    return os.path.join(root, "docs", "en", doc_id, "index.md")


def _manifest_entry(root, doc_id):
    with open(os.path.join(root, "docs-manifest.yaml"), encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return next((e for e in data["documents"] if e["id"] == doc_id), None)


def _frontmatter_version(root, doc_id):
    header = bump_version.docmeta.parse_header(_read(_doc_path(root, doc_id)))
    return str(header.fields["Version"])


class BumpRules(unittest.TestCase):
    """Pure bump arithmetic: suffix preservation, missing components."""

    def test_patch_minor_major_and_draft_suffix(self):
        self.assertEqual(bump_version.bump_version("0.2.0-draft", "patch"), "0.2.1-draft")
        self.assertEqual(bump_version.bump_version("0.15.1-draft", "minor"), "0.16.0-draft")
        self.assertEqual(bump_version.bump_version("2.0.0", "major"), "3.0.0")
        self.assertEqual(bump_version.bump_version("1", "minor"), "1.1.0")
        self.assertEqual(bump_version.bump_version("1", "patch"), "1.0.1")
        self.assertEqual(bump_version.bump_version("1.5", "major"), "2.0.0")
        self.assertEqual(bump_version.bump_version("0.9.9-draft", "major"), "1.0.0-draft")

    def test_malformed_version_rejected(self):
        with self.assertRaises(bump_version.BumpError):
            bump_version.bump_version("1.2.3.4", "patch")


class HappyPath(unittest.TestCase):
    """patch / minor / major end-to-end on fixture documents."""

    def _assert_bumped(self, root, doc_id, old, new, note):
        cl = os.path.join(root, "CHANGELOGS", f"{doc_id}.changes.md")
        self.assertEqual(_frontmatter_version(root, doc_id), new)
        with open(cl, encoding="utf-8") as fh:
            self.assertEqual(fh.read().splitlines()[0], f"<!-- CHANGES v{new}: {note} -->")
        entry = _manifest_entry(root, doc_id)
        self.assertEqual(entry["version"], new)
        self.assertEqual(gen_manifest.main(["--root", root, "--check"]), 0)

    def test_patch_preserves_draft_suffix(self):
        root = _copy_corpus()
        rc, _, err = _run(root, "--id", "alpha", "--kind", "patch", "--note", "patched it")
        self.assertEqual(rc, 0, err)
        self._assert_bumped(root, "alpha", "0.2.0-draft", "0.2.1-draft", "patched it")

    def test_minor_resets_patch_preserves_draft(self):
        root = _copy_corpus()
        rc, _, err = _run(root, "--id", "delta", "--kind", "minor", "--note", "added section")
        self.assertEqual(rc, 0, err)
        self._assert_bumped(root, "delta", "0.15.1-draft", "0.16.0-draft", "added section")

    def test_minor_on_partial_version(self):
        root = _copy_corpus()
        rc, _, err = _run(root, "--id", "beta", "--kind", "minor", "--note", "missing parts -> 0")
        self.assertEqual(rc, 0, err)
        self._assert_bumped(root, "beta", "1", "1.1.0", "missing parts -> 0")

    def test_major_resets_minor_and_patch(self):
        root = _copy_corpus()
        rc, _, err = _run(root, "--id", "gamma", "--kind", "major", "--note", "rewrite")
        self.assertEqual(rc, 0, err)
        self._assert_bumped(root, "gamma", "2.0.0", "3.0.0", "rewrite")

    def test_manifest_parity_with_frontmatter(self):
        """Scenario 7: manifest version for the id matches document frontmatter."""
        root = _copy_corpus()
        rc, _, err = _run(root, "--id", "alpha", "--kind", "minor", "--note", "parity check")
        self.assertEqual(rc, 0, err)
        self.assertEqual(_manifest_entry(root, "alpha")["version"],
                         _frontmatter_version(root, "alpha"))


class NoteAndArgs(unittest.TestCase):
    def test_missing_note_exit_2_no_changes(self):
        """Scenario 2: --note missing -> exit 2, files byte-identical."""
        root = _copy_corpus()
        before = _snapshot(root)
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            bump_version.main(["--root", root, "--id", "alpha", "--kind", "patch"])
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(_snapshot(root), before)

    def test_blank_note_exit_2(self):
        root = _copy_corpus()
        before = _snapshot(root)
        rc, _, err = _run(root, "--id", "alpha", "--kind", "patch", "--note", "   ")
        self.assertEqual(rc, 2)
        self.assertIn("--note", err)
        self.assertEqual(_snapshot(root), before)

    def test_note_written_verbatim_first_line(self):
        """Scenario 3: note verbatim, entry is the FIRST changelog line."""
        root = _copy_corpus()
        note = "Fixed refs -- see §2.1; kept `<!-- markup -->` verbatim"
        rc, _, err = _run(root, "--id", "alpha", "--kind", "patch", "--note", note)
        self.assertEqual(rc, 0, err)
        cl = os.path.join(root, "CHANGELOGS", "alpha.changes.md")
        lines = _read(cl).splitlines()
        self.assertEqual(lines[0], f"<!-- CHANGES v0.2.1-draft: {note} -->")
        # Previous newest entry shifted down, still present.
        self.assertIn("<!-- CHANGES v0.2.0-draft: initial fixture changelog (alpha). -->", lines)

    def test_invalid_kind_exit_2(self):
        root = _copy_corpus()
        before = _snapshot(root)
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            bump_version.main(["--root", root, "--id", "alpha", "--kind", "huge", "--note", "x"])
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(_snapshot(root), before)


class Refusals(unittest.TestCase):
    def test_unknown_id_exit_2_no_changes(self):
        """Scenario 4: unknown --id -> non-zero exit, no changes anywhere."""
        root = _copy_corpus()
        before = _snapshot(root)
        rc, _, err = _run(root, "--id", "nonexistent", "--kind", "patch", "--note", "nope")
        self.assertEqual(rc, 2)
        self.assertIn("nonexistent", err)
        self.assertEqual(_snapshot(root), before)

    def test_malformed_version_refused(self):
        """Scenario 5a: Version violating _VERSION_RE -> refusal, no changes."""
        root = _copy_corpus()
        before = _snapshot(root)
        rc, _, err = _run(root, "--id", "zeta", "--kind", "patch", "--note", "should refuse")
        self.assertNotEqual(rc, 0)
        self.assertIn("version-format", err)
        self.assertEqual(_snapshot(root), before)

    def test_missing_required_key_refused(self):
        """Scenario 5b: frontmatter missing a required key -> refusal, no changes."""
        root = _copy_corpus()
        # Inject the broken document (kept out of the corpus: it breaks
        # build_entries for the whole corpus, which is itself the refusal path).
        doc_dir = os.path.join(root, "docs", "en", "epsilon")
        os.makedirs(doc_dir)
        shutil.copy(os.path.join(BROKEN, "epsilon_missing_abstraction.md"),
                    os.path.join(doc_dir, "index.md"))
        with open(os.path.join(root, "CHANGELOGS", "epsilon.changes.md"), "w") as fh:
            fh.write("<!-- CHANGES v0.1.0: seeded. -->\n")
        before = _snapshot(root)
        rc, _, err = _run(root, "--id", "epsilon", "--kind", "minor", "--note", "should refuse")
        self.assertEqual(rc, 2)
        self.assertIn("Abstraction", err)
        self.assertEqual(_snapshot(root), before)
        # A valid id also refuses while the corpus has a broken file (build_entries fails).
        rc, _, err = _run(root, "--id", "alpha", "--kind", "patch", "--note", "also refuse")
        self.assertEqual(rc, 2)
        self.assertEqual(_snapshot(root), before)


class AtomicityAndRollback(unittest.TestCase):
    def test_rollback_when_changelog_write_fails(self):
        """Scenario 6: changelog write fails after document write succeeded."""
        root = _copy_corpus()
        before = _snapshot(root)
        cl_abs = os.path.join(root, "CHANGELOGS", "alpha.changes.md")
        real_write = bump_version._atomic_write

        def failing_write(path, data):
            if os.path.abspath(path) == cl_abs:
                raise OSError("simulated changelog write failure")
            real_write(path, data)

        original = bump_version._atomic_write
        bump_version._atomic_write = failing_write
        try:
            rc, _, err = _run(root, "--id", "alpha", "--kind", "patch", "--note", "boom")
        finally:
            bump_version._atomic_write = original
        self.assertNotEqual(rc, 0)
        self.assertIn("rolled back", err)
        after = _snapshot(root)
        self.assertEqual(after["docs/en/alpha/index.md"],
                         before["docs/en/alpha/index.md"])  # document restored
        self.assertEqual(after["docs-manifest.yaml"], before["docs-manifest.yaml"])
        self.assertEqual(after, before)  # nothing anywhere changed
        leftovers = [n for n in os.listdir(root) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_only_version_line_changed(self):
        """Scenario 9: bytes outside the Version: line are unchanged (1-line diff)."""
        root = _copy_corpus()
        before = _snapshot(root)
        rc, _, err = _run(root, "--id", "alpha", "--kind", "minor", "--note", "one line only")
        self.assertEqual(rc, 0, err)
        with open(_doc_path(root, "alpha"), "rb") as fh:
            after = fh.read()
        old_lines = before["docs/en/alpha/index.md"].decode("utf-8").splitlines()
        new_lines = after.decode("utf-8").splitlines()
        self.assertEqual(len(old_lines), len(new_lines))
        diffs = [i for i, (a, b) in enumerate(zip(old_lines, new_lines)) if a != b]
        self.assertEqual(len(diffs), 1)
        self.assertEqual(old_lines[diffs[0]], "Version: 0.2.0-draft")
        self.assertEqual(new_lines[diffs[0]], "Version: 0.3.0-draft")


class DryRun(unittest.TestCase):
    def test_dry_run_plan_printed_zero_fs_changes(self):
        """Scenario 8: --dry-run prints the plan, leaves all files untouched."""
        root = _copy_corpus()
        paths = [_doc_path(root, "alpha"),
                 os.path.join(root, "CHANGELOGS", "alpha.changes.md"),
                 os.path.join(root, "docs-manifest.yaml")]
        def _rb(p):
            with open(p, "rb") as fh:
                return fh.read()
        before_bytes = {p: _rb(p) for p in paths}
        before_stat = {p: os.stat(p) for p in paths}
        before_mtimes = {p: (st.st_mtime_ns, st.st_ctime_ns) for p, st in before_stat.items()}
        rc, out, err = _run(root, "--id", "delta", "--kind", "minor",
                            "--note", "dry-run smoke", "--dry-run")
        self.assertEqual(rc, 0, err)
        self.assertIn("0.15.1-draft -> 0.16.0-draft", out)
        self.assertIn("docs/en/delta/index.md", out)
        self.assertIn("CHANGELOGS/delta.changes.md", out)
        self.assertIn("<!-- CHANGES v0.16.0-draft: dry-run smoke -->", out)
        self.assertIn("docs-manifest.yaml", out)
        for p in paths:
            with open(p, "rb") as fh:
                self.assertEqual(fh.read(), before_bytes[p])
            self.assertEqual((os.stat(p).st_mtime_ns, os.stat(p).st_ctime_ns), before_mtimes[p])
        # And the refusal paths also work in dry-run mode:
        rc, _, _ = _run(root, "--id", "zeta", "--kind", "patch", "--note", "x", "--dry-run")
        self.assertEqual(rc, 2)


class NewlineConvention(unittest.TestCase):
    def test_crlf_document_and_changelog_stay_crlf(self):
        """Scenario 10: CRLF fixture keeps CRLF in document and changelog."""
        root = _copy_corpus()
        for p in (_doc_path(root, "alpha"), os.path.join(root, "CHANGELOGS", "alpha.changes.md")):
            with open(p, "rb") as fh:
                data = fh.read()
            with open(p, "wb") as fh:
                fh.write(data.replace(b"\n", b"\r\n"))
        rc, _, err = _run(root, "--id", "alpha", "--kind", "patch", "--note", "crlf preserved")
        self.assertEqual(rc, 0, err)
        expected_first = "<!-- CHANGES v0.2.1-draft: crlf preserved -->"
        for p in (_doc_path(root, "alpha"), os.path.join(root, "CHANGELOGS", "alpha.changes.md")):
            with open(p, "rb") as fh:
                data = fh.read()
            self.assertIn(b"\r\n", data)
            self.assertEqual(data.replace(b"\r\n", b"").count(b"\n"), 0)  # no lone LF
            if p.endswith("changes.md"):
                self.assertEqual(data.split(b"\r\n")[0].decode("utf-8"), expected_first)
        self.assertEqual(_frontmatter_version(root, "alpha"), "0.2.1-draft")
        # Manifest itself is LF by convention (gen_manifest renders LF).
        with open(os.path.join(root, "docs-manifest.yaml"), "rb") as fh:
            self.assertNotIn(b"\r\n", fh.read())


if __name__ == "__main__":
    unittest.main()
