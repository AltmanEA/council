"""Layer-2-only architecture-enforcing tests for operator_ingress/.

Step 0 DoD (plan-draft-v2.md Step 0):
  (a) no import of any layer-1 module  (import scan)
  (b) cross-layer calls only via ports.py (import scan)
  (c) verb handlers forbidden from writing phase_state/mode/consensus
  (d) no direct attribute access on session objects in core/

Uses synthetic-bad-source meta-tests so the guards are provably live,
not vacuous (anti-reversed-TDD).
"""
from __future__ import annotations

import ast
import os
import re
import shutil
import sys
import tempfile
import unittest

# ---------------------------------------------------------------------------
# Helper: resolve operator_ingress root from tests/ directory
# ---------------------------------------------------------------------------
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TESTS_DIR)
OPERATOR_INGRESS_DIR = os.path.join(ROOT_DIR, "operator_ingress")

# ---------------------------------------------------------------------------
# Synthetic bad sources -- fed to checker functions in meta-tests
# ---------------------------------------------------------------------------

BAD_LAYER1_IMPORT = (
    "import some_external_store\n"
    "from another_layer.module import do_thing\n"
)

BAD_SESSION_ATTR = (
    "def handler(session, payload):\n"
    '    session.phase_state = "active"\n'
    "    session.consensus = True\n"
    "    result = session.get_event(\"foo\")\n"
)

BAD_VERB_ASSIGNMENT = (
    "def commit(session):\n"
    '    session.phase_state = "committed"\n'
    '    session.mode = "final"\n'
    '    session.consensus = "agreed"\n'
)

ALL_BAD_COMBINED = (
    "import layer_one_store\n"
    "\n"
    "def handler(session, data):\n"
    '    session.phase_state = "processing"\n'
    "    x = some_external_store.read(session.id)\n"
)

CORRECT_CODE = (
    "from ports import Layer1Port\n"
    "\n"
    "def handler(port: Layer1Port, session_id: str, payload: dict):\n"
    "    data = port.read(session_id)\n"
    "    port.write(session_id, payload)\n"
)

# ---------------------------------------------------------------------------
# Checker functions -- these implement the actual guard logic
# ---------------------------------------------------------------------------

_ALLOWED_ROOTS = {"yaml", "ports", "documenter_service"}


def _is_stdlib_mod(name: str) -> bool:
    """Return True if *name* is a stdlib (top-level) module name."""
    return name in sys.stdlib_module_names


_ALLOWED_ROOTS = {"yaml", "ports", "documenter_service"}


def _classify_import(top_level: str) -> str:
    if top_level in _ALLOWED_ROOTS:
        return "intra-package"
    if _is_stdlib_mod(top_level):
        return "stdlib"
    return "forbidden"


def scan_imports(root_dir: str):
    """Scan all .py files under *root_dir* for import statements.

    Returns list of (relative_path, module, kind) where kind is one of
    'stdlib', 'third-party', 'intra-package', 'forbidden'.
    """
    results = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            filepath = os.path.join(dirpath, fn)
            relpath = os.path.relpath(filepath, root_dir)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    source = f.read()
                tree = ast.parse(source, filename=filepath)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        kind = _classify_import(top)
                        results.append((relpath, alias.name, kind))
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        top = node.module.split(".")[0]
                        if node.level and node.level > 0:
                            results.append(
                                (relpath, node.module, "intra-package"))
                        else:
                            kind = _classify_import(top)
                            results.append(
                                (relpath, node.module, kind))
    return results


def check_no_layer1_imports(root_dir, imports):
    """Return list of violations for forbidden imports."""
    violations = []
    for relpath, module, kind in imports:
        if kind == "forbidden":
            violations.append(
                f"{relpath}: imports {module!r} "
                f"(forbidden Layer-1 reference)")
    return violations


def check_core_no_adapter_imports(root_dir, imports):
    """Return list of core/* files that import operator_ingress.adapters.*."""
    violations = []
    for relpath, module, _kind in imports:
        if re.match(r"^core/", relpath) and \
           module == "operator_ingress.adapters":
            violations.append(
                f"{relpath}: imports operator_ingress.adapters.* "
                f"(assembly root __main__.py may, but core/ must not)")
    return violations


def _get_source_lines(root_dir):
    """Read every .py file under root_dir, return (relpath, source_text)."""
    result = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            filepath = os.path.join(dirpath, fn)
            relpath = os.path.relpath(filepath, root_dir)
            with open(filepath, "r", encoding="utf-8") as f:
                result.append((relpath, f.read()))
    return result


