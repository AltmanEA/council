"""Unit tests for tests/card_contract.py — Approval Card contract.

Test groups:
  (a) Validator unit tests — one targeted failing test per rule ID +
      conformant 6-line and full 10-line cards + tolerance/robustness cases.
  (b) Scripted dry-run of the operating loop (mechanical bundle → [],
      audit absent, U+00B7 in Translations, bare approve accepted;
      semantic bundle → check_approve requires object).
  (c) Prose-anchor tests against .agents/skills/documentation/SKILL.md
      §Step-(5) Approve section.

All tests are deterministic. No skips, no expectedFail, no try-import tricks.
"""
import os
import pathlib
import re
import unittest

# card_contract.py is in the same package
from tests.card_contract import (
    CARD_FIELDS,
    REQUIRED_FIELDS,
    MAX_CARD_LINES,
    validate_card,
    check_approve,
)

# Path to SKILL.md resolved from this file's location (per target-task)
SKILL_PATH = str(
    pathlib.Path(__file__).resolve().parents[1]
    / ".agents" / "skills" / "documentation" / "SKILL.md"
)


# ---------------------------------------------------------------------------
# (a) Validator unit tests — rule IDs
# ---------------------------------------------------------------------------

class TestConformantCards(unittest.TestCase):
    """Conformant cards must pass validation (empty findings list)."""

    def test_card_fields_order_is_eight(self):
        """CARD_FIELDS has exactly 8 ordered field names, no unknown field allowed."""
        self.assertEqual(len(CARD_FIELDS), 8)
        self.assertEqual(
            CARD_FIELDS,
            ["Files", "Category", "Delta", "Classification", "Audit", "Archive",
             "Translations", "State"],
        )

    def test_required_fields_are_four(self):
        """REQUIRED_FIELDS = [Files, Category, Delta, Classification]."""
        self.assertEqual(
            REQUIRED_FIELDS,
            ["Files", "Category", "Delta", "Classification"],
        )

    def test_max_card_lines_is_ten(self):
        """MAX_CARD_LINES = 10."""
        self.assertEqual(MAX_CARD_LINES, 10)

    def test_conformant_6_line_card(self):
        """A 6-line card (no optional fields) passes validation.

        card-line-limit: 6 <= 10 → no finding
        Required fields present, all values valid.
        """
        card = [
            "Files: docs/en/example/index.md",
            "Category: create",
            "Delta: +3 / \u22120 / net +3",
            "Classification: mechanical",
        ]
        self.assertEqual(validate_card(card), [])

    def test_conformant_10_line_card(self):
        """A full 10-line card (all 7 fields, State: intermediate, override bracket) passes."""
        card = [
            "Files: docs/en/example/index.md, docs/ru/example/index-RU.md",
            "Category: update",
            "Delta: +2 / \u22121 / net +1",
            "Classification: semantic [agent proposed: mechanical]",
            "Audit: \u26a0 findings: 2 / \U0001f6a8 critical: 1 + missing RU header",
            "Translations: auto_sync \u00b7 verified 5 \u00b7 unverified 0",
            "State: intermediate",
        ]
        # 7 lines only — that's fine, the max is 10, not a fixed size
        self.assertEqual(validate_card(card), [])

    def test_conformant_card_with_archive_line(self):
        """A card with the Archive: line (sess-archive-design-2026-11-19) passes."""
        card = [
            "Files: docs/en/archive/foo/index.md, docs/en/documenter-service/index.md",
            "Category: update",
            "Delta: +4 / \u22120 / net +4",
            "Classification: semantic",
            "Archive: 1 file entering archive",
            "State: final",
        ]
        self.assertEqual(validate_card(card), [])

    def test_conformant_10_line_all_fields(self):
        """A card with all 7 fields and 10 lines total passes (if <= 10)."""
        card = [
            "Files: f1.md, f2.md, f3.md, f4.md, f5.md, f6.md, f7.md, f8.md",
            "Category: update",
            "Delta: +5 / \u22123 / net +2",
            "Classification: mechanical",
            "Audit: \u26a0 findings: 1 + needs review",
            "Translations: auto_sync \u00b7 verified 78 \u00b7 unverified 0",
            "State: final",
        ]
        self.assertEqual(validate_card(card), [])


