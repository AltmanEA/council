"""Unit tests for tools/check_all.py (Stage B, plan sess-doc-reliability-algo).

Every case runs the CLI (check_all.main) against a temp copy of the fixture
corpus tests/fixtures/check_all/corpus/ (clean, manifest parity verified) —
the gen_manifest fixtures are NOT modified. The final test class additionally
runs the checker against the LIVE repository corpus and asserts only that it
exits cleanly (0 or 1; live medium findings are warnings, not failures) and
that --json output parses as JSONL.
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
REPO_ROOT = os.path.dirname(HERE)


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


class TestCleanCorpus(unittest.TestCase):
    def test_clean_corpus_exit_0(self):
        root = _clean_root()
        rc, out, _ = _run(root)
        self.assertEqual(rc, 0, out)
        self.assertIn("PASS", out)

    def test_fixture_manifest_is_in_parity(self):
        # Guard: the checked-in fixture manifest must equal generated output.
        with open(os.path.join(CORPUS, "docs-manifest.yaml"), "rb") as fh:
            on_disk = fh.read()
        text, errors = gen_manifest.generate(CORPUS)
        self.assertEqual(errors, [])
        self.assertEqual(text.encode("utf-8"), on_disk)


class TestRule1LineCount(unittest.TestCase):
    def test_line_count_overflow_high(self):
        root = _clean_root()
        body = "\n".join(f"line {i}" for i in range(201))
        _write_doc(root, "docs/en/beta/index.md",
                   "# Beta Document\n"
                   "id: beta\n"
                   "Version: 0.1\n"
                   "Status: draft\n"
                   "Abstraction: conceptual\n"
                   "changelog-path: CHANGELOGS/beta.changes.md\n\n"
                   "## Purpose\n\n" + body + "\n")
        rc, records = _jsonl(root)
        hits = _find(records, rule="line-count", severity="high")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["file"], "docs/en/beta/index.md")
        self.assertEqual(rc, 1)

    def test_metadata_and_blank_lines_not_counted(self):
        root = _clean_root()
        # 197 body + H1 + `## Purpose` = exactly 200 content lines despite a
        # much larger raw file (metadata block and blanks are excluded).
        body = "\n".join(f"line {i}" for i in range(197))
        _write_doc(root, "docs/en/beta/index.md",
                   "# Beta Document\n"
                   "id: beta\n"
                   "Version: 0.1\n"
                   "Status: draft\n"
                   "Abstraction: conceptual\n"
                   "changelog-path: CHANGELOGS/beta.changes.md\n"
                   "title: " + "x" * 60 + "\n\n\n\n"
                   "## Purpose\n\n" + body + "\n")
        _touch_manifest(root)  # new `title` field changes generated output
        rc, records = _jsonl(root)
        self.assertEqual(_find(records, rule="line-count"), [])
        self.assertEqual(rc, 0)


class TestRule2Changelog(unittest.TestCase):
    def test_missing_changelog_high(self):
        root = _clean_root()
        os.remove(os.path.join(root, "CHANGELOGS", "beta.changes.md"))
        rc, records = _jsonl(root)
        hits = _find(records, rule="changelog-path-missing", severity="high")
        self.assertEqual([h["file"] for h in hits], ["docs/en/beta/index.md"])
        self.assertEqual(rc, 1)

    def test_changelog_wrong_location_medium(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/beta/index.md")
        _write_doc(root, "docs/en/beta/index.md", text.replace(
            "changelog-path: CHANGELOGS/beta.changes.md",
            "changelog-path: notes/beta.changes.md"))
        _, records = _jsonl(root)
        self.assertTrue(_find(records, rule="changelog-path-location",
                              severity="medium"))


class TestRule4CrossRefs(unittest.TestCase):
    def test_broken_anchor_medium_not_blocking(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee [beta section](beta/index.md#no-such-heading).\n")
        rc, records = _jsonl(root)
        hits = _find(records, rule="broken-anchor", severity="medium")
        self.assertTrue(hits)
        self.assertEqual(rc, 0)  # medium does not block at default severity
        rc_strict, _, _ = _run(root, "--strict")
        self.assertEqual(rc_strict, 1)

    def test_missing_reference_docs_en_path_high(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee `docs/en/ghost/index.md` for details.\n")
        rc, records = _jsonl(root)
        hits = _find(records, rule="missing-reference", severity="high")
        self.assertTrue(any("ghost" in h["description"] for h in hits))
        self.assertEqual(rc, 1)

    def test_unresolved_section_reference_medium(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/beta/index.md")
        _write_doc(root, "docs/en/beta/index.md",
                   text + "\nSee §Totally Absent Section for semantics.\n")
        rc, records = _jsonl(root)
        hits = _find(records, rule="unresolved-reference", severity="medium")
        self.assertTrue(any("Totally Absent" in h["description"] for h in hits))
        self.assertEqual(rc, 0)

    def test_section_reference_to_real_heading_passes(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/beta/index.md")
        _write_doc(root, "docs/en/beta/index.md",
                   text + "\nAs described in §Purpose above, this is fine.\n")
        _, records = _jsonl(root)
        self.assertEqual(_find(records, rule="unresolved-reference"), [])

    # -- (a) relative-path file references ------------------------------------

    def _add_deep_doc(self, root, body):
        """Add docs/en/alpha/deep.md (parent index carries
        allow_non_index_paths) with caller-supplied body, mirroring the
        live-corpus layer-2.md `../index.md` regression."""
        _write_doc(root, "docs/en/alpha/deep.md",
                   "# Deep Doc\n"
                   "id: deep\n"
                   "Version: 0.1\n"
                   "Status: draft\n"
                   "Abstraction: reference\n"
                   "changelog-path: CHANGELOGS/alpha.changes.md\n\n" + body)
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text.replace("changelog-path: CHANGELOGS/alpha.changes.md",
                                "changelog-path: CHANGELOGS/alpha.changes.md\n"
                                "allow_non_index_paths: true"))
        _touch_manifest(root)

    def test_relative_path_reference_resolves_file_relative_first(self):
        """`../index.md` from a non-index file resolves against the FILE PATH
        (join), landing on the containing folder's index.md (live-corpus
        layer-2.md regression); `../../beta/index.md` reaches the sibling
        folder. Both must pass with zero findings."""
        root = _clean_root()
        self._add_deep_doc(
            root,
            "## Purpose\n\n"
            "Placement: `../index.md` §Purpose; sibling `../../beta/index.md`.\n\n"
            "## Cross-References\n\n"
            "- `../index.md` — layer model and dependency rules\n")
        rc, records = _jsonl(root)
        self.assertEqual(_find(records, rule="missing-reference"), [])
        self.assertEqual(_find(records, rule="broken-anchor"), [])
        self.assertEqual(_find(records, rule="unresolved-reference"), [])
        self.assertEqual(rc, 0)

    def test_relative_path_reference_broken_high(self):
        """A relative token that resolves nowhere is high missing-reference."""
        root = _clean_root()
        self._add_deep_doc(
            root,
            "## Purpose\n\nDeep.\n\n"
            "## Cross-References\n\n"
            "- `../ghost/index.md` — nonexistent sibling\n")
        rc, records = _jsonl(root)
        hits = _find(records, rule="missing-reference", severity="high")
        self.assertTrue(any("../ghost/index.md" in h["description"]
                            for h in hits))
        self.assertEqual(rc, 1)

    # -- (b) same-line file detection ------------------------------------------

    def test_same_line_named_file_heading_hit_passes(self):
        """Line names the target file (backticked, trailing comma) and the
        §Name exists in that file -> PASS."""
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nField semantics are in `beta/index.md`, "
                   "§Purpose, verbatim.\n")
        _, records = _jsonl(root)
        self.assertEqual(_find(records, rule="broken-anchor"), [])
        self.assertEqual(_find(records, rule="unresolved-reference"), [])

    def test_same_line_named_file_heading_miss_high(self):
        """Line names the target file and the §Name is absent from it ->
        broken-anchor HIGH (bound-file verification)."""
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee `beta/index.md`, §Nonexistent Bound Target "
                   "for details.\n")
        rc, records = _jsonl(root)
        hits = _find(records, rule="broken-anchor", severity="high")
        self.assertTrue(any("Nonexistent Bound Target" in h["description"]
                            for h in hits))
        self.assertEqual(rc, 1)

    def test_same_line_plain_path_no_backticks_hit_passes(self):
        """Without backticks: plain docs/en path + §Name hit passes."""
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nPer docs/en/beta/index.md §Purpose this is ok.\n")
        _, records = _jsonl(root)
        self.assertEqual(_find(records, rule="broken-anchor"), [])
        self.assertEqual(_find(records, rule="unresolved-reference"), [])

    # -- (c) corpus-wide heading index ------------------------------------------

    def test_corpus_wide_unique_heading_resolves_passes(self):
        """No file named on the line: a §Name matching exactly one corpus
        heading (in another file) resolves there and passes."""
        root = _clean_root()
        text = _read_doc(root, "docs/en/beta/index.md")
        _write_doc(root, "docs/en/beta/index.md",
                   text + "\n## Gamma Rules\n\nUnique heading in beta.\n")
        _write_doc(root, "docs/en/gamma/index.md",
                   "# Gamma Document\n"
                   "id: gamma\n"
                   "Version: 0.1\n"
                   "Status: draft\n"
                   "Abstraction: conceptual\n"
                   "changelog-path: CHANGELOGS/beta.changes.md\n\n"
                   "## Purpose\n\n"
                   "Behavior follows §Gamma Rules as specified.\n")
        _touch_manifest(root)
        _, records = _jsonl(root)
        self.assertEqual(
            _find(records, rule="unresolved-reference"), [])
        self.assertEqual(
            _find(records, rule="ambiguous-section-reference"), [])

    def test_ambiguous_heading_low_not_medium(self):
        """No file named, §Name matches multiple corpus headings -> LOW
        ambiguous-section-reference (never medium)."""
        root = _clean_root()
        for rel in ("docs/en/alpha/index.md", "docs/en/beta/index.md"):
            text = _read_doc(root, rel)
            _write_doc(root, rel,
                       text + "\n## Shared Heading\n\nShared in two files.\n")
        _write_doc(root, "docs/en/gamma/index.md",
                   "# Gamma Document\n"
                   "id: gamma\n"
                   "Version: 0.1\n"
                   "Status: draft\n"
                   "Abstraction: conceptual\n"
                   "changelog-path: CHANGELOGS/beta.changes.md\n\n"
                   "## Purpose\n\n"
                   "Compare §Shared Heading across documents.\n")
        _touch_manifest(root)
        rc, records = _jsonl(root)
        hits = _find(records, rule="ambiguous-section-reference")
        self.assertTrue(any("Shared Heading" in h["description"]
                            for h in hits))
        self.assertTrue(all(h["severity"] == "low" for h in hits))
        # candidates are listed (max 3)
        hit = next(h for h in hits if "Shared Heading" in h["description"])
        self.assertIn("docs/en/alpha/index.md", hit["description"])
        self.assertIn("docs/en/beta/index.md", hit["description"])
        self.assertEqual(rc, 0)  # low never blocks at default severity

    def test_zero_matches_stays_medium(self):
        """§Name matching no heading corpus-wide stays medium
        unresolved-reference (the signal worth keeping)."""
        root = _clean_root()
        _write_doc(root, "docs/en/gamma/index.md",
                   "# Gamma Document\n"
                   "id: gamma\n"
                   "Version: 0.1\n"
                   "Status: draft\n"
                   "Abstraction: conceptual\n"
                   "changelog-path: CHANGELOGS/beta.changes.md\n\n"
                   "## Purpose\n\n"
                   "See §Wholly Unknown Topic for semantics.\n")
        _touch_manifest(root)
        rc, records = _jsonl(root)
        hits = _find(records, rule="unresolved-reference", severity="medium")
        self.assertTrue(any("Wholly Unknown Topic" in h["description"]
                            for h in hits))
        self.assertEqual(rc, 0)

    # -- (d) implementation-file §refs (AGENTS.md §1.6) --------------------------

    def test_implementation_file_ref_hit_passes(self):
        """`fallback/index.md` §Name resolves against the real file's
        headings: found -> PASS."""
        root = _clean_root()
        _write_doc(root, "fallback/index.md",
                   "# Subagent Fallback Mode\n\n"
                   "## Overview\n\nFlow.\n\n"
                   "## Session workspace convention\n\nLayout.\n")
        text = _read_doc(root, "docs/en/beta/index.md")
        _write_doc(root, "docs/en/beta/index.md",
                   text + "\nLayout per `fallback/index.md` "
                   "§Session workspace convention.\n")
        _, records = _jsonl(root)
        self.assertEqual(_find(records, rule="unresolved-reference"), [])
        self.assertEqual(_find(records, rule="broken-anchor"), [])

    def test_implementation_file_ref_miss_low_never_medium(self):
        """`AGENTS.md` §Name not found -> LOW broken-anchor; the line must
        never surface at medium/high (out of manifest scope)."""
        root = _clean_root()
        _write_doc(root, "AGENTS.md",
                   "# Documentation Agent Instructions\n\n"
                   "## 1. Purpose\n\nOps guide.\n\n"
                   "## 7. File Conventions\n\nNaming.\n")
        text = _read_doc(root, "docs/en/beta/index.md")
        _write_doc(root, "docs/en/beta/index.md",
                   text + "\nConventions per `AGENTS.md` "
                   "§Nonexistent Chapter Here.\n")
        rc, records = _jsonl(root)
        hits = _find(records, rule="broken-anchor")
        self.assertTrue(any("Nonexistent Chapter Here" in h["description"]
                            for h in hits))
        hit = next(h for h in hits if "Nonexistent Chapter Here" in h["description"])
        self.assertEqual(hit["severity"], "low")
        self.assertEqual(rc, 0)

    def test_implementation_file_numeric_ref_resolves(self):
        """Numeric §refs resolve against numbered headings of the named
        implementation file: found -> PASS."""
        root = _clean_root()
        _write_doc(root, "AGENTS.md",
                   "# Documentation Agent Instructions\n\n"
                   "## 1. Purpose\n\nOps guide.\n\n"
                   "### 1.7 Tooling Separation\n\nTools.\n")
        text = _read_doc(root, "docs/en/beta/index.md")
        _write_doc(root, "docs/en/beta/index.md",
                   text + "\nAll sessions run in fallback mode per "
                   "`AGENTS.md` §1.7.\n")
        _, records = _jsonl(root)
        self.assertEqual(_find(records, rule="unresolved-reference"), [])
        self.assertEqual(_find(records, rule="broken-anchor"), [])


class TestHumanReadableTokenFormat(unittest.TestCase):
    """Token contract with tools/hooks/pre-commit: every finding line in the
    DEFAULT human-readable mode is `rule=<id> severity=<sev> file=<path>
    <description>` so the hook's `grep 'severity=high'` works unchanged."""

    def test_finding_lines_carry_tokens_and_parse(self):
        root = _clean_root()
        os.remove(os.path.join(root, "CHANGELOGS", "beta.changes.md"))
        rc, out, _ = _run(root)
        self.assertEqual(rc, 1)
        finding_lines = [ln for ln in out.splitlines() if "rule=" in ln]
        self.assertTrue(finding_lines)
        for ln in finding_lines:
            head, _, tail = ln.partition(" ")
            parts = dict(kv.split("=", 1) for kv in (head, ln.split(" ")[1],
                                                     ln.split(" ")[2]))
            self.assertEqual(set(parts), {"rule", "severity", "file"})
            self.assertIn(parts["severity"], ("low", "medium", "high"))
            self.assertTrue(parts["file"].endswith(".md")
                            or parts["file"].endswith(".yaml"))
            self.assertTrue(tail.strip())  # description present
        # the hook's block-mode filter:
        self.assertTrue(any("severity=high" in ln for ln in finding_lines))

    def test_high_finding_line_contains_literal_severity_high(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee `docs/en/ghost/index.md` for details.\n")
        rc, out, _ = _run(root)
        self.assertEqual(rc, 1)
        high_lines = [ln for ln in out.splitlines() if "severity=high" in ln]
        self.assertTrue(high_lines)
        self.assertTrue(any("rule=missing-reference" in ln for ln in high_lines))
        # hook grep simulation: block-mode would match
        self.assertTrue(all(ln.startswith("rule=") for ln in high_lines))

    def test_json_mode_unchanged(self):
        """--json still emits exactly {rule, severity, file, description}."""
        root = _clean_root()
        os.remove(os.path.join(root, "CHANGELOGS", "beta.changes.md"))
        rc, records = _jsonl(root)
        self.assertEqual(rc, 1)
        self.assertTrue(records)
        for r in records:
            self.assertEqual(set(r.keys()),
                             {"rule", "severity", "file", "description"})
        self.assertTrue(any(r["severity"] == "high" for r in records))


class TestRule6ManifestParity(unittest.TestCase):
    def test_manifest_drift_high(self):
        root = _clean_root()
        manifest = os.path.join(root, "docs-manifest.yaml")
        with open(manifest, "a", encoding="utf-8") as fh:
            fh.write("\n# hand-edited\n")
        rc, records = _jsonl(root)
        hits = _find(records, rule="manifest-drift", severity="high")
        self.assertEqual(len(hits), 1)
        self.assertIn("diff lines", hits[0]["description"])
        self.assertEqual(rc, 1)

    def test_orphan_high(self):
        """A docs/en file that cannot enter the generated entries (frontmatter
        parse failure) and is not covered by an allow_non_index_paths parent
        is an orphan (high)."""
        root = _clean_root()
        _write_doc(root, "docs/en/beta/extras.md",
                   "# Extras\n"
                   "Version: 0.1\n"  # no id -> parse failure -> not generated
                   "Status: draft\n"
                   "Abstraction: reference\n"
                   "changelog-path: CHANGELOGS/beta.changes.md\n\n"
                   "## Purpose\n\nNot in the generated manifest and not covered\n"
                   "by an allow_non_index_paths parent.\n")
        rc, records = _jsonl(root)
        hits = _find(records, rule="orphan", severity="high")
        self.assertEqual([h["file"] for h in hits], ["docs/en/beta/extras.md"])
        self.assertEqual(rc, 1)

    def test_non_index_allowed_by_parent_index_not_orphan(self):
        root = _clean_root()
        # Give alpha allow_non_index_paths; add a non-listed sibling that
        # cannot be generated (missing id). Parent coverage suppresses the
        # orphan finding (the frontmatter finding still fires, and naming is
        # satisfied because the parent index carries the flag).
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text.replace("changelog-path: CHANGELOGS/alpha.changes.md",
                                "changelog-path: CHANGELOGS/alpha.changes.md\n"
                                "allow_non_index_paths: true"))
        _write_doc(root, "docs/en/alpha/extra.md",
                   "# Extra\n"
                   "Version: 0.1\n"  # no id -> not in generated entries
                   "Status: draft\n"
                   "Abstraction: reference\n"
                   "changelog-path: CHANGELOGS/beta.changes.md\n\n"
                   "## Purpose\n\nCovered by parent index.\n")
        # (manifest intentionally left stale: --write refuses on the parse
        # error; parity-skipped/drift findings are not asserted here)
        rc, records = _jsonl(root)
        self.assertEqual(_find(records, rule="orphan"), [])
        self.assertEqual(_find(records, rule="naming"), [])
        self.assertTrue(_find(records, rule="frontmatter", severity="high"))


