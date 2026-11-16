#!/usr/bin/env python3
"""Unit tests for techdoc_translator.py functions.

No network, no LLM -- stdlib only. Must complete in <5 s.

Run:  python3 tests/test_unit.py
"""
from __future__ import annotations

import os
import sys
import unittest

# Add the project root to sys.path so we can import techdoc_translator.
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from techdoc_translator import (  # noqa: E402
    needs_skip,
    enforce_glossary,
    load_glossary,
    restore_heading_prefix,
    restore_list_marker,
    _GLOSSARY_CACHE,
)


class TestNeedsSkip(unittest.TestCase):
    """needs_skip: structural lines that must not be translated."""

    def test_empty_line(self):
        self.assertTrue(needs_skip(""))
        self.assertTrue(needs_skip("   "))
        self.assertTrue(needs_skip("\t"))

    def test_separator_triple_dash(self):
        self.assertTrue(needs_skip("---"))
        self.assertTrue(needs_skip("--- "))

    def test_heading_not_skip(self):
        self.assertFalse(needs_skip("# Heading"))
        self.assertFalse(needs_skip("## Subheading"))
        self.assertFalse(needs_skip("   ### Tertiary"))

    def test_table_separator(self):
        self.assertTrue(needs_skip("|---|:--:|"))
        self.assertTrue(needs_skip("|-------|------|------|"))

    def test_metadata_skip(self):
        self.assertTrue(needs_skip("id: test"))
        self.assertTrue(needs_skip("Version: 1.0"))
        self.assertTrue(needs_skip("Status: draft"))
        self.assertTrue(needs_skip("title: Test Document"))

    def test_table_separator_preserved(self):
        self.assertTrue(needs_skip("|---|---|"))

    def test_regular_line_not_skip(self):
        self.assertFalse(needs_skip("This is a regular line."))
        self.assertFalse(needs_skip("  Indented prose."))

    def test_code_fence(self):
        self.assertFalse(needs_skip("```python"))

    def test_skip_pattern(self):
        rx = __import__('re').compile(r'^# SKIP')
        self.assertTrue(needs_skip("# SKIP this", skip_patterns=[rx]))
        self.assertFalse(needs_skip("This is normal", skip_patterns=[rx]))


class TestEnforceGlossary(unittest.TestCase):
    """enforce_glossary: invariants on glossary term handling."""

    def setUp(self):
        # Fresh glossary for each test
        _GLOSSARY_CACHE.clear()

    def test_no_consensus_budget_unchanged(self):
        """no_consensus_budget is an identifier; enforce_glossary
        should NOT modify it."""
        text = "no_consensus_budget of 3 rounds"
        result = enforce_glossary(text, [])
        self.assertEqual(result, text)

    def test_escalation_timeout_unchanged(self):
        """escalation_timeout_minutes is an identifier; should not be modified."""
        text = "escalation_timeout_minutes = 30"
        result = enforce_glossary(text, [])
        self.assertEqual(result, text)


class TestRestoreHeadingPrefix(unittest.TestCase):
    """restore_heading_prefix: prefix recovery."""

    def test_prefix_restored(self):
        src = "## Overview"
        translated = "Обзор"
        result = restore_heading_prefix(src, translated)
        self.assertTrue(result.startswith("##"))

    def test_correct_prefix_passes(self):
        src = "## Overview"
        translated = "## Обзор"
        result = restore_heading_prefix(src, translated)
        self.assertEqual(result, translated)

    def test_no_prefix_in_source(self):
        src = "Regular text"
        translated = "Обычный текст"
        result = restore_heading_prefix(src, translated)
        self.assertEqual(result, translated)

    def test_various_depths(self):
        for depth in range(1, 7):
            src = "#" * depth + " Heading"
            translated = f"Заголовок"
            result = restore_heading_prefix(src, translated)
            self.assertTrue(result.startswith("#" * depth))


class TestRestoreListMarker(unittest.TestCase):
    """restore_list_marker: marker recovery."""

    def test_numbered_list(self):
        src = "1. First item"
        translated = "First item"
        result = restore_list_marker(src, translated)
        self.assertTrue(result.startswith("1."))

    def test_bullet_list(self):
        src = "- Second item"
        translated = "Second item"
        result = restore_list_marker(src, translated)
        self.assertTrue(result.startswith("- "))

    def test_correct_marker_passes(self):
        src = "- Item"
        translated = "- Пункт"
        result = restore_list_marker(src, translated)
        self.assertEqual(result, translated)

    def test_no_marker_in_source(self):
        src = "Regular text"
        translated = "Обычный текст"
        result = restore_list_marker(src, translated)
        self.assertEqual(result, translated)


class TestSpanRestore(unittest.TestCase):
    def test_positional_restore(self):
        out = __import__('techdoc_translator', fromlist=['restore_code_spans']).restore_code_spans(
            "значение `заблокированная-эскалация` тут",
            "value `awaiting-operator` here")
        self.assertIn('`awaiting-operator`', out)
        self.assertNotIn('заблокированная', out)

    def test_decoration_stripped(self):
        out = __import__('techdoc_translator', fromlist=['restore_code_spans']).restore_code_spans(
            "это `some-service` component",
            "this some-service component")
        self.assertEqual(out, "это some-service component")

    def test_dropped_backticks_rewrapped(self):
        out = __import__('techdoc_translator', fromlist=['restore_code_spans']).restore_code_spans(
            "флаг allow + reason тут",
            "flag `allow` + reason here")
        self.assertIn('`allow`', out)

    def test_equal_count_noop(self):
        src = "see `a` and `b`"
        out = __import__('techdoc_translator', fromlist=['restore_code_spans']).restore_code_spans(
            "смотри `a` и `b`", src)
        self.assertEqual(out, "смотри `a` и `b`")


class TestLiteralTokens(unittest.TestCase):
    def test_permission_table_not_translatable(self):
        lt = __import__('techdoc_translator', fromlist=['_is_translatable_content'])
        self.assertFalse(lt._is_translatable_content("| `perm` | allow | deny |"))
        self.assertTrue(lt._is_translatable_content("The operator resolves this escalation"))


if __name__ == "__main__":
    unittest.main()
