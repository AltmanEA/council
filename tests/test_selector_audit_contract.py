"""Prose-anchor tests for the Selector audit-contract / read-only clarification (v0.6.0).

Verifies that every document-body reference to audit behavior and read-only policy
is qualified: audit record always present in output; markdown file only at
`audit_dir` when provided; project-artifact writes excluded.

Does NOT modify any runtime tests or fixtures.
"""
import os
import re
import unittest

import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]

SKILL_PATH = str(_ROOT / ".agents" / "skills" / "selector" / "SKILL.md")
ROLE_SELECTOR_PATH = str(_ROOT / ".agents" / "skills" / "selector" / "roles" / "selector.md")
ROLE_LAYER2_PATH = str(_ROOT / ".agents" / "skills" / "selector" / "roles" / "selector_layer2.md")
SPEC_EN_PATH = str(_ROOT / "docs/en/selector/index.md")
SPEC_RU_PATH = str(_ROOT / "docs/ru/selector/index-RU.md")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestNoUnconditionalWritePhrases(unittest.TestCase):
    """Old unconditional phrases must NOT appear in any prose file.

    Only the exact old PATTERNS are forbidden — words like 'no writes'
    are permitted in the new qualified form (e.g. 'no writes to docs/, manifest …').
    """

    @classmethod
    def setUpClass(cls):
        cls.skill = _read(SKILL_PATH)
        cls.role_sel = _read(ROLE_SELECTOR_PATH)
        cls.role_l2 = _read(ROLE_LAYER2_PATH)
        cls.spec_en = _read(SPEC_EN_PATH)
        cls.spec_ru = _read(SPEC_RU_PATH)

    # -- forbidden exact patterns (unconditional old contract) --
    FORBIDDEN_PATTERNS = [
        "Every call produces an audit artifact",
        r"\*\*Read-only\*\*: no writes",
        r"no file modifications",
    ]

    def test_skill_no_forbidden_patterns(self):
        """SKILL.md must not contain any forbidden pattern."""
        for pattern in self.FORBIDDEN_PATTERNS:
            self.assertNotRegex(
                self.skill, pattern,
                f"SKILL.md matches forbidden pattern: {pattern!r}"
            )

    def test_role_selector_no_forbidden_patterns(self):
        """roles/selector.md must not contain any forbidden pattern."""
        for pattern in self.FORBIDDEN_PATTERNS:
            self.assertNotRegex(
                self.role_sel, pattern,
                f"roles/selector.md matches forbidden pattern: {pattern!r}"
            )

    def test_role_layer2_no_forbidden_patterns(self):
        """roles/selector_layer2.md must not contain any forbidden pattern."""
        for pattern in self.FORBIDDEN_PATTERNS:
            self.assertNotRegex(
                self.role_l2, pattern,
                f"roles/selector_layer2.md matches forbidden pattern: {pattern!r}"
            )

    def test_spec_en_no_forbidden_patterns(self):
        """docs/en/selector/index.md must not contain any forbidden pattern."""
        for pattern in self.FORBIDDEN_PATTERNS:
            self.assertNotRegex(
                self.spec_en, pattern,
                f"docs/en/selector/index.md matches forbidden pattern: {pattern!r}"
            )


class TestEnAnchorsPresent(unittest.TestCase):
    """EN files must contain the new qualified anchors (case-insensitive)."""

    @classmethod
    def setUpClass(cls):
        cls.skill = _read(SKILL_PATH)
        cls.role_sel = _read(ROLE_SELECTOR_PATH)
        cls.role_l2 = _read(ROLE_LAYER2_PATH)
        cls.spec_en = _read(SPEC_EN_PATH)

    EN_ANCHORS = [
        "audit record",
        "caller-provided `audit_dir`",
        "project artifacts",
    ]

    def test_skill_has_en_anchors(self):
        text = self.skill.lower()
        for anchor in self.EN_ANCHORS:
            self.assertIn(
                anchor.lower(), text,
                f"SKILL.md missing (case-insensitive): {anchor!r}"
            )

    def test_role_selector_has_en_anchors(self):
        text = self.role_sel.lower()
        for anchor in self.EN_ANCHORS:
            self.assertIn(
                anchor.lower(), text,
                f"roles/selector.md missing (case-insensitive): {anchor!r}"
            )

    def test_role_layer2_has_en_anchors(self):
        text = self.role_l2.lower()
        for anchor in self.EN_ANCHORS:
            self.assertIn(
                anchor.lower(), text,
                f"roles/selector_layer2.md missing (case-insensitive): {anchor!r}"
            )

    def test_spec_en_has_en_anchors(self):
        text = self.spec_en.lower()
        for anchor in self.EN_ANCHORS:
            self.assertIn(
                anchor.lower(), text,
                f"docs/en/selector/index.md missing (case-insensitive): {anchor!r}"
            )


class TestRuAnchorsPresent(unittest.TestCase):
    """RU mirror must contain the Russian-language equivalents (case-insensitive)."""

    @classmethod
    def setUpClass(cls):
        cls.spec_ru = _read(SPEC_RU_PATH)

    RU_ANCHORS = [
        "аудит-запись",         # audit record
        "audit_dir",            # kept as identifier
        "артефактов проекта",   # project artifacts
    ]

    def test_spec_ru_has_ru_anchors(self):
        text = self.spec_ru.lower()
        for anchor in self.RU_ANCHORS:
            self.assertIn(
                anchor.lower(), text,
                f"docs/ru/selector/index-RU.md missing (case-insensitive): {anchor!r}"
            )


class TestEnRuLineParity(unittest.TestCase):
    """EN and RU spec files must have the same line count (92 lines)."""

    @classmethod
    def setUpClass(cls):
        with open(SPEC_EN_PATH, "r", encoding="utf-8") as f:
            cls.en_lines = len(f.readlines())
        with open(SPEC_RU_PATH, "r", encoding="utf-8") as f:
            cls.ru_lines = len(f.readlines())

    def test_en_lines_92(self):
        self.assertEqual(self.en_lines, 92, f"EN spec has {self.en_lines} lines, expected 92")

    def test_ru_lines_92(self):
        self.assertEqual(self.ru_lines, 92, f"RU spec has {self.ru_lines} lines, expected 92")

    def test_parity(self):
        self.assertEqual(self.en_lines, self.ru_lines,
                         f"EN ({self.en_lines}) != RU ({self.ru_lines})")


class TestVersionAlignment(unittest.TestCase):
    """Version must be 0.6.0 in both EN and RU frontmatter."""

    @classmethod
    def setUpClass(cls):
        cls.spec_en = _read(SPEC_EN_PATH)
        cls.spec_ru = _read(SPEC_RU_PATH)

    def test_en_version_060(self):
        self.assertIn("Version: 0.6.0", self.spec_en)

    def test_ru_version_060(self):
        self.assertIn("Version: 0.6.0", self.spec_ru)


if __name__ == "__main__":
    unittest.main()