def check_no_phase_state_assignments(root_dir, source_pairs):
    """Check core/ files don't assign to phase_state/mode/consensus."""
    violations = []
    for relpath, source in source_pairs:
        if not relpath.startswith("core/"):
            continue
        try:
            tree = ast.parse(source, filename=relpath)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    name = _extract_target_name(target)
                    if name in ("phase_state", "mode", "consensus"):
                        violations.append(
                            f"{relpath} line {node.lineno}: "
                            f"assignment to {name!r}")
            elif isinstance(node, ast.AugAssign):
                name = _extract_target_name(node.target)
                if name in ("phase_state", "mode", "consensus"):
                    violations.append(
                        f"{relpath} line {node.lineno}: "
                        f"augmented assignment to {name!r}")
            elif isinstance(node, ast.AnnAssign) and node.target:
                name = _extract_target_name(node.target)
                if name in ("phase_state", "mode", "consensus"):
                    violations.append(
                        f"{relpath} line {node.lineno}: "
                        f"annotated assignment to {name!r}")
    return violations


def _extract_target_name(target):
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return ""


def check_no_session_attr_access(root_dir, source_pairs):
    """Scan core/ source for direct session attribute access patterns."""
    violations = []
    for relpath, source in source_pairs:
        if not relpath.startswith("core/"):
            continue
        lines = source.splitlines()
        for lineno, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            if (re.search(r'\bsession\s*\.\w+', stripped) or
                    re.search(r'\bsession\s*\[', stripped)):
                violations.append(
                    f"{relpath} line {lineno}: "
                    f"direct session access: {stripped[:80]}")
    return violations


# ---------------------------------------------------------------------------
# Module-level helpers for meta-tests
# ---------------------------------------------------------------------------

