"""Additional tests for the Documenter policy: entry validation, tier
authorization, operator ID, and matching (Task W1, Part B).

Appends to existing test_documenter_policy_diff.py — import-compatible with the
original.  Run with: python3 -m unittest tests.test_documenter_policy_new.
"""
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from documenter_service.core.errors import StructuredError  # noqa: E402
from documenter_service.core.policy import (  # noqa: E402
    PolicyError, check_tier2_authorized, check_tier3_authorized,
    load_policy, match_operation, match_pattern, operator_id_valid,
    validate_policy)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                        "documenter")
MANIFEST_IDS = {"alpha", "beta", "gamma"}


def _enable_operator_surface(root):
    """Create the ADR-013 Operator Surface readiness sentinel under root."""
    sentinel = os.path.join(root, "documenter", ".operator_surface_ready")
    os.makedirs(os.path.dirname(sentinel), exist_ok=True)
    with open(sentinel, "w") as f:
        f.write("")
    return sentinel


def _policy(**over):
    base = {
        "documenter_policy": {
            "version": "0.2.0",
            "active_tier": 0,
            "allowed_operations": [],
            "audit_freshness": 30,
            "briefing_ref": None,
        }
    }
    base["documenter_policy"].update(over)
    return base


class TestTier2ValidPolicyWithOpsAndPatterns(unittest.TestCase):
    """A valid tier-2 policy with operation+pattern entries loads when briefing
    file exists (mvp-data-models §2, policy-reference §Per-Operation Entries)."""

    def test_valid_tier2_policy_loads(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as fh:
            fh.write("operator briefing content\n")
            briefing_path = fh.name
        try:
            policy = _policy(
                active_tier=2,
                briefing_ref=briefing_path,
                allowed_operations=[
                    {
                        "type": "operation",
                        "change_type": "update",
                        "trust_level": "safe",
                        "targets": [],
                        "requires_diff_preview": True,
                    },
                    {
                        "type": "pattern",
                        "pattern_id": "auto-bump",
                        "pattern_description": "Deterministic patch bumps",
                        "match_criteria": {
                            "change_type": "update",
                            "file_pattern": "CHANGELOGS/*.changes.md",
                        },
                        "trust_level": "safe",
                    },
                ],
            )
            result = validate_policy(policy, manifest_ids=MANIFEST_IDS)
            self.assertEqual(result.get("active_tier"), 2)
            ops = result.get("allowed_operations")
            self.assertEqual(len(ops), 2)
            self.assertEqual(ops[0]["type"], "operation")
            self.assertEqual(ops[1]["type"], "pattern")
        finally:
            os.unlink(briefing_path)


class TestCheckTier2Authorized(unittest.TestCase):
    """check_tier2_authorized: tier, briefing_ref, and file existence."""

    def test_tier2_with_briefing_file_ok(self):
        with tempfile.TemporaryDirectory() as root:
            bp = os.path.join(root, "_briefing.md")
            with open(bp, "w") as fh:
                fh.write("briefing\n")
            policy = _policy(
                active_tier=2,
                briefing_ref=bp,
                allowed_operations=[{"type": "operation", "change_type": "update",
                                     "trust_level": "safe", "targets": []}],
            )
            inner = policy["documenter_policy"]
            # ADR-013: without the surface sentinel, Tier 2+ is refused...
            with self.assertRaises(StructuredError) as ctx:
                check_tier2_authorized(inner, root)
            self.assertEqual(ctx.exception.error_category, "tier_interlock")
            self.assertIn("Operator Surface not built", ctx.exception.message)
            # ...and passes once the sentinel is present.
            _enable_operator_surface(root)
            # Should not raise
            check_tier2_authorized(inner, root)

    def test_tier2_no_briefing_file_raises(self):
        policy = _policy(
            active_tier=2,
            briefing_ref="/tmp/definitely/not/a/real/file.md",
            allowed_operations=[{"type": "operation", "change_type": "update",
                                 "trust_level": "safe", "targets": []}],
        )
        with self.assertRaises(StructuredError) as ctx:
            check_tier2_authorized(policy["documenter_policy"], "/tmp")
        self.assertEqual(ctx.exception.error_category, "tier_interlock")
        self.assertIn("briefing file not found", ctx.exception.message)

    def test_tier1_raises_tier_interlock(self):
        policy = _policy(
            active_tier=1,
            briefing_ref="/some/path.md",
            allowed_operations=[{"type": "operation", "change_type": "update",
                                 "trust_level": "safe", "targets": []}],
        )
        with self.assertRaises(StructuredError) as ctx:
            check_tier2_authorized(policy["documenter_policy"], "/")
        self.assertEqual(ctx.exception.error_category, "tier_interlock")
        self.assertIn("active_tier=1 < 2", ctx.exception.message)

    def test_none_policy_raises(self):
        with self.assertRaises(StructuredError) as ctx:
            check_tier2_authorized(None, "/")
        self.assertEqual(ctx.exception.error_category, "tier_interlock")

    def test_null_briefing_ref_raises(self):
        policy = _policy(
            active_tier=2,
            briefing_ref=None,
            allowed_operations=[{"type": "operation", "change_type": "update",
                                 "trust_level": "safe", "targets": []}],
        )
        with self.assertRaises(StructuredError) as ctx:
            check_tier2_authorized(policy["documenter_policy"], "/")
        self.assertEqual(ctx.exception.error_category, "tier_interlock")
        self.assertIn("briefing_ref is null", ctx.exception.message)


class TestCheckTier3Authorized(unittest.TestCase):
    def test_tier3_ok(self):
        with tempfile.TemporaryDirectory() as root:
            bp = os.path.join(root, "_briefing.md")
            with open(bp, "w") as fh:
                fh.write("briefing\n")
            policy = _policy(
                active_tier=3,
                briefing_ref=bp,
                allowed_operations=[{"type": "operation", "change_type": "update",
                                     "trust_level": "safe", "targets": []}],
            )
            _enable_operator_surface(root)
            check_tier3_authorized(policy["documenter_policy"], root)

    def test_tier2_fails_tier3(self):
        with tempfile.TemporaryDirectory() as root:
            bp = os.path.join(root, "_briefing.md")
            with open(bp, "w") as fh:
                fh.write("briefing\n")
            policy = _policy(
                active_tier=2,
                briefing_ref=bp,
                allowed_operations=[{"type": "operation", "change_type": "update",
                                     "trust_level": "safe", "targets": []}],
            )
            _enable_operator_surface(root)
            with self.assertRaises(StructuredError) as ctx:
                check_tier3_authorized(policy["documenter_policy"], root)
            self.assertEqual(ctx.exception.error_category, "tier_interlock")
            self.assertIn("active_tier=2 < 3", ctx.exception.message)


class TestPatternValidation(unittest.TestCase):
    """Per-entry pattern: pattern_id, description, match_criteria, glob chars."""

    def test_pattern_dup_pattern_id(self):
        policy = _policy(
            active_tier=2,
            briefing_ref="b",
            allowed_operations=[
                {
                    "type": "pattern",
                    "pattern_id": "dup-id",
                    "pattern_description": "first",
                    "match_criteria": {"change_type": "update"},
                    "trust_level": "safe",
                },
                {
                    "type": "pattern",
                    "pattern_id": "dup-id",  # duplicate
                    "pattern_description": "second",
                    "match_criteria": {"change_type": "split"},
                    "trust_level": "review",
                },
            ],
        )
        with self.assertRaises(PolicyError) as ctx:
            validate_policy(policy, manifest_ids=MANIFEST_IDS)
        self.assertIn("duplicate pattern_id", ctx.exception.reason)

    def test_pattern_missing_pattern_id(self):
        policy = _policy(
            active_tier=2,
            briefing_ref="b",
            allowed_operations=[
                {
                    "type": "pattern",
                    "pattern_description": "no id",
                    "match_criteria": {"change_type": "update"},
                    "trust_level": "safe",
                },
            ],
        )
        with self.assertRaises(PolicyError) as ctx:
            validate_policy(policy, manifest_ids=MANIFEST_IDS)
        self.assertIn("pattern_id", ctx.exception.reason)

    def test_pattern_invalid_pattern_id_not_kebab(self):
        policy = _policy(
            active_tier=2,
            briefing_ref="b",
            allowed_operations=[
                {
                    "type": "pattern",
                    "pattern_id": "BAD_ID",  # uppercase, underscore
                    "pattern_description": "bad id",
                    "match_criteria": {"change_type": "update"},
                    "trust_level": "safe",
                },
            ],
        )
        with self.assertRaises(PolicyError) as ctx:
            validate_policy(policy, manifest_ids=MANIFEST_IDS)
        self.assertIn("pattern_id", ctx.exception.reason)

    def test_pattern_missing_description(self):
        policy = _policy(
            active_tier=2,
            briefing_ref="b",
            allowed_operations=[
                {
                    "type": "pattern",
                    "pattern_id": "no-desc",
                    "pattern_description": "",  # empty
                    "match_criteria": {"change_type": "update"},
                    "trust_level": "safe",
                },
            ],
        )
        with self.assertRaises(PolicyError) as ctx:
            validate_policy(policy, manifest_ids=MANIFEST_IDS)
        self.assertIn("pattern_description", ctx.exception.reason)

    def test_pattern_missing_match_criteria(self):
        policy = _policy(
            active_tier=2,
            briefing_ref="b",
            allowed_operations=[
                {
                    "type": "pattern",
                    "pattern_id": "no-criteria",
                    "pattern_description": "no criteria",
                    "trust_level": "safe",
                },
            ],
        )
        with self.assertRaises(PolicyError) as ctx:
            validate_policy(policy, manifest_ids=MANIFEST_IDS)
        self.assertIn("match_criteria", ctx.exception.reason)

    def test_pattern_invalid_glob_chars(self):
        policy = _policy(
            active_tier=2,
            briefing_ref="b",
            allowed_operations=[
                {
                    "type": "pattern",
                    "pattern_id": "bad-glob",
                    "pattern_description": "bad glob",
                    "match_criteria": {
                        "change_type": "update",
                        "file_pattern": "docs/**/*.md\n\n",  # newline is invalid
                    },
                    "trust_level": "safe",
                },
            ],
        )
        with self.assertRaises(PolicyError) as ctx:
            validate_policy(policy, manifest_ids=MANIFEST_IDS)
        self.assertIn("file_pattern", ctx.exception.reason)

    def test_pattern_valid_glob_no_file_pattern(self):
        policy = _policy(
            active_tier=2,
            briefing_ref="b",
            allowed_operations=[
                {
                    "type": "pattern",
                    "pattern_id": "any-file",
                    "pattern_description": "matches any",
                    "match_criteria": {"change_type": "update"},
                    "trust_level": "safe",
                },
            ],
        )
        result = validate_policy(policy, manifest_ids=MANIFEST_IDS)
        self.assertEqual(result.get("active_tier"), 2)


class TestRequiresDiffPreviewValidation(unittest.TestCase):
    def test_requires_diff_preview_false_raises(self):
        policy = _policy(
            active_tier=2,
            briefing_ref="b",
            allowed_operations=[
                {
                    "type": "operation",
                    "change_type": "update",
                    "trust_level": "safe",
                    "targets": [],
                    "requires_diff_preview": False,
                },
            ],
        )
        with self.assertRaises(PolicyError) as ctx:
            validate_policy(policy, manifest_ids=MANIFEST_IDS)
        self.assertIn("requires_diff_preview must be true", ctx.exception.reason)

    def test_requires_diff_preview_absent_ok(self):
        policy = _policy(
            active_tier=2,
            briefing_ref="b",
            allowed_operations=[
                {
                    "type": "operation",
                    "change_type": "update",
                    "trust_level": "safe",
                    "targets": [],
                },
            ],
        )
        result = validate_policy(policy, manifest_ids=MANIFEST_IDS)
        self.assertEqual(result.get("active_tier"), 2)


class TestOperatorIdValid(unittest.TestCase):
    def test_operator_id_valid_good(self):
        self.assertTrue(operator_id_valid("op-abc"))
        self.assertTrue(operator_id_valid("op-abc123"))
        self.assertTrue(operator_id_valid("op-foo-bar"))
        self.assertTrue(operator_id_valid("op-1abc"))

    def test_operator_id_valid_bad(self):
        self.assertFalse(operator_id_valid("not-valid"))
        self.assertFalse(operator_id_valid("op-"))
        self.assertFalse(operator_id_valid("op-a"))  # too short (needs 3+ after prefix)
        self.assertFalse(operator_id_valid("OP-abc"))  # uppercase
        self.assertFalse(operator_id_valid("op-1_"))  # underscore


class TestMatchOperation(unittest.TestCase):
    def test_match_operation_change_type(self):
        policy = _policy(
            active_tier=2,
            briefing_ref="b",
            allowed_operations=[
                {"type": "operation", "change_type": "update",
                 "trust_level": "safe", "targets": []},
                {"type": "operation", "change_type": "split",
                 "trust_level": "review", "targets": []},
            ],
        )
        result = validate_policy(policy, manifest_ids=MANIFEST_IDS)
        self.assertIsNotNone(match_operation(result, change_type="update",
                                             target_id="alpha"))
        self.assertIsNotNone(match_operation(result, change_type="split",
                                             target_id="beta"))
        self.assertIsNone(match_operation(result, change_type="create_ru",
                                          target_id="gamma"))

    def test_match_operation_targets_filter(self):
        policy = _policy(
            active_tier=2,
            briefing_ref="b",
            allowed_operations=[
                {"type": "operation", "change_type": "update",
                 "trust_level": "safe", "targets": ["alpha", "beta"]},
            ],
        )
        result = validate_policy(policy, manifest_ids=MANIFEST_IDS)
        self.assertIsNotNone(match_operation(result, change_type="update",
                                             target_id="alpha"))
        self.assertIsNotNone(match_operation(result, change_type="update",
                                             target_id="beta"))
        self.assertIsNone(match_operation(result, change_type="update",
                                          target_id="gamma"))

    def test_match_operation_empty_targets_match_any(self):
        policy = _policy(
            active_tier=2,
            briefing_ref="b",
            allowed_operations=[
                {"type": "operation", "change_type": "update",
                 "trust_level": "safe", "targets": []},
            ],
        )
        result = validate_policy(policy, manifest_ids=MANIFEST_IDS)
        self.assertIsNotNone(match_operation(result, change_type="update",
                                             target_id="any-target"))

    def test_match_operation_none_policy(self):
        self.assertIsNone(match_operation(None, change_type="update",
                                         target_id="x"))


class TestMatchPattern(unittest.TestCase):
    def test_match_pattern_glob_star(self):
        policy = _policy(
            active_tier=2,
            briefing_ref="b",
            allowed_operations=[
                {
                    "type": "pattern",
                    "pattern_id": "star-test",
                    "pattern_description": "star glob",
                    "match_criteria": {
                        "change_type": "update",
                        "file_pattern": "docs/*.md",
                    },
                    "trust_level": "safe",
                },
            ],
        )
        result = validate_policy(policy, manifest_ids=MANIFEST_IDS)
        self.assertIsNotNone(match_pattern(result, change_type="update",
                                           rel_path="docs/foo.md"))
        self.assertIsNotNone(match_pattern(result, change_type="update",
                                           rel_path="docs/bar.md"))
        self.assertIsNone(match_pattern(result, change_type="update",
                                        rel_path="src/foo.md"))

    def test_match_pattern_double_star(self):
        policy = _policy(
            active_tier=2,
            briefing_ref="b",
            allowed_operations=[
                {
                    "type": "pattern",
                    "pattern_id": "double-star",
                    "pattern_description": "recursive",
                    "match_criteria": {
                        "change_type": "create_ru",
                        "file_pattern": "**/index.md",
                    },
                    "trust_level": "review",
                },
            ],
        )
        result = validate_policy(policy, manifest_ids=MANIFEST_IDS)
        self.assertIsNotNone(match_pattern(result, change_type="create_ru",
                                           rel_path="a/b/index.md"))
        self.assertIsNotNone(match_pattern(result, change_type="create_ru",
                                           rel_path="index.md"))

    def test_match_pattern_empty_pattern_matches_any(self):
        policy = _policy(
            active_tier=2,
            briefing_ref="b",
            allowed_operations=[
                {
                    "type": "pattern",
                    "pattern_id": "match-any",
                    "pattern_description": "match any file",
                    "match_criteria": {"change_type": "update"},
                    "trust_level": "safe",
                },
            ],
        )
        result = validate_policy(policy, manifest_ids=MANIFEST_IDS)
        self.assertIsNotNone(match_pattern(result, change_type="update",
                                           rel_path="anything.txt"))

    def test_match_pattern_none_policy(self):
        self.assertIsNone(match_pattern(None, change_type="update",
                                        rel_path="x"))

    def test_match_pattern_change_type_mismatch(self):
        policy = _policy(
            active_tier=2,
            briefing_ref="b",
            allowed_operations=[
                {
                    "type": "pattern",
                    "pattern_id": "ptn",
                    "pattern_description": "update only",
                    "match_criteria": {"change_type": "update"},
                    "trust_level": "safe",
                },
            ],
        )
        result = validate_policy(policy, manifest_ids=MANIFEST_IDS)
        self.assertIsNone(match_pattern(result, change_type="split",
                                        rel_path="docs/x.md"))


if __name__ == "__main__":
    unittest.main()
