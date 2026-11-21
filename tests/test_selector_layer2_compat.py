"""Compatibility tests: Layer 1 runtime.validate_output must accept Layer 2 output.

Layer 1 validate_output() checks only the presence of its mandatory keys and the
structure of gap / ranked_ids; new fields do not cause rejection.  These tests
verify that a Layer 2 output passes Layer 1's validator without modification.

Uses unittest + stdlib only.  Runtime loaded via importlib.
"""
import importlib.util
import json
import os
import unittest

import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Layer 1 runtime path (already present in the repo)
_RUNTIME_DIR = _ROOT / ".agents" / "skills" / "selector" / "runtime"
_RUNTIME_PATH = str(_RUNTIME_DIR / "selector_runtime.py")

_FIXTURE_DIR = str(_ROOT / ".agents" / "skills" / "selector" / "fixtures")
_OUTPUT_L2_VALID = os.path.join(_FIXTURE_DIR, "output.layer2.valid.json")
_OUTPUT_L2_TRUNCATED = os.path.join(_FIXTURE_DIR, "output.layer2.truncated.json")


def _load_runtime():
    """Load selector_runtime module via importlib."""
    spec = importlib.util.spec_from_file_location("selector_runtime", _RUNTIME_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(
            f"Layer 1 runtime not found at {_RUNTIME_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path):
    """Read a JSON file and return the parsed object."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# TestLayer1Compat — Layer 1 validate_output accepts Layer 2 output
# ---------------------------------------------------------------------------

class TestLayer1Compat(unittest.TestCase):
    """Layer 1 validate_output must accept Layer 2 output without changes."""

    @classmethod
    def setUpClass(cls):
        cls.runtime = _load_runtime()
        cls.valid = _read_json(_OUTPUT_L2_VALID)
        cls.truncated = _read_json(_OUTPUT_L2_TRUNCATED)

    def test_l2_valid_passes_l1_validator(self):
        """Layer 2 valid output must pass Layer 1 validate_output with zero errors."""
        errors = self.runtime.validate_output(self.valid)
        self.assertEqual(
            errors, [],
            f"Layer 1 validator rejected L2 valid output: {errors}",
        )

    def test_l2_truncated_passes_l1_validator(self):
        """Layer 2 truncated output must pass Layer 1 validate_output with zero errors."""
        errors = self.runtime.validate_output(self.truncated)
        self.assertEqual(
            errors, [],
            f"Layer 1 validator rejected L2 truncated output: {errors}",
        )

    def test_layer1_ignores_extra_fields(self):
        """Layer 1 validator must not reject output with additional keys."""
        extra = {"contract_version": "2.0.0", "form": "Layer 2"}
        output = dict(self.valid)
        output.update(extra)
        errors = self.runtime.validate_output(output)
        self.assertEqual(errors, [], "L1 validator must not reject extra fields")


# ---------------------------------------------------------------------------
# TestRankPreservation — ranked_ids preserves rank/discoverable/status
# ---------------------------------------------------------------------------

class TestRankPreservation(unittest.TestCase):
    """Layer 2 output must preserve rank, discoverable, status in ranked_ids."""

    @classmethod
    def setUpClass(cls):
        cls.valid = _read_json(_OUTPUT_L2_VALID)

    def test_ranked_ids_have_id(self):
        """Each ranked_ids entry must have 'id' field."""
        for eid, entry in self.valid.get("ranked_ids", {}).items():
            self.assertIn("id", entry, f"ranked_ids[{eid}] missing 'id'")

    def test_ranked_ids_have_rank(self):
        """Each ranked_ids entry must have 'rank' field."""
        for eid, entry in self.valid.get("ranked_ids", {}).items():
            self.assertIn("rank", entry, f"ranked_ids[{eid}] missing 'rank'")
            self.assertIsInstance(entry["rank"], int, f"rank must be int for {eid}")

    def test_ranked_ids_have_discoverable(self):
        """Each ranked_ids entry must have 'discoverable' field."""
        for eid, entry in self.valid.get("ranked_ids", {}).items():
            self.assertIn("discoverable", entry)
            self.assertIn(entry["discoverable"], ("yes", "no"))

    def test_ranked_ids_have_status(self):
        """Each ranked_ids entry must have 'status' field."""
        for eid, entry in self.valid.get("ranked_ids", {}).items():
            self.assertIn("status", entry, f"ranked_ids[{eid}] missing 'status'")

    def test_ranked_ids_order_is_valid(self):
        """Ranks must form a contiguous 1..N sequence."""
        ranks = sorted(e["rank"] for e in self.valid.get("ranked_ids", {}).values())
        expected = list(range(1, len(ranks) + 1))
        self.assertEqual(ranks, expected)


# ---------------------------------------------------------------------------
# TestGapCoreIntact — gap core fields are unchanged in Layer 2
# ---------------------------------------------------------------------------

class TestGapCoreIntact(unittest.TestCase):
    """The gap core (gap_type, searched_sources, covered_items, omitted_items)
    must remain intact in Layer 2 output."""

    @classmethod
    def setUpClass(cls):
        cls.valid = _read_json(_OUTPUT_L2_VALID)
        cls.truncated = _read_json(_OUTPUT_L2_TRUNCATED)

    def test_valid_gap_has_core_fields(self):
        """Valid output gap must have all 4 core fields."""
        gap = self.valid.get("gap", {})
        for key in ("gap_type", "searched_sources", "covered_items", "omitted_items"):
            self.assertIn(key, gap, f"Gap missing core field: {key}")

    def test_truncated_gap_has_core_fields(self):
        """Truncated output gap must have all 4 core fields."""
        gap = self.truncated.get("gap", {})
        for key in ("gap_type", "searched_sources", "covered_items", "omitted_items"):
            self.assertIn(key, gap, f"Gap missing core field: {key}")

    def test_valid_gap_type_is_string(self):
        self.assertIsInstance(self.valid["gap"]["gap_type"], str)

    def test_truncated_gap_type_is_budget_stop(self):
        self.assertEqual(self.truncated["gap"]["gap_type"], "budget_stop")

    def test_sourced_sources_is_list(self):
        """gap.searched_sources must be an array."""
        self.assertIsInstance(self.valid["gap"]["searched_sources"], list)


if __name__ == "__main__":
    unittest.main()
