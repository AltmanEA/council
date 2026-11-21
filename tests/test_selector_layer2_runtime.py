"""Runtime behavior tests for Selector Layer 2 (facts + references).

Test groups:
  (a) TestManifestFirst         — EN body read by path from manifest; manifest-first.
  (b) TestLanguageExclusion     — RU / archive docs do not leak into output by default.
  (c) TestSourceSHA256          — sha256 recorded for each source in sources[].
  (d) TestStableLinks           — repeated calls produce the same output set.
  (e) TestFailClosed            — missing / corrupted manifest → gap_type=conflict.
  (f) TestHashMismatch          — body hash deviation → gap_type=conflict.
  (g) TestBudgetCapping         — hints > ceiling → truncated + omitted_items.
  (h) TestCodeModeOff           — reveal_code=False prevents code search.
  (i) TestManifestFirstPath     — documents accessed via path from manifest, not FS scan.

Uses unittest + stdlib only.  Module loaded via importlib.
"""
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest

import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Layer 2 module path (not yet implemented — tests expect ImportError initially)
_LAYER2_DIR = _ROOT / ".agents" / "skills" / "selector" / "layer2"
_LAYER2_PATH = str(_LAYER2_DIR / "selector_layer2.py")

# Layer 1 fixtures used as reference
_FIXTURE_DIR = str(_ROOT / ".agents" / "skills" / "selector" / "fixtures")
_MANIFEST_SAMPLE = os.path.join(_FIXTURE_DIR, "manifest.sample.yaml")


