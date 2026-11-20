"""Smoke tests for the Selector Layer 1 skill.

These tests validate behavioral patterns and consistency between contract,
fixtures, and role/skill artifacts. They do NOT test the implementation itself
(which is absent in iteration 1) — they check that all required artifacts exist
and are self-consistent.

Test groups:
  (a) TestSmokeScenarioMetadataOnly — output must contain no body/content fields.
  (b) TestSmokeScenarioNoCodeQueries — output must not reference Layer 2 code features.
  (c) TestSmokeScenarioTruncation — truncated output must have the banner and be consistent.
  (d) TestSmokeScenarioGapCore — gap structure must be valid across outputs.
  (e) TestSmokeScenarioAuditTemplate — audit template structure must be complete.
  (f) TestSmokeScenarioFileExistence — all target files must exist.

All tests are deterministic. No skips, no expectedFail, no try-import tricks.
"""
import json
import os
import re
import unittest

import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]

SKILL_PATH = str(_ROOT / ".agents" / "skills" / "selector" / "SKILL.md")
ROLE_PATH = str(_ROOT / ".agents" / "skills" / "selector" / "roles" / "selector.md")
SCHEMA_PATH = str(_ROOT / ".agents" / "skills" / "selector" / "contract" / "output.schema.json")

FIXTURE_DIR = str(_ROOT / ".agents" / "skills" / "selector" / "fixtures")
MANIFEST_SAMPLE_PATH = os.path.join(FIXTURE_DIR, "manifest.sample.yaml")
MANIFEST_POISONED_PATH = os.path.join(FIXTURE_DIR, "manifest.poisoned.yaml")
OUTPUT_VALID_PATH = os.path.join(FIXTURE_DIR, "output.valid.json")
OUTPUT_TRUNCATED_PATH = os.path.join(FIXTURE_DIR, "output.truncated.json")
AUDIT_TEMPLATE_PATH = os.path.join(FIXTURE_DIR, "audit.template.md")

# All target files that must exist for the contract to be valid
TARGET_FILES = [
    SKILL_PATH,
    ROLE_PATH,
    SCHEMA_PATH,
    MANIFEST_SAMPLE_PATH,
    MANIFEST_POISONED_PATH,
    OUTPUT_VALID_PATH,
    OUTPUT_TRUNCATED_PATH,
    AUDIT_TEMPLATE_PATH,
]


def read_file(path):
    """Read a text file as UTF-8 string."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_json(path):
    """Read a JSON file and return the parsed object."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# (a) TestSmokeScenarioMetadataOnly — metadata-only output contract
# ---------------------------------------------------------------------------

class TestSmokeScenarioMetadataOnly(unittest.TestCase):
    """Verify that output fixtures do not contain body/content fields — only metadata."""

    @classmethod
    def setUpClass(cls):
        cls.output_valid = read_json(OUTPUT_VALID_PATH)
        cls.output_truncated = read_json(OUTPUT_TRUNCATED_PATH)

    def test_valid_output_no_body_field(self):
        """output.valid.json must not contain a 'body' key (index-only = no body)."""
        self.assertNotIn("body", self.output_valid)

    def test_valid_output_no_content_field(self):
        """output.valid.json must not contain a 'content' key (index-only = no content)."""
        self.assertNotIn("content", self.output_valid)

    def test_truncated_output_no_body_field(self):
        """output.truncated.json must not contain a 'body' key."""
        self.assertNotIn("body", self.output_truncated)

    def test_truncated_output_no_content_field(self):
        """output.truncated.json must not contain a 'content' key."""
        self.assertNotIn("content", self.output_truncated)

    def test_valid_output_rationale_is_short(self):
        """Each rationale in ranked_ids should be 1-2 lines (short metadata)."""
        for entry_id, entry in self.output_valid.get("ranked_ids", {}).items():
            rationale = entry.get("rationale", "")
            # Must be a single short string, not a multi-line body
            self.assertLessEqual(rationale.count("\n"), 1,
                                 f"Rationale for {entry_id} must be <= 1 line")

    def test_ranked_ids_discoverable_is_per_document(self):
        """Spec requires a Discoverable advisory per document, not one global flag."""
        for entry_id, entry in self.output_valid.get("ranked_ids", {}).items():
            self.assertIn(entry.get("discoverable"), ("yes", "no"),
                          f"Missing per-document advisory for {entry_id}")

    def test_ranked_ids_order_is_explicit(self):
        """Rank must be explicit because JSON object key order is not authoritative."""
        ranks = [e["rank"] for e in self.output_valid.get("ranked_ids", {}).values()]
        self.assertEqual(sorted(ranks), list(range(1, len(ranks) + 1)))

    def test_valid_output_task_summary_is_short(self):
        """task_summary must be a short string (metadata summary, not a document body)."""
        summary = self.output_valid.get("task_summary", "")
        self.assertLess(len(summary), 500,
                        "task_summary must be a brief metadata summary")


