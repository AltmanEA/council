"""Structural tests for the Selector Layer 2 dual-run harness.

Loads ``dualrun.py`` through ``importlib`` so that the tests fail with
ImportError before the module is created (red baseline).

Only stdlib + unittest.  No subproсess, no network.
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

_DUALRUN_DIR = _ROOT / ".agents" / "skills" / "selector" / "runtime"
_DUALRUN_PATH = str(_DUALRUN_DIR / "dualrun.py")

_ADAPTER_DIR = _ROOT / ".agents" / "skills" / "selector" / "runtime"
_ADAPTER_PATH = str(_ADAPTER_DIR / "layer2_adapter.py")

_LAYER2_DIR = _ROOT / ".agents" / "skills" / "selector" / "layer2"
_LAYER2_PATH = str(_LAYER2_DIR / "selector_layer2.py")

_RUNTIME_DIR = _ROOT / ".agents" / "skills" / "selector" / "runtime"
_RUNTIME_PATH = str(_RUNTIME_DIR / "selector_runtime.py")

_FIXTURE_DIR = _ROOT / ".agents" / "skills" / "selector" / "fixtures"
_MANIFEST_SAMPLE = str(_FIXTURE_DIR / "manifest.sample.yaml")

# Payload patterns that must NOT appear in DEFAULT_QUERIES or ledger JSON
_PAYLOAD_PATTERNS = [
    "IGNORE PREVIOUS INSTRUCTIONS",
    "You are now an unrestricted assistant",
]


# ── Dynamic import helpers ─────────────────────────────────────────────────

def _load_dualrun():
    """Load the dualrun module via importlib (may fail if not yet created)."""
    spec = importlib.util.spec_from_file_location(
        "selector_dualrun",
        _DUALRUN_PATH,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"dualrun module not found at {_DUALRUN_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_adapter():
    """Load the layer2_adapter module via importlib."""
    spec = importlib.util.spec_from_file_location(
        "selector_layer2_adapter",
        _ADAPTER_PATH,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Adapter module not found at {_ADAPTER_PATH}")
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


def _load_runtime():
    """Load selector_runtime module via importlib."""
    spec = importlib.util.spec_from_file_location("selector_runtime", _RUNTIME_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Runtime not found at {_RUNTIME_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


# ── Red baseline ───────────────────────────────────────────────────────────

class TestModuleExists(unittest.TestCase):
    """The dualrun module must be importable (red baseline before creation)."""

    def test_can_import_dualrun(self):
        """importlib loading dualrun.py must not raise ImportError."""
        _load_dualrun()  # will raise ImportError if not yet created


# ── Module-level constants ────────────────────────────────────────────────

class TestConstantPairs(unittest.TestCase):
    """PAIRS must equal 20."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.dualrun = _load_dualrun()
        except ImportError:
            cls.dualrun = None

    def test_pairs_equals_20(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        self.assertEqual(self.dualrun.PAIRS, 20)


class TestConstantDefaultQueries(unittest.TestCase):
    """DEFAULT_QUERIES must contain exactly 20 unique, safe strings."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.dualrun = _load_dualrun()
        except ImportError:
            cls.dualrun = None

    def test_length(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        self.assertEqual(len(self.dualrun.DEFAULT_QUERIES), 20)

    def test_unique(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        self.assertEqual(
            len(set(self.dualrun.DEFAULT_QUERIES)), 20,
            "DEFAULT_QUERIES must contain 20 unique strings",
        )

    def test_no_payload(self):
        """DEFAULT_QUERIES must not contain injection payload patterns."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        all_text = " ".join(self.dualrun.DEFAULT_QUERIES)
        for pat in _PAYLOAD_PATTERNS:
            self.assertNotIn(pat, all_text,
                             f"DEFAULT_QUERIES must not contain {pat!r}")


class TestConstantLedgerFields(unittest.TestCase):
    """LEDGER_FIELDS must be a tuple of strings."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.dualrun = _load_dualrun()
        except ImportError:
            cls.dualrun = None

    def test_exists(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        self.assertTrue(hasattr(self.dualrun, "LEDGER_FIELDS"))

    def test_is_tuple(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        self.assertIsInstance(self.dualrun.LEDGER_FIELDS, tuple)


class TestDefaultMode(unittest.TestCase):
    """DEFAULT_MODE must be 'layer1'."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.dualrun = _load_dualrun()
        except ImportError:
            cls.dualrun = None

    def test_default_mode_layer1(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        self.assertEqual(self.dualrun.DEFAULT_MODE, "layer1")


# ── collect() ledger structure ────────────────────────────────────────────

class TestCollectLedgerStructure(unittest.TestCase):
    """collect() must return a ledger dict with all required top-level keys."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.dualrun = _load_dualrun()
        except ImportError:
            cls.dualrun = None

    def test_collect_returns_dict(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        self.assertIsInstance(ledger, dict)

    # ── Top-level ledger keys ──────────────────────────────────────────

    def test_observational_only_true(self):
        """observational_only must be True."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        self.assertTrue(ledger["observational_only"])

    def test_gates_empty(self):
        """gates must be an empty list."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        self.assertEqual(ledger["gates"], [])

    def test_pairs_equals_20(self):
        """ledger.pairs must equal 20."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        self.assertEqual(ledger["pairs"], 20)

    def test_results_length(self):
        """ledger.results must contain exactly 20 entries."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        self.assertEqual(len(ledger["results"]), 20)

    def test_default_mode(self):
        """default_mode must be 'layer1'."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        self.assertEqual(ledger["default_mode"], "layer1")

    def test_form_scope(self):
        """form_scope must be 'Layer 1 default / Layer 2 opt-in'."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        self.assertEqual(ledger["form_scope"], "Layer 1 default / Layer 2 opt-in")

    def test_kind(self):
        """kind must be 'selector-dual-run-ledger'."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        self.assertEqual(ledger["kind"], "selector-dual-run-ledger")

    def test_contract_version(self):
        """contract_version must be '2.0.0'."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        self.assertEqual(ledger["contract_version"], "2.0.0")

    def test_manifest_sha256_present(self):
        """manifest_sha256 must be a non-empty string."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        self.assertIsInstance(ledger["manifest_sha256"], str)
        self.assertTrue(len(ledger["manifest_sha256"]) > 0)

    def test_manifest_sha256_unchanged(self):
        """manifest_sha256_unchanged must be True (manifest not modified)."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        self.assertTrue(ledger["manifest_sha256_unchanged"])

    def test_metrics_present(self):
        """ledger.metrics must be a dict with known keys."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        self.assertIsInstance(ledger["metrics"], dict)

    def test_metrics_rank_overlap_mean(self):
        """metrics must contain rank_overlap_mean."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        self.assertIn("rank_overlap_mean", ledger["metrics"])

    def test_metrics_rank_overlap_min(self):
        """metrics must contain rank_overlap_min."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        self.assertIn("rank_overlap_min", ledger["metrics"])

    def test_metrics_rank_overlap_max(self):
        """metrics must contain rank_overlap_max."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        self.assertIn("rank_overlap_max", ledger["metrics"])

    def test_metrics_exact_rank_match_count(self):
        """metrics must contain exact_rank_match_count."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        self.assertIn("exact_rank_match_count", ledger["metrics"])

    def test_metrics_gap_type_distribution(self):
        """metrics must contain gap_type_distribution with layer1 + layer2."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        gap = ledger["metrics"]["gap_type_distribution"]
        self.assertIn("layer1", gap)
        self.assertIn("layer2", gap)

    def test_metrics_truncated_count(self):
        """metrics must contain truncated_count with layer1 + layer2."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        trunc = ledger["metrics"]["truncated_count"]
        self.assertIn("layer1", trunc)
        self.assertIn("layer2", trunc)

    def test_metrics_injection_detected_count(self):
        """metrics must contain injection_detected_count."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        self.assertIn("injection_detected_count", ledger["metrics"])

    def test_metrics_code_mode_distribution(self):
        """metrics must contain code_mode_distribution with 'off' == PAIRS."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        cm = ledger["metrics"]["code_mode_distribution"]
        self.assertIn("off", cm)
        self.assertEqual(cm["off"], 20)

    def test_metrics_validation_error_count(self):
        """metrics must contain validation_error_count."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        self.assertIn("validation_error_count", ledger["metrics"])


# ── Per-pair invariants ───────────────────────────────────────────────────

class TestPairLayer1(unittest.TestCase):
    """Each pair's layer1 output must not contain 'form' and must validate."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.dualrun = _load_dualrun()
            cls.runtime = _load_runtime()
        except ImportError:
            cls.dualrun = None
            cls.runtime = None

    def test_no_form_key_in_layer1(self):
        if self.dualrun is None or self.runtime is None:
            self.fail("Module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            self.assertNotIn(
                "form", pair["layer1"],
                f"layer1 of pair {pair['index']} must not have 'form' key",
            )

    def test_layer1_validate_output_empty(self):
        if self.dualrun is None or self.runtime is None:
            self.fail("Module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            errors = self.runtime.validate_output(pair["layer1"])
            self.assertEqual(
                errors, [],
                f"layer1 of pair {pair['index']} must validate cleanly: {errors}",
            )

    def test_layer1_has_ranked_ids(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            self.assertIn("ranked_ids", pair["layer1"])

    def test_layer1_has_gap_type(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            self.assertIn("gap_type", pair["layer1"])

    def test_layer1_has_truncated(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            self.assertIn("truncated", pair["layer1"])


class TestPairLayer2(unittest.TestCase):
    """Each pair's layer2 output must have form=Layer2, code_mode=off,
    contract_version=2.0.0, and pass both validators."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.dualrun = _load_dualrun()
            cls.layer2 = _load_layer2()
            cls.runtime = _load_runtime()
        except ImportError:
            cls.dualrun = None
            cls.layer2 = None
            cls.runtime = None

    def test_form_is_layer2(self):
        if self.dualrun is None or self.layer2 is None:
            self.fail("Module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            self.assertEqual(
                pair["layer2"]["form"], "Layer 2",
                f"layer2 of pair {pair['index']} must have form='Layer 2'",
            )

    def test_contract_version(self):
        if self.dualrun is None or self.layer2 is None:
            self.fail("Module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            self.assertEqual(
                pair["layer2"]["contract_version"], "2.0.0",
                f"layer2 of pair {pair['index']} must have contract_version='2.0.0'",
            )

    def test_code_mode_off(self):
        if self.dualrun is None or self.layer2 is None:
            self.fail("Module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            self.assertEqual(
                pair["layer2"]["code_mode"], "off",
                f"layer2 of pair {pair['index']} must have code_mode='off'",
            )

    def test_validate_output_v2_empty(self):
        """validate_output_v2 must return [] for all layer2 outputs."""
        if self.dualrun is None or self.layer2 is None:
            self.fail("Module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            errors = self.layer2.validate_output_v2(pair["layer2"])
            self.assertEqual(
                errors, [],
                f"layer2 of pair {pair['index']} must validate clean v2: {errors}",
            )

    def test_validate_output_layer1_accepts_layer2(self):
        """validate_output (Layer 1) must accept Layer 2 output."""
        if self.dualrun is None or self.layer2 is None:
            self.fail("Module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            errors = self.runtime.validate_output(pair["layer2"])
            self.assertEqual(
                errors, [],
                f"layer2 of pair {pair['index']} must validate clean l1: {errors}",
            )

    def test_layer2_has_ranked_ids(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            self.assertIn("ranked_ids", pair["layer2"])

    def test_layer2_has_gap_type(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            self.assertIn("gap_type", pair["layer2"])

    def test_layer2_has_truncated(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            self.assertIn("truncated", pair["layer2"])

    def test_layer2_has_injection_detected(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            self.assertIn("injection_detected", pair["layer2"])

    def test_layer2_has_sources_count(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            self.assertIn("sources_count", pair["layer2"])


class TestPairQueryAndId(unittest.TestCase):
    """Each pair must carry its index and query."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.dualrun = _load_dualrun()
        except ImportError:
            cls.dualrun = None

    def test_indices_0_to_19(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        indices = [p["index"] for p in ledger["results"]]
        self.assertEqual(sorted(indices), list(range(20)))

    def test_queries_unique(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        queries = [p["query"] for p in ledger["results"]]
        self.assertEqual(len(set(queries)), 20)

    def test_query_in_default_queries(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            self.assertIn(pair["query"], self.dualrun.DEFAULT_QUERIES)


class TestPairRankOverlap(unittest.TestCase):
    """Each pair must have a rank_overlap float in [0.0, 1.0]."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.dualrun = _load_dualrun()
        except ImportError:
            cls.dualrun = None

    def test_rank_overlap_present(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            self.assertIn("rank_overlap", pair)
            self.assertIsInstance(pair["rank_overlap"], (int, float))
            self.assertGreaterEqual(pair["rank_overlap"], 0.0)
            self.assertLessEqual(pair["rank_overlap"], 1.0)


# ── No payload in serialised ledger ────────────────────────────────────────

class TestLedgerNoPayload(unittest.TestCase):
    """The serialised JSON ledger must not contain injection payload strings."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.dualrun = _load_dualrun()
        except ImportError:
            cls.dualrun = None

    def test_no_payload_in_json(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        json_str = json.dumps(ledger, sort_keys=True)
        for pat in _PAYLOAD_PATTERNS:
            self.assertNotIn(pat, json_str,
                             f"Serialised ledger must not contain {pat!r}")


# ── write_ledger ───────────────────────────────────────────────────────────

class TestWriteLedger(unittest.TestCase):
    """write_ledger must write valid JSON; respects env var SELECTOR_DUALRUN_LEDGER."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.dualrun = _load_dualrun()
        except ImportError:
            cls.dualrun = None

    def test_writes_valid_json(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ledger.json")
            ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
            returned = self.dualrun.write_ledger(ledger, path)
            self.assertEqual(returned, path)
            with open(path, "r", encoding="utf-8") as f:
                read_back = json.load(f)
            self.assertEqual(read_back["kind"], "selector-dual-run-ledger")

    def test_creates_parent_dir(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        with tempfile.TemporaryDirectory() as tmpdir:
            sub = os.path.join(tmpdir, "nested", "dir")
            path = os.path.join(sub, "ledger.json")
            ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
            returned = self.dualrun.write_ledger(ledger, path)
            self.assertEqual(returned, path)
            self.assertTrue(os.path.isfile(path))

    def test_respects_env_var(self):
        """SELECTOR_DUALRUN_LEDGER must override the output path."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        env_backup = os.environ.get("SELECTOR_DUALRUN_LEDGER")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                env_path = os.path.join(tmpdir, "env_ledger.json")
                os.environ["SELECTOR_DUALRUN_LEDGER"] = env_path
                ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
                # Call write_ledger without explicit path (env overrides)
                returned = self.dualrun.write_ledger(ledger, "/dev/null")
                self.assertEqual(returned, env_path)
                self.assertTrue(os.path.isfile(env_path))
                with open(env_path, "r", encoding="utf-8") as f:
                    json.load(f)  # must be valid JSON
        finally:
            if env_backup is not None:
                os.environ["SELECTOR_DUALRUN_LEDGER"] = env_backup
            else:
                os.environ.pop("SELECTOR_DUALRUN_LEDGER", None)


# ── Adapter DEFAULT_MODE ──────────────────────────────────────────────────

class TestAdapterDefaultMode(unittest.TestCase):
    """adapter.DEFAULT_MODE must be 'layer1' — Layer 2 does not self-activate."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.adapter = _load_adapter()
        except ImportError:
            cls.adapter = None

    def test_adapter_default_mode(self):
        if self.adapter is None:
            self.fail("Adapter module not found")
        self.assertEqual(self.adapter.DEFAULT_MODE, "layer1")


# ── Iteration 2: additional invariants (diff-review blind spots) ───────────

class TestManifestSha256TwoReads(unittest.TestCase):
    """manifest_sha256_unchanged MUST be computed from two real reads.

    Patch dualrun._sha256_of: first call returns the real SHA,
    second call returns "deadbeef". After collect() the ledger must
    report manifest_sha256_unchanged is False.
    """

    @classmethod
    def setUpClass(cls):
        try:
            cls.dualrun = _load_dualrun()
        except ImportError:
            cls.dualrun = None

    def test_sha256_unchanged_false_with_differing_reads(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        real_sha = _sha256_of(_MANIFEST_SAMPLE)
        call_count = 0
        original_sha256_of = self.dualrun._sha256_of

        def patched_sha256_of(path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return real_sha
            return "deadbeef"

        try:
            self.dualrun._sha256_of = patched_sha256_of
            ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
            self.assertFalse(
                ledger["manifest_sha256_unchanged"],
                "manifest_sha256_unchanged must be False when two real reads differ",
            )
            self.assertGreaterEqual(
                call_count, 2,
                "_sha256_of must be called at least twice (before and after runs)",
            )
        finally:
            self.dualrun._sha256_of = original_sha256_of


class TestTmpdirCleanedUp(unittest.TestCase):
    """collect() must delete its internal TemporaryDirectory after 40 audit runs.

    Patch tempfile.mkdtemp to record created paths, call collect(), then
    assert every recorded path no longer exists on disk.
    """

    @classmethod
    def setUpClass(cls):
        try:
            cls.dualrun = _load_dualrun()
        except ImportError:
            cls.dualrun = None

    def test_tmpdir_removed_after_collect(self):
        if self.dualrun is None:
            self.fail("dualrun module not found")
        created_paths = []
        original_mkdtemp = tempfile.mkdtemp

        def recording_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            created_paths.append(path)
            return path

        try:
            self.dualrun.tempfile.mkdtemp = recording_mkdtemp
            self.dualrun.collect(_MANIFEST_SAMPLE)
        finally:
            self.dualrun.tempfile.mkdtemp = original_mkdtemp

        for p in created_paths:
            self.assertFalse(
                os.path.exists(p),
                f"Temporary audit directory {p} must be removed after collect()",
            )


class TestRedaction(unittest.TestCase):
    """Compact output must redact facts.claim to '[redacted]' and omit
    request_intent from both layer1 and layer2 dicts."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.dualrun = _load_dualrun()
            cls.layer2 = _load_layer2()
            cls.runtime = _load_runtime()
        except ImportError:
            cls.dualrun = None
            cls.layer2 = None
            cls.runtime = None

    def test_facts_claim_redacted_layer2(self):
        """layer2 facts[].claim must be '[redacted]' for every pair."""
        if self.dualrun is None or self.layer2 is None:
            self.fail("Module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            for i, fact in enumerate(pair["layer2"].get("facts", [])):
                self.assertEqual(
                    fact.get("claim"), "[redacted]",
                    f"layer2 facts[{i}] claim must be '[redacted]' (pair {pair['index']})",
                )

    def test_facts_sources_preserved_layer2(self):
        """layer2 facts must still have sources[] and status[] for v2 validation."""
        if self.dualrun is None or self.layer2 is None:
            self.fail("Module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            for i, fact in enumerate(pair["layer2"].get("facts", [])):
                self.assertIn(
                    "sources", fact,
                    f"layer2 facts[{i}] must still have 'sources' key (pair {pair['index']})",
                )
                self.assertIn(
                    "status", fact,
                    f"layer2 facts[{i}] must still have 'status' key (pair {pair['index']})",
                )

    def test_no_request_intent_layer1(self):
        """request_intent must be absent from layer1 output."""
        if self.dualrun is None:
            self.fail("dualrun module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            self.assertNotIn(
                "request_intent", pair["layer1"],
                f"layer1 of pair {pair['index']} must not have 'request_intent'",
            )

    def test_no_request_intent_layer2(self):
        """request_intent must be absent from layer2 output."""
        if self.dualrun is None or self.layer2 is None:
            self.fail("Module not found")
        ledger = self.dualrun.collect(_MANIFEST_SAMPLE)
        for pair in ledger["results"]:
            self.assertNotIn(
                "request_intent", pair["layer2"],
                f"layer2 of pair {pair['index']} must not have 'request_intent'",
            )


if __name__ == "__main__":
    unittest.main()