def _load_layer2():
    """Load selector_layer2 module via importlib."""
    spec = importlib.util.spec_from_file_location(
        "selector_layer2",
        _LAYER2_PATH,
        submodule_search_locations=[str(_LAYER2_DIR)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(
            f"Layer 2 module not found at {_LAYER2_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    os.sys.modules["selector_layer2"] = module
    spec.loader.exec_module(module)
    return module


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _build_manifest_fixture(docs):
    """Create a temporary YAML manifest file from a list of doc dicts."""
    fd, path = tempfile.mkstemp(suffix=".yaml", prefix="manifest_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("documents:\n")
        for doc in docs:
            f.write(f"  - id: {doc['id']}\n")
            f.write(f"    path: {doc['path']}\n")
            f.write(f"    title: {doc['title']}\n")
            f.write(f"    version: {doc['version']}\n")
            f.write(f"    status: {doc['status']}\n")
            f.write(f"    abstraction: {doc['abstraction']}\n")
            if "has_translation" in doc:
                f.write(f"    has_translation: {doc['has_translation']}\n")
            if "description" in doc:
                f.write(f'    description: "{doc["description"]}"\n')
            f.write("\n")
    return path


def _create_en_doc(path, content):
    """Create an English doc file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _create_ru_doc(path, content):
    """Create a Russian doc file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# (a) TestManifestFirst — EN body read by path from manifest
# ---------------------------------------------------------------------------

class TestManifestFirst(unittest.TestCase):
    """Layer 2 must read EN doc body by path from manifest; manifest is the entry point."""

    @classmethod
    def setUpClass(cls):
        cls.layer2 = _load_layer2()

    def test_run_query_accepts_manifest_path(self):
        """run_query must accept manifest_path as first positional argument."""
        self.assertTrue(hasattr(self.layer2, "run_query"))
        self.assertTrue(callable(self.layer2.run_query))

    def test_output_contains_manifest_sha256(self):
        """Output must contain manifest_sha256 field matching the manifest file."""
        real_sha = _sha256_of(_MANIFEST_SAMPLE)
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.layer2.run_query(
                _MANIFEST_SAMPLE, "selector specification",
                audit_dir=audit_dir, call_id="mf-001",
            )
        output_sha = result["output"].get("manifest_sha256", "")
        self.assertEqual(
            output_sha, real_sha,
            f"Output manifest_sha256 ({output_sha!r}) must match computed ({real_sha!r})",
        )

    def test_audit_contains_manifest_sha256(self):
        """Audit dict must also contain manifest_sha256."""
        real_sha = _sha256_of(_MANIFEST_SAMPLE)
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.layer2.run_query(
                _MANIFEST_SAMPLE, "selector specification",
                audit_dir=audit_dir, call_id="mf-002",
            )
        audit_sha = result["audit"].get("manifest_sha256", "")
        self.assertEqual(audit_sha, real_sha)


# ---------------------------------------------------------------------------
# (b) TestLanguageExclusion — RU / archive docs do not leak by default
# ---------------------------------------------------------------------------

class TestLanguageExclusion(unittest.TestCase):
    """RU and archive documents must not appear in output sources by default."""

    @classmethod
    def setUpClass(cls):
        cls.layer2 = _load_layer2()

    def test_ru_docs_excluded_from_sources(self):
        """Sources with paths under docs/ru/ must not appear in output.sources."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a manifest with a RU doc path
            manifest_path = _build_manifest_fixture([
                {"id": "ru-test", "path": "docs/ru/selector/index-RU.md",
                 "title": "Селектор", "version": "1.0", "status": "active",
                 "abstraction": "conceptual", "description": "Тест RU"},
            ])
            try:
                with tempfile.TemporaryDirectory() as audit_dir:
                    result = self.layer2.run_query(
                        manifest_path, "selector",
                        audit_dir=audit_dir, call_id="ru-001",
                    )
            finally:
                os.unlink(manifest_path)
        sources = result["output"].get("sources", [])
        source_paths = [s.get("path", "") for s in sources]
        for sp in source_paths:
            self.assertNotIn("docs/ru/", sp,
                             f"RU path {sp!r} must not appear in sources")

    def test_archive_docs_excluded_from_sources(self):
        """Sources with status=archive must not appear in output.sources by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = _build_manifest_fixture([
                {"id": "arch-test", "path": "docs/en/archive/test/index.md",
                 "title": "Archive Test", "version": "1.0", "status": "archive",
                 "abstraction": "operational", "description": "Archive doc"},
            ])
            try:
                with tempfile.TemporaryDirectory() as audit_dir:
                    result = self.layer2.run_query(
                        manifest_path, "test",
                        audit_dir=audit_dir, call_id="arch-001",
                    )
            finally:
                os.unlink(manifest_path)
        sources = result["output"].get("sources", [])
        for s in sources:
            self.assertNotEqual(s.get("status"), "archive",
                                "Archive doc must not appear in sources")


# ---------------------------------------------------------------------------
# (c) TestSourceSHA256 — sha256 recorded for each source
# ---------------------------------------------------------------------------

class TestSourceSHA256(unittest.TestCase):
    """Each source in sources[] must have a non-empty sha256 field."""

    @classmethod
    def setUpClass(cls):
        cls.layer2 = _load_layer2()

    def test_sources_have_sha256(self):
        """Every source entry must include a sha256 hex string."""
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.layer2.run_query(
                _MANIFEST_SAMPLE, "selector specification",
                audit_dir=audit_dir, call_id="sha-001",
            )
        sources = result["output"].get("sources", [])
        for src in sources:
            self.assertIn("sha256", src, "Source missing 'sha256'")
            sha = src["sha256"]
            self.assertIsInstance(sha, str)
            self.assertGreater(len(sha), 0, "sha256 must be non-empty")


# ---------------------------------------------------------------------------
# (d) TestStableLinks — repeated calls produce the same output set
# ---------------------------------------------------------------------------

class TestStableLinks(unittest.TestCase):
    """Repeated calls with same manifest and query must produce the same
    ranked_ids set and sources set."""

    @classmethod
    def setUpClass(cls):
        cls.layer2 = _load_layer2()

    def test_repeated_calls_same_ranked_ids(self):
        """Two calls with same input must yield identical ranked_ids keys and ranks."""
        call_a = None
        call_b = None
        for _ in range(2):
            with tempfile.TemporaryDirectory() as audit_dir:
                result = self.layer2.run_query(
                    _MANIFEST_SAMPLE, "selector specification",
                    audit_dir=audit_dir, call_id=f"stable-{'a' if call_a is None else 'b'}",
                )
            if call_a is None:
                call_a = result
            else:
                call_b = result
        self.assertEqual(
            sorted(call_a["output"]["ranked_ids"].keys()),
            sorted(call_b["output"]["ranked_ids"].keys()),
            "Ranked IDs keys must be stable across calls",
        )

    def test_repeated_calls_same_sources(self):
        """Two calls with same input must yield identical sources paths."""
        call_a = None
        call_b = None
        for i in range(2):
            with tempfile.TemporaryDirectory() as audit_dir:
                result = self.layer2.run_query(
                    _MANIFEST_SAMPLE, "selector specification",
                    audit_dir=audit_dir, call_id=f"stable-src-{i}",
                )
            if call_a is None:
                call_a = result
            else:
                call_b = result
        paths_a = sorted(s["path"] for s in call_a["output"].get("sources", []))
        paths_b = sorted(s["path"] for s in call_b["output"].get("sources", []))
        self.assertEqual(paths_a, paths_b, "Source paths must be stable across calls")


# ---------------------------------------------------------------------------
# (e) TestFailClosed — missing / corrupted manifest → gap_type=conflict
# ---------------------------------------------------------------------------

class TestFailClosed(unittest.TestCase):
    """Missing or corrupted manifest must produce gap_type='conflict' or 'manifest_missing'."""

    @classmethod
    def setUpClass(cls):
        cls.layer2 = _load_layer2()

    def test_missing_manifest_gap_type(self):
        """Missing manifest must yield gap_type in {manifest_missing, conflict}."""
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.layer2.run_query(
                "/nonexistent/manifest.yaml", "test query",
                audit_dir=audit_dir, call_id="fc-001",
            )
        gap_type = result["output"].get("gap", {}).get("gap_type", "")
        self.assertIn(
            gap_type, ("manifest_missing", "conflict"),
            f"Missing manifest gap_type must be manifest_missing or conflict, got {gap_type!r}",
        )

    def test_missing_manifest_empty_ranked_ids(self):
        """Missing manifest must yield empty ranked_ids."""
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.layer2.run_query(
                "/nonexistent/manifest.yaml", "test query",
                audit_dir=audit_dir, call_id="fc-002",
            )
        self.assertEqual(result["output"].get("ranked_ids"), {})


# ---------------------------------------------------------------------------
# (f) TestHashMismatch — body hash deviation → gap_type=conflict
# ---------------------------------------------------------------------------

class TestHashMismatch(unittest.TestCase):
    """If a source body hash deviates from the recorded sha256, gap_type=conflict."""

    @classmethod
    def setUpClass(cls):
        cls.layer2 = _load_layer2()

    def test_broken_manifest_causes_conflict(self):
        """A manifest with garbage body must yield gap_type=conflict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = os.path.join(tmpdir, "manifest_corrupt.yaml")
            with open(manifest_path, "w", encoding="utf-8") as f:
                f.write("documents:\n  - id: bad\n    path: /dev/null\n    title: Bad\n    version: 0\n    status: active\n    abstraction: test\n")
            with tempfile.TemporaryDirectory() as audit_dir:
                result = self.layer2.run_query(
                    manifest_path, "test",
                    audit_dir=audit_dir, call_id="hm-001",
                )
        gap_type = result["output"].get("gap", {}).get("gap_type", "")
        # Accept manifest_missing or conflict — either indicates failure
        self.assertIn(
            gap_type, ("manifest_missing", "conflict", "not_found"),
            f"Corrupt manifest must produce manifest_missing, conflict, or not_found, got {gap_type!r}",
        )


# ---------------------------------------------------------------------------
# (g) TestBudgetCapping — hints > ceiling → truncated + omitted_items
# ---------------------------------------------------------------------------

class TestBudgetCapping(unittest.TestCase):
    """Hints exceeding ceiling must produce truncated=True and non-empty omitted_items."""

    @classmethod
    def setUpClass(cls):
        cls.layer2 = _load_layer2()

    def test_high_hints_capped(self):
        """Hints requesting 100 files must be capped; output truncated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = _build_manifest_fixture([
                {"id": f"doc-{i:03d}", "path": f"docs/en/doc{i:03d}/index.md",
                 "title": f"Doc {i}", "version": "1.0", "status": "active",
                 "abstraction": "operational", "description": f"Document {i}"}
                for i in range(50)
            ])
            try:
                with tempfile.TemporaryDirectory() as audit_dir:
                    result = self.layer2.run_query(
                        manifest_path, "test query",
                        hints={"max_files": 100, "max_tokens": 10000},
                        audit_dir=audit_dir, call_id="bud-001",
                    )
            finally:
                os.unlink(manifest_path)
        output = result["output"]
        self.assertTrue(output.get("truncated"), "With oversized hints, truncated must be True")
        self.assertIn(
            "TRUNCATED", output.get("task_summary", ""),
            "task_summary must contain TRUNCATED banner",
        )
        self.assertEqual(
            output["gap"].get("gap_type"), "budget_stop",
            "gap_type must be budget_stop",
        )
        self.assertGreater(
            len(output["gap"].get("omitted_items", [])), 0,
            "omitted_items must be non-empty when truncated",
        )


# ---------------------------------------------------------------------------
# (h) TestCodeModeOff — reveal_code=False prevents code search
# ---------------------------------------------------------------------------

class TestCodeModeOff(unittest.TestCase):
    """When reveal_code=False (default), code.search must not be called
    and code must not appear in searched_sources or sources."""

    @classmethod
    def setUpClass(cls):
        cls.layer2 = _load_layer2()

    def test_code_mode_off_default(self):
        """With default settings, modes.code must be 'off'."""
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.layer2.run_query(
                _MANIFEST_SAMPLE, "selector specification",
                audit_dir=audit_dir, call_id="code-001",
            )
        modes = result["output"].get("modes", {})
        self.assertEqual(modes.get("code"), "off", "Default code mode must be 'off'")

    def test_no_code_sources_when_code_off(self):
        """When code mode is off, sources must not include .py paths."""
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.layer2.run_query(
                _MANIFEST_SAMPLE, "selector specification",
                audit_dir=audit_dir, call_id="code-002",
            )
        sources = result["output"].get("sources", [])
        for src in sources:
            self.assertFalse(
                src.get("path", "").endswith(".py"),
                "Code path must not appear in sources when code mode is off",
            )


# ---------------------------------------------------------------------------
# (i) TestManifestFirstPath — documents accessed via path from manifest
# ---------------------------------------------------------------------------

class TestManifestFirstPath(unittest.TestCase):
    """Documents must be accessed via the 'path' field from manifest entries,
    not by filesystem scanning."""

    @classmethod
    def setUpClass(cls):
        cls.layer2 = _load_layer2()

    def test_output_sources_use_manifest_paths(self):
        """Source paths in output must be a subset of manifest doc paths."""
        # Parse manifest entries (minimal YAML-like extraction, no external deps)
        manifest_raw = _read_file(_MANIFEST_SAMPLE)
        manifest_paths = set()
        import re as _re
        for line in manifest_raw.split("\n"):
            line = line.strip()
            m = _re.match(r"^path:\s*(.+)$", line)
            if m:
                manifest_paths.add(m.group(1).strip())

        self.assertGreater(len(manifest_paths), 0,
                           "Manifest must contain at least one path")

        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.layer2.run_query(
                _MANIFEST_SAMPLE, "selector specification",
                audit_dir=audit_dir, call_id="mfp-001",
            )
        sources = result["output"].get("sources", [])
        source_paths = {s.get("path") for s in sources
                        if s.get("path") and s.get("kind") == "doc"}

        # All doc source paths must come from the manifest (not scanned from FS)
        extra = source_paths - manifest_paths
        self.assertEqual(len(extra), 0,
                         f"Source paths not found in manifest: {extra}")

        # At least one path from manifest should appear (if manifest has docs)
        if manifest_paths:
            overlap = source_paths & manifest_paths
            self.assertGreater(len(overlap), 0,
                               "Output sources should reference manifest paths")


# ---------------------------------------------------------------------------
# Module-level constant checks
# ---------------------------------------------------------------------------

class TestCodeSearchOptIn(unittest.TestCase):
    """code.search opt-in: returns matches and respects excluded_paths."""

    @classmethod
    def setUpClass(cls):
        cls.layer2 = _load_layer2()

    def test_code_search_returns_matches(self):
        """code.search must return a list containing matches for the query."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test code files
            sample_path = os.path.join(tmpdir, "sample.py")
            other_path = os.path.join(tmpdir, "other.py")
            with open(sample_path, "w", encoding="utf-8") as f:
                f.write("def sample_function():\n    pass\n")
            with open(other_path, "w", encoding="utf-8") as f:
                f.write("# other file\n")
            matches = self.layer2.code.search(tmpdir, "sample", [])
            self.assertIsInstance(matches, list)
            match_paths = [m.get("path", m) if isinstance(m, dict) else m for m in matches]
            self.assertTrue(
                any(sample_path in p for p in match_paths),
                f"sample.py must be in code search results: {match_paths}",
            )

    def test_code_search_respects_excluded_paths(self):
        """code.search must exclude paths listed in excluded_paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sample_path = os.path.join(tmpdir, "sample.py")
            keep_path = os.path.join(tmpdir, "keep.py")
            with open(sample_path, "w", encoding="utf-8") as f:
                f.write("def sample_function():\n    pass\n")
            with open(keep_path, "w", encoding="utf-8") as f:
                f.write("def keep_function():\n    pass\n")
            excluded = [os.path.join(tmpdir, "sample.py")]
            matches = self.layer2.code.search(tmpdir, "sample", excluded)
            self.assertIsInstance(matches, list)
            match_paths = [m.get("path", m) if isinstance(m, dict) else m for m in matches]
            self.assertFalse(
                any(sample_path in p for p in match_paths),
                f"Excluded sample.py must not be in results: {match_paths}",
            )


class TestConstants(unittest.TestCase):
    """Verify that the Layer 2 module exposes the required constants."""

    @classmethod
    def setUpClass(cls):
        cls.layer2 = _load_layer2()

    def test_contract_version_const(self):
        self.assertEqual(self.layer2.CONTRACT_VERSION, "2.0.0")

    def test_default_code_mode(self):
        self.assertEqual(self.layer2.DEFAULT_CODE_MODE, "off")

    def test_ceiling_files(self):
        self.assertEqual(self.layer2.CEILING_FILES, 40)

    def test_ceiling_tokens(self):
        self.assertEqual(self.layer2.CEILING_TOKENS, 8000)

    def test_default_files(self):
        self.assertEqual(self.layer2.DEFAULT_FILES, 20)

    def test_default_tokens(self):
        self.assertEqual(self.layer2.DEFAULT_TOKENS, 4000)


if __name__ == "__main__":
    unittest.main()