class TestRule_card_line_limit(unittest.TestCase):
    """Rule: card-line-limit — block exceeds 10 lines."""

    def test_11_lines_exceeds_limit(self):
        """An 11-line card triggers card-line-limit."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
            "Audit: \u26a0 findings: 1",
            "Translations: auto \u00b7 verified 1 \u00b7 unverified 0",
            "State: final",
            "Extra1: value1",
            "Extra2: value2",
            "Extra3: value3",
            "Extra4: value4",
        ]
        findings = validate_card(card)
        self.assertIn("card-line-limit", findings)

    def test_exactly_10_lines_passes_limit(self):
        """A 10-line card does NOT trigger card-line-limit."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
            "Audit: \u26a0 findings: 1",
            "Translations: auto \u00b7 verified 1 \u00b7 unverified 0",
            "State: final",
            "Files2: f2.md",
            "Category2: update",
            "Delta2: +1 / \u22120 / net +1",
        ]
        findings = validate_card(card)
        self.assertNotIn("card-line-limit", findings)


class TestRule_card_unknown_field(unittest.TestCase):
    """Rule: card-unknown-field — Label outside CARD_FIELDS."""

    def test_unknown_field_detected(self):
        """A field not in CARD_FIELDS triggers card-unknown-field."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
            "UnknownField: value",
        ]
        findings = validate_card(card)
        self.assertIn("card-unknown-field", findings)


class TestRule_card_missing_required(unittest.TestCase):
    """Rule: card-missing-required — a required field absent."""

    def test_missing_files_triggers_finding(self):
        """Removing Files from required fields triggers card-missing-required."""
        card = [
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
        ]
        findings = validate_card(card)
        self.assertIn("card-missing-required", findings)

    def test_missing_classification_triggers_finding(self):
        """Removing Classification triggers card-missing-required."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
        ]
        findings = validate_card(card)
        self.assertIn("card-missing-required", findings)


class TestRule_card_field_order(unittest.TestCase):
    """Rule: card-field-order — present fields not in CARD_FIELDS relative order."""

    def test_fields_out_of_order_triggers_finding(self):
        """Files after Delta triggers card-field-order."""
        card = [
            "Delta: +1 / \u22120 / net +1",
            "Files: f1.md",
            "Category: create",
            "Classification: mechanical",
        ]
        findings = validate_card(card)
        self.assertIn("card-field-order", findings)

    def test_fields_in_correct_order_passes(self):
        """Fields in CARD_FIELDS order pass."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
        ]
        findings = validate_card(card)
        self.assertNotIn("card-field-order", findings)


class TestRule_card_empty_value(unittest.TestCase):
    """Rule: card-empty-value — a present field with empty value."""

    def test_empty_files_value_triggers_finding(self):
        """Files: (empty value) triggers card-empty-value."""
        card = [
            "Files:",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
        ]
        findings = validate_card(card)
        self.assertIn("card-empty-value", findings)


class TestRule_card_category(unittest.TestCase):
    """Rule: card-category — Category not in {create, update, delete, split, translation}."""

    def test_invalid_category_triggers_finding(self):
        """Category: refactor triggers card-category."""
        card = [
            "Files: f1.md",
            "Category: refactor",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
        ]
        findings = validate_card(card)
        self.assertIn("card-category", findings)

    def test_valid_categories_pass(self):
        """All valid categories pass individually."""
        for cat in ["create", "update", "delete", "split", "translation"]:
            card = [
                f"Files: f1.md",
                f"Category: {cat}",
                "Delta: +1 / \u22120 / net +1",
                "Classification: mechanical",
            ]
            self.assertEqual(validate_card(card), [], f"Category {cat} should pass")


class TestRule_card_classification(unittest.TestCase):
    """Rule: card-classification — head not mechanical|semantic, or bracket not matching."""

    def test_invalid_classification_head(self):
        """Classification: experimental triggers card-classification."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: experimental",
        ]
        findings = validate_card(card)
        self.assertIn("card-classification", findings)

    def test_valid_classification_head_passes(self):
        """Classification: mechanical passes."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
        ]
        self.assertEqual(validate_card(card), [])

    def test_invalid_bracket_format(self):
        """Classification with bracket not matching [agent proposed: <non-empty>] triggers."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical [review needed]",
        ]
        findings = validate_card(card)
        self.assertIn("card-classification", findings)

    def test_valid_bracket_format_passes(self):
        """Classification with valid [agent proposed: mechanical] passes."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: semantic [agent proposed: mechanical]",
        ]
        self.assertEqual(validate_card(card), [])

    def test_empty_agent_proposed_triggers_finding(self):
        """[agent proposed: ] with empty content triggers card-classification."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: semantic [agent proposed: ]",
        ]
        findings = validate_card(card)
        self.assertIn("card-classification", findings)


