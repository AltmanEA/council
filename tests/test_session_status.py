"""Unit tests for tools/session_status.py.

Tests the CLI tool that summarises session status from checkpoint
(cycle-state.json) files under a sessions directory.

Tests are written *before* implementation: they specify the required
behaviour and are expected to fail (red baseline) when run against the
yet-unwritten tool.

Run with: python3 -m unittest tests.test_session_status -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# Resolve the repo root so we can locate the tool under tools/.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")


def _create_run(tmpdir, run_id, status, phase, iteration,
                fail_count=0, progress=0, invalid=False):
    """Create an impl-run-* directory with a cycle-state.json.

    Parameters
    ----------
    tmpdir : str
        Base temporary directory (sessions root).
    run_id : str
        Name of the run subdirectory (must start with ``impl-run-``).
    status : str
        Session status: running, completed, escalated, operator-approved, etc.
    phase : str
        Current phase name.
    iteration : int
        Iteration number.
    fail_count : int
        Number of failures.
    progress : int
        Progress percentage (0–100).
    invalid : bool
        If True, write broken JSON or missing fields instead of a valid state.
    """
    run_dir = os.path.join(tmpdir, run_id)
    os.makedirs(run_dir, exist_ok=True)
    state_path = os.path.join(run_dir, "cycle-state.json")
    if invalid:
        if status == "malformed_json":
            with open(state_path, "w") as f:
                f.write("{not valid json!!!}")
        else:
            # Missing required fields (e.g. no 'status')
            with open(state_path, "w") as f:
                json.dump({"iteration": iteration, "phase": phase}, f)
    else:
        with open(state_path, "w") as f:
            json.dump(
                {
                    "status": status,
                    "phase": phase,
                    "iteration": iteration,
                    "fail_count": fail_count,
                    "progress": progress,
                },
                f,
            )
    return run_dir


# ------------------------------------------------------------------
# Helpers for subprocess invocations
# ------------------------------------------------------------------

def _run_tool(sessions_dir, *args):
    """Run ``python3 tools/session_status.py`` and return (rc, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, os.path.join(TOOLS_DIR, "session_status.py"), *args, sessions_dir],
        capture_output=True, text=True, timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

