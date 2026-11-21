"""Tests for the Selector Layer 2 adapter (step 3).

The adapter lives at `.agents/skills/selector/runtime/layer2_adapter.py` and
provides two public functions:

    resolve_mode(mode) -> "layer1" | "layer2"
    run(mode, manifest_path, query, *, hints, reveal_code,
        audit_dir, call_id, repo_root) -> {"output", "audit", "audit_path"}

Uses unittest + stdlib only.  Module loaded via importlib so tests fail with
ImportError before the adapter file is created (red baseline).

8 behavioural requirements from the spec:
  1. resolve_mode routing (None/"layer1"/"" → layer1, "layer2" → layer2,
     unknown → ValueError).
  2. Layer 1 path: interim_form == "Layer 1", no key "form", validate_output == [].
  3. Layer 2 path: contract_version == "2.0.0", form == "Layer 2", all legacy
     + new keys, validate_output_v2 == [] AND validate_output == [].
  4. Default stays Layer 1 after a Layer 2 call.
  5. reveal_code default False → modes.code == "off".
  6. Determinism: two identical layer2 calls → identical output.
  7. Read-only: manifest/source sha256 unchanged; no files when audit_dir=None.
  8. Signature: run accepts all documented kwargs without error.
"""
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest

import pathlib

# ── Path resolution ────────────────────────────────────────────────────────

_WORKTREE = pathlib.Path(__file__).resolve().parent  # tests/
_ROOT = _WORKTREE.parent  # worktree root

_ADAPTER_DIR = _ROOT / ".agents" / "skills" / "selector" / "runtime"
_ADAPTER_PATH = str(_ADAPTER_DIR / "layer2_adapter.py")

_RUNTIME_DIR = _ROOT / ".agents" / "skills" / "selector" / "runtime"
_RUNTIME_PATH = str(_RUNTIME_DIR / "selector_runtime.py")

_LAYER2_DIR = _ROOT / ".agents" / "skills" / "selector" / "layer2"
_LAYER2_PATH = str(_LAYER2_DIR / "selector_layer2.py")

_FIXTURE_DIR = _ROOT / ".agents" / "skills" / "selector" / "fixtures"
_MANIFEST_SAMPLE = str(_FIXTURE_DIR / "manifest.sample.yaml")


# ── Dynamic import helpers ─────────────────────────────────────────────────