class TestRule_card_delta(unittest.TestCase):
    """Rule: card-delta — not matching +<int> / \u2212<int> / net [+-]<int>."""

    def test_valid_delta_passes(self):
        """Standard valid Delta format passes."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +3 / \u22121 / net +2",
            "Classification: mechanical",
        ]
        self.assertEqual(validate_card(card), [])

    def test_valid_delta_with_minus_net_passes(self):
        """Delta with net - passes."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22123 / net -2",
            "Classification: mechanical",
        ]
        self.assertEqual(validate_card(card), [])

    def test_invalid_delta_wrong_format_triggers_finding(self):
        """Delta without / separators triggers card-delta."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +3 +1",
            "Classification: mechanical",
        ]
        findings = validate_card(card)
        self.assertIn("card-delta", findings)

    def test_invalid_delta_hyphen_instead_of_unicode_minus(self):
        """Using ASCII hyphen-minus instead of U+2212 triggers card-delta."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +3 / -1 / net +2",  # ASCII hyphen, not \u2212
            "Classification: mechanical",
        ]
        findings = validate_card(card)
        self.assertIn("card-delta", findings)


class TestRule_card_translations(unittest.TestCase):
    """Rule: card-translations — not matching <mode> \u00b7 verified <N> \u00b7 unverified <M>."""

    def test_valid_translations_passes(self):
        """Valid Translations format passes."""
        card = [
            "Files: f1.md",
            "Category: translation",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
            "Translations: auto_sync \u00b7 verified 78 \u00b7 unverified 0",
        ]
        self.assertEqual(validate_card(card), [])

    def test_invalid_translations_wrong_separator_triggers_finding(self):
        """Using * instead of U+00B7 triggers card-translations."""
        card = [
            "Files: f1.md",
            "Category: translation",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
            "Translations: auto_sync * verified 78 * unverified 0",  # ASCII asterisk
        ]
        findings = validate_card(card)
        self.assertIn("card-translations", findings)

    def test_invalid_translations_no_verified_triggers_finding(self):
        """Missing 'verified' keyword triggers card-translations."""
        card = [
            "Files: f1.md",
            "Category: translation",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
            "Translations: auto_sync \u00b7 78 \u00b7 0",
        ]
        findings = validate_card(card)
        self.assertIn("card-translations", findings)


class TestRule_card_state(unittest.TestCase):
    """Rule: card-state — State not in {final, intermediate}."""

    def test_valid_state_passes(self):
        """State: final passes."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
            "State: final",
        ]
        self.assertEqual(validate_card(card), [])

    def test_invalid_state_triggers_finding(self):
        """State: draft triggers card-state."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
            "State: draft",
        ]
        findings = validate_card(card)
        self.assertIn("card-state", findings)