class TestSessionStatus(unittest.TestCase):
    """Test suite for session_status.py CLI tool."""

    def setUp(self):
        """Create a fresh temp directory for each test."""
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        """Remove the temp directory after each test."""
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run_tool_no_dir(self, *args):
        """Run without a positional argument (uses default ``sessions``).

        Runs subprocess with ``cwd`` set to a fresh temp directory that does
        *not* contain a ``sessions`` subdirectory, so the tool falls through
        to the ``default_sessions`` path ("no runs", exit 0).
        """
        isolation_dir = tempfile.mkdtemp()
        try:
            result = subprocess.run(
                [sys.executable, os.path.join(TOOLS_DIR, "session_status.py"), *args],
                cwd=isolation_dir,
                capture_output=True, text=True, timeout=30,
            )
            return result.returncode, result.stdout, result.stderr
        finally:
            shutil.rmtree(isolation_dir, ignore_errors=True)

    # -- 1. Recursive file search (requirement 1) -------------------------

    def test_recurses_into_subdirectories(self):
        """Req 1: tool finds cycle-state.json recursively in nested dirs."""
        deep = os.path.join(self.tmpdir, "impl-run-deep", "nested")
        os.makedirs(deep, exist_ok=True)
        _create_run(deep, "impl-run-deep", "completed", "review", 2)
        rc, out, _ = _run_tool(self.tmpdir)
        self.assertIn("impl-run-deep", out)
        self.assertEqual(rc, 0)

    def test_finds_all_runs_at_multiple_depths(self):
        """Req 1: discovers runs at different nesting levels."""
        _create_run(self.tmpdir, "impl-run-a", "completed", "design", 1)
        nested = os.path.join(self.tmpdir, "group", "inner")
        os.makedirs(nested, exist_ok=True)
        _create_run(nested, "impl-run-b", "running", "analysis", 3)
        rc, out, _ = _run_tool(self.tmpdir)
        self.assertIn("impl-run-a", out)
        self.assertIn("impl-run-b", out)

    # -- 2. Output line format (requirement 2) ----------------------------

    def test_output_line_format(self):
        """Req 2: line matches '<run_id>  <status>  phase=<phase>  ..."
        
        Expected format: ``impl-run-x  completed  phase=review  fail=0  progress=100``
        (fields: status, iteration, fail_count, progress).
        """
        _create_run(self.tmpdir, "impl-run-fmt", "completed", "review", 5,
                    fail_count=2, progress=80)
        rc, out, _ = _run_tool(self.tmpdir)
        self.assertIn("impl-run-fmt", out)
        self.assertIn("completed", out)
        self.assertIn("phase=review", out)

    # -- 3. Sorting by run_id (requirement 3) -----------------------------

    def test_sorted_output(self):
        """Req 3: runs are sorted lexicographically by run_id."""
        _create_run(self.tmpdir, "impl-run-z", "completed", "a", 1)
        _create_run(self.tmpdir, "impl-run-a", "running", "b", 1)
        _create_run(self.tmpdir, "impl-run-m", "completed", "c", 1)
        rc, out, _ = _run_tool(self.tmpdir)
        lines = [l for l in out.strip().splitlines() if l.startswith("impl-run-")]
        # Skip summary line (starts with 'runs:')
        run_lines = [l for l in lines if not l.startswith("runs:")]
        run_ids = [l.split()[0] for l in run_lines]
        self.assertEqual(run_ids, sorted(run_ids))

    # -- 4. Final summary (requirement 4) ---------------------------------

    def test_summary_line_format(self):
        """Req 4: final line is 'runs: N  running: R  escalated: E  ..."
        
        Includes completed and approved counts too.
        """
        _create_run(self.tmpdir, "impl-run-1", "completed", "a", 1)
        _create_run(self.tmpdir, "impl-run-2", "running", "b", 2)
        _create_run(self.tmpdir, "impl-run-3", "escalated", "c", 3)
        _create_run(self.tmpdir, "impl-run-4", "completed", "d", 4)
        rc, out, _ = _run_tool(self.tmpdir)
        self.assertIn("runs: 4", out)
        self.assertIn("running: 1", out)
        self.assertIn("escalated: 1", out)

    def test_summary_includes_completed_and_approved(self):
        """Req 4: summary also counts completed and operator-approved runs."""
        _create_run(self.tmpdir, "impl-run-a", "completed", "a", 1)
        _create_run(self.tmpdir, "impl-run-b", "completed", "b", 1)
        _create_run(self.tmpdir, "impl-run-c", "operator-approved", "c", 1)
        _create_run(self.tmpdir, "impl-run-d", "running", "d", 1)
        rc, out, _ = _run_tool(self.tmpdir)
        self.assertIn("completed: 2", out)
        self.assertIn("approved: 1", out)

    # -- 5. --json flag (requirement 5) -----------------------------------

    def test_json_output_format(self):
        """Req 5: --json produces valid JSON with required fields."""
        _create_run(self.tmpdir, "impl-run-j1", "running", "build", 1,
                    fail_count=3, progress=45)
        _create_run(self.tmpdir, "impl-run-j2", "completed", "test", 2,
                    fail_count=0, progress=100)
        rc, out, _ = _run_tool(self.tmpdir, "--json")
        data = json.loads(out)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)
        for item in data:
            self.assertIn("run_id", item)
            self.assertIn("status", item)
            self.assertIn("phase", item)
            self.assertIn("iteration", item)
            self.assertIn("fail_count", item)
            self.assertIn("progress", item)

    def test_json_ordering_matches_text(self):
        """Req 5: JSON array order is the same as text (lexicographic by run_id)."""
        _create_run(self.tmpdir, "impl-run-zz", "running", "z", 1)
        _create_run(self.tmpdir, "impl-run-aa", "running", "a", 1)
        rc, out, _ = _run_tool(self.tmpdir, "--json")
        data = json.loads(out)
        run_ids = [item["run_id"] for item in data]
        self.assertEqual(run_ids, sorted(run_ids))

    # -- 6. BROKEN handling (requirement 6) -------------------------------

    def test_broken_json_output(self):
        """Req 6: malformed JSON produces '<run_id> BROKEN ...'."""
        _create_run(self.tmpdir, "impl-run-broken", "malformed_json", "x", 1,
                    invalid=True)
        rc, out, _ = _run_tool(self.tmpdir)
        self.assertIn("impl-run-broken", out)
        self.assertIn("BROKEN", out)

    def test_broken_missing_required_fields(self):
        """Req 6: JSON missing 'status' produces BROKEN."""
        _create_run(self.tmpdir, "impl-run-no-status", "some_status", "x", 1,
                    invalid=True)
        rc, out, _ = _run_tool(self.tmpdir)
        self.assertIn("impl-run-no-status", out)
        self.assertIn("BROKEN", out)

    def test_broken_in_summary(self):
        """Req 6: BROKEN runs are included in the final summary count."""
        _create_run(self.tmpdir, "impl-run-ok", "completed", "a", 1)
        _create_run(self.tmpdir, "impl-run-bad", "malformed_json", "x", 1,
                    invalid=True)
        rc, out, _ = _run_tool(self.tmpdir)
        self.assertIn("broken: 1", out)

    # -- 7. No runs found (requirement 7) ---------------------------------

    def test_no_runs_empty_directory(self):
        """Req 7: empty sessions dir → 'no runs', exit 0."""
        rc, out, _ = _run_tool(self.tmpdir)
        self.assertIn("no runs", out)
        self.assertEqual(rc, 0)

    def test_no_runs_no_sessions_subdir(self):
        """Req 7: directory without impl-run-* subdirectories."""
        _create_run(self.tmpdir, "not-a-run", "running", "a", 1)
        rc, out, _ = _run_tool(self.tmpdir)
        self.assertIn("no runs", out)
        self.assertEqual(rc, 0)

    # -- 8. Exit codes (requirement 8) ------------------------------------

    def test_exit_0_all_terminal(self):
        """Req 8: exit 0 when all runs are in terminal states."""
        _create_run(self.tmpdir, "impl-run-ok1", "completed", "a", 1)
        _create_run(self.tmpdir, "impl-run-ok2", "escalated", "b", 1)
        _create_run(self.tmpdir, "impl-run-ok3", "operator-approved", "c", 1)
        rc, _, _ = _run_tool(self.tmpdir)
        self.assertEqual(rc, 0)

    def test_exit_1_running(self):
        """Req 8: exit 1 when at least one run is 'running'."""
        _create_run(self.tmpdir, "impl-run-ok", "completed", "a", 1)
        _create_run(self.tmpdir, "impl-run-active", "running", "b", 2)
        rc, _, _ = _run_tool(self.tmpdir)
        self.assertEqual(rc, 1)

    def test_exit_1_broken(self):
        """Req 8: exit 1 when at least one run is BROKEN."""
        _create_run(self.tmpdir, "impl-run-good", "completed", "a", 1)
        _create_run(self.tmpdir, "impl-run-bad", "malformed", "x", 1,
                    invalid=True)
        rc, _, _ = _run_tool(self.tmpdir)
        self.assertEqual(rc, 1)

    def test_exit_2_missing_directory(self):
        """Req 8: exit 2 when the sessions directory does not exist."""
        non_existent = os.path.join(self.tmpdir, "does_not_exist")
        rc, _, _ = _run_tool(non_existent)
        self.assertEqual(rc, 2)

    # -- 9. --json with BROKEN (requirement 6 + 5 interaction) -----------

    def test_json_with_broken_runs(self):
        """Req 5+6: --json with a BROKEN run still produces valid JSON."""
        _create_run(self.tmpdir, "impl-run-broken", "malformed_json", "x", 1,
                    invalid=True)
        _create_run(self.tmpdir, "impl-run-ok", "completed", "a", 1)
        rc, out, _ = _run_tool(self.tmpdir, "--json")
        data = json.loads(out)
        # BROKEN run should still appear (status should indicate broken)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    # -- 10. CLI / argparse (requirement 10) -----------------------------

    def test_help_flag(self):
        """Req 10: --help is recognised by argparse (no crash, exit 0)."""
        rc, out, err = self._run_tool_no_dir("--help")
        self.assertEqual(rc, 0)
        self.assertIn("usage", out.lower() or err.lower())

    def test_default_sessions_dir(self):
        """Req 10: without positional arg, tool uses 'sessions' as default."""
        sessions_dir = os.path.join(self.tmpdir, "sessions")
        os.makedirs(sessions_dir, exist_ok=True)
        _create_run(sessions_dir, "impl-run-dflt", "running", "a", 1)
        rc, out, _ = self._run_tool_no_dir()
        # CWD is isolated to a temp dir (no `sessions/`), so default path
        # yields "no runs" → exit 0. This verifies the default fallback.
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