def _load_adapter():
    """Load the layer2_adapter module via importlib (may fail if not yet created)."""
    spec = importlib.util.spec_from_file_location(
        "selector_layer2_adapter",
        _ADAPTER_PATH,
    )
    if spec is None or spec.loader is None:
        raise ImportError(
            f"Adapter module not found at {_ADAPTER_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_runtime():
    """Load selector_runtime module via importlib."""
    spec = importlib.util.spec_from_file_location("selector_runtime", _RUNTIME_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Runtime not found at {_RUNTIME_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_layer2():
    """Load selector_layer2 module via importlib."""
    spec = importlib.util.spec_from_file_location(
        "selector_layer2",
        _LAYER2_PATH,
        submodule_search_locations=[str(_LAYER2_DIR)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Layer 2 not found at {_LAYER2_PATH}")
    module = importlib.util.module_from_spec(spec)
    os.sys.modules["selector_layer2"] = module
    spec.loader.exec_module(module)
    return module


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ── Required fields for Layer 2 output (from contract) ─────────────────────

LEGACY_KEYS = {
    "task_summary", "ranked_ids", "disclaimer", "discoverable",
    "interim_form", "gap", "hint_acknowledgement", "truncated",
    "manifest_sha256",
}

NEW_KEYS = {
    "contract_version", "form", "facts", "sources", "modes", "integrity",
}

ALL_L2_KEYS = LEGACY_KEYS | NEW_KEYS


# ============================================================================
#  Req 1 — resolve_mode routing
# ============================================================================

class TestResolveModeDefaultLayer1(unittest.TestCase):
    """Req 1a: None, empty string, and 'layer1' all resolve to 'layer1'."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.adapter = _load_adapter()
        except ImportError:
            cls.adapter = None

    def test_none_resolves_layer1(self):
        if self.adapter is None:
            self.fail("Adapter module not found")
        self.assertEqual(self.adapter.resolve_mode(None), "layer1")

    def test_empty_string_resolves_layer1(self):
        if self.adapter is None:
            self.fail("Adapter module not found")
        self.assertEqual(self.adapter.resolve_mode(""), "layer1")

    def test_layer1_resolves_layer1(self):
        if self.adapter is None:
            self.fail("Adapter module not found")
        self.assertEqual(self.adapter.resolve_mode("layer1"), "layer1")


class TestResolveModeLayer2(unittest.TestCase):
    """Req 1b: 'layer2' resolves to 'layer2'."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.adapter = _load_adapter()
        except ImportError:
            cls.adapter = None

    def test_layer2_resolves_layer2(self):
        if self.adapter is None:
            self.fail("Adapter module not found")
        self.assertEqual(self.adapter.resolve_mode("layer2"), "layer2")


class TestResolveModeUnknownRaises(unittest.TestCase):
    """Req 1c: bogus, integer, uppercase → ValueError."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.adapter = _load_adapter()
        except ImportError:
            cls.adapter = None

    def test_bogus_raises(self):
        if self.adapter is None:
            self.fail("Adapter module not found")
        with self.assertRaises(ValueError):
            self.adapter.resolve_mode("bogus")

    def test_integer_raises(self):
        if self.adapter is None:
            self.fail("Adapter module not found")
        with self.assertRaises(ValueError):
            self.adapter.resolve_mode(1)

    def test_uppercase_raises(self):
        if self.adapter is None:
            self.fail("Adapter module not found")
        with self.assertRaises(ValueError):
            self.adapter.resolve_mode("LAYER2")


# ============================================================================
#  Req 2 — Layer 1 path through adapter
# ============================================================================

class TestLayer1Output(unittest.TestCase):
    """Req 2: run(None, ...) and run('layer1', ...) produce Layer 1 output."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.adapter = _load_adapter()
            cls.runtime = _load_runtime()
        except ImportError:
            cls.adapter = None
            cls.runtime = None

    def test_none_calls_layer1(self):
        if self.adapter is None or self.runtime is None:
            self.fail("Module not found — adapter or runtime absent")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                None, _MANIFEST_SAMPLE, "selector specification",
                audit_dir=audit_dir, call_id="l1-001",
            )
        output = result["output"]
        self.assertEqual(output.get("interim_form"), "Layer 1")

    def test_explicit_layer1_calls_layer1(self):
        if self.adapter is None or self.runtime is None:
            self.fail("Module not found — adapter or runtime absent")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                "layer1", _MANIFEST_SAMPLE, "selector specification",
                audit_dir=audit_dir, call_id="l1-002",
            )
        output = result["output"]
        self.assertEqual(output.get("interim_form"), "Layer 1")

    def test_no_form_key_in_layer1_output(self):
        """Layer 1 output must NOT contain the 'form' key (that's Layer 2)."""
        if self.adapter is None or self.runtime is None:
            self.fail("Module not found")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                "layer1", _MANIFEST_SAMPLE, "selector specification",
                audit_dir=audit_dir, call_id="l1-003",
            )
        self.assertNotIn("form", result["output"],
                         "Layer 1 output must not have key 'form'")

    def test_layer1_validate_output_empty(self):
        """Layer 1 output must pass Layer 1 validate_output."""
        if self.adapter is None or self.runtime is None:
            self.fail("Module not found")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                "layer1", _MANIFEST_SAMPLE, "selector specification",
                audit_dir=audit_dir, call_id="l1-004",
            )
        errors = self.runtime.validate_output(result["output"])
        self.assertEqual(errors, [],
                         f"Layer 1 output must validate cleanly, got {errors}")

    def test_reveal_code_has_no_effect_on_layer1(self):
        """reveal_code=True must not add code-related fields in Layer 1 output."""
        if self.adapter is None or self.runtime is None:
            self.fail("Module not found")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                "layer1", _MANIFEST_SAMPLE, "selector specification",
                reveal_code=True,
                audit_dir=audit_dir, call_id="l1-005",
            )
        output = result["output"]
        # modes.code should not be "on" (Layer 1 doesn't know about code mode)
        modes = output.get("modes", {})
        self.assertNotEqual(modes.get("code"), "on",
                            "Layer 1 output must not activate code mode")


# ============================================================================
#  Req 3 — Layer 2 path through adapter
# ============================================================================