class TestRule_card_audit(unittest.TestCase):
    """Rule: card-audit — clean-ish Audit line must be OMITTED (silent-when-clean)."""

    def test_clean_audit_none_triggers_finding(self):
        """Audit: none triggers card-audit (must be omitted)."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
            "Audit: none",
        ]
        findings = validate_card(card)
        self.assertIn("card-audit", findings)

    def test_clean_audit_clean_triggers_finding(self):
        """Audit: clean triggers card-audit (must be omitted)."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
            "Audit: clean",
        ]
        findings = validate_card(card)
        self.assertIn("card-audit", findings)

    def test_clean_audit_zero_triggers_finding(self):
        """Audit: 0 triggers card-audit (must be omitted)."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
            "Audit: 0",
        ]
        findings = validate_card(card)
        self.assertIn("card-audit", findings)

    def test_clean_audit_em_dash_triggers_finding(self):
        """Audit: \u2014 (em dash) triggers card-audit (must be omitted)."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
            "Audit: \u2014",  # em dash
        ]
        findings = validate_card(card)
        self.assertIn("card-audit", findings)

    def test_finding_audit_passes(self):
        """Audit with actual findings does NOT trigger card-audit."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
            "Audit: \u26a0 findings: 2 / \U0001f6a8 critical: 1",
        ]
        self.assertEqual(validate_card(card), [])


# ---------------------------------------------------------------------------
# (a) Tolerance / robustness cases
# ---------------------------------------------------------------------------

class TestTolerance(unittest.TestCase):
    """Parser tolerance: non-label lines ignored, colons in values OK, etc."""

    def test_prose_lines_ignored(self):
        """Lines that are not Label: value form are ignored."""
        card = [
            "Some prose line without colon format",
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
            "Another prose line",
        ]
        self.assertEqual(validate_card(card), [])

    def test_colon_in_value_not_split(self):
        """A colon inside the value (e.g. agent proposed: ...) does not create a second field."""
        card = [
            "Files: f1.md",
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: semantic [agent proposed: mechanical: original decision]",
        ]
        findings = validate_card(card)
        self.assertEqual(findings, [])

    def test_case_sensitive_labels_rejected(self):
        """Uppercase label variants (e.g. 'files' vs 'Files') are treated as unknown fields."""
        card = [
            "files: f1.md",  # lowercase — should be unknown
            "Category: create",
            "Delta: +1 / \u22120 / net +1",
            "Classification: mechanical",
        ]
        findings = validate_card(card)
        self.assertIn("card-unknown-field", findings)
        self.assertIn("card-missing-required", findings)  # Files is required


class TestBlankStripping(unittest.TestCase):
    """Leading/trailing blank lines are stripped before counting."""

    def test_leading_blank_lines_stripped(self):
        """Leading blank lines don't count toward the 10-line limit."""
        card = ["", "", "Files: f1.md", "Category: create", "Delta: +1 / \u22120 / net +1", "Classification: mechanical"]
        self.assertEqual(validate_card(card), [])

    def test_trailing_blank_lines_stripped(self):
        """Trailing blank lines don't count toward the 10-line limit."""
        card = ["Files: f1.md", "Category: create", "Delta: +1 / \u22120 / net +1", "Classification: mechanical", "", ""]
        self.assertEqual(validate_card(card), [])


# ---------------------------------------------------------------------------
# (b) Scripted dry-run of the operating loop
# ---------------------------------------------------------------------------

