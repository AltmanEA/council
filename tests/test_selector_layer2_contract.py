"""Contract tests for the Selector Layer 2 output schema.

Test groups:
  (a) TestLayer2Additivity       — all 9 legacy + 6 new fields present in fixtures.
  (b) TestValidateOutputV2       — validate_output_v2 on valid/truncated returns [].
  (c) TestEmptyFactsRestriction  — empty facts rejected unless gap_type in permitted set.
  (d) TestFactSources            — every fact has >= 1 source.
  (e) TestConstitutionalFields   — contract_version, form, interim_form are consts.
  (f) TestAdditiveGapKeys        — gap has additive Layer 2 keys.

Uses unittest + stdlib only. Fixture JSON read directly. Module loaded via importlib.
"""
import importlib.util
import json
import os
import unittest

import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]

FIXTURE_DIR = str(_ROOT / ".agents" / "skills" / "selector" / "fixtures")
CONTRACT_DIR = str(_ROOT / ".agents" / "skills" / "selector" / "contract")

OUTPUT_L2_VALID = os.path.join(FIXTURE_DIR, "output.layer2.valid.json")
OUTPUT_L2_TRUNCATED = os.path.join(FIXTURE_DIR, "output.layer2.truncated.json")
SCHEMA_L2 = os.path.join(CONTRACT_DIR, "output.layer2.schema.json")


# ── 9 legacy fields (must survive into Layer 2) ──────────────────────────
LEGACY_KEYS = {
    "task_summary",
    "ranked_ids",
    "disclaimer",
    "discoverable",
    "interim_form",
    "gap",
    "hint_acknowledgement",
    "truncated",
    "manifest_sha256",
}

# ── 6 new Layer 2 fields ─────────────────────────────────────────────────
NEW_KEYS = {
    "contract_version",
    "form",
    "facts",
    "sources",
    "modes",
    "integrity",
}

# ── Gap additive keys introduced in Layer 2 ──────────────────────────────
L2_GAP_KEYS = {
    "gap_type",
    "searched_sources",
    "covered_items",
    "omitted_items",
    "excluded_paths",
    "code_paths_searched",
}