class TestNaming(unittest.TestCase):
    def test_non_kebab_folder_high(self):
        root = _clean_root()
        _write_doc(root, "docs/en/Bad Folder/index.md",
                   "# Bad\n"
                   "id: bad\n"
                   "Version: 0.1\n"
                   "Status: draft\n"
                   "Abstraction: reference\n"
                   "changelog-path: CHANGELOGS/beta.changes.md\n\n"
                   "## Purpose\n\nNon kebab folder.\n")
        _touch_manifest(root)
        rc, records = _jsonl(root)
        hits = _find(records, rule="naming", severity="high")
        self.assertTrue(any("Bad Folder" in h["description"] for h in hits))
        self.assertEqual(rc, 1)


class TestSchema(unittest.TestCase):
    def test_last_modified_deprecated_warning(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/beta/index.md")
        _write_doc(root, "docs/en/beta/index.md", text.replace(
            "Status: draft", "Status: draft\nLast Modified: 2026-01-01"))
        rc, records = _jsonl(root)
        hits = _find(records, rule="last-modified-deprecated", severity="warning")
        self.assertEqual(len(hits), 1)
        self.assertEqual(rc, 0)  # warning never blocks
        rc_strict, _, _ = _run(root, "--strict")
        self.assertEqual(rc_strict, 1)

    def test_bad_frontmatter_is_finding_not_exit_2(self):
        """DocMetaError corpus condition -> high finding, exit 1 (not 2)."""
        root = _clean_root()
        _write_doc(root, "docs/en/broken/index.md",
                   "# Broken\nVersion: 0.1\nStatus: draft\n"
                   "Abstraction: reference\n"
                   "changelog-path: CHANGELOGS/beta.changes.md\n\n"
                   "## Purpose\n\nMissing id.\n")
        rc, out, err = _run(root)
        self.assertEqual(rc, 1, out + err)
        self.assertNotIn("INTERNAL ERROR", err)
        _, records = _jsonl(root)
        self.assertTrue(_find(records, rule="frontmatter", severity="high"))


class TestCli(unittest.TestCase):
    def test_json_output_is_jsonl_with_required_keys(self):
        root = _clean_root()
        os.remove(os.path.join(root, "CHANGELOGS", "beta.changes.md"))
        rc, records = _jsonl(root)
        self.assertTrue(records)
        for r in records:
            self.assertEqual(set(r.keys()),
                             {"rule", "severity", "file", "description"})
            self.assertIsInstance(r["rule"], str)
            self.assertIn(r["severity"], ("warning", "low", "medium", "high"))

    def test_severity_filter_and_rule_selection(self):
        root = _clean_root()
        # medium-only finding (broken anchor)
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee [x](beta/index.md#nope).\n")
        rc_default, _, _ = _run(root)
        self.assertEqual(rc_default, 0)
        rc_med, _, _ = _run(root, "--severity", "medium")
        self.assertEqual(rc_med, 1)
        # --rule selection excludes the cross-ref group -> clean
        rc_sel, _, _ = _run(root, "--rule", "line-count", "--rule", "naming")
        self.assertEqual(rc_sel, 0)

    def test_unknown_rule_token_exit_2(self):
        root = _clean_root()
        rc, _, err = _run(root, "--rule", "glossary")  # 3 is not implemented
        self.assertEqual(rc, 2)
        self.assertIn("unknown --rule", err)


class TestInternalError(unittest.TestCase):
    def test_unreadable_manifest_fails_loud_exit_2(self):
        """docs-manifest.yaml as a directory -> IsADirectoryError inside
        rule-6: validator-side IO failure must exit 2 with remediation,
        distinct from corpus findings."""
        root = _clean_root()
        os.remove(os.path.join(root, "docs-manifest.yaml"))
        os.mkdir(os.path.join(root, "docs-manifest.yaml"))
        rc, out, err = _run(root)
        self.assertEqual(rc, 2)
        self.assertIn("INTERNAL ERROR", err)
        self.assertIn("Remediation", err)
        self.assertIn("Traceback", err)


class TestLiveCorpus(unittest.TestCase):
    """Smoke run against the real repository. Findings here are reported
    verbatim to the operator by design; the tool must not crash."""

    def test_live_corpus_runs_clean_exit_code(self):
        rc, out, err = _run(REPO_ROOT, "--json")
        self.assertIn(rc, (0, 1), err)
        for line in out.splitlines():
            rec = json.loads(line)
            self.assertEqual(set(rec.keys()),
                             {"rule", "severity", "file", "description"})


if __name__ == "__main__":
    unittest.main()