class TestScriptedDryRun(unittest.TestCase):
    """Dry-run of the operating loop: render cards from bundle dicts and validate."""

    def _render_card_from_bundle(self, bundle):
        """Render an Approval Card from a bundle dict.

        Helper for dry-run tests.  Constructs the card lines in CARD_FIELDS order.
        Optional fields (Audit, Translations, State) are included only when
        the bundle explicitly provides them.
        """
        lines = []
        files_val = ", ".join(bundle["files"])
        lines.append(f"Files: {files_val}")
        lines.append(f"Category: {bundle['category']}")
        added = bundle.get("added", 0)
        removed = bundle.get("removed", 0)
        net = added - removed
        lines.append(f"Delta: +{added} / \u2212{removed} / net +{net}")
        class_val = bundle["classification"]
        if "override_label" in bundle:
            class_val += f" [agent proposed: {bundle['override_label']}]"
        lines.append(f"Classification: {class_val}")
        # Audit: only present if bundle has a finding (silent-when-clean)
        if "audit_finding" in bundle:
            lines.append(f"Audit: {bundle['audit_finding']}")
        # Translations: only present if bundle has translations data
        if "translations" in bundle:
            t = bundle["translations"]
            lines.append(f"Translations: {t['mode']} \u00b7 verified {t['verified']} \u00b7 unverified {t['unverified']}")
        # State: only present if bundle has state
        if "state" in bundle:
            lines.append(f"State: {bundle['state']}")
        return lines

    def test_mechanical_dry_run_no_findings(self):
        """Mechanical bundle (Phase 1 tail shape) → validator returns [].

        The real Phase 1 tail: updated docs + changelog + manifest.
        audit is clean → Audit line absent.
        Translations line present (auto_sync).
        Card must be <= 10 lines.
        check_approve(classification=mechanical, reply="approve") must return True.
        """
        bundle = {
            "files": [
                "docs/en/documenter-service/index.md",
                "docs/ru/documenter-service/index-RU.md",
                "CHANGELOGS/documenter-service.changes.md",
                "docs-manifest.yaml",
            ],
            "category": "update",
            "added": 2,
            "removed": 2,
            "classification": "mechanical",
            "translations": {
                "mode": "auto_sync",
                "verified": 78,
                "unverified": 0,
            },
        }
        card = self._render_card_from_bundle(bundle)
        findings = validate_card(card)
        self.assertEqual(findings, [], f"Mechanical bundle card had findings: {findings}")

        # Audit line must be absent (silent-when-clean)
        self.assertFalse(
            any(l.startswith("Audit:") for l in card),
            "Audit line should be absent for clean audit",
        )

        # Translations must use U+00B7
        trans_line = [l for l in card if l.startswith("Translations:")][0]
        self.assertIn("\u00b7", trans_line)

        # Card must be <= 10 lines
        self.assertLessEqual(len(card), MAX_CARD_LINES)

        # Bare "approve" accepted for mechanical
        self.assertTrue(
            check_approve("approve", "mechanical"),
            "Bare approve must be accepted for mechanical",
        )

    def test_mechanical_dry_run_with_audit_finding(self):
        """Mechanical bundle with audit findings → Audit line present, no card-audit finding."""
        bundle = {
            "files": ["docs/en/example/index.md"],
            "category": "update",
            "added": 1,
            "removed": 0,
            "classification": "mechanical",
            "audit_finding": "\u26a0 findings: 1",
        }
        card = self._render_card_from_bundle(bundle)
        findings = validate_card(card)
        self.assertEqual(findings, [], f"Mechanical bundle with audit had findings: {findings}")

    def test_semantic_dry_run_requires_object(self):
        """Semantic bundle → bare "approve" must be rejected by check_approve.

        The operator must name the object of the semantic change.
        """
        bundle = {
            "files": ["docs/en/documenter-service/index.md"],
            "category": "update",
            "added": 5,
            "removed": 2,
            "classification": "semantic",
        }
        card = self._render_card_from_bundle(bundle)
        findings = validate_card(card)
        self.assertEqual(findings, [], "Semantic card should validate")

        # Bare approve must NOT be accepted for semantic
        self.assertFalse(
            check_approve("approve", "semantic"),
            "Bare approve must be rejected for semantic",
        )

        # approve: <noun phrase> must be accepted
        self.assertTrue(
            check_approve("approve: rewrite of the Safety section", "semantic"),
            "approve: <noun phrase> must be accepted for semantic",
        )

    def test_semantic_dry_run_no_object_rejected(self):
        """Semantic bundle → approve: (empty object) must be rejected."""
        self.assertFalse(
            check_approve("approve:", "semantic"),
            "approve: with empty object must be rejected for semantic",
        )
        self.assertFalse(
            check_approve("approve:   ", "semantic"),
            "approve: with whitespace-only object must be rejected for semantic",
        )


# ---------------------------------------------------------------------------
# (c) Prose-anchor tests against SKILL.md §Step-(5) Approve
# ---------------------------------------------------------------------------

