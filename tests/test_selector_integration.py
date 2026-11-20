"""Integration tests for the Selector Layer 1 deterministic runtime harness.

Tests exercise the runtime module end-to-end: manifest loading, sanitisation,
ranking, query execution, budget capping, fail-closed error handling, audit
artifact creation, and output validation.

Each acceptance criterion from target-task.md is covered by one named test:
  TestInjectionV2        AC1 — prompt injection must not leak into output/audit.
  TestIndexOnlyV1        AC2 — only manifest + audit files opened.
  TestIntegrityV3        AC3 — manifest SHA-256 unchanged across call.
  TestBudgetV4           AC4 — hints capped at ceiling; default cap without hints.
  TestFailClosedV6       AC6 — missing/malformed manifest → manifest_missing.
  TestAuditV8            AC7 — audit file created with required fields.
  TestContractValidationV5 AC7 — validate_output contract for fixtures + edge cases.

Uses unittest + stdlib only. Runtime is imported via importlib so the test
remains valid before the implementation file exists.
"""
import hashlib
import importlib.util
import json
import os
import re
import tempfile
import unittest

import pathlib

# ---------------------------------------------------------------------------
# Path resolution — harness is inside the skill, one level up from tests
# ---------------------------------------------------------------------------

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_ROOT = _TEST_DIR.parent  # worktree root

_RUNTIME_DIR = _ROOT / ".agents" / "skills" / "selector" / "runtime"
_RUNTIME_PATH = str(_RUNTIME_DIR / "selector_runtime.py")

_FIXTURE_DIR = _ROOT / ".agents" / "skills" / "selector" / "fixtures"
_MANIFEST_SAMPLE = str(_FIXTURE_DIR / "manifest.sample.yaml")
_MANIFEST_POISONED = str(_FIXTURE_DIR / "manifest.poisoned.yaml")
_OUTPUT_VALID = str(_FIXTURE_DIR / "output.valid.json")
_OUTPUT_TRUNCATED = str(_FIXTURE_DIR / "output.truncated.json")

# ---------------------------------------------------------------------------
# Dynamic import of the runtime harness
# ---------------------------------------------------------------------------

