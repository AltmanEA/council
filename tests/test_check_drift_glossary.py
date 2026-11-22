"""Unit tests for tools/check_drift.py — explicit --glossary contract.

Tests the new --glossary gate behavior per operator decision (session d1-glossary-default-fix):
  - Without --glossary → exit 2 (no implicit default).
  - --glossary none → vacuous gate, exit 0, provenance says vacuous.
  - --glossary <nonexistent> → exit 2.
  - --glossary <0-terms> with non-empty EN → exit 2.
  - --glossary <valid file> → provenance with status=checked, terms=N.
  - --json mode: stdout stays clean, provenance in stderr.

These tests MUST be RED before implementation is changed.
"""
import json
import os
import subprocess
import sys
import unittest

WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_DIR = os.path.join(WORKTREE, "tools")
FIXTURES_DIR = os.path.join(TOOLS_DIR, "tests", "fixtures", "check_drift", "phase4")


def _run_cli(*extra_args):
    """Run check_drift.py as subprocess from WORKTREE root.

    Returns (exit_code, stdout_text, stderr_text).
    """
    cmd = [sys.executable, os.path.join(TOOLS_DIR, "check_drift.py")] + list(extra_args)
    result = subprocess.run(
        cmd,
        cwd=WORKTREE,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


class TestGlossaryExplicitContract(unittest.TestCase):
    """Contract: --glossary must be explicit or sentinel 'none'.

    ANTI-REVERSED-TDD: These tests MUST be RED against current implementation.
    Current code: line 636-639 silently defaults to repo-level glossary;
    no 'none' sentinel; no provenance.
    """

    def test_a_glossary_none_sentinel_vacuous(self):
        """--glossary none → gate 4 vacuous: provenance says vacuous, exit 0.

        Run from WORKTREE root (which is NOT the tools repo directory).
        No phase4-glossary finding should appear.
        """
        rc, out, err = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_good.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", "none",
        )
        self.assertEqual(rc, 0, f"Expected exit 0 for 'none' sentinel, got {rc}\nstderr: {err}")
        self.assertNotIn("rule=phase4-glossary", out,
                         "Vacuous run should not emit phase4-glossary findings")
        self.assertIn("status=vacuous", out + err,
                      "Provenance must contain status=vacuous")

    def test_b_no_glossary_flag_exits_2(self):
        """No --glossary flag at all → exit 2, stderr says 'glossary is required'."""
        rc, _, err = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_good.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
        )
        self.assertEqual(rc, 2,
                         f"Expected exit 2 when --glossary is omitted, got {rc}")
        self.assertIn("--glossary", err.lower() or err,
                      "stderr should mention --glossary requirement")

    def test_c_nonexistent_glossary_path_exits_2(self):
        """--glossary <nonexistent path> → exit 2."""
        rc, _, err = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_good.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", "/nonexistent/path/to/glossary.md",
        )
        self.assertEqual(rc, 2,
                         f"Expected exit 2 for nonexistent glossary path, got {rc}")

    def test_d_zero_terms_glossary_with_nonempty_en_exits_2(self):
        """--glossary <file with 0 parsed terms> + non-empty EN → exit 2."""
        rc, _, err = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_good.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "empty-glossary.md"),
        )
        self.assertEqual(rc, 2,
                         f"Expected exit 2 for 0-term glossary with non-empty EN, got {rc}")

    def test_e_valid_glossary_provenance_checked(self):
        """--glossary mini-glossary.md → exit 0 (or expected findings), provenance has status=checked and terms=N.

        mini-glossary has 3 terms; en.md + ru_good.md should pass (or produce documented
        findings). Provenance must always be printed.
        """
        rc, out, err = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_good.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        # Provenance MUST be present regardless of exit code
        self.assertIn("status=checked", out + err,
                      "Provenance must contain status=checked for a valid glossary")
        self.assertIn("terms=", out + err,
                      "Provenance must include term count")
        self.assertIn("path=", out + err,
                      "Provenance must include resolved path")
        # With good fixtures and valid glossary: rc should be 0 (no findings)
        # unless there are known glossary findings for this fixture set.
        self.assertEqual(rc, 0,
                    f"Expected exit 0 with valid glossary and good fixtures, got rc={rc}, out={out}")

    def test_f_json_stdout_clean_provenance_in_stderr(self):
        """--json mode: stdout lines all parse as finding JSON (no provenance pollution); provenance in stderr."""
        rc, stdout, stderr = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_bad_identity.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
            "--json",
        )
        # stdout must be empty or contain ONLY valid JSON finding objects
        for line in stdout.strip().splitlines():
            if line.strip():
                rec = json.loads(line)
                self.assertIn("rule", rec, f"stdout line should be a finding JSON: {line}")
                self.assertIn("severity", rec, f"stdout line should have severity: {line}")

        # Provenance must be in stderr when --json is used
        self.assertIn("glossary:", stderr,
                      "Provenance must be in stderr for --json mode")
        self.assertIn("status=", stderr,
                      "Provenance in stderr must contain status")


if __name__ == "__main__":
    unittest.main()
