"""Postcondition tests for the Selector fail-closed path (critical fix C2).

A malformed / unavailable manifest must produce an output that passes BOTH
contract validators (Layer 1 ``validate_output`` and Layer 2
``validate_output_v2``).  Previously the generator mapped every non-"not
found"/"empty" error to ``gap_type="conflict"`` with empty ``facts`` and
``ranked_ids``, which both validators reject.

Tests load the runtime modules through importlib, matching the adapter path.
"""
import importlib.util
import os
import pathlib
import tempfile
import unittest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_RUNTIME_DIR = _ROOT / ".agents" / "skills" / "selector" / "runtime"
_LAYER2_DIR = _ROOT / ".agents" / "skills" / "selector" / "layer2"
_FIXTURE_MANIFEST = str(
    _ROOT / ".agents" / "skills" / "selector" / "fixtures" / "manifest.sample.yaml"
)


def _load(name, path, subs=None):
    spec = importlib.util.spec_from_file_location(name, str(path), submodule_search_locations=subs)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    os.sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _FailClosedBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Preload Layer 1, as layer2_adapter does — this is the documented path.
        cls.runtime = _load("selector_runtime", _RUNTIME_DIR / "selector_runtime.py")
        cls.layer2 = _load(
            "selector_layer2", _LAYER2_DIR / "selector_layer2.py", subs=[str(_LAYER2_DIR)]
        )

    def _run(self, manifest_path):
        return self.layer2.run_query(
            manifest_path,
            "selector specification",
            call_id="failclosed-test",
            repo_root=str(_ROOT),
        )

    def assert_clean_fail_closed(self, result, expected_kind):
        output = result["output"]
        audit = result["audit"]
        gap = output["gap"]
        self.assertEqual(gap["gap_type"], "manifest_missing")
        self.assertEqual(gap.get("error_kind"), expected_kind)
        self.assertEqual(audit.get("error_kind"), expected_kind)
        self.assertEqual(output["ranked_ids"], {})
        self.assertEqual(output["facts"], [])
        self.assertEqual(self.runtime.validate_output(output), [])
        self.assertEqual(self.layer2.validate_output_v2(output), [])
        self.assertEqual(audit.get("validation_errors"), [])


class TestParseError(_FailClosedBase):
    def test_malformed_yaml_is_manifest_missing_with_parse_error_kind(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "broken.yaml")
            with open(path, "w", encoding="utf-8") as f:
                f.write("documents: [unclosed\n")
            self.assert_clean_fail_closed(self._run(path), "parse_error")


class TestUnavailableManifest(_FailClosedBase):
    def test_missing_file(self):
        self.assert_clean_fail_closed(
            self._run("/nonexistent/selector-manifest.yaml"), "not_found"
        )

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "empty.yaml")
            with open(path, "w", encoding="utf-8") as f:
                f.write("")
            self.assert_clean_fail_closed(self._run(path), "empty")


class TestNormalPathPostcondition(_FailClosedBase):
    def test_valid_manifest_has_no_postcondition_errors(self):
        result = self._run(_FIXTURE_MANIFEST)
        self.assertEqual(result["audit"].get("validation_errors"), [])


if __name__ == "__main__":
    unittest.main()
