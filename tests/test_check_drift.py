"""Unit tests for tools/check_drift.py — Phase 4 translation write-gates.

Tests the new --phase4 mode with four deterministic gates:
  phase4-fail, phase4-parity, phase4-identity, phase4-glossary.

Also tests regression of existing drift mode (without --phase4).
Uses both subprocess CLI and direct function import (two levels, like test_check_all).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# Paths relative to WORKTREE root
# __file__ is at {WORKTREE}/tests/test_check_drift.py
# dirname(2) -> WORKTREE
WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_DIR = os.path.join(WORKTREE, "tools")
FIXTURES_DIR = os.path.join(TOOLS_DIR, "tests", "fixtures", "check_drift", "phase4")

# Add tools to path for direct import
sys.path.insert(0, TOOLS_DIR)


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


class TestPhase4FailGate(unittest.TestCase):
    """Gate: phase4-fail — report JSON fail field must be 0."""

    def test_fail0_exits_0_no_phase4_finding(self):
        """report_fail0.json has fail=0 → all gates pass, rc 0, no phase4 lines."""
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_good.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        self.assertEqual(rc, 0)
        self.assertNotIn("rule=phase4-", out)

    def test_fail2_exits_1_with_phase4_fail_finding(self):
        """report_fail2.json has fail=2 → phase4-fail finding, rc 1."""
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_good.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail2.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        self.assertEqual(rc, 1)
        self.assertIn("rule=phase4-fail", out)
        self.assertIn("severity=high", out)

    def test_malformed_report_exit_2(self):
        """Malformed JSON → exit 2 + stderr ERROR."""
        rc, _, err = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_good.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_malformed.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        self.assertEqual(rc, 2)
        self.assertIn("ERROR", err)

    def test_missing_report_file_exit_2(self):
        """Report file does not exist → exit 2 + stderr ERROR."""
        rc, _, err = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_good.md"),
            "--report", "/nonexistent/report.json",
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        self.assertEqual(rc, 2)
        self.assertIn("ERROR", err)

    def test_report_field_not_int_exit_2(self):
        """Report has fail as string → internal error (exit 2)."""
        with tempfile.TemporaryDirectory() as td:
            bad_report = os.path.join(td, "report_bad_type.json")
            with open(bad_report, "w") as f:
                json.dump({"fail": "two"}, f)
            rc, _, err = _run_cli(
                "--phase4",
                os.path.join(FIXTURES_DIR, "en.md"),
                os.path.join(FIXTURES_DIR, "ru_good.md"),
                "--report", bad_report,
                "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
            )
            self.assertEqual(rc, 2)
            self.assertIn("ERROR", err)


class TestPhase4ParityGate(unittest.TestCase):
    """Gate: phase4-parity — 1:1 line parity between EN and RU."""

    def test_good_fixtures_parity_pass(self):
        """ru_good.md same line count → parity OK (combined with other clean gates)."""
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_good.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        self.assertEqual(rc, 0)
        self.assertNotIn("rule=phase4-parity", out)

    def test_parity_length_mismatch_emits_one_finding(self):
        """ru_bad_parity.md has 30 lines vs EN 29 → ONE phase4-parity finding."""
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_bad_parity.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        self.assertEqual(rc, 1)
        # Exactly one parity line
        parity_lines = [l for l in out.splitlines() if "rule=phase4-parity" in l]
        self.assertEqual(len(parity_lines), 1)
        self.assertIn("line count:", parity_lines[0])

    def test_parity_length_mismatch_stops_positional_checks(self):
        """When lengths differ, no further positional (identity/glossary) checks run."""
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_bad_parity.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        self.assertNotIn("rule=phase4-identity", out)
        self.assertNotIn("rule=phase4-glossary", out)


class TestPhase4IdentityGate(unittest.TestCase):
    """Gate: phase4-identity — all body lines identical → EN copy detection."""

    def test_identity_all_identical_finds_en_copy(self):
        """ru_bad_identity.md is byte-identical EN copy → phase4-identity finding."""
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_bad_identity.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        self.assertEqual(rc, 1)
        self.assertIn("rule=phase4-identity", out)
        self.assertIn("EN copy", out)

    def test_identity_partial_no_finding(self):
        """ru_partially_translated.md: some body lines differ → NO phase4-identity."""
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_partially_translated.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        self.assertNotIn("rule=phase4-identity", out)

    def test_identity_zero_body_no_finding(self):
        """Document with only headers/metadata → zero body lines → no finding."""
        # Create minimal fixture with only metadata and no body
        with tempfile.TemporaryDirectory() as td:
            en = os.path.join(td, "en.md")
            ru = os.path.join(td, "ru.md")
            for f in (en, ru):
                with open(f, "w") as fh:
                    fh.write(
                        "# Header\n\n"
                        "id: test\n"
                        "Version: 1.0\n"
                        "Status: draft\n"
                        "Abstraction: conceptual\n"
                        "changelog-path: CHANGELOGS/test.changes.md\n"
                    )
            rc, out, _ = _run_cli(
                "--phase4", en, ru,
                "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
                "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
            )
            # Zero body → no findings (phase4 now implemented)
            self.assertNotIn("rule=phase4-identity", out)


class TestPhase4GlossaryGate(unittest.TestCase):
    """Gate: phase4-glossary — EN-body terms must have RU equivalent in RU text.

    Strict semantics: EN form alone in RU does NOT satisfy the gate.
    Only the RU equivalent (case-insensitive substring) in RU body passes.
    """

    def test_good_glossary_pass(self):
        """ru_good.md has RU equivalents for all EN-body terms → no glossary finding."""
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_good.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        self.assertEqual(rc, 0)
        self.assertNotIn("rule=phase4-glossary", out)

    def test_bad_glossary_untranslated_finds_failure(self):
        """ru_bad_glossary.md leaves 'Translation' as English → phase4-glossary."""
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_bad_glossary.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        self.assertEqual(rc, 1)
        self.assertIn("rule=phase4-glossary", out)

    def test_partial_translation_one_glossary_finding(self):
        """ru_bad_glossary.md (29 lines, same as EN): verbatim EN at a body index →
        exactly one glossary finding.

        Same line count as EN, so parity passes. But line 12 has verbatim "Translation"
        (should be "Перевод") → one glossary finding.
        Identity must NOT fire (body not fully identical).
        """
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_bad_glossary.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        # Should have exactly one glossary finding
        glossary_lines = [l for l in out.splitlines() if "rule=phase4-glossary" in l]
        self.assertEqual(len(glossary_lines), 1)
        # Should NOT have identity finding (body not fully identical)
        self.assertNotIn("rule=phase4-identity", out)

    def test_glossary_explicit_flag_determinism(self):
        """With explicit --glossary flag, behavior is deterministic (mini-glossary fixture).

        The old implicit default from __file__ is removed: the contract now requires
        either --glossary <path> or --glossary none. This test exercises the explicit
        flag path with the known-good mini-glossary fixture.
        """
        # With our mini-glossary that has all terms covered in ru_good
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_good.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        self.assertEqual(rc, 0)

    def test_glossary_term_not_in_en_body_ignored(self):
        """Term 'Governance' is in glossary but NOT in EN body → ignored.

        mini-glossary has "Governance" but it doesn't appear in any EN body line.
        Should not cause a false glossary finding.
        """
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_good.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        # Must not have glossary findings for ignored terms
        self.assertNotIn("rule=phase4-glossary", out)


class TestTableHyphenParityRegression(unittest.TestCase):
    """Regression: table body rows with hyphens must NOT be structural.

    AMENDED parity rule: structural table rows are ONLY separator rows
    (set(s) ⊆ {|, -, :, space}). Body rows with hyphenated prose like
    "Controlled-file" are NOT structural — matching the amending in
    target-task.md §phase4-parity.
    """

    def test_table_body_with_hyphens_not_structural(self):
        """EN table body row has hyphenated text, RU counterpart does not.

        With the bug: _is_structural's `'|' and '-' in s` marks the EN row
        as structural (because of hyphen in "Controlled-file") while the RU row
        (no hyphen) is not → structural divergence at line 22 (false positive).

        With the fix: neither row is structural (hyphens are body content) →
        no structural divergence. This test is RED against current code (bug
        not yet fixed).
        """
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en_table_hyphens.md"),
            os.path.join(FIXTURES_DIR, "ru_table_no_hyphens.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        # After fix: hyphens should NOT cause structural divergence
        self.assertNotIn("structural divergence", out)


class TestGlossaryFlexionRegression(unittest.TestCase):
    """Regression: RU equivalents in declined forms must match via stem-prefix.

    AMENDED glossary rule: use stem-prefix match (first 5 chars of each word).
    e.g. "Документация" → stem "док" matches "документации" (prepositional).
    """

    def test_declined_russian_equivalent_matches(self):
        """EN term 'Documentation' appears as 'документации' (declined) in RU.

        Old substring check fails: "документация" is NOT in "документации".
        New stem-prefix: "док" is a word-start of "документации" → OK.
        This test is RED against current code (bug not yet fixed).
        """
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en_flexion.md"),
            os.path.join(FIXTURES_DIR, "ru_flexion_declined.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        self.assertNotIn("rule=phase4-glossary", out)


class TestGlossaryDocumentLevelScope(unittest.TestCase):
    """Regression: RU equivalent may appear in ANY body line, not just the
    corresponding line (document-level scope, not per-line).
    """

    def test_russian_equiv_in_different_body_line(self):
        """EN term 'Translation' on line 11, RU equivalent 'Перевод' on line 12.

        If scope is per-line (bug), this fails. With document-level scope,
        the RU equivalent found anywhere in RU body satisfies the gate.
        This test is RED against current code (bug not yet fixed).
        """
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en_scope.md"),
            os.path.join(FIXTURES_DIR, "ru_scope_different_line.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        self.assertNotIn("rule=phase4-glossary", out)


class TestPhase4Isolation(unittest.TestCase):
    """Each gate fails in isolation — other three gates clean."""

    def test_fail_gate_isolated(self):
        """report_fail2 + good files: only phase4-fail fires."""
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_good.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail2.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        self.assertEqual(rc, 1)
        self.assertIn("rule=phase4-fail", out)
        self.assertNotIn("rule=phase4-parity", out)
        self.assertNotIn("rule=phase4-identity", out)
        self.assertNotIn("rule=phase4-glossary", out)

    def test_parity_gate_isolated(self):
        """ru_bad_parity: only phase4-parity fires (other gates not reached/passed)."""
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_bad_parity.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        self.assertEqual(rc, 1)
        self.assertIn("rule=phase4-parity", out)

    def test_identity_gate_isolated(self):
        """ru_bad_identity: only phase4-identity fires."""
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_bad_identity.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        self.assertEqual(rc, 1)
        self.assertIn("rule=phase4-identity", out)
        self.assertNotIn("rule=phase4-parity", out)

    def test_glossary_gate_isolated(self):
        """ru_bad_glossary with mini-glossary: only phase4-glossary fires."""
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_bad_glossary.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        self.assertEqual(rc, 1)
        self.assertIn("rule=phase4-glossary", out)
        self.assertNotIn("rule=phase4-parity", out)


class TestJsonOutput(unittest.TestCase):
    """--json: flat objects {rule, severity, file, description}."""

    def test_json_schema_flat_object(self):
        """Each --json line has exactly {rule, severity, file, description}."""
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_bad_identity.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", "none",
            "--json",
        )
        self.assertEqual(rc, 1)
        for line in out.strip().splitlines():
            rec = json.loads(line)
            self.assertEqual(set(rec.keys()), {"rule", "severity", "file", "description"})
            self.assertEqual(rec["rule"], "phase4-identity")
            self.assertEqual(rec["severity"], "high")

    def test_no_coverage_musur_in_json(self):
        """--json output must not contain coverage footer lines."""
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_bad_identity.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
            "--json",
        )
        self.assertNotIn("coverage:", out)


class TestHumanRendering(unittest.TestCase):
    """Human mode: one finding line per finding, then coverage footer."""

    def test_human_rendering_format(self):
        """Each finding: rule=... severity=... file=... description."""
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_bad_identity.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", "none",
        )
        self.assertEqual(rc, 1)
        finding_lines = [l for l in out.splitlines() if "rule=" in l]
        self.assertTrue(finding_lines)
        for ln in finding_lines:
            self.assertIn("rule=phase4-identity", ln)
            self.assertIn("severity=high", ln)

    def test_coverage_footer_lists_gate_rules(self):
        """Human footer shows deterministic gate rule IDs in phase4 mode."""
        rc, out, _ = _run_cli(
            "--phase4",
            os.path.join(FIXTURES_DIR, "en.md"),
            os.path.join(FIXTURES_DIR, "ru_bad_identity.md"),
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(FIXTURES_DIR, "mini-glossary.md"),
        )
        # Footer should reference phase4 rules
        self.assertTrue(any("phase4" in l.lower() or "gate" in l.lower() for l in out.splitlines()))


class TestDriftRegression(unittest.TestCase):
    """Existing drift mode (no --phase4) must preserve current behavior."""

    def test_drift_identical_exits_0(self):
        """Identical files → drift mode rc 0."""
        rc, out, _ = _run_cli(
            os.path.join(FIXTURES_DIR, "drift_identical.md"),
            os.path.join(FIXTURES_DIR, "drift_identical.md"),
        )
        self.assertEqual(rc, 0)

    def test_drift_different_exits_1(self):
        """Different files → drift mode rc 1 (headings/structural differences)."""
        rc, out, _ = _run_cli(
            os.path.join(FIXTURES_DIR, "drift_identical.md"),
            os.path.join(FIXTURES_DIR, "drift_different.md"),
        )
        self.assertEqual(rc, 1)

    def test_drift_bad_usage_exits_2(self):
        """Wrong number of args → exit 2."""
        rc, _, err = _run_cli()
        self.assertEqual(rc, 2)


class TestCheckParityDeleted(unittest.TestCase):
    """tools/check_parity.py must NOT exist after displacement."""

    def test_check_parity_not_exists(self):
        rc, _, _ = _run_cli("--help")  # just a subprocess to verify env
        self.assertFalse(
            os.path.exists(os.path.join(TOOLS_DIR, "check_parity.py")),
            "tools/check_parity.py should not exist (displaced by check_drift phase4)",
        )


class TestLiveCorpus(unittest.TestCase):
    """Run --phase4 against the real EN/RU documenter-service corpus."""

    @unittest.skipUnless(
        os.path.exists(os.path.join(WORKTREE, "docs", "ru", "documenter-service", "index-RU.md"))
        and os.path.exists(os.path.join(WORKTREE, "docs", "en", "documenter-service", "index.md")),
        "No live EN/RU corpus for live test",
    )
    def test_live_documenter_service(self):
        """Real corpus: check_drift --phase4 on documenter-service EN/RU must exit 0."""
        en_path = os.path.join(WORKTREE, "docs", "en", "documenter-service", "index.md")
        ru_path = os.path.join(WORKTREE, "docs", "ru", "documenter-service", "index-RU.md")

        rc, out, err = _run_cli(
            "--phase4", en_path, ru_path,
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(WORKTREE, "docs", "en", "glossary", "index.md"),
        )
        self.assertEqual(rc, 0, f"Live corpus failed: {out}\n{err}")
        self.assertNotIn("rule=phase4-", out)


class TestEnLeakageIdentifierTails(unittest.TestCase):
    """T-1 regression: identifier tails and short markers are not EN leakage.

    Drift-mode en-leakage flagged body lines without Cyrillic whenever any
    [A-Za-z]{2,} matched — tracing-ID continuations like 'OQ-6).' produced
    false findings.  Only alphabetic runs >=3 letters surviving identifier-span
    removal count as untranslated prose.
    """

    def _run_drift(self, en_body, ru_body):
        with tempfile.TemporaryDirectory() as td:
            en = os.path.join(td, "en.md")
            ru = os.path.join(td, "ru.md")
            with open(en, "w", encoding="utf-8") as fh:
                fh.write("# Title\n\n" + "\n\n".join(en_body) + "\n")
            with open(ru, "w", encoding="utf-8") as fh:
                fh.write("# Заголовок\n\n" + "\n\n".join(ru_body) + "\n")
            rc, out, _ = _run_cli(en, ru)
        return rc, out

    def test_identifier_tail_not_flagged(self):
        rc, out = self._run_drift(
            ["Open question OQ-6).", "More English text here."],
            ["Открытый вопрос", "OQ-6).", "Больше русского текста."],
        )
        # line-count parity differs (3 vs 2 body) only if we miscount; keep counts equal
        self.assertNotIn("rule=en-leakage", out)

    def test_real_leak_still_flagged(self):
        rc, out = self._run_drift(
            ["Open question.", "Second line."],
            ["Открытый вопрос.", "TODO fix now"],
        )
        self.assertIn("rule=en-leakage", out)
        self.assertEqual(rc, 1)

    def test_marker_and_version_not_flagged(self):
        rc, out = self._run_drift(
            ["See ADR-014 and v0.1.0.", "Done."],
            ["См. ADR-014 и v0.1.0.", "Готово."],
        )
        # version/ID spans sit on lines that also have Cyrillic; main check is
        # a pure marker line:
        rc, out = self._run_drift(
            ["OQ-6).", "F-3) ADR-014"],
            ["Что-то первое.", "OQ-6).\nF-3) ADR-014"],
        )
        self.assertNotIn("rule=en-leakage", out)


if __name__ == "__main__":
    unittest.main()