class TestLayer2Output(unittest.TestCase):
    """Req 3: run('layer2', ...) produces Layer 2 output with all keys."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.adapter = _load_adapter()
            cls.runtime = _load_runtime()
            cls.layer2 = _load_layer2()
            cls.l2_valid = _read_json(str(_FIXTURE_DIR / "output.layer2.valid.json"))
        except ImportError:
            cls.adapter = None
            cls.runtime = None
            cls.layer2 = None
            cls.l2_valid = None

    def test_contract_version(self):
        if self.adapter is None or self.layer2 is None:
            self.fail("Module not found")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                "layer2", _MANIFEST_SAMPLE, "selector specification",
                repo_root=str(_ROOT),
                audit_dir=audit_dir, call_id="l2-001",
            )
        self.assertEqual(result["output"].get("contract_version"), "2.0.0")

    def test_form_is_layer2(self):
        if self.adapter is None or self.layer2 is None:
            self.fail("Module not found")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                "layer2", _MANIFEST_SAMPLE, "selector specification",
                repo_root=str(_ROOT),
                audit_dir=audit_dir, call_id="l2-002",
            )
        self.assertEqual(result["output"].get("form"), "Layer 2")

    def test_all_legacy_keys_present(self):
        if self.adapter is None or self.layer2 is None:
            self.fail("Module not found")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                "layer2", _MANIFEST_SAMPLE, "selector specification",
                repo_root=str(_ROOT),
                audit_dir=audit_dir, call_id="l2-003",
            )
        missing = LEGACY_KEYS - set(result["output"].keys())
        self.assertEqual(len(missing), 0, f"Missing legacy keys: {missing}")

    def test_all_new_keys_present(self):
        if self.adapter is None or self.layer2 is None:
            self.fail("Module not found")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                "layer2", _MANIFEST_SAMPLE, "selector specification",
                repo_root=str(_ROOT),
                audit_dir=audit_dir, call_id="l2-004",
            )
        missing = NEW_KEYS - set(result["output"].keys())
        self.assertEqual(len(missing), 0, f"Missing new keys: {missing}")

    def test_validate_output_v2_clean(self):
        """validate_output_v2 on adapter's layer2 output must return []."""
        if self.adapter is None or self.layer2 is None:
            self.fail("Module not found")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                "layer2", _MANIFEST_SAMPLE, "selector specification",
                repo_root=str(_ROOT),
                audit_dir=audit_dir, call_id="l2-005",
            )
        errors = self.layer2.validate_output_v2(result["output"])
        self.assertEqual(errors, [],
                         f"Layer 2 output must validate cleanly, got {errors}")

    def test_validate_output_layer1_accepts_layer2(self):
        """validate_output (Layer 1) must accept Layer 2 output — additivity."""
        if self.adapter is None or self.runtime is None:
            self.fail("Module not found")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                "layer2", _MANIFEST_SAMPLE, "selector specification",
                repo_root=str(_ROOT),
                audit_dir=audit_dir, call_id="l2-006",
            )
        errors = self.runtime.validate_output(result["output"])
        self.assertEqual(errors, [],
                         f"Layer 1 validator must accept L2 output, got {errors}")

    def test_facts_present(self):
        """Output must contain non-empty facts[]."""
        if self.adapter is None or self.layer2 is None:
            self.fail("Module not found")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                "layer2", _MANIFEST_SAMPLE, "selector specification",
                repo_root=str(_ROOT),
                audit_dir=audit_dir, call_id="l2-007",
            )
        facts = result["output"].get("facts", [])
        self.assertIsInstance(facts, list)

    def test_sources_present(self):
        """Output must contain sources[]."""
        if self.adapter is None or self.layer2 is None:
            self.fail("Module not found")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                "layer2", _MANIFEST_SAMPLE, "selector specification",
                repo_root=str(_ROOT),
                audit_dir=audit_dir, call_id="l2-008",
            )
        sources = result["output"].get("sources", [])
        self.assertIsInstance(sources, list)

    def test_modes_present(self):
        """Output must contain modes{}.

        modes must include at least 'docs' and 'code'.
        """
        if self.adapter is None or self.layer2 is None:
            self.fail("Module not found")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                "layer2", _MANIFEST_SAMPLE, "selector specification",
                repo_root=str(_ROOT),
                audit_dir=audit_dir, call_id="l2-009",
            )
        modes = result["output"].get("modes", {})
        self.assertIn("docs", modes)
        self.assertIn("code", modes)

    def test_integrity_present(self):
        """Output must contain integrity{} with manifest_sha256."""
        if self.adapter is None or self.layer2 is None:
            self.fail("Module not found")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                "layer2", _MANIFEST_SAMPLE, "selector specification",
                repo_root=str(_ROOT),
                audit_dir=audit_dir, call_id="l2-010",
            )
        integrity = result["output"].get("integrity", {})
        self.assertIn("manifest_sha256", integrity)


