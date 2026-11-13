"""Unit tests for tools/classify_bump.py (Stage C, plan sess-doc-reliability-algo).

Runs the read-only classifier against a fixture corpus under
tests/fixtures/classify_bump/ (copied into tempdirs; the live repo root,
manifest, and logs are never touched). Two documents exist so external
§-references (beta -> alpha) can be detected; classification candidates are
built by mutating the alpha document text.
"""
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import classify_bump
import gen_manifest

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "classify_bump")
CORPUS = os.path.join(FIXTURES, "corpus")

# Stable fragments of the fixture alpha document used to build candidates.
PURPOSE_SENTENCE = ("the governance section that Beta references externally via a section "
                    "reference, so heading removal must classify as major.")
APPENDIX_SENTENCE = ("This appendix holds filler prose used for typo-fix patch classification "
                     "and nothing else of substance.")


def _copy_corpus():
    """Copy fixture corpus to a temp dir and generate its manifest."""
    d = tempfile.mkdtemp()
    root = os.path.join(d, "repo")
    shutil.copytree(CORPUS, root)
    assert gen_manifest.main(["--root", root, "--write"]) == 0
    return root


def _doc_path(root, doc_id):
    return os.path.join(root, "docs", "en", doc_id, "index.md")


def _read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _disk_text(root, doc_id="alpha"):
    return _read(_doc_path(root, doc_id))


def _candidate_file(root, text):
    fd, path = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return path


