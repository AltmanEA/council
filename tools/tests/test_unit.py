#!/usr/bin/env python3
"""Unit tests for local_translate.py functions.

No network, no LLM -- stdlib only. Must complete in <5 s.

Run:  python3 tools/tests/test_unit.py
"""
from __future__ import annotations

import os
import sys
import unittest

# Add tools/ to sys.path so we can import local_translate and docmeta directly.
TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS_DIR)

from local_translate import (  # noqa: E402
    needs_skip,
    enforce_glossary,
    load_glossary,
    restore_heading_prefix,
    restore_list_marker,
    METADATA_KEYS,
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
        self.assertTrue(needs_skip("has_translation: docs/ru/foo/index-RU.md"))

    def test_table_separator_preserved(self):
        """Table separators are structural (from consensus: SUBJ-003 C)."""
        self.assertTrue(needs_skip("|---|---|"))

    def test_regular_line_not_skip(self):
        self.assertFalse(needs_skip("This is a regular line."))
        self.assertFalse(needs_skip("  Indented prose."))

    def test_code_fence(self):
        """needs_skip is called from block splitter; fences handled there.
        needs_skip itself does NOT see them."""
        self.assertFalse(needs_skip("```python"))


class TestEnforceGlossary(unittest.TestCase):
    """enforce_glossary: invariants on glossary term handling."""

    def setUp(self):
        # Fresh glossary for each test
        load_glossary(None)

    def test_no_consensus_budget_unchanged(self):
        """no_consensus_budget is an identifier-like value; enforce_glossary
        should NOT modify it (regex boundary check)."""
        text = "no_consensus_budget of 3 rounds"
        result = enforce_glossary(text, [])
        self.assertEqual(result, text)

    def test_consensus_term_changes(self):
        """'Consensus' in glossary should be force-applied."""
        load_glossary(os.path.join(TOOLS_DIR, "..", "docs", "en", "glossary", "index.md"))
        terms = [k for k in _GLOSSARY_CACHE.keys() if "consensus" in k.lower()]
        if terms:
            text = "The Consensus process is deterministic"
            result = enforce_glossary(text, terms)
            # Should contain Russian equivalent, not English "Consensus"
            self.assertNotEqual(result, text)

    def test_escalation_timeout_unchanged(self):
        """escalation_timeout_minutes is an identifier; should not be modified."""
        text = "escalation_timeout_minutes = 30"
        result = enforce_glossary(text, [])
        self.assertEqual(result, text)


class TestRestoreHeadingPrefix(unittest.TestCase):
    """restore_heading_prefix: prefix recovery."""

    def test_prefix_restored(self):
        """If model drops # prefix, it should be restored from source."""
        src = "## Overview"
        translated = "Обзор"  # model dropped the ##
        result = restore_heading_prefix(src, translated)
        self.assertTrue(result.startswith("##"))

    def test_correct_prefix_passes(self):
        """If the # prefix is correct, the line passes through."""
        src = "## Overview"
        translated = "## Обзор"
        result = restore_heading_prefix(src, translated)
        self.assertEqual(result, translated)

    def test_no_prefix_in_source(self):
        """Non-heading source passes translation unchanged."""
        src = "Regular text"
        translated = "Обычный текст"
        result = restore_heading_prefix(src, translated)
        self.assertEqual(result, translated)

    def test_various_depths(self):
        """Works with all heading depths 1-6."""
        for depth in range(1, 7):
            src = "#" * depth + " Heading"
            translated = f"Заголовок"
            result = restore_heading_prefix(src, translated)
            self.assertTrue(result.startswith("#" * depth))


class TestRestoreListMarker(unittest.TestCase):
    """restore_list_marker: marker recovery."""

    def test_numbered_list(self):
        """1. marker restored if model dropped it."""
        src = "1. First item"
        translated = "First item"
        result = restore_list_marker(src, translated)
        self.assertTrue(result.startswith("1."))

    def test_bullet_list(self):
        """- marker restored."""
        src = "- Second item"
        translated = "Second item"
        result = restore_list_marker(src, translated)
        self.assertTrue(result.startswith("- "))

    def test_correct_marker_passes(self):
        """Correct marker passes through."""
        src = "- Item"
        translated = "- Пункт"
        result = restore_list_marker(src, translated)
        self.assertEqual(result, translated)

    def test_no_marker_in_source(self):
        """Non-list source passes translation unchanged."""
        src = "Regular text"
        translated = "Обычный текст"
        result = restore_list_marker(src, translated)
        self.assertEqual(result, translated)


# Import the cache for glossary-aware tests
from local_translate import _GLOSSARY_CACHE  # noqa: E402


import local_translate as lt  # noqa: E402


class TestSpanRestore(unittest.TestCase):
    def test_positional_restore(self):
        out = lt.restore_code_spans("значение `заблокированная-эскалация` тут",
                                    "value `awaiting-operator` here")
        self.assertIn('`awaiting-operator`', out)
        self.assertNotIn('заблокированная', out)

    def test_decoration_stripped(self):
        # model added backticks around plain source text
        out = lt.restore_code_spans("это `Documenter` сервис",
                                    "this Documenter service")
        self.assertEqual(out, "это Documenter сервис")

    def test_legit_span_untouched_when_decoration_present(self):
        out = lt.restore_code_spans("шлюз `pre_check_override` и `x`",
                                    "gate `pre_check_override` and x")
        # legit span preserved; decorated plain 'x' unwrapped
        self.assertIn('`pre_check_override`', out)
        self.assertEqual(out, "шлюз `pre_check_override` и x")

    def test_dropped_backticks_rewrapped(self):
        out = lt.restore_code_spans("флаг allow + reason тут",
                                    "flag `allow` + reason here")
        self.assertIn('`allow`', out)

    def test_equal_count_noop(self):
        src = "see `a` and `b`"
        out = lt.restore_code_spans("смотри `a` и `b`", src)
        self.assertEqual(out, "смотри `a` и `b`")

class TestLiteralTokens(unittest.TestCase):
    def test_permission_table_not_translatable(self):
        self.assertFalse(lt._is_translatable_content("| `council.status` | allow | deny |"))
        self.assertTrue(lt._is_translatable_content("The operator resolves this escalation"))


if __name__ == "__main__":
    unittest.main()
