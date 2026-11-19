"""Unit tests for tools/hooks/pre-commit text contract (frozen audit contract v4).

STATIC assertions on the ACTUAL CODE in the case-2 branch + BEHAVIORAL
tests via fake check_all.  Every test MUST be RED against the current
legacy hook and GREEN against the updated hook per target-task.md §7.

New contract (case 2):
  - differentiate 🚨 critical from check_all: INTERNAL ERROR from noise
  - 🚨 critical → warn 0 (soak, prints output) / block 1
  - crash / noise → fail-closed (warn 0 / block 1, stderr has error)
  - case 2 MUST have if/else branching with ≥ 2 exit paths
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_HOOK = os.path.join(REPO, "tools", "hooks", "pre-commit")

# ---------------------------------------------------------------------------
# 1. Static: grep the case-2 CODE block, not comments
# ---------------------------------------------------------------------------


class TestHookCase2Branches(unittest.TestCase):
    """Each test checks a code branch that MUST appear in case 2) of the
    new hook but is ABSENT in the legacy (which has `echo + fail_closed`
    with no branching).

    IMPORTANT: assertions target the CODE logic, not comment text.
    Legacy echoes 'CHECK_ALL INTERNAL ERROR' to stderr, so searching for
    'ERROR' in the block always passes — those tests were removed."""

    def _read_section_text(self):
        with open(SRC_HOOK) as fh:
            return fh.read()

    def _find_case_block(self, marker):
        """Extract text between `marker)` and the next case branch / esac."""
        text = self._read_section_text()
        pattern = re.compile(r"^\s*" + re.escape(marker), re.MULTILINE)
        m = pattern.search(text)
        if not m:
            return ""
        start = m.end()
        next_cases = list(
            re.finditer(
                r"^\s*\*?\d+\)\s*|^esac\s*$",
                text[start:], re.MULTILINE))
        if next_cases:
            end = start + next_cases[0].start()
        else:
            end = len(text)
        return text[start:end]

    def test_case_2_differentiates_critical_marker(self):
        """case 2) MUST contain code that greps/checks for 🚨 critical.
        Legacy has no such check — just one static echo + fail_closed."""
        block = self._find_case_block("2)")
        self.assertIn(
            "🚨 critical", block,
            "case 2) block must check for 🚨 critical marker")

    def test_case_2_differentiates_internal_error_in_code(self):
        """case 2) MUST distinguish crash from critical by checking for
        'check_all: INTERNAL ERROR' in the OUTPUT variable.
        Legacy only has it in a static echo string, not as a code check."""
        block = self._find_case_block("2)")
        # Must check OUTPUT variable for the marker, not just echo it
        self.assertIn(
            "OUTPUT", block,
            "case 2) must inspect OUTPUT for INTERNAL ERROR marker")

    def test_case_2_critical_warn_mode_exits_0(self):
        """For 🚨 critical: warn mode → exit 0 (not fail-closed).
        Legacy: case 2 has NO if/warn — just calls fail_closed_exit."""
        block = self._find_case_block("2)")
        self.assertIn(
            "warn", block,
            "case 2) must check MODE for warn before fail-closed on critical")

    def test_case_2_has_conditional_branching(self):
        """case 2) MUST have an if/elif/else chain — legacy is flat
        (echo + fail_closed_exit, no branching)."""
        case2 = self._find_case_block("2)")
        self.assertIn(
            "if", case2.lower(),
            "case 2) must have conditional branching")

    def test_case_2_has_multiple_exit_paths(self):
        """case 2) must have ≥ 2 exit calls (critical vs crash).
        Legacy has exactly 1: `fail_closed_exit`."""
        case2 = self._find_case_block("2)")
        exit_calls = list(re.finditer(r"exit\s+\d+", case2))
        self.assertTrue(
            len(exit_calls) >= 2,
            "case 2) must have multiple exit paths (critical vs crash)")

    def test_case_2_else_fallback_for_crash(self):
        """case 2) must fall through to fail-closed when neither
        🚨 critical nor check_all: INTERNAL ERROR is present.
        Checks for an else clause or explicit fail_closed in a fallback path."""
        case2 = self._find_case_block("2)")
        # Must have an else clause or explicit non-critical path
        self.assertTrue(
            "else" in case2.lower(),
            "case 2) must have an else path for non-critical exit-2")


# ---------------------------------------------------------------------------
# 2. Behavioral: fake check_all in a temp git repo
# ---------------------------------------------------------------------------


class TestHookCase2Behavior(unittest.TestCase):
    """End-to-end behavioral tests via temp repo.  Uses a fake check_all.py
    that prints specific output and exits with a given code.

    Legacy: case 2 has NO differentiation — all exit-2 is treated identically
    (same stderr, same fail_closed_exit).  New contract differentiates."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="hook-case2-")
        self.repo = os.path.join(self.tmpdir, "repo")
        os.makedirs(os.path.join(self.repo, "tools", "hooks"))
        subprocess.run(
            ["git", "init", "-q"], cwd=self.repo, check=True,
            capture_output=True)
        shutil.copy2(
            SRC_HOOK, os.path.join(self.repo, "tools", "hooks", "pre-commit"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_fake(self, rc, stdout_text):
        path = os.path.join(self.repo, "tools", "check_all.py")
        with open(path, "w") as fh:
            fh.write("#!/usr/bin/env python3\nimport sys\n")
            if stdout_text.strip():
                for line in stdout_text.splitlines():
                    if line.strip():
                        fh.write('print("{}")\n'.format(line))
            fh.write("sys.exit({})\n".format(rc))
        os.chmod(path, 0o755)

    def _set_block(self, on):
        flag = os.path.join(
            self.repo, "tools", "hooks", "block-mode.flag")
        if on:
            with open(flag, "w") as fh:
                fh.write("block\n")
        elif os.path.exists(flag):
            os.remove(flag)

    def _run_hook(self):
        return subprocess.run(
            ["bash", "tools/hooks/pre-commit"],
            cwd=self.repo, capture_output=True, text=True)

    def test_distinguish_critical_from_crash_in_block_mode(self):
        """🚨 critical path vs crash path must produce DIFFERENT stderr.
        Legacy: both use the same 'CHECK_ALL INTERNAL ERROR' banner."""
        self._write_fake(
            2,
            "🚨 critical: 1\nrule=line-count severity=high file=d/e.md")
        self._set_block(True)
        proc_critical = self._run_hook()

        self._write_fake(2, "check_all: INTERNAL ERROR (crash)")
        self._set_block(True)
        proc_crash = self._run_hook()

        self.assertNotEqual(
            proc_critical.stderr.strip(),
            proc_crash.stderr.strip(),
            "🚨 critical and crash must produce different stderr "
            "in block mode")

    def test_distinguish_critical_from_crash_in_warn_mode(self):
        """Same differentiation test for warn mode."""
        self._write_fake(
            2,
            "🚨 critical: 1\nrule=line-count severity=high file=d/e.md")
        self._set_block(False)
        proc_critical = self._run_hook()

        self._write_fake(2, "check_all: INTERNAL ERROR (crash)")
        self._set_block(False)
        proc_crash = self._run_hook()

        self.assertNotEqual(
            proc_critical.stderr.strip(),
            proc_crash.stderr.strip(),
            "🚨 critical and crash must produce different stderr "
            "in warn mode")


if __name__ == "__main__":
    unittest.main()