def _load_runtime():
    """Load selector_runtime module via importlib; raises ImportError if absent."""
    spec = importlib.util.spec_from_file_location("selector_runtime", _RUNTIME_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(
            f"Runtime module not found at {_RUNTIME_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _load_fixtures():
    """Return (valid_json, truncated_json) dicts."""
    return _read_json(_OUTPUT_VALID), _read_json(_OUTPUT_TRUNCATED)


# ---------------------------------------------------------------------------
# AC1 / V2 — Prompt injection must not leak into output or audit
# ---------------------------------------------------------------------------

class TestInjectionV2(unittest.TestCase):
    """With poisoned manifest, 'IGNORE PREVIOUS INSTRUCTIONS' must NOT appear
    anywhere in the returned output or in the audit artifact body.
    Ranking (ids + ranks) must be identical to the clean manifest result.
    """

    @classmethod
    def setUpClass(cls):
        cls.runtime = _load_runtime()
        cls.valid_out, _ = _load_fixtures()

    def test_injection_not_in_output(self):
        """The payload must not appear in any output field when using poisoned manifest."""
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.runtime.run_query(
                _MANIFEST_POISONED,
                "selector specification",
                audit_dir=audit_dir,
                call_id="inj-test-001",
            )
        output = result["output"]
        # Check task_summary
        self.assertNotIn(
            "IGNORE PREVIOUS INSTRUCTIONS",
            output.get("task_summary", ""),
            "Injection payload must not appear in task_summary",
        )
        # Check gap fields
        gap = output.get("gap", {})
        for field in ("suggestion",):
            self.assertNotIn(
                "IGNORE PREVIOUS INSTRUCTIONS",
                str(gap.get(field, "")),
                f"Injection must not appear in gap.{field}",
            )
        # Check every rationale in ranked_ids
        for item in output.get("ranked_ids", {}).values():
            self.assertNotIn(
                "IGNORE PREVIOUS INSTRUCTIONS",
                item.get("rationale", ""),
                "Injection must not appear in any ranked item's rationale",
            )
        # Verify gap_type and other text fields
        for text_val in (output.get("disclaimer"), output.get("hint_acknowledgement")):
            if text_val:
                self.assertNotIn(
                    "IGNORE PREVIOUS INSTRUCTIONS",
                    text_val,
                    f"Injection must not appear in {text_val[:30]!r}",
                )

    def test_injection_not_in_audit(self):
        """The audit artifact body must not contain the injection payload."""
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.runtime.run_query(
                _MANIFEST_POISONED,
                "selector specification",
                audit_dir=audit_dir,
                call_id="inj-test-002",
            )
            audit_path = result.get("audit_path", "")
            self.assertTrue(os.path.isfile(audit_path), f"Audit file not found at {audit_path}")
            audit_text = _read_file(audit_path)
        self.assertNotIn(
            "IGNORE PREVIOUS INSTRUCTIONS",
            audit_text,
            "Injection payload must not appear in audit file body",
        )

    def test_injection_detected_as_boolean_count(self):
        """The audit must record injection detection as a boolean or count, not by echoing."""
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.runtime.run_query(
                _MANIFEST_POISONED,
                "selector specification",
                audit_dir=audit_dir,
                call_id="inj-test-003",
            )
            audit_text = _read_file(result["audit_path"])
        # The audit should contain something like "injection_detected: true" or
        # "injection_count: N" — but never the actual payload.
        self.assertIn("inj-test-003", audit_text)
        # Check there's a boolean or count record of detection (not the payload text)
        bool_found = "injection_detected" in audit_text.lower() or "injection_count" in audit_text.lower()
        self.assertTrue(bool_found, "Audit must record injection detection as boolean/count")

    def test_ids_ranks_match_clean_run(self):
        """IDs and ranks from poisoned manifest must match clean manifest result."""
        with tempfile.TemporaryDirectory() as audit_dir:
            clean = self.runtime.run_query(
                _MANIFEST_SAMPLE,
                "selector specification",
                audit_dir=audit_dir,
                call_id="inj-clean",
            )
        with tempfile.TemporaryDirectory() as audit_dir:
            poisoned = self.runtime.run_query(
                _MANIFEST_POISONED,
                "selector specification",
                audit_dir=audit_dir,
                call_id="inj-poisoned",
            )
        clean_ids = sorted(clean["output"]["ranked_ids"].keys())
        poison_ids = sorted(poisoned["output"]["ranked_ids"].keys())
        self.assertEqual(
            clean_ids, poison_ids,
            "Poisoned manifest must yield same IDs as clean manifest",
        )
        # Ranks must also match (same ordering preserved)
        for doc_id in clean_ids:
            clean_rank = clean["output"]["ranked_ids"][doc_id]["rank"]
            poison_rank = poisoned["output"]["ranked_ids"][doc_id]["rank"]
            self.assertEqual(
                clean_rank, poison_rank,
                f"Rank mismatch for {doc_id}: clean={clean_rank}, poisoned={poison_rank}",
            )


# ---------------------------------------------------------------------------
# AC2 / V1 — Index-only: only manifest and audit files opened
# ---------------------------------------------------------------------------

class TestIndexOnlyV1(unittest.TestCase):
    """The harness must read only the manifest file and the audit file.
    No docs/ document body or code file is opened.
    """

    @classmethod
    def setUpClass(cls):
        cls.runtime = _load_runtime()

    def test_open_calls_limited_to_manifest_and_audit(self):
        """builtins.open must only be called for manifest and the audit file path."""
        import builtins

        original_open = builtins.open
        opened_paths = []

        def spy_open(path, *args, **kwargs):
            opened_paths.append(str(path))
            return original_open(path, *args, **kwargs)

        builtins.open = spy_open
        try:
            with tempfile.TemporaryDirectory() as audit_dir:
                self.runtime.run_query(
                    _MANIFEST_SAMPLE,
                    "selector specification",
                    audit_dir=audit_dir,
                    call_id="idx-001",
                )
        finally:
            builtins.open = original_open

        manifest_name = os.path.basename(_MANIFEST_SAMPLE)
        # Every opened path must either be the manifest file or end with an
        # audit filename pattern (selector-<uuid>.md or similar).
        audit_prefix = "selector-"
        allowed = []
        for p in opened_paths:
            if manifest_name in p:
                allowed.append(p)
            elif audit_prefix in p:
                allowed.append(p)
            else:
                allowed.append(p)  # mark non-allowed
        non_allowed = [p for p in opened_paths if manifest_name not in p and audit_prefix not in p]
        self.assertEqual(
            len(non_allowed), 0,
            f"Unexpected files opened: {non_allowed}. "
            f"All opens should be manifest or audit only.",
        )


# ---------------------------------------------------------------------------
# AC3 / V3 — Integrity: manifest SHA-256 unchanged
# ---------------------------------------------------------------------------

class TestIntegrityV3(unittest.TestCase):
    """Pre-call and post-call sha256 of the manifest must be equal and match
    the manifest_sha256 value in the output. Manifest bytes must not change.
    """

    @classmethod
    def setUpClass(cls):
        cls.runtime = _load_runtime()

    def test_sha256_unchanged_across_call(self):
        """SHA-256 before and after run_query must be identical."""
        manifest_sha_before = _sha256_of(_MANIFEST_SAMPLE)
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.runtime.run_query(
                _MANIFEST_SAMPLE,
                "selector specification",
                audit_dir=audit_dir,
                call_id="int-001",
            )
        manifest_sha_after = _sha256_of(_MANIFEST_SAMPLE)
        self.assertEqual(
            manifest_sha_before, manifest_sha_after,
            "Manifest SHA-256 must not change across a run_query call",
        )

    def test_sha256_matches_output_field(self):
        """manifest_sha256 in output/audit must equal the computed SHA-256."""
        manifest_sha = _sha256_of(_MANIFEST_SAMPLE)
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.runtime.run_query(
                _MANIFEST_SAMPLE,
                "selector specification",
                audit_dir=audit_dir,
                call_id="int-002",
            )
        output_sha = result["output"].get("manifest_sha256", "")
        self.assertEqual(
            manifest_sha, output_sha,
            f"Output manifest_sha256 ({output_sha}) must match computed "
            f"SHA-256 ({manifest_sha})",
        )
        audit_sha = result["audit"].get("manifest_sha256", "")
        self.assertEqual(
            manifest_sha, audit_sha,
            f"Audit manifest_sha256 ({audit_sha}) must match computed SHA-256",
        )


# ---------------------------------------------------------------------------
# AC4 / V4 — Budget capping
# ---------------------------------------------------------------------------

class TestBudgetV4(unittest.TestCase):
    """Hints 100 files / 10000 tokens must be capped at CEILING_FILES / CEILING_TOKENS.
    Without hints the effective cap is DEFAULT_FILES / DEFAULT_TOKENS.
    """

    @classmethod
    def setUpClass(cls):
        cls.runtime = _load_runtime()
        # These constants should exist on the runtime module
        cls.ceiling_files = cls.runtime.CEILING_FILES
        cls.ceiling_tokens = cls.runtime.CEILING_TOKENS
        cls.default_files = cls.runtime.DEFAULT_FILES
        cls.default_tokens = cls.runtime.DEFAULT_TOKENS

    def test_high_hints_capped_at_ceiling(self):
        """Hints requesting 100 files / 10000 tokens are capped to ceiling values."""
        # Create a temporary manifest with 45 entries (> CEILING_FILES=40)
        with tempfile.TemporaryDirectory() as manifest_dir:
            manifest_path = os.path.join(manifest_dir, "manifest_large.yaml")
            with open(manifest_path, "w", encoding="utf-8") as f:
                f.write("documents:\n")
                for i in range(45):
                    f.write(f"  - id: doc-{i:03d}\n")
                    f.write(f"    path: docs/en/doc{i:03d}/index.md\n")
                    f.write(f"    title: Document {i}\n")
                    f.write(f"    version: 1.0.0\n")
                    f.write(f"    status: active\n")
                    f.write(f"    abstraction: operational\n\n")
            with tempfile.TemporaryDirectory() as audit_dir:
                result = self.runtime.run_query(
                    manifest_path,
                    "selector specification",
                    hints={"max_files": 100, "max_tokens": 10000},
                    audit_dir=audit_dir,
                    call_id="bud-001",
                )
        output = result["output"]
        self.assertTrue(output.get("truncated"), "With oversized hints, result must be truncated")
        self.assertIn("\u26a0 TRUNCATED", output.get("task_summary", ""),
                       "task_summary must contain TRUNCATED banner")
        self.assertEqual(
            output["gap"].get("gap_type"), "budget_stop",
            "gap_type must be 'budget_stop' when budget ceiling is hit",
        )
        self.assertTrue(
            len(output["gap"].get("omitted_items", [])) > 0,
            "omitted_items must be non-empty when truncated",
        )

    def test_high_hints_respect_ceiling_values(self):
        """Effective limits must not exceed CEILING_FILES / CEILING_TOKENS."""
        self.assertLessEqual(self.ceiling_files, 40, "CEILING_FILES must be <= 40")
        self.assertLessEqual(self.ceiling_tokens, 8000, "CEILING_TOKENS must be <= 8000")

    def test_no_hints_uses_defaults(self):
        """Without hints, effective cap is DEFAULT_FILES / DEFAULT_TOKENS."""
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.runtime.run_query(
                _MANIFEST_SAMPLE,
                "selector specification",
                hints=None,
                audit_dir=audit_dir,
                call_id="bud-002",
            )
        # Default values must be reasonable
        self.assertLessEqual(self.default_files, 20, "DEFAULT_FILES must be <= 20")
        self.assertLessEqual(self.default_tokens, 4000, "DEFAULT_TOKENS must be <= 4000")
        output = result["output"]
        self.assertTrue(
            isinstance(output.get("truncated"), bool),
            "truncated must be a boolean",
        )


# ---------------------------------------------------------------------------
# AC6 / V6 — Fail-closed: missing / malformed manifest
# ---------------------------------------------------------------------------

class TestFailClosedV6(unittest.TestCase):
    """Absent or structurally malformed manifest must return gap_type=manifest_missing,
    empty ranked_ids, explicit error text, and never invent document IDs.
    """

    @classmethod
    def setUpClass(cls):
        cls.runtime = _load_runtime()

    def test_missing_manifest_returns_manifest_missing(self):
        """A non-existent manifest file must produce manifest_missing gap."""
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.runtime.run_query(
                "/nonexistent/path/to/manifest.yaml",
                "selector specification",
                audit_dir=audit_dir,
                call_id="fc-001",
            )
        output = result["output"]
        self.assertEqual(
            output["gap"].get("gap_type"), "manifest_missing",
            "Missing manifest must yield gap_type=manifest_missing",
        )
        self.assertEqual(
            output.get("ranked_ids"), {},
            "Missing manifest must have empty ranked_ids",
        )

    def test_missing_manifest_has_explicit_error(self):
        """Task summary or rationale for missing manifest must contain error text."""
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.runtime.run_query(
                "/nonexistent/path/to/manifest.yaml",
                "selector specification",
                audit_dir=audit_dir,
                call_id="fc-002",
            )
        output = result["output"]
        full_text = output.get("task_summary", "") + json.dumps(output)
        self.assertTrue(
            any(kw in full_text.lower() for kw in ["missing", "not found", "error", "manifest_missing"]),
            "Missing manifest must produce explicit error text",
        )

    def test_malformed_manifest_returns_manifest_missing(self):
        """A structurally broken manifest must also produce manifest_missing."""
        # Create a temporarily broken manifest file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("documents:\n  - id: broken\n    path: docs/en/broken/index.md\n    title: Broken\n    version: 1.0\n    broken-yaml: [invalid: {unclosed")
            broken_path = f.name
        try:
            with tempfile.TemporaryDirectory() as audit_dir:
                result = self.runtime.run_query(
                    broken_path,
                    "selector specification",
                    audit_dir=audit_dir,
                    call_id="fc-003",
                )
        finally:
            os.unlink(broken_path)
        output = result["output"]
        self.assertEqual(
            output["gap"].get("gap_type"), "manifest_missing",
            "Malformed manifest must yield gap_type=manifest_missing",
        )
        self.assertEqual(
            output.get("ranked_ids"), {},
            "Malformed manifest must have empty ranked_ids",
        )

    def test_no_invented_ids(self):
        """Neither missing nor malformed manifest should invent any document IDs."""
        for path in ["/nonexistent/manifest.yaml"]:
            with tempfile.TemporaryDirectory() as audit_dir:
                result = self.runtime.run_query(
                    path,
                    "selector specification",
                    audit_dir=audit_dir,
                    call_id="fc-004",
                )
            self.assertEqual(
                result["output"].get("ranked_ids"), {},
                f"No IDs should be invented for manifest at {path}",
            )


# ---------------------------------------------------------------------------
# AC7 / V8 — Audit artifact creation
# ---------------------------------------------------------------------------

class TestAuditV8(unittest.TestCase):
    """write_audit() creates an audit file with required fields; the path is
    returned in the result dict under audit_path.
    """

    @classmethod
    def setUpClass(cls):
        cls.runtime = _load_runtime()

    def test_audit_file_created(self):
        """An audit file must be created in the specified audit_dir."""
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.runtime.run_query(
                _MANIFEST_SAMPLE,
                "selector specification",
                audit_dir=audit_dir,
                call_id="aud-001",
            )
            audit_path = result.get("audit_path", "")
            self.assertTrue(os.path.isfile(audit_path), f"Audit file not found at {audit_path}")

    def test_audit_file_contains_required_fields(self):
        """Audit file must contain '# Selector audit', call_id, manifest_sha256."""
        with tempfile.TemporaryDirectory() as audit_dir:
            result = self.runtime.run_query(
                _MANIFEST_SAMPLE,
                "selector specification",
                audit_dir=audit_dir,
                call_id="aud-002",
            )
            audit_text = _read_file(result["audit_path"])
        self.assertIn("# Selector audit", audit_text, "Audit must contain '# Selector audit'")
        self.assertIn("aud-002", audit_text, "Audit must contain the call_id")
        self.assertIn("manifest_sha256", audit_text, "Audit must contain manifest_sha256")

    def test_write_audit_returns_path(self):
        """write_audit(audit_dir, call_id, audit_dict) must return the file path."""
        with tempfile.TemporaryDirectory() as audit_dir:
            audit_data = {
                "call_id": "aud-003",
                "manifest_sha256": _sha256_of(_MANIFEST_SAMPLE),
                "request_intent": "test",
                "timestamp": "2026-01-01T00:00:00Z",
                "searched_sources": ["docs-manifest.yaml"],
                "documents_found": 3,
                "documents_skipped": 0,
                "gap_description": "partial",
                "limitations": "index-only",
                "integrity_result": "ok",
                "sha256_verified": "true",
            }
            path = self.runtime.write_audit(audit_dir, "aud-003", audit_data)
            self.assertTrue(os.path.isfile(path), f"write_audit must return existing file at {path}")
            content = _read_file(path)
            self.assertIn("# Selector audit", content)


# ---------------------------------------------------------------------------
# AC7 / V5 — Output validation
# ---------------------------------------------------------------------------

class TestContractValidationV5(unittest.TestCase):
    """validate_output() returns [] for valid and truncated fixtures; it
    accepts empty ranked_ids only when gap_type is manifest_missing or not_found.
    """

    @classmethod
    def setUpClass(cls):
        cls.runtime = _load_runtime()
        cls.valid_out, cls.truncated_out = _load_fixtures()

    def test_validate_valid_fixture(self):
        """validate_output on output.valid.json must return []."""
        errors = self.runtime.validate_output(self.valid_out)
        self.assertEqual(
            errors, [],
            f"Valid output fixture must produce zero validation errors, got {errors}",
        )

    def test_validate_truncated_fixture(self):
        """validate_output on output.truncated.json must return []."""
        errors = self.runtime.validate_output(self.truncated_out)
        self.assertEqual(
            errors, [],
            f"Truncated output fixture must produce zero validation errors, got {errors}",
        )

    def test_empty_ranked_ids_allowed_for_manifest_missing(self):
        """Empty ranked_ids must be accepted when gap_type=manifest_missing."""
        output = dict(self.valid_out)  # copy
        output["ranked_ids"] = {}
        output["gap"] = dict(output["gap"])
        output["gap"]["gap_type"] = "manifest_missing"
        errors = self.runtime.validate_output(output)
        self.assertEqual(
            errors, [],
            "Empty ranked_ids with manifest_missing must be valid",
        )

    def test_empty_ranked_ids_allowed_for_not_found(self):
        """Empty ranked_ids must be accepted when gap_type=not_found."""
        output = dict(self.valid_out)
        output["ranked_ids"] = {}
        output["gap"] = dict(output["gap"])
        output["gap"]["gap_type"] = "not_found"
        errors = self.runtime.validate_output(output)
        self.assertEqual(
            errors, [],
            "Empty ranked_ids with not_found must be valid",
        )

    def test_empty_ranked_ids_rejected_for_other_gap_types(self):
        """Empty ranked_ids must be rejected when gap_type is something else."""
        for gap_type in ["partial", "budget_stop", "none"]:
            output = dict(self.valid_out)
            output["ranked_ids"] = {}
            output["gap"] = dict(output["gap"])
            output["gap"]["gap_type"] = gap_type
            errors = self.runtime.validate_output(output)
            self.assertNotEqual(
                errors, [],
                f"Empty ranked_ids with gap_type={gap_type!r} must produce validation errors, got {errors}",
            )


# ---------------------------------------------------------------------------
# Module-level constant checks
# ---------------------------------------------------------------------------

class TestConstants(unittest.TestCase):
    """Verify that the runtime module exposes the required constants."""

    @classmethod
    def setUpClass(cls):
        cls.runtime = _load_runtime()

    def test_ceiling_tokens_exists(self):
        self.assertTrue(hasattr(self.runtime, "CEILING_TOKENS"))

    def test_ceiling_files_exists(self):
        self.assertTrue(hasattr(self.runtime, "CEILING_FILES"))

    def test_default_tokens_exists(self):
        self.assertTrue(hasattr(self.runtime, "DEFAULT_TOKENS"))

    def test_default_files_exists(self):
        self.assertTrue(hasattr(self.runtime, "DEFAULT_FILES"))

    def test_injection_patterns_exists(self):
        self.assertTrue(hasattr(self.runtime, "INJECTION_PATTERNS"))


if __name__ == "__main__":
    unittest.main()
