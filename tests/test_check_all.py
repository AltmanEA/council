"""Unit tests for tools/check_all.py (Stage B, plan sess-doc-reliability-algo).

Every case runs the CLI (check_all.main) against a temp copy of the fixture
corpus tests/fixtures/check_all/corpus/ (clean, manifest parity verified) —
the gen_manifest fixtures are NOT modified. The final test class additionally
runs the checker against the LIVE repository corpus and asserts only that it
exits cleanly (0 or 1; live medium findings are warnings, not failures) and
that --json output parses as JSONL.

Updated for the frozen audit contract:
  --severity means *minimum REPORTED severity* (not minimum blocking);
  default is "low" (warning ≤ low ≤ medium ≤ high all reported);
  clean -> silent (no "OK" line);
  exit codes computed over REPORTED findings (0/1/2 per contract);
  human rendering: w/ marker lines, token contract on every hint line.
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
    def test_clean_corpus_exit_0_silent(self):
        """Contract §4 (human rendering): clean -> no output, exit 0."""
        root = _clean_root()
        rc, out, _ = _run(root)
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_fixture_manifest_is_in_parity(self):
        # Guard: the checked-in fixture manifest must equal generated output.
        with open(os.path.join(CORPUS, "docs-manifest.yaml"), "rb") as fh:
            on_disk = fh.read()
        text, errors = gen_manifest.generate(CORPUS)
        self.assertEqual(errors, [])
        self.assertEqual(text.encode("utf-8"), on_disk)


class TestContractRenderExitCodes(unittest.TestCase):
    """Frozen contract: exit codes and rendering for human-readable output.

    §1.  exit 0 = no reported findings; exit 1 = findings, none high;
         exit 2 = at least one high reported.
    §4.  human rendering: clean=silent; no-high = "\u26a0 findings: N";
         high = "\U0001f6a8 critical: N" then "\u26a0 findings: M"; then hint lines.
    """

    def test_clean_silent_no_ok_line(self):
        """Clean corpus: stdout empty, exit 0 (no "OK" line)."""
        root = _clean_root()
        rc, out, _ = _run(root)
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_clean_silent_under_severity_low(self):
        """Even with --severity low, a clean corpus produces no output."""
        root = _clean_root()
        rc, out, _ = _run(root, "--severity", "low")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_low_only_finding_severity_warn_marker_exit_1(self):
        """Findings at low/medium only, --severity low -> "\u26a0 findings: N" exit 1."""
        root = _clean_root()
        # A broken anchor is medium severity
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee [x](beta/index.md#nope).\n")
        _touch_manifest(root)
        rc, out, _ = _run(root, "--severity", "medium")
        lines = out.splitlines()
        self.assertIn("\u26a0 findings:", lines[0])
        self.assertTrue(lines[0].startswith("\u26a0"))
        # Count of reported findings equals count of lines after header
        self.assertEqual(len(lines) - 1, len([l for l in lines[1:] if "rule=" in l]))
        self.assertEqual(rc, 1)

    def test_high_finding_critical_and_findings_lines_exit_2(self):
        """One high finding -> "\U0001f6a8 critical: 1" + "\u26a0 findings: N", exit 2."""
        root = _clean_root()
        os.remove(os.path.join(root, "CHANGELOGS", "beta.changes.md"))
        rc, out, _ = _run(root)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("\U0001f6a8"))
        self.assertIn("critical:", lines[0])
        self.assertIn("findings:", lines[1])
        self.assertEqual(rc, 2)

    def test_high_and_medium_findings_sorted_by_severity(self):
        """Findings sorted: high first, then medium, then low."""
        root = _clean_root()
        # Remove beta changelog -> high (changelog-path-missing)
        os.remove(os.path.join(root, "CHANGELOGS", "beta.changes.md"))
        # Add broken anchor to alpha -> medium (broken-anchor)
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee [x](beta/index.md#nope).\n")
        _touch_manifest(root)
        rc, out, _ = _run(root, "--severity", "low")
        lines = out.splitlines()
        # Skip the header line(s) (critical + findings)
        hint_lines = [l for l in lines[2:] if l.startswith("rule=")]
        severities = []
        for l in hint_lines:
            sev = l.split(" ")[1].split("=")[1]
            severities.append(sev)
        # high before medium before low
        self.assertEqual(severities, ["high", "medium"])
        self.assertEqual(rc, 2)


class TestSeverityFilterReportingAndExitCode(unittest.TestCase):
    """Contract §2: --severity means minimum REPORTED severity.
    §1: exit codes are over REPORTED findings.

    Default severity is "high", so only high findings are reported.
    --severity low reports low/medium/high; --severity medium reports medium/high.
    --strict reports everything (equivalent to --severity warning).
    """

    def test_severity_high_hides_medium_not_reported(self):
        """With explicit --severity high: medium-only findings are not reported -> exit 0."""
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee [x](beta/index.md#nope).\n")
        _touch_manifest(root)
        rc, out, _ = _run(root, "--severity", "high")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_severity_medium_shows_medium_exit_1(self):
        """--severity medium: medium findings are reported -> exit 1."""
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee [x](beta/index.md#nope).\n")
        _touch_manifest(root)
        rc, out, _ = _run(root, "--severity", "medium")
        self.assertEqual(rc, 1)
        self.assertTrue(out.startswith("\u26a0"))

    def test_severity_low_hides_only_low(self):
        """At default severity=low: medium findings reported -> exit 1.
        --severity high: medium hidden -> exit 0."""
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee [x](beta/index.md#nope).\n")
        _touch_manifest(root)
        # At default severity=low: medium reported -> exit 1
        rc_low, out_low, _ = _run(root)
        self.assertEqual(rc_low, 1)
        self.assertTrue(out_low.startswith("\u26a0"))
        # At --severity high: medium hidden -> exit 0
        rc_high, out_high, _ = _run(root, "--severity", "high")
        self.assertEqual(rc_high, 0)
        self.assertEqual(out_high, "")

    def test_severity_filters_json_output(self):
        """--json mode: severity filter still applies, no marker lines."""
        root = _clean_root()
        # medium-only finding
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee [x](beta/index.md#nope).\n")
        _touch_manifest(root)
        # Default (low) -> medium reported
        rc_h, records_h = _jsonl(root)
        self.assertEqual(rc_h, 1)
        self.assertTrue(records_h)
        # --severity medium -> records reported
        rc_m, records_m = _jsonl(root, "--severity", "medium")
        self.assertEqual(rc_m, 1)
        self.assertTrue(records_m)
        for r in records_m:
            self.assertEqual(set(r.keys()), {"rule", "severity", "file", "description"})
            self.assertIn(r["severity"], ("medium", "high"))

    def test_severity_filters_exit_code(self):
        """When severity filter hides all findings, exit code is 0 (clean)."""
        root = _clean_root()
        # Add a single medium-only finding (broken anchor in alpha)
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee [x](beta/index.md#nope).\n")
        _touch_manifest(root)
        # Default severity=low: medium reported -> exit 1
        rc_default, records_default = _jsonl(root)
        self.assertEqual(rc_default, 1)
        self.assertTrue(records_default)
        self.assertTrue(_find(records_default, rule="broken-anchor", severity="medium"))
        # --severity high: medium hidden -> exit 0, empty
        rc_high, records_high = _jsonl(root, "--severity", "high")
        self.assertEqual(rc_high, 0)
        self.assertEqual(records_high, [])

    def test_strict_reports_all_findings(self):
        """--strict reports every finding regardless of severity -> exit code
        computed over all reported findings."""
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee [x](beta/index.md#nope).\n")
        _touch_manifest(root)
        rc, out, _ = _run(root, "--strict")
        # Medium finding reported at --strict -> exit 1
        self.assertEqual(rc, 1)
        self.assertTrue(out.startswith("\u26a0"))

    def test_strict_exposes_low_warning(self):
        """--strict exposes even warning-severity findings."""
        root = _clean_root()
        text = _read_doc(root, "docs/en/beta/index.md")
        _write_doc(root, "docs/en/beta/index.md", text.replace(
            "Status: draft", "Status: draft\nLast Modified: 2026-01-01"))
        _touch_manifest(root)
        rc, out, _ = _run(root, "--strict")
        self.assertEqual(rc, 1)
        self.assertTrue(out.startswith("\u26a0"))


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
        _touch_manifest(root)
        rc, records = _jsonl(root)
        hits = _find(records, rule="line-count", severity="high")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["file"], "docs/en/beta/index.md")
        self.assertEqual(rc, 1 if not hits else 2)

    def test_metadata_and_blank_lines_not_counted(self):
        root = _clean_root()
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
        _touch_manifest(root)
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
        self.assertEqual(rc, 2)

    def test_changelog_wrong_location_medium(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/beta/index.md")
        _write_doc(root, "docs/en/beta/index.md", text.replace(
            "changelog-path: CHANGELOGS/beta.changes.md",
            "changelog-path: notes/beta.changes.md"))
        _touch_manifest(root)
        _, records = _jsonl(root)
        self.assertTrue(_find(records, rule="changelog-path-location",
                              severity="medium"))


class TestRule4CrossRefs(unittest.TestCase):
    def test_broken_anchor_medium_not_blocking(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee [beta section](beta/index.md#no-such-heading).\n")
        _touch_manifest(root)
        rc, records = _jsonl(root)
        hits = _find(records, rule="broken-anchor", severity="medium")
        self.assertTrue(hits)
        # Default severity=low: medium reported -> exit 1
        self.assertEqual(rc, 1)
        rc_strict, records_strict = _jsonl(root, "--strict")
        self.assertTrue(_find(records_strict, rule="broken-anchor", severity="medium"))
        # At --strict, medium reported, no high -> exit 1
        self.assertEqual(rc_strict, 1)

    def test_missing_reference_docs_en_path_high(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee `docs/en/ghost/index.md` for details.\n")
        _touch_manifest(root)
        rc, records = _jsonl(root)
        hits = _find(records, rule="missing-reference", severity="high")
        self.assertTrue(any("ghost" in h["description"] for h in hits))
        self.assertEqual(rc, 2)

    def test_unresolved_section_reference_medium(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/beta/index.md")
        _write_doc(root, "docs/en/beta/index.md",
                   text + "\nSee §Totally Absent Section for semantics.\n")
        _touch_manifest(root)
        rc, records = _jsonl(root)
        hits = _find(records, rule="unresolved-reference", severity="medium")
        self.assertTrue(any("Totally Absent" in h["description"] for h in hits))
        self.assertEqual(rc, 1)

    def test_section_reference_to_real_heading_passes(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/beta/index.md")
        _write_doc(root, "docs/en/beta/index.md",
                   text + "\nAs described in §Purpose above, this is fine.\n")
        _touch_manifest(root)
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
        self.assertEqual(rc, 2)

    # -- (b) same-line file detection ------------------------------------------

    def test_same_line_named_file_heading_hit_passes(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nField semantics are in `beta/index.md`, "
                   "§Purpose, verbatim.\n")
        _touch_manifest(root)
        _, records = _jsonl(root)
        self.assertEqual(_find(records, rule="broken-anchor"), [])
        self.assertEqual(_find(records, rule="unresolved-reference"), [])

    def test_same_line_named_file_heading_miss_high(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee `beta/index.md`, §Nonexistent Bound Target "
                   "for details.\n")
        _touch_manifest(root)
        rc, records = _jsonl(root)
        hits = _find(records, rule="broken-anchor", severity="high")
        self.assertTrue(any("Nonexistent Bound Target" in h["description"]
                            for h in hits))
        self.assertEqual(rc, 2)

    def test_same_line_plain_path_no_backticks_hit_passes(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nPer docs/en/beta/index.md §Purpose this is ok.\n")
        _touch_manifest(root)
        _, records = _jsonl(root)
        self.assertEqual(_find(records, rule="broken-anchor"), [])
        self.assertEqual(_find(records, rule="unresolved-reference"), [])

    # -- (c) corpus-wide heading index ------------------------------------------

    def test_corpus_wide_unique_heading_resolves_passes(self):
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
        """ambiguous-section-reference severity=low (not medium) at default low."""
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
        self.assertFalse(any(h["severity"] == "medium"
                              for h in hits))
        hit = next(h for h in hits if "Shared Heading" in h["description"])
        self.assertIn("docs/en/alpha/index.md", hit["description"])
        self.assertIn("docs/en/beta/index.md", hit["description"])
        # Default severity=low: low finding reported -> exit 1
        self.assertEqual(rc, 1)

    def test_zero_matches_stays_medium(self):
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
        # Default severity=low: medium reported -> exit 1 (no high)
        self.assertEqual(rc, 1)

    # -- (d) implementation-file §refs (AGENTS.md §1.6) --------------------------

    def test_implementation_file_ref_hit_passes(self):
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
        # Default severity=low: low finding reported -> exit 1
        self.assertEqual(rc, 1)

    def test_implementation_file_numeric_ref_resolves(self):
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
    def test_finding_lines_carry_tokens_and_parse(self):
        root = _clean_root()
        os.remove(os.path.join(root, "CHANGELOGS", "beta.changes.md"))
        rc, out, _ = _run(root)
        self.assertEqual(rc, 2)
        finding_lines = [ln for ln in out.splitlines() if "rule=" in ln]
        self.assertTrue(finding_lines)
        for ln in finding_lines:
            head, _, tail = ln.partition(" ")
            fields = dict(kv.split("=", 1) for kv in (head, ln.split(" ")[1],
                                                     ln.split(" ")[2]))
            self.assertEqual(set(fields), {"rule", "severity", "file"})
            self.assertIn(fields["severity"], ("low", "medium", "high"))
            self.assertTrue(fields["file"].endswith(".md")
                            or fields["file"].endswith(".yaml"))
            self.assertTrue(tail.strip())
        self.assertTrue(any("severity=high" in ln for ln in finding_lines))

    def test_high_finding_line_contains_literal_severity_high(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee `docs/en/ghost/index.md` for details.\n")
        _touch_manifest(root)
        rc, out, _ = _run(root)
        self.assertEqual(rc, 2)
        high_lines = [ln for ln in out.splitlines() if "severity=high" in ln]
        self.assertTrue(high_lines)
        self.assertTrue(any("rule=missing-reference" in ln for ln in high_lines))
        self.assertTrue(all(ln.startswith("rule=") for ln in high_lines))

    def test_json_mode_unchanged(self):
        root = _clean_root()
        os.remove(os.path.join(root, "CHANGELOGS", "beta.changes.md"))
        rc, records = _jsonl(root)
        self.assertEqual(rc, 2)
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
        self.assertEqual(rc, 2)

    def test_orphan_high(self):
        root = _clean_root()
        _write_doc(root, "docs/en/beta/extras.md",
                   "# Extras\n"
                   "Version: 0.1\n"
                   "Status: draft\n"
                   "Abstraction: reference\n"
                   "changelog-path: CHANGELOGS/beta.changes.md\n\n"
                   "## Purpose\n\nNot in the generated manifest and not covered\n"
                   "by an allow_non_index_paths parent index.\n")
        # Do NOT call _touch_manifest — file lacks required "id" field.
        # check_all internal regen will detect orphan (skip + manifest-drift).
        rc, records = _jsonl(root)
        hits = _find(records, rule="orphan", severity="high")
        self.assertTrue(any("extras.md" in h["file"] for h in hits))
        self.assertTrue(rc == 2 or rc == 1)  # 2 if high finding present

    def test_non_index_allowed_by_parent_index_not_orphan(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text.replace("changelog-path: CHANGELOGS/alpha.changes.md",
                                "changelog-path: CHANGELOGS/alpha.changes.md\n"
                                "allow_non_index_paths: true"))
        _write_doc(root, "docs/en/alpha/extra.md",
                   "# Extra\n"
                   "id: alpha-extra\n"
                   "Version: 0.1\n"
                   "Status: draft\n"
                   "Abstraction: reference\n"
                   "changelog-path: CHANGELOGS/beta.changes.md\n\n"
                   "## Purpose\n\nCovered by parent index.\n")
        _touch_manifest(root)
        rc, records = _jsonl(root)
        # allowed_non_index_paths prevents orphan + naming findings
        self.assertEqual(_find(records, rule="orphan"), [])
        self.assertEqual(_find(records, rule="naming"), [])
        # No frontmatter error — allow_non_index_paths is valid YAML
        self.assertEqual(_find(records, rule="frontmatter"), [])
        self.assertEqual(rc, 0)

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
        self.assertEqual(rc, 2)

class TestSchema(unittest.TestCase):
    def test_last_modified_deprecated_warning(self):
        root = _clean_root()
        text = _read_doc(root, "docs/en/beta/index.md")
        _write_doc(root, "docs/en/beta/index.md", text.replace(
            "Status: draft", "Status: draft\nLast Modified: 2026-01-01"))
        _touch_manifest(root)
        rc, records = _jsonl(root)
        # Default severity=low: warning-severity hidden → exit 0, no findings
        self.assertEqual(len(records), 0)
        self.assertEqual(rc, 0)
        rc_strict, records_strict = _jsonl(root, "--strict")
        self.assertEqual(rc_strict, 1)
        hits_strict = _find(records_strict, rule="last-modified-deprecated",
                            severity="warning")
        self.assertEqual(len(hits_strict), 1)

    def test_bad_frontmatter_is_finding_not_exit_2(self):
        root = _clean_root()
        _write_doc(root, "docs/en/broken/index.md",
                   "# Broken\nVersion: 0.1\nStatus: draft\n"
                   "Abstraction: reference\n"
                   "changelog-path: CHANGELOGS/beta.changes.md\n\n"
                   "## Purpose\n\nMissing id.\n")
        # Do NOT call _touch_manifest — file lacks required "id" field.
        # check_all handles it internally (parity-skipped + frontmatter findings).
        rc, out, err = _run(root)
        self.assertEqual(rc, 2, out + err)
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
        text = _read_doc(root, "docs/en/alpha/index.md")
        _write_doc(root, "docs/en/alpha/index.md",
                   text + "\nSee [x](beta/index.md#nope).\n")
        _touch_manifest(root)
        rc_default, records_default = _jsonl(root)
        # Default (low) -> medium reported -> exit 1
        self.assertEqual(rc_default, 1)
        self.assertTrue(records_default)
        rc_med, records_med = _jsonl(root, "--severity", "medium")
        self.assertEqual(rc_med, 1)
        self.assertTrue(records_med)
        # --severity high -> medium hidden -> exit 0, empty
        rc_high, records_high = _jsonl(root, "--severity", "high")
        self.assertEqual(rc_high, 0)
        self.assertEqual(records_high, [])
        rc_sel, records_sel = _jsonl(root, "--rule", "line-count", "--rule", "naming")
        self.assertEqual(rc_sel, 0)
        self.assertEqual(records_sel, [])

    def test_unknown_rule_token_exit_2(self):
        root = _clean_root()
        rc, _, err = _run(root, "--rule", "glossary")
        self.assertEqual(rc, 2)
        self.assertIn("unknown --rule", err)

class TestInternalError(unittest.TestCase):
    def test_unreadable_manifest_fails_loud_exit_2(self):
        root = _clean_root()
        os.remove(os.path.join(root, "docs-manifest.yaml"))
        os.mkdir(os.path.join(root, "docs-manifest.yaml"))
        rc, out, err = _run(root)
        self.assertEqual(rc, 2)
        self.assertIn("INTERNAL ERROR", err)
        self.assertIn("Remediation", err)
        self.assertIn("Traceback", err)

    def test_internal_error_distinguishable_from_critical_marker(self):
        root = _clean_root()
        os.remove(os.path.join(root, "docs-manifest.yaml"))
        os.mkdir(os.path.join(root, "docs-manifest.yaml"))
        rc, out, err = _run(root)
        self.assertEqual(rc, 2)
        self.assertNotIn("\U0001f6a8", err)

class TestLiveCorpus(unittest.TestCase):
    def test_live_corpus_runs_clean_exit_code(self):
        rc, out, err = _run(REPO_ROOT, "--json")
        # default severity=low: low/medium findings reported → exit 1 is normal;
        # 0 means clean, 1 means low/medium only (no high = good).
        # Exit 2 would indicate internal error — should never happen.
        self.assertIn(rc, (0, 1), err)
        for line in out.splitlines():
            rec = json.loads(line)
            self.assertEqual(set(rec.keys()),
                             {"rule", "severity", "file", "description"})

if __name__ == "__main__":
    unittest.main()