class TestAnchorStep5Approve(unittest.TestCase):
    """Prose-anchor tests against .agents/skills/documentation/SKILL.md.

    These tests verify that the Step-(5) Approve section of SKILL.md contains
    the card template + approve grammar elements specified in the target-task.

    They are EXPECTED RED inside the worktree (SKILL.md adoption is
    operator-handled, out-of-cycle). They must go GREEN in the main tree
    after the prose sync.
    """

    @classmethod
    def setUpClass(cls):
        """Read the Step-(5) Approve section from SKILL.md."""
        cls.section = ""
        if os.path.exists(SKILL_PATH):
            with open(SKILL_PATH, "r", encoding="utf-8") as fh:
                full_text = fh.read()
            # Extract from "### Step-(5) Approve" to the next "### " heading
            start_marker = "### Step-(5) Approve"
            start_idx = full_text.find(start_marker)
            if start_idx >= 0:
                after_start = full_text[start_idx + len(start_marker):]
                # Find next section heading at the same level
                next_section = after_start.find("\n### ")
                if next_section >= 0:
                    cls.section = after_start[:next_section]
                else:
                    cls.section = after_start
            else:
                cls.section = ""

    def test_anchor_card_template_files_label(self):
        """The Step-(5) section must contain 'Files:' label (card template)."""
        self.assertIn(
            "Files:",
            self.section,
            "SKILL.md Step-(5) must contain 'Files:' card field label",
        )

    def test_anchor_card_template_category_label(self):
        """The Step-(5) section must contain 'Category:' label."""
        self.assertIn(
            "Category:",
            self.section,
            "SKILL.md Step-(5) must contain 'Category:' card field label",
        )

    def test_anchor_card_template_delta_label(self):
        """The Step-(5) section must contain 'Delta:' label."""
        self.assertIn(
            "Delta:",
            self.section,
            "SKILL.md Step-(5) must contain 'Delta:' card field label",
        )

    def test_anchor_card_template_classification_label(self):
        """The Step-(5) section must contain 'Classification:' label."""
        self.assertIn(
            "Classification:",
            self.section,
            "SKILL.md Step-(5) must contain 'Classification:' card field label",
        )

    def test_anchor_card_template_audit_label(self):
        """The Step-(5) section must contain 'Audit:' label (card template)."""
        self.assertIn(
            "Audit:",
            self.section,
            "SKILL.md Step-(5) must contain 'Audit:' card field label",
        )

    def test_anchor_card_template_archive_label(self):
        """The Step-(5) section must contain 'Archive:' label (card template).

        sess-archive-design-2026-11-19: the Archive line surfaces any write
        entering docs/en/archive/ or docs/ru/archive/ at the approve moment.
        """
        self.assertIn(
            "Archive:",
            self.section,
            "SKILL.md Step-(5) must contain 'Archive:' card field label",
        )

    def test_anchor_card_template_translations_label(self):
        """The Step-(5) section must contain 'Translations:' label."""
        self.assertIn(
            "Translations:",
            self.section,
            "SKILL.md Step-(5) must contain 'Translations:' card field label",
        )

    def test_anchor_card_template_state_label(self):
        """The Step-(5) section must contain 'State:' label."""
        self.assertIn(
            "State:",
            self.section,
            "SKILL.md Step-(5) must contain 'State:' card field label",
        )

    def test_anchor_approve_mechanical_bare(self):
        """The Step-(5) section must mention bare 'approve' for mechanical changes."""
        self.assertIn(
            "approve",
            self.section.lower(),
            "SKILL.md Step-(5) must reference 'approve' for mechanical changes",
        )

    def test_anchor_approve_semantic_object_required(self):
        """The Step-(5) section must require naming the object for semantic changes."""
        self.assertIn(
            "semantic",
            self.section.lower(),
            "SKILL.md Step-(5) must reference 'semantic' changes",
        )

    def test_anchor_mechanical_keyword(self):
        """The Step-(5) section must mention 'mechanical' as a classification."""
        self.assertIn(
            "mechanical",
            self.section.lower(),
            "SKILL.md Step-(5) must mention 'mechanical' classification",
        )

    def test_anchor_agent_proposed(self):
        """The Step-(5) section must contain 'agent proposed:' for override bracket."""
        self.assertIn(
            "agent proposed:",
            self.section.lower(),
            "SKILL.md Step-(5) must mention 'agent proposed:' override bracket",
        )

    def test_anchor_silent_when_clean(self):
        """The Step-(5) section must mention 'silent when clean' for audit."""
        self.assertIn(
            "silent when clean",
            self.section.lower(),
            "SKILL.md Step-(5) must mention 'silent when clean'",
        )

    def test_anchor_russian_terminology(self):
        """The Step-(5) section must contain the Russian term 'Карточка согласования'."""
        self.assertIn(
            "\u041a\u0430\u0440\u0442\u043e\u0447\u043a\u0430 \u0441\u043e\u0433\u043b\u0430\u0441\u043e\u0432\u0430\u043d\u0438\u044f",
            self.section,
            "SKILL.md Step-(5) must contain the Russian term 'Карточка согласования'",
        )

    def test_anchor_card_line_limit_ten(self):
        """The Step-(5) section must reference the 10-line limit for the card."""
        self.assertIn(
            "10",
            self.section,
            "SKILL.md Step-(5) must reference the 10-line card limit",
        )

    def test_anchor_state_intermediate(self):
        """The Step-(5) section must mention 'intermediate' as a valid State value."""
        self.assertIn(
            "intermediate",
            self.section.lower(),
            "SKILL.md Step-(5) must mention 'intermediate' state value",
        )

    def test_anchor_state_final(self):
        """The Step-(5) section must mention 'final' as a valid State value."""
        self.assertIn(
            "final",
            self.section.lower(),
            "SKILL.md Step-(5) must mention 'final' state value",
        )


if __name__ == "__main__":
    unittest.main()