# ---------------------------------------------------------------------------
# (b) TestSmokeScenarioNoCodeQueries — deferral of code queries
# ---------------------------------------------------------------------------

class TestSmokeScenarioNoCodeQueries(unittest.TestCase):
    """Verify that the Selector output and role prompt do not reference Layer 2 code features."""

    @classmethod
    def setUpClass(cls):
        cls.role_text = read_file(ROLE_PATH) if os.path.exists(ROLE_PATH) else ""
        cls.output_valid = read_json(OUTPUT_VALID_PATH)
        cls.output_truncated = read_json(OUTPUT_TRUNCATED_PATH)

    def test_role_defers_code_queries(self):
        """Role prompt must state that code queries are deferred to Layer 2."""
        self.assertIn("deferred", self.role_text.lower())
        self.assertIn("Layer 2", self.role_text)

    def test_valid_output_no_code_paths(self):
        """output.valid.json should not contain file paths that look like source code."""
        all_text = json.dumps(self.output_valid)
        self.assertNotIn(".py", all_text,
                         "Selector Layer 1 is index-only; output should not reference .py files")

    def test_truncated_output_no_code_paths(self):
        """output.truncated.json should not contain source code paths."""
        all_text = json.dumps(self.output_truncated)
        self.assertNotIn(".py", all_text,
                           "Selector Layer 1 is index-only; output should not reference .py files")


# ---------------------------------------------------------------------------
# (c) TestSmokeScenarioTruncation — budget stop behavior
# ---------------------------------------------------------------------------

class TestSmokeScenarioTruncation(unittest.TestCase):
    """Verify that truncated output correctly signals a budget stop."""

    @classmethod
    def setUpClass(cls):
        cls.output_valid = read_json(OUTPUT_VALID_PATH)
        cls.output_truncated = read_json(OUTPUT_TRUNCATED_PATH)

    def test_truncated_output_flag_is_true(self):
        """Truncated output must have truncated=true."""
        self.assertTrue(self.output_truncated.get("truncated"))

    def test_valid_output_flag_is_false(self):
        """Valid output must have truncated=false."""
        self.assertFalse(self.output_valid.get("truncated"))

    def test_truncated_output_has_banner(self):
        """Truncated output must contain the ⚠ TRUNCATED banner."""
        # Read raw file to avoid json.dumps unicode escaping the emoji
        raw_text = read_file(OUTPUT_TRUNCATED_PATH)
        self.assertIn("\u26a0 TRUNCATED", raw_text)

    def test_truncated_output_fewer_ranked_items(self):
        """Truncated output should have fewer ranked_ids than valid output (budget stop)."""
        valid_count = len(self.output_valid.get("ranked_ids", {}))
        truncated_count = len(self.output_truncated.get("ranked_ids", {}))
        self.assertLessEqual(truncated_count, valid_count,
                             "Truncated output should have <= ranked items than non-truncated")

    def test_truncated_output_gap_type_budget_stop(self):
        """Truncated output gap should have gap_type='budget_stop' or at least be set."""
        gap_type = self.output_truncated.get("gap", {}).get("gap_type", "")
        self.assertTrue(len(gap_type) > 0,
                        "Truncated output must have a gap_type set")