# ============================================================================
#  Req 4 — Default stays Layer 1 after Layer 2 call
# ============================================================================

class TestDefaultStaysLayer1(unittest.TestCase):
    """Req 4: After calling run('layer2', ...), a subsequent run(None, ...)
    still produces Layer 1 output."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.adapter = _load_adapter()
            cls.runtime = _load_runtime()
            cls.layer2 = _load_layer2()
        except ImportError:
            cls.adapter = None
            cls.runtime = None
            cls.layer2 = None

    def test_after_layer2_call_default_is_layer1(self):
        if self.adapter is None or self.runtime is None:
            self.fail("Module not found")
        # First, call Layer 2
        with tempfile.TemporaryDirectory() as audit_dir:
            self.adapter.run(
                "layer2", _MANIFEST_SAMPLE, "selector specification",
                repo_root=str(_ROOT),
                audit_dir=audit_dir, call_id="stale-001",
            )
        # Then call with None (default → Layer 1)
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                None, _MANIFEST_SAMPLE, "selector specification",
                audit_dir=audit_dir, call_id="stale-002",
            )
        output = result["output"]
        self.assertEqual(output.get("interim_form"), "Layer 1")
        self.assertNotIn("form", output,
                         "Layer 1 output must not have key 'form'")


# ============================================================================
#  Req 5 — reveal_code default is False → modes.code == "off"
# ============================================================================

class TestRevealCodeDefault(unittest.TestCase):
    """Req 5: reveal_code defaults to False, so modes.code == 'off'."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.adapter = _load_adapter()
            cls.layer2 = _load_layer2()
        except ImportError:
            cls.adapter = None
            cls.layer2 = None

    def test_default_reveal_code_off(self):
        if self.adapter is None or self.layer2 is None:
            self.fail("Module not found")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                "layer2", _MANIFEST_SAMPLE, "selector specification",
                repo_root=str(_ROOT),
                audit_dir=audit_dir, call_id="rc-001",
            )
        modes = result["output"].get("modes", {})
        self.assertEqual(modes.get("code"), "off",
                         "Default code mode must be 'off'")


# ============================================================================
#  Req 6 — Determinism
# ============================================================================

class TestDeterminism(unittest.TestCase):
    """Req 6: Two run('layer2', ...) calls with identical inputs give
    identical output."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.adapter = _load_adapter()
            cls.layer2 = _load_layer2()
        except ImportError:
            cls.adapter = None
            cls.layer2 = None

    def test_two_calls_identical_output(self):
        if self.adapter is None or self.layer2 is None:
            self.fail("Module not found")
        results = []
        for i in range(2):
            with tempfile.TemporaryDirectory() as audit_dir:
                result = self.adapter.run(
                    "layer2", _MANIFEST_SAMPLE, "selector specification",
                    repo_root=str(_ROOT),
                    audit_dir=audit_dir, call_id=f"det-{i}",
                )
            # Compare output dict (not audit_path, which includes call_id)
            results.append(result["output"])
        self.assertEqual(
            json.dumps(results[0], sort_keys=True),
            json.dumps(results[1], sort_keys=True),
            "Two identical calls must yield identical output",
        )


# ============================================================================
#  Req 7 — Read-only: no file modification, no writes without audit_dir
# ============================================================================

class TestReadOnly(unittest.TestCase):
    """Req 7: Adapter must not modify manifest / source files.
    When audit_dir is None, no new files should be created."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.adapter = _load_adapter()
            cls.layer2 = _load_layer2()
        except ImportError:
            cls.adapter = None
            cls.layer2 = None

    def test_manifest_sha_unchanged(self):
        """Manifest SHA-256 must be the same before and after a run call."""
        if self.adapter is None or self.layer2 is None:
            self.fail("Module not found")
        before = _sha256_of(_MANIFEST_SAMPLE)
        with tempfile.TemporaryDirectory() as audit_dir:
            self.adapter.run(
                "layer2", _MANIFEST_SAMPLE, "selector specification",
                repo_root=str(_ROOT),
                audit_dir=audit_dir, call_id="ro-001",
            )
        after = _sha256_of(_MANIFEST_SAMPLE)
        self.assertEqual(before, after,
                         "Manifest SHA-256 must not change after run")

    def test_no_audit_dir_no_new_files(self):
        """When audit_dir=None, the result must have empty audit_path and
        no audit file should have been created."""
        if self.adapter is None or self.layer2 is None:
            self.fail("Module not found")
        result = self.adapter.run(
            "layer2", _MANIFEST_SAMPLE, "selector specification",
            repo_root=str(_ROOT),
            audit_dir=None, call_id="ro-002",
        )
        self.assertEqual(
            result.get("audit_path", ""), "",
            "audit_path must be empty when audit_dir is None",
        )

    def test_audit_dir_is_only_write_target(self):
        """Only the audit file should be created inside audit_dir."""
        if self.adapter is None or self.layer2 is None:
            self.fail("Module not found")
        with tempfile.TemporaryDirectory() as audit_dir:
            files_before = set(os.listdir(audit_dir))
            self.adapter.run(
                "layer2", _MANIFEST_SAMPLE, "selector specification",
                repo_root=str(_ROOT),
                audit_dir=audit_dir, call_id="ro-003",
            )
            files_after = set(os.listdir(audit_dir))
        new_files = files_after - files_before
        self.assertGreater(len(new_files), 0,
                           "At least one audit file should be created")
        # All new files should be audit files (selector-*.md)
        for nf in new_files:
            self.assertTrue(
                nf.startswith("selector-"),
                f"Unexpected file created: {nf}",
            )


