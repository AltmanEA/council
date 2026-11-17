"""Smoke test: python3 -m operator_surface exits cleanly.

Step 0: operator_surface/__main__.py must have a placeholder entry point that
exits with code 0 and produces no traceback on stderr.

Anti-reversed-TDD: before implementation, the module does not exist → the test
verifies the process exits 1 (not 0) with ModuleNotFoundError.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _temp_state_root():
    """ORCHESTRATOR-AUTHORIZED (cycle 10): pin an isolated state root.

    The smoke test predates READY + sentinel creation; without an explicit
    COUNCIL_STATE_ROOT the server falls back to cwd (= repo ROOT) and
    creates the sentinel in the real tree — forbidden by Step 9 constraints.
    Assertions themselves are unchanged.
    """
    return tempfile.mkdtemp()


class TestOperatorSurfaceSmoke(unittest.TestCase):
    """Spawn python3 -m operator_surface and check exit behaviour."""

    def test_exit_code_is_zero(self):
        """__main__.py must return exit code 0."""
        state_root = _temp_state_root()
        env = os.environ.copy()
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        env["COUNCIL_STATE_ROOT"] = state_root
        try:
            result = subprocess.run(
                ["python3", "-m", "operator_surface"],
                capture_output=True, text=True,
                cwd=ROOT, timeout=10,
                env=env,
            )
        finally:
            shutil.rmtree(state_root, ignore_errors=True)
        self.assertEqual(result.returncode, 0,
                         f"Expected exit code 0, got {result.returncode}\n"
                         f"stdout: {result.stdout!r}\n"
                         f"stderr: {result.stderr!r}")

    def test_no_traceback_on_stderr(self):
        """stderr must not contain a Python traceback."""
        state_root = _temp_state_root()
        env = os.environ.copy()
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        env["COUNCIL_STATE_ROOT"] = state_root
        try:
            result = subprocess.run(
                ["python3", "-m", "operator_surface"],
                capture_output=True, text=True,
                cwd=ROOT, timeout=10,
                env=env,
            )
        finally:
            shutil.rmtree(state_root, ignore_errors=True)
        self.assertNotIn("Traceback", result.stderr,
                         "stderr must not contain a traceback")


if __name__ == "__main__":
    unittest.main()