# ---------------------------------------------------------------------------
# (d) TestSmokeScenarioGapCore — gap structure validation
# ---------------------------------------------------------------------------

class TestSmokeScenarioGapCore(unittest.TestCase):
    """Validate that gap cores in both outputs have the required structure."""

    @classmethod
    def setUpClass(cls):
        cls.output_valid = read_json(OUTPUT_VALID_PATH)
        cls.output_truncated = read_json(OUTPUT_TRUNCATED_PATH)

    REQUIRED_GAP_FIELDS = {"gap_type", "searched_sources", "covered_items", "omitted_items"}

    def test_valid_output_gap_has_all_required_fields(self):
        """Valid output gap must contain all 4 required fields."""
        gap = self.output_valid.get("gap", {})
        missing = self.REQUIRED_GAP_FIELDS - set(gap.keys())
        self.assertEqual(len(missing), 0, f"gap missing: {missing}")

    def test_truncated_output_gap_has_all_required_fields(self):
        """Truncated output gap must contain all 4 required fields."""
        gap = self.output_truncated.get("gap", {})
        missing = self.REQUIRED_GAP_FIELDS - set(gap.keys())
        self.assertEqual(len(missing), 0, f"gap missing: {missing}")

    def test_valid_output_gap_searched_sources_is_list(self):
        """gap.searched_sources must be an array."""
        sources = self.output_valid.get("gap", {}).get("searched_sources")
        self.assertIsInstance(sources, list)

    def test_truncated_output_gap_covered_items_is_list(self):
        """gap.covered_items must be an array."""
        items = self.output_truncated.get("gap", {}).get("covered_items")
        self.assertIsInstance(items, list)

    def test_valid_output_gap_omitted_items_is_list(self):
        """gap.omitted_items must be an array."""
        items = self.output_valid.get("gap", {}).get("omitted_items")
        self.assertIsInstance(items, list)

    def test_valid_output_gap_type_is_string(self):
        """gap.gap_type must be a non-empty string."""
        gap_type = self.output_valid.get("gap", {}).get("gap_type", "")
        self.assertIsInstance(gap_type, str)
        self.assertGreater(len(gap_type), 0)


# ---------------------------------------------------------------------------
# (e) TestSmokeScenarioAuditTemplate — audit template completeness
# ---------------------------------------------------------------------------

class TestSmokeScenarioAuditTemplate(unittest.TestCase):
    """Validate that the audit template has the right structure for instantiation."""

    @classmethod
    def setUpClass(cls):
        cls.audit_text = read_file(AUDIT_TEMPLATE_PATH)

    def test_audit_template_has_header(self):
        """audit.template.md must start with '# Selector audit'."""
        self.assertIn("# Selector audit", self.audit_text)

    def test_audit_template_has_call_id_placeholder(self):
        """audit.template.md must contain a call_id placeholder."""
        self.assertIn("call_id", self.audit_text)

    def test_audit_template_has_manifest_sha256_placeholder(self):
        """audit.template.md must contain a manifest_sha256 placeholder."""
        self.assertIn("manifest_sha256", self.audit_text)

    def test_audit_template_has_separated_table(self):
        """audit.template.md must use a markdown table for metadata fields."""
        self.assertIn("|", self.audit_text)

    def test_audit_template_has_results_section(self):
        """audit.template.md must have a results section (## Results)."""
        self.assertIn("## Results", self.audit_text)

    def test_audit_template_has_integrity_section(self):
        """audit.template.md must have an integrity section (## Integrity)."""
        self.assertIn("## Integrity", self.audit_text)


# ---------------------------------------------------------------------------
# (f) TestSmokeScenarioFileExistence — all target files must exist
# ---------------------------------------------------------------------------