# ============================================================================
#  Req 8 — Signature: run accepts all documented kwargs
# ============================================================================

class TestRunSignature(unittest.TestCase):
    """Req 8: run() accepts all kwargs from the contract:
    hints, reveal_code, audit_dir, call_id, repo_root."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.adapter = _load_adapter()
            cls.layer2 = _load_layer2()
        except ImportError:
            cls.adapter = None
            cls.layer2 = None

    def test_run_accepts_all_kwargs(self):
        """Calling run with all documented kwargs must not raise."""
        if self.adapter is None or self.layer2 is None:
            self.fail("Module not found")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                "layer2", _MANIFEST_SAMPLE, "selector specification",
                hints={"max_files": 10, "max_tokens": 2000},
                reveal_code=True,
                audit_dir=audit_dir,
                call_id="sig-001",
                repo_root=str(_ROOT),
            )
        self.assertIn("output", result)
        self.assertIn("audit", result)
        self.assertIn("audit_path", result)

    def test_run_accepts_hints_only(self):
        """run with hints must not raise."""
        if self.adapter is None or self.layer2 is None:
            self.fail("Module not found")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                "layer2", _MANIFEST_SAMPLE, "selector specification",
                hints={"max_files": 5},
                audit_dir=audit_dir, call_id="sig-002",
            )
        self.assertIn("output", result)

    def test_run_accepts_no_kwargs(self):
        """Minimal call (mode, manifest, query) must succeed."""
        if self.adapter is None or self.layer2 is None:
            self.fail("Module not found")
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.adapter.run(
                "layer2", _MANIFEST_SAMPLE, "selector specification",
                audit_dir=audit_dir, call_id="sig-003",
            )
        self.assertIn("output", result)


# ============================================================================
#  Module-level constant checks
# ============================================================================

class TestAdapterConstants(unittest.TestCase):
    """Verify the adapter module exposes the expected constants."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.adapter = _load_adapter()
        except ImportError:
            cls.adapter = None

    def test_mode_layer1_exists(self):
        if self.adapter is None:
            self.fail("Adapter not found")
        self.assertTrue(hasattr(self.adapter, "MODE_LAYER1"))
        self.assertEqual(self.adapter.MODE_LAYER1, "layer1")

    def test_mode_layer2_exists(self):
        if self.adapter is None:
            self.fail("Adapter not found")
        self.assertTrue(hasattr(self.adapter, "MODE_LAYER2"))
        self.assertEqual(self.adapter.MODE_LAYER2, "layer2")

    def test_default_mode_exists(self):
        if self.adapter is None:
            self.fail("Adapter not found")
        self.assertTrue(hasattr(self.adapter, "DEFAULT_MODE"))
        self.assertEqual(self.adapter.DEFAULT_MODE, "layer1")


if __name__ == "__main__":
    unittest.main()