def _read_json(path):
    """Read a JSON file and return the parsed object."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_layer2():
    """Load selector_layer2 module via importlib (may fail if not yet implemented)."""
    layer2_path = str(_ROOT / ".agents" / "skills" / "selector" / "layer2" / "selector_layer2.py")
    spec = importlib.util.spec_from_file_location(
        "selector_layer2",
        layer2_path,
        submodule_search_locations=[str(_ROOT / ".agents" / "skills" / "selector" / "layer2")],
    )
    if spec is None or spec.loader is None:
        raise ImportError(
            f"Layer 2 module not found at {layer2_path}"
        )
    module = importlib.util.module_from_spec(spec)
    os.sys.modules["selector_layer2"] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# (a) TestLayer2Additivity — all 9 legacy + 6 new fields present
# ---------------------------------------------------------------------------

class TestLayer2Additivity(unittest.TestCase):
    """Both valid and truncated fixtures must contain all 9 legacy + 6 new fields."""

    @classmethod
    def setUpClass(cls):
        cls.valid = _read_json(OUTPUT_L2_VALID)
        cls.truncated = _read_json(OUTPUT_L2_TRUNCATED)

    def test_valid_has_all_legacy_keys(self):
        """output.layer2.valid.json must contain all 9 legacy fields."""
        missing = LEGACY_KEYS - set(self.valid.keys())
        self.assertEqual(len(missing), 0, f"Missing legacy keys: {missing}")

    def test_valid_has_all_new_keys(self):
        """output.layer2.valid.json must contain all 6 new Layer 2 fields."""
        missing = NEW_KEYS - set(self.valid.keys())
        self.assertEqual(len(missing), 0, f"Missing new keys: {missing}")

    def test_valid_has_no_extra_top_keys(self):
        """Valid output must not contain extra top-level keys beyond 9+6."""
        expected = LEGACY_KEYS | NEW_KEYS
        extra = set(self.valid.keys()) - expected
        self.assertEqual(len(extra), 0, f"Unexpected extra keys: {extra}")

    def test_truncated_has_all_legacy_keys(self):
        """output.layer2.truncated.json must contain all 9 legacy fields."""
        missing = LEGACY_KEYS - set(self.truncated.keys())
        self.assertEqual(len(missing), 0, f"Missing legacy keys: {missing}")

    def test_truncated_has_all_new_keys(self):
        """output.layer2.truncated.json must contain all 6 new Layer 2 fields."""
        missing = NEW_KEYS - set(self.truncated.keys())
        self.assertEqual(len(missing), 0, f"Missing new keys: {missing}")

    def test_both_share_same_keys(self):
        """Valid and truncated fixtures must have identical key sets."""
        self.assertEqual(set(self.valid.keys()), set(self.truncated.keys()))


# ---------------------------------------------------------------------------
# (b) TestValidateOutputV2 — validate_output_v2 on fixtures returns []
# ---------------------------------------------------------------------------

class TestValidateOutputV2(unittest.TestCase):
    """validate_output_v2(valid) and validate_output_v2(truncated) must return []."""

    @classmethod
    def setUpClass(cls):
        cls.valid = _read_json(OUTPUT_L2_VALID)
        cls.truncated = _read_json(OUTPUT_L2_TRUNCATED)
        try:
            cls.layer2 = _load_layer2()
        except ImportError:
            cls.layer2 = None

    def test_validate_valid_fixture_is_empty(self):
        """validate_output_v2 on output.layer2.valid.json must return []."""
        if self.layer2 is None:
            self.fail("Layer 2 module not yet implemented — cannot call validate_output_v2")
        errors = self.layer2.validate_output_v2(self.valid)
        self.assertEqual(errors, [], f"Valid fixture must produce zero errors, got: {errors}")

    def test_validate_truncated_fixture_is_empty(self):
        """validate_output_v2 on output.layer2.truncated.json must return []."""
        if self.layer2 is None:
            self.fail("Layer 2 module not yet implemented — cannot call validate_output_v2")
        errors = self.layer2.validate_output_v2(self.truncated)
        self.assertEqual(errors, [], f"Truncated fixture must produce zero errors, got: {errors}")


# ---------------------------------------------------------------------------
# (c) TestEmptyFactsRestriction — empty facts rejected outside permitted gap_type
# ---------------------------------------------------------------------------

class TestEmptyFactsRestriction(unittest.TestCase):
    """Empty facts array must be rejected unless gap_type is one of the permitted values."""

    @classmethod
    def setUpClass(cls):
        cls.valid = _read_json(OUTPUT_L2_VALID)
        cls.truncated = _read_json(OUTPUT_L2_TRUNCATED)
        try:
            cls.layer2 = _load_layer2()
        except ImportError:
            cls.layer2 = None

    PERMITTED_EMPTY_GAPS = {"not_found", "manifest_missing", "scope_limited"}

    def test_empty_facts_allowed_for_not_found(self):
        """Empty facts must be accepted when gap_type='not_found'."""
        output = dict(self.valid)
        output["facts"] = []
        output["gap"] = dict(output["gap"])
        output["gap"]["gap_type"] = "not_found"
        output["gap"]["omitted_items"] = []
        output["gap"]["covered_items"] = []
        output["ranked_ids"] = {}
        if self.layer2 is None:
            self.fail("Layer 2 module not yet implemented")
        errors = self.layer2.validate_output_v2(output)
        self.assertEqual(errors, [], "Empty facts with not_found must be valid")

    def test_empty_facts_allowed_for_manifest_missing(self):
        """Empty facts must be accepted when gap_type='manifest_missing'."""
        output = dict(self.valid)
        output["facts"] = []
        output["gap"] = dict(output["gap"])
        output["gap"]["gap_type"] = "manifest_missing"
        output["gap"]["omitted_items"] = []
        output["gap"]["covered_items"] = []
        output["ranked_ids"] = {}
        if self.layer2 is None:
            self.fail("Layer 2 module not yet implemented")
        errors = self.layer2.validate_output_v2(output)
        self.assertEqual(errors, [], "Empty facts with manifest_missing must be valid")

    def test_empty_facts_allowed_for_scope_limited(self):
        """Empty facts must be accepted when gap_type='scope_limited'."""
        output = dict(self.valid)
        output["facts"] = []
        output["gap"] = dict(output["gap"])
        output["gap"]["gap_type"] = "scope_limited"
        if self.layer2 is None:
            self.fail("Layer 2 module not yet implemented")
        errors = self.layer2.validate_output_v2(output)
        self.assertEqual(errors, [], "Empty facts with scope_limited must be valid")

    def test_empty_facts_rejected_for_partial(self):
        """Empty facts must be rejected when gap_type='partial'."""
        output = dict(self.valid)
        output["facts"] = []
        if self.layer2 is None:
            self.fail("Layer 2 module not yet implemented")
        errors = self.layer2.validate_output_v2(output)
        self.assertNotEqual(errors, [], "Empty facts with partial must produce validation errors")

    def test_empty_facts_rejected_for_budget_stop(self):
        """Empty facts must be rejected when gap_type='budget_stop'."""
        output = dict(self.truncated)
        output["facts"] = []
        if self.layer2 is None:
            self.fail("Layer 2 module not yet implemented")
        errors = self.layer2.validate_output_v2(output)
        self.assertNotEqual(errors, [], "Empty facts with budget_stop must produce validation errors")

    def test_empty_facts_rejected_for_none(self):
        """Empty facts must be rejected when gap_type='none'."""
        output = dict(self.valid)
        output["facts"] = []
        output["gap"] = dict(output["gap"])
        output["gap"]["gap_type"] = "none"
        if self.layer2 is None:
            self.fail("Layer 2 module not yet implemented")
        errors = self.layer2.validate_output_v2(output)
        self.assertNotEqual(errors, [], "Empty facts with none must produce validation errors")


# ---------------------------------------------------------------------------
# (d) TestFactSources — every fact has >= 1 source
# ---------------------------------------------------------------------------

class TestFactSources(unittest.TestCase):
    """Every fact in the output must have at least one source in its sources array."""

    @classmethod
    def setUpClass(cls):
        cls.valid = _read_json(OUTPUT_L2_VALID)
        cls.truncated = _read_json(OUTPUT_L2_TRUNCATED)

    def test_valid_facts_all_have_sources(self):
        """All facts in valid fixture must have non-empty sources arrays."""
        facts = self.valid.get("facts", [])
        for i, fact in enumerate(facts):
            sources = fact.get("sources", [])
            self.assertGreater(len(sources), 0, f"Fact {i} must have >= 1 source")

    def test_truncated_facts_all_have_sources(self):
        """All facts in truncated fixture must have non-empty sources arrays."""
        facts = self.truncated.get("facts", [])
        for i, fact in enumerate(facts):
            sources = fact.get("sources", [])
            self.assertGreater(len(sources), 0, f"Fact {i} must have >= 1 source")

    def test_facts_have_claim_and_status(self):
        """Each fact must have 'claim' and 'status' fields."""
        for name, fixture in [("valid", self.valid), ("truncated", self.truncated)]:
            for i, fact in enumerate(fixture.get("facts", [])):
                self.assertIn("claim", fact, f"Fact {i} in {name} must have 'claim'")
                self.assertIn("status", fact, f"Fact {i} in {name} must have 'status'")


# ---------------------------------------------------------------------------
# (e) TestConstitutionalFields — const values for version, form, interim_form
# ---------------------------------------------------------------------------

class TestConstitutionalFields(unittest.TestCase):
    """contract_version='2.0.0', form='Layer 2', interim_form='Layer 1'."""

    @classmethod
    def setUpClass(cls):
        cls.valid = _read_json(OUTPUT_L2_VALID)
        cls.truncated = _read_json(OUTPUT_L2_TRUNCATED)

    def test_valid_contract_version(self):
        self.assertEqual(self.valid.get("contract_version"), "2.0.0")

    def test_valid_form(self):
        self.assertEqual(self.valid.get("form"), "Layer 2")

    def test_valid_interim_form(self):
        self.assertEqual(self.valid.get("interim_form"), "Layer 1")

    def test_truncated_contract_version(self):
        self.assertEqual(self.truncated.get("contract_version"), "2.0.0")

    def test_truncated_form(self):
        self.assertEqual(self.truncated.get("form"), "Layer 2")

    def test_truncated_interim_form(self):
        self.assertEqual(self.truncated.get("interim_form"), "Layer 1")

    def test_interim_form_not_layer2(self):
        """interim_form must remain 'Layer 1' (legacy), not 'Layer 2'."""
        self.assertEqual(self.valid.get("interim_form"), "Layer 1")
        self.assertNotEqual(self.valid.get("interim_form"), "Layer 2")


# ---------------------------------------------------------------------------
# (f) TestSchemaStructure — L2 schema declares new fields
# ---------------------------------------------------------------------------

class TestSchemaStructure(unittest.TestCase):
    """output.layer2.schema.json exists and declares new L2 fields."""

    def test_schema_file_exists(self):
        self.assertTrue(os.path.isfile(SCHEMA_L2), f"Schema not found: {SCHEMA_L2}")

    def test_schema_is_object(self):
        schema = _read_json(SCHEMA_L2)
        self.assertIsInstance(schema, dict)

    def test_schema_declares_contract_version(self):
        """Schema must declare contract_version property."""
        schema = _read_json(SCHEMA_L2)
        self.assertIn("contract_version", schema.get("properties", {}))

    def test_schema_declares_form(self):
        """Schema must declare form property."""
        schema = _read_json(SCHEMA_L2)
        self.assertIn("form", schema.get("properties", {}))

    def test_schema_declares_facts(self):
        """Schema must declare facts property."""
        schema = _read_json(SCHEMA_L2)
        self.assertIn("facts", schema.get("properties", {}))

    def test_schema_declares_sources(self):
        """Schema must declare sources property."""
        schema = _read_json(SCHEMA_L2)
        self.assertIn("sources", schema.get("properties", {}))

    def test_schema_declares_modes(self):
        """Schema must declare modes property."""
        schema = _read_json(SCHEMA_L2)
        self.assertIn("modes", schema.get("properties", {}))

    def test_schema_declares_integrity(self):
        """Schema must declare integrity property."""
        schema = _read_json(SCHEMA_L2)
        self.assertIn("integrity", schema.get("properties", {}))

    def test_schema_contract_version_is_const(self):
        schema = _read_json(SCHEMA_L2)
        cv = schema["properties"].get("contract_version", {})
        self.assertEqual(cv.get("const"), "2.0.0", "contract_version must be const '2.0.0'")

    def test_schema_form_is_const(self):
        schema = _read_json(SCHEMA_L2)
        f = schema["properties"].get("form", {})
        self.assertEqual(f.get("const"), "Layer 2", "form must be const 'Layer 2'")


# ---------------------------------------------------------------------------
# (g) TestAdditiveGapKeys — gap contains L2 additive keys
# ---------------------------------------------------------------------------

class TestAdditiveGapKeys(unittest.TestCase):
    """gap must contain the Layer 2 additive keys: excluded_paths, code_paths_searched."""

    @classmethod
    def setUpClass(cls):
        cls.valid = _read_json(OUTPUT_L2_VALID)
        cls.truncated = _read_json(OUTPUT_L2_TRUNCATED)

    def test_valid_gap_has_additive_keys(self):
        """Valid output gap must have all L2 additive keys."""
        gap = self.valid.get("gap", {})
        missing = L2_GAP_KEYS - set(gap.keys())
        self.assertEqual(len(missing), 0, f"Missing gap keys: {missing}")

    def test_truncated_gap_has_additive_keys(self):
        """Truncated output gap must have all L2 additive keys."""
        gap = self.truncated.get("gap", {})
        missing = L2_GAP_KEYS - set(gap.keys())
        self.assertEqual(len(missing), 0, f"Missing gap keys: {missing}")


if __name__ == "__main__":
    unittest.main()