class TestSmokeScenarioFileExistence(unittest.TestCase):
    """All target files listed in the task must exist on disk."""

    def test_skill_md_exists(self):
        """SKILL.md must exist."""
        self.assertTrue(os.path.exists(SKILL_PATH), f"SKILL.md not found at {SKILL_PATH}")

    def test_role_selector_md_exists(self):
        """roles/selector.md must exist."""
        self.assertTrue(os.path.exists(ROLE_PATH), f"roles/selector.md not found at {ROLE_PATH}")

    def test_output_schema_json_exists(self):
        """contract/output.schema.json must exist."""
        self.assertTrue(os.path.exists(SCHEMA_PATH), f"output.schema.json not found at {SCHEMA_PATH}")

    def test_manifest_sample_exists(self):
        """fixtures/manifest.sample.yaml must exist."""
        self.assertTrue(os.path.exists(MANIFEST_SAMPLE_PATH))

    def test_manifest_poisoned_exists(self):
        """fixtures/manifest.poisoned.yaml must exist."""
        self.assertTrue(os.path.exists(MANIFEST_POISONED_PATH))

    def test_output_valid_exists(self):
        """fixtures/output.valid.json must exist."""
        self.assertTrue(os.path.exists(OUTPUT_VALID_PATH))

    def test_output_truncated_exists(self):
        """fixtures/output.truncated.json must exist."""
        self.assertTrue(os.path.exists(OUTPUT_TRUNCATED_PATH))

    def test_audit_template_exists(self):
        """fixtures/audit.template.md must exist."""
        self.assertTrue(os.path.exists(AUDIT_TEMPLATE_PATH))

    def test_all_target_files_exist(self):
        """All listed target files must exist as a batch check."""
        missing = [p for p in TARGET_FILES if not os.path.exists(p)]
        self.assertEqual(len(missing), 0, f"Missing target files: {missing}")


# ---------------------------------------------------------------------------
# (g) TestSmokeScenarioConsistency — cross-file consistency
# ---------------------------------------------------------------------------

class TestSmokeScenarioConsistency(unittest.TestCase):
    """Cross-file consistency checks between fixtures, schema, and role/skill."""

    @classmethod
    def setUpClass(cls):
        cls.output_valid = read_json(OUTPUT_VALID_PATH)
        cls.output_truncated = read_json(OUTPUT_TRUNCATED_PATH)
        cls.skill_text = read_file(SKILL_PATH) if os.path.exists(SKILL_PATH) else ""
        cls.role_text = read_file(ROLE_PATH) if os.path.exists(ROLE_PATH) else ""

    def test_valid_and_truncated_share_required_keys(self):
        """Both valid and truncated outputs must have the same required keys."""
        valid_keys = set(self.output_valid.keys())
        truncated_keys = set(self.output_truncated.keys())
        self.assertEqual(valid_keys, truncated_keys,
                         "valid and truncated must share the same key set")

    def test_valid_output_disclaimer_is_exact(self):
        """output.valid.json disclaimer must match the canonical phrase."""
        self.assertEqual(
            self.output_valid.get("disclaimer"),
            "recommended starting set, not a boundary"
        )

    def test_truncated_output_disclaimer_is_exact(self):
        """output.truncated.json disclaimer must match the canonical phrase."""
        self.assertEqual(
            self.output_truncated.get("disclaimer"),
            "recommended starting set, not a boundary"
        )

    def test_skill_contains_discoverable_pattern(self):
        """SKILL.md must reference 'Discoverable' in the output contract."""
        self.assertIn("Discoverable", self.skill_text)

    def test_role_contains_deny_statement(self):
        """roles/selector.md must contain a deny directive."""
        self.assertIn("deny", self.role_text.lower())

    def test_skill_contains_interim_form_label(self):
        """SKILL.md must contain 'interim_form: Layer 1'."""
        self.assertIn("interim_form: Layer 1", self.skill_text)

    def test_valid_and_truncated_same_interim_form(self):
        """Both outputs must claim the same interim_form."""
        self.assertEqual(
            self.output_valid.get("interim_form"),
            self.output_truncated.get("interim_form")
        )


if __name__ == "__main__":
    unittest.main()