def _run(root, *argv):
    """Run classify_bump.main; returns (rc, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = classify_bump.main(["--root", root, *argv])
    return rc, out.getvalue(), err.getvalue()


def _classify(root, candidate_text, doc_id="alpha"):
    return classify_bump.classify(root, doc_id, candidate_text)


def _sha256_tree(root, subdir):
    """Map of relpath -> sha256 hexdigest for every file under root/subdir."""
    out = {}
    base = os.path.join(root, subdir)
    for dirpath, _, filenames in os.walk(base):
        for name in filenames:
            abs_path = os.path.join(dirpath, name)
            rel = os.path.relpath(abs_path, root).replace("\\", "/")
            with open(abs_path, "rb") as fh:
                out[rel] = hashlib.sha256(fh.read()).hexdigest()
    return out


class ClassifierRules(unittest.TestCase):
    """Rules 1-4: patch / minor / major / ambiguous first-match classification."""

    def test_typo_fix_is_patch(self):
        """Case 1: single-word replacement in a paragraph -> patch."""
        root = _copy_corpus()
        candidate = _disk_text(root).replace(
            "typo-fix patch classification", "typo-fix patch classificationX")
        result = _classify(root, candidate)
        self.assertEqual(result["verdict"], "patch")
        self.assertEqual(result["rules_triggered"], ["token-overlap-patch"])
        self.assertFalse(result["ambiguous"])
        self.assertFalse(result["escalated"])

    def test_added_section_is_minor(self):
        """Case 2: new heading + paragraphs appended -> structural minor."""
        root = _copy_corpus()
        candidate = _disk_text(root) + (
            "\n## New Section\n\nSome new prose content added for the structural "
            "minor classification path.\n")
        result = _classify(root, candidate)
        self.assertEqual(result["verdict"], "minor")
        self.assertEqual(result["rules_triggered"], ["structural-minor"])
        self.assertFalse(result["ambiguous"])
        self.assertFalse(result["escalated"])

    def test_external_referenced_heading_removed_is_major(self):
        """Case 3: heading with an external §-ref from beta removed -> major."""
        root = _copy_corpus()
        self.assertIn("§Governance Rules", _disk_text(root, "beta"))
        candidate = _disk_text(root).replace("## Governance Rules\n", "")
        result = _classify(root, candidate)
        self.assertEqual(result["verdict"], "major")
        self.assertIn("external-heading-removed", result["rules_triggered"])
        self.assertTrue(result["escalated"])

    def test_unreferenced_heading_removed_is_not_major(self):
        """A removed heading nobody references externally is not major."""
        root = _copy_corpus()
        candidate = _disk_text(root).replace("## Appendix\n", "")
        result = _classify(root, candidate)
        self.assertNotEqual(result["verdict"], "major")
        self.assertNotIn("external-heading-removed", result["rules_triggered"])

    def test_mixed_diff_is_ambiguous_minor(self):
        """Case 4: insert/delete plus low-ratio replacements -> ambiguous minor."""
        root = _copy_corpus()
        text = _disk_text(root)
        text = text.replace(
            "Stage C fixture target document for the version-bump classifier.",
            "Wholly unrelated sentences about watering gardens and migrating birds.")
        text = text.replace(APPENDIX_SENTENCE, "Brand-new appended sentence about other topics.")
        text = text + "\n## Another Section\n\nMore inserted content here.\n"
        result = _classify(root, text)
        self.assertEqual(result["verdict"], "minor")
        self.assertTrue(result["ambiguous"])
        self.assertEqual(result["rules_triggered"], ["ambiguous-default-minor"])
        self.assertTrue(result["escalated"])
        joined = " ".join(result["warnings"])
        self.assertIn("never silent patch", joined)
        self.assertIn("§7.5", joined)

    def test_required_key_removed_is_major(self):
        """Required frontmatter key present on disk, absent in candidate."""
        root = _copy_corpus()
        candidate = _disk_text(root).replace("Status: draft\n", "")
        result = _classify(root, candidate)
        self.assertEqual(result["verdict"], "major")
        self.assertIn("required-key-removed", result["rules_triggered"])
        self.assertTrue(result["escalated"])

    def test_abstraction_changed_is_major(self):
        """Changed Abstraction value -> major abstraction-changed."""
        root = _copy_corpus()
        candidate = _disk_text(root).replace("Abstraction: protocol", "Abstraction: reference")
        result = _classify(root, candidate)
        self.assertEqual(result["verdict"], "major")
        self.assertIn("abstraction-changed", result["rules_triggered"])
        self.assertTrue(result["escalated"])

    def test_frontmatter_line_replacement_not_patch(self):
        """A Version-line replacement is a frontmatter touch -> never patch."""
        root = _copy_corpus()
        candidate = _disk_text(root).replace(
            "Version: 0.2.0-draft", "Version: 0.2.0-draft2")
        result = _classify(root, candidate)
        self.assertNotEqual(result["verdict"], "patch")

    def test_heading_or_marker_line_replacement_not_patch(self):
        """A replaced ATX heading line disqualifies the patch rule."""
        root = _copy_corpus()
        candidate = _disk_text(root).replace(
            "## Purpose", "## Purpose and Scope")
        result = _classify(root, candidate)
        self.assertNotEqual(result["verdict"], "patch")


class EscalationFormat(unittest.TestCase):
    """Case 5: §6-format escalation block in human-readable output."""

    def _assert_block(self, out):
        self.assertIn("ESCALATION", out)
        self.assertIn("option 1:", out)
        self.assertIn("option 2:", out)
        self.assertIn("recommendation:", out)

    def test_ambiguous_human_output(self):
        root = _copy_corpus()
        text = _disk_text(root).replace(
            "Stage C fixture target document for the version-bump classifier.",
            "Wholly unrelated sentences about watering gardens and migrating birds.")
        cand = _candidate_file(root, text)
        rc, out, err = _run(root, "--id", "alpha", "--candidate", cand, "--no-log")
        self.assertEqual(rc, 0, err)
        self._assert_block(out)
        self.assertIn("never silent patch", out)

    def test_major_human_output(self):
        root = _copy_corpus()
        text = _disk_text(root).replace("## Governance Rules\n", "")
        cand = _candidate_file(root, text)
        rc, out, err = _run(root, "--id", "alpha", "--candidate", cand, "--no-log")
        self.assertEqual(rc, 0, err)
        self._assert_block(out)
        self.assertIn("headings must be re-anchored", out)


class JsonlLog(unittest.TestCase):
    """Case 6: decision log is written once per classification, JSONL shape."""

    def test_ambiguous_writes_single_log_line(self):
        root = _copy_corpus()
        log = os.path.join(tempfile.mkdtemp(), "nested", "classify_log.jsonl")
        text = _disk_text(root).replace(
            "Stage C fixture target document for the version-bump classifier.",
            "Wholly unrelated sentences about watering gardens and migrating birds.")
        cand = _candidate_file(root, text)
        rc, _, err = _run(root, "--id", "alpha", "--candidate", cand, "--log", log)
        self.assertEqual(rc, 0, err)
        with open(log, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        self.assertEqual(len(lines), 1)
        rec = json.loads(lines[0])
        self.assertTrue(rec["ambiguous"])
        self.assertTrue(rec["escalated"])
        self.assertEqual(rec["id"], "alpha")
        self.assertEqual(rec["verdict"], "minor")
        self.assertEqual(rec["rules_triggered"], ["ambiguous-default-minor"])
        self.assertIn("ts", rec)
        self.assertIn("T", rec["ts"])  # ISO UTC

    def test_no_log_does_not_create_file(self):
        root = _copy_corpus()
        log = os.path.join(tempfile.mkdtemp(), "classify_log.jsonl")
        cand = _candidate_file(root, _disk_text(root) + "\n## Extra\n\nProse.\n")
        rc, _, err = _run(root, "--id", "alpha", "--candidate", cand, "--no-log",
                          "--log", log)
        self.assertEqual(rc, 0, err)
        self.assertFalse(os.path.exists(log))


class ReportGate(unittest.TestCase):
    """Case 7: --report escalation-rate gate (HCD metric, 20%)."""

    @staticmethod
    def _write_log(path, total, escalated):
        with open(path, "w", encoding="utf-8") as fh:
            for i in range(total):
                fh.write(json.dumps({
                    "ts": "2026-11-13T00:00:00+00:00", "id": f"doc{i}",
                    "verdict": "minor", "ambiguous": False,
                    "escalated": i < escalated, "rules_triggered": ["x"],
                }) + "\n")

    def test_gate_exceeded_exit_3(self):
        root = _copy_corpus()
        log = os.path.join(tempfile.mkdtemp(), "log.jsonl")
        self._write_log(log, 10, 3)
        rc, out, err = _run(root, "--report", "--log", log)
        self.assertEqual(rc, 3)
        self.assertIn("classifier requires redesign", out)
        self.assertIn("total: 10", out)
        self.assertIn("escalated: 3", out)

    def test_gate_within_exit_0(self):
        root = _copy_corpus()
        log = os.path.join(tempfile.mkdtemp(), "log.jsonl")
        self._write_log(log, 10, 1)
        rc, out, err = _run(root, "--report", "--log", log)
        self.assertEqual(rc, 0)
        self.assertNotIn("classifier requires redesign", out)

    def test_broken_lines_ignored_with_warning(self):
        root = _copy_corpus()
        log = os.path.join(tempfile.mkdtemp(), "log.jsonl")
        self._write_log(log, 2, 0)
        with open(log, "a", encoding="utf-8") as fh:
            fh.write("this is not json\n")
        rc, out, err = _run(root, "--report", "--log", log)
        self.assertEqual(rc, 0)
        self.assertIn("WARNING", err)
        self.assertIn("total: 2", out)

    def test_missing_log_empty_report(self):
        root = _copy_corpus()
        rc, out, err = _run(root, "--report",
                            "--log", os.path.join(tempfile.mkdtemp(), "none.jsonl"))
        self.assertEqual(rc, 0)
        self.assertIn("total: 0", out)

    def test_report_json_shape_and_exit(self):
        root = _copy_corpus()
        log = os.path.join(tempfile.mkdtemp(), "log.jsonl")
        self._write_log(log, 10, 3)
        rc, out, err = _run(root, "--report", "--log", log, "--json")
        self.assertEqual(rc, 3)
        data = json.loads(out)
        self.assertEqual(set(data), {"total", "escalated", "escalation_rate",
                                     "requires_redesign"})
        self.assertEqual(data["total"], 10)
        self.assertEqual(data["escalated"], 3)
        self.assertTrue(data["requires_redesign"])


class StdinAndReadonly(unittest.TestCase):
    """Case 8: --candidate - reads stdin; the corpus is never modified."""

    def test_stdin_candidate_and_readonly_corpus(self):
        root = _copy_corpus()
        before = _sha256_tree(root, "docs")
        text = _disk_text(root).replace(
            "typo-fix patch classification", "typo-fix patch classificationX")
        log = os.path.join(tempfile.mkdtemp(), "log.jsonl")
        out, err = io.StringIO(), io.StringIO()
        with patch("sys.stdin", io.StringIO(text)), \
                redirect_stdout(out), redirect_stderr(err):
            rc = classify_bump.main(["--root", root, "--id", "alpha",
                                     "--candidate", "-", "--log", log])
        self.assertEqual(rc, 0, err.getvalue())
        self.assertEqual(before, _sha256_tree(root, "docs"))
        # The log lives outside docs/ and is the only artifact written.
        self.assertTrue(os.path.isfile(log))


class Identical(unittest.TestCase):
    """Case 9: candidate identical to disk -> none, no log, exit 0."""

    def test_identical_verdict_none(self):
        root = _copy_corpus()
        log = os.path.join(tempfile.mkdtemp(), "log.jsonl")
        cand = _candidate_file(root, _disk_text(root))
        rc, out, err = _run(root, "--id", "alpha", "--candidate", cand, "--log", log)
        self.assertEqual(rc, 0, err)
        self.assertIn("verdict: none", out)
        self.assertFalse(os.path.exists(log))

    def test_candidate_version_bump_line_alone_not_patch(self):
        """A bare Version: line change is a frontmatter touch -> never patch."""
        root = _copy_corpus()
        cand = _candidate_file(root, _disk_text(root).replace(
            "Version: 0.2.0-draft", "Version: 0.3.0"))
        rc, out, err = _run(root, "--id", "alpha", "--candidate", cand, "--no-log")
        self.assertEqual(rc, 0, err)
        self.assertNotIn("verdict: patch", out)


class JsonOutput(unittest.TestCase):
    """Case 10: deterministic --json output with the fixed key set."""

    def test_deterministic_and_key_set(self):
        root = _copy_corpus()
        text = _disk_text(root).replace(
            "typo-fix patch classification", "typo-fix patch classificationX")
        cand = _candidate_file(root, text)
        outputs = []
        for _ in range(2):
            rc, out, err = _run(root, "--id", "alpha", "--candidate", cand,
                                "--json", "--no-log")
            self.assertEqual(rc, 0, err)
            outputs.append(out)
        self.assertEqual(outputs[0], outputs[1])  # byte-identical
        data = json.loads(outputs[0])
        self.assertEqual(set(data), {"id", "verdict", "ambiguous", "escalated",
                                     "rules_triggered", "warnings", "escalation"})
        self.assertEqual(data["verdict"], "patch")
        self.assertIsNone(data["escalation"])

    def test_escalation_object_shape(self):
        root = _copy_corpus()
        text = _disk_text(root).replace("## Governance Rules\n", "")
        cand = _candidate_file(root, text)
        rc, out, err = _run(root, "--id", "alpha", "--candidate", cand,
                            "--json", "--no-log")
        self.assertEqual(rc, 0, err)
        data = json.loads(out)
        self.assertTrue(data["escalated"])
        self.assertEqual(len(data["escalation"]["options"]), 2)
        self.assertIn("recommendation", data["escalation"])


class Refusals(unittest.TestCase):
    """Exit 2 paths: unknown id, unreadable candidate, unparsable candidate."""

    def test_unknown_id_exit_2(self):
        root = _copy_corpus()
        cand = _candidate_file(root, _disk_text(root) + "\n## Extra\n\nProse.\n")
        rc, _, err = _run(root, "--id", "nonexistent", "--candidate", cand, "--no-log")
        self.assertEqual(rc, 2)
        self.assertIn("nonexistent", err)

    def test_unreadable_candidate_exit_2(self):
        root = _copy_corpus()
        rc, _, err = _run(root, "--id", "alpha", "--candidate",
                          os.path.join(tempfile.mkdtemp(), "missing.md"), "--no-log")
        self.assertEqual(rc, 2)
        self.assertIn("candidate", err.lower())

    def test_broken_candidate_frontmatter_exit_2(self):
        """Candidate without an H1 fails docmeta.parse_header -> exit 2."""
        root = _copy_corpus()
        text = _disk_text(root).replace("# Alpha Document\n", "")
        text = text + "\n## Extra Section\n\nProse added so it is not identical.\n"
        cand = _candidate_file(root, text)
        rc, _, err = _run(root, "--id", "alpha", "--candidate", cand, "--no-log")
        self.assertEqual(rc, 2)
        self.assertIn("H1", err)

    def test_missing_candidate_or_id_exit_2(self):
        root = _copy_corpus()
        rc, _, err = _run(root, "--id", "alpha")
        self.assertEqual(rc, 2)
        rc, _, err = _run(root, "--candidate", "/dev/null")
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