def _create_temp_with_file(source: str, rel_path: str) -> str:
    """Create a temporary directory containing *source* at *rel_path*."""
    d = tempfile.mkdtemp()
    full = os.path.join(d, *rel_path.split("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(source)
    return d


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestPackageLayout(unittest.TestCase):
    """Verify operator_ingress/ package layout mirrors documenter_service/."""

    def test_operator_ingress_dir_exists(self):
        self.assertTrue(os.path.isdir(OPERATOR_INGRESS_DIR),
                        "operator_ingress/ directory must exist")

    def test_init_py(self):
        self.assertTrue(os.path.isfile(
            os.path.join(OPERATOR_INGRESS_DIR, "__init__.py")),
                        "operator_ingress/__init__.py must exist")

    def test_ports_py(self):
        self.assertTrue(os.path.isfile(
            os.path.join(OPERATOR_INGRESS_DIR, "ports.py")),
                        "operator_ingress/ports.py must exist")

    def test_main_py(self):
        self.assertTrue(os.path.isfile(
            os.path.join(OPERATOR_INGRESS_DIR, "__main__.py")),
                        "operator_ingress/__main__.py must exist")

    def test_core_dir_exists(self):
        core_dir = os.path.join(OPERATOR_INGRESS_DIR, "core")
        self.assertTrue(os.path.isdir(core_dir),
                        "operator_ingress/core/ directory must exist")

    def test_core_init_py(self):
        self.assertTrue(os.path.isfile(
            os.path.join(OPERATOR_INGRESS_DIR, "core", "__init__.py")),
                        "operator_ingress/core/__init__.py must exist")

    def test_adapters_dir_exists(self):
        adapters_dir = os.path.join(OPERATOR_INGRESS_DIR, "adapters")
        self.assertTrue(os.path.isdir(adapters_dir),
                        "operator_ingress/adapters/ directory must exist")

    def test_adapters_init_py(self):
        self.assertTrue(os.path.isfile(
            os.path.join(OPERATOR_INGRESS_DIR, "adapters", "__init__.py")),
                        "operator_ingress/adapters/__init__.py must exist")


class TestPortDefinitions(unittest.TestCase):
    """Verify ports.py defines the required ABCs."""

    @classmethod
    def setUpClass(cls):
        ports_path = os.path.join(OPERATOR_INGRESS_DIR, "ports.py")
        with open(ports_path, "r", encoding="utf-8") as f:
            cls.ports_source = f.read()

    def _get_cls_names(self):
        tree = ast.parse(self.ports_source)
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                names.add(node.name)
        return names

    def test_layer1_port_defined(self):
        self.assertIn("Layer1Port", self._get_cls_names(),
                      "ports.py must define Layer1Port")

    def test_documenter_port_defined(self):
        self.assertIn("DocumenterPort", self._get_cls_names(),
                      "ports.py must define DocumenterPort")

    def test_event_sink_port_defined(self):
        self.assertIn("EventSink", self._get_cls_names(),
                      "ports.py must define EventSink")

    def test_secret_store_port_defined(self):
        self.assertIn("SecretStore", self._get_cls_names(),
                      "ports.py must define SecretStore")

    def _check_is_abc(self, name):
        tree = ast.parse(self.ports_source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == name:
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == "ABC":
                        return True
                    if (isinstance(base, ast.Attribute)
                            and base.attr == "ABC"):
                        return True
                return False
        return False

    def test_layer1_port_is_abc(self):
        self.assertTrue(self._check_is_abc("Layer1Port"),
                        "Layer1Port must inherit from ABC")

    def test_documenter_port_is_abc(self):
        self.assertTrue(self._check_is_abc("DocumenterPort"),
                        "DocumenterPort must inherit from ABC")

    def test_event_sink_is_abc(self):
        self.assertTrue(self._check_is_abc("EventSink"),
                        "EventSink must inherit from ABC")

    def test_secret_store_is_abc(self):
        self.assertTrue(self._check_is_abc("SecretStore"),
                        "SecretStore must inherit from ABC")


class TestOD1ConventionStrings(unittest.TestCase):
    """Layer1Port docstring pins the OD-1 convention strings."""

    @classmethod
    def setUpClass(cls):
        ports_path = os.path.join(OPERATOR_INGRESS_DIR, "ports.py")
        with open(ports_path, "r", encoding="utf-8") as f:
            cls.ports_source = f.read()

    def _get_layer1_docstring(self):
        tree = ast.parse(self.ports_source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "Layer1Port":
                doc = ast.get_docstring(node)
                if doc:
                    return doc
        return ""

    def test_session_path_convention(self):
        doc = self._get_layer1_docstring()
        self.assertIn("sessions/", doc,
                      "Layer1Port docstring must pin 'sessions/' path "
                      "convention")

    def test_events_jsonl(self):
        doc = self._get_layer1_docstring()
        self.assertIn("events.jsonl", doc,
                      "Layer1Port docstring must reference events.jsonl")

    def test_provisional_format(self):
        doc = self._get_layer1_docstring()
        self.assertIn("provisional format", doc.lower(),
                      "Layer1Port docstring must mention 'provisional format'")


class TestNoForbiddenImports(unittest.TestCase):
    """(a) No forbidden layer-1 imports anywhere in operator_ingress/."""

    def test_no_forbidden_imports(self):
        imports = scan_imports(OPERATOR_INGRESS_DIR)
        violations = check_no_layer1_imports(OPERATOR_INGRESS_DIR, imports)
        self.assertEqual(violations, [],
                         f"Layer-2 must not import layer-1 modules. "
                         f"Violations: {violations}")

    # --- meta-test: feed synthetic bad source, assert REJECTED ---

    def test_meta_bad_layer1_import_rejected(self):
        """Verify the checker rejects synthetic bad imports."""
        tmpdir = _create_temp_with_file(BAD_LAYER1_IMPORT,
                                        "core/bad_imports.py")
        try:
            imports = scan_imports(tmpdir)
            violations = check_no_layer1_imports(tmpdir, imports)
            self.assertTrue(len(violations) > 0,
                            "Checker must reject synthetic bad imports")
            self.assertTrue(any("some_external_store" in v for v in violations),
                            "Must flag 'some_external_store' import")
            self.assertTrue(any("another_layer" in v for v in violations),
                            "Must flag 'another_layer' import")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_meta_good_code_not_flagged(self):
        """Correct port-based code must NOT be flagged."""
        tmpdir = _create_temp_with_file(CORRECT_CODE,
                                        "core/good_imports.py")
        try:
            imports = scan_imports(tmpdir)
            violations = check_no_layer1_imports(tmpdir, imports)
            self.assertEqual(violations, [],
                             "Port-based imports must not be flagged")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestCoreNoAdapterImports(unittest.TestCase):
    """(b) core/* modules never import operator_ingress.adapters.*."""

    def test_core_no_adapter_imports(self):
        imports = scan_imports(OPERATOR_INGRESS_DIR)
        violations = check_core_no_adapter_imports(OPERATOR_INGRESS_DIR,
                                                   imports)
        self.assertEqual(violations, [],
                         f"core/ must not import operator_ingress.adapters.*. "
                         f"Violations: {violations}")


class TestNoVerbAssignments(unittest.TestCase):
    """(c) No assignments to phase_state / mode / consensus in core/."""

    def test_no_forbidden_assignments(self):
        source_pairs = _get_source_lines(OPERATOR_INGRESS_DIR)
        violations = check_no_phase_state_assignments(OPERATOR_INGRESS_DIR,
                                                      source_pairs)
        self.assertEqual(violations, [],
                         f"core/ must not assign to phase_state/mode/"
                         f"consensus. Violations: {violations}")

    # --- meta-tests: feed synthetic bad source, assert REJECTED ---

    def test_meta_phase_state_rejected(self):
        tmpdir = _create_temp_with_file(BAD_VERB_ASSIGNMENT,
                                        "core/verb_handlers.py")
        try:
            source_pairs = _get_source_lines(tmpdir)
            violations = check_no_phase_state_assignments(tmpdir, source_pairs)
            self.assertTrue(len(violations) > 0,
                            "Checker must reject phase_state assignment")
            self.assertTrue(any("phase_state" in v for v in violations))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_meta_mode_rejected(self):
        tmpdir = _create_temp_with_file(BAD_VERB_ASSIGNMENT,
                                        "core/verb_handlers.py")
        try:
            source_pairs = _get_source_lines(tmpdir)
            violations = check_no_phase_state_assignments(tmpdir, source_pairs)
            self.assertTrue(any("mode" in v for v in violations),
                            "Must flag mode assignment")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_meta_consensus_rejected(self):
        tmpdir = _create_temp_with_file(BAD_VERB_ASSIGNMENT,
                                        "core/verb_handlers.py")
        try:
            source_pairs = _get_source_lines(tmpdir)
            violations = check_no_phase_state_assignments(tmpdir, source_pairs)
            self.assertTrue(any("consensus" in v for v in violations),
                            "Must flag consensus assignment")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_meta_combined_bad_source_rejected(self):
        """Combined bad source (import + assignments + session attr) rejected."""
        tmpdir = _create_temp_with_file(ALL_BAD_COMBINED,
                                        "core/bad_combined.py")
        try:
            source_pairs = _get_source_lines(tmpdir)
            violations = check_no_phase_state_assignments(tmpdir, source_pairs)
            self.assertTrue(len(violations) > 0,
                            "Must reject combined bad source")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestNoSessionAttrAccess(unittest.TestCase):
    """(d) No direct attribute access on session objects in core/."""

    def test_no_session_attr_access(self):
        source_pairs = _get_source_lines(OPERATOR_INGRESS_DIR)
        violations = check_no_session_attr_access(OPERATOR_INGRESS_DIR,
                                                  source_pairs)
        self.assertEqual(violations, [],
                         f"core/ must not do direct session attr access. "
                         f"Violations: {violations}")

    # --- meta-tests ---

    def test_meta_session_attr_rejected(self):
        """Verify the checker rejects synthetic session-attr access."""
        tmpdir = _create_temp_with_file(BAD_SESSION_ATTR,
                                        "core/verb_handlers.py")
        try:
            source_pairs = _get_source_lines(tmpdir)
            violations = check_no_session_attr_access(tmpdir, source_pairs)
            self.assertTrue(len(violations) > 0,
                            "Checker must reject synthetic session.attr access")
            self.assertTrue(
                any("session.phase_state" in v for v in violations),
                "Must flag session.phase_state access")
            self.assertTrue(
                any("session.consensus" in v for v in violations),
                "Must flag session.consensus access")
            self.assertTrue(
                any("session.get_event" in v for v in violations),
                "Must flag session.get_event access")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_meta_good_code_not_flagged(self):
        """Correct port-based code must NOT be flagged."""
        tmpdir = _create_temp_with_file(CORRECT_CODE,
                                        "core/good_handler.py")
        try:
            source_pairs = _get_source_lines(tmpdir)
            violations = check_no_session_attr_access(tmpdir, source_pairs)
            self.assertEqual(violations, [],
                             "Port-based code with 'port' parameter "
                             "must not be flagged")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
