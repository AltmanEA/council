"""Unit tests for the Stage B git hook tooling (plan sess-doc-reliability-algo):
tools/install-hooks.sh and tools/hooks/pre-commit.

Every test runs against a THROWAWAY temp git repo — never the live repo.
`git config` is only ever invoked with the temp repo as cwd (local config).
The hook is executed directly (git hooks are plain executables); nothing is
committed, so no git identity is required.

check_all.py is faked: the real validator is developed in parallel and must
not be a test dependency. The fake honors the hook's token contract —
findings lines contain `severity=<level>` and `file=<path>` tokens — and
its exit code is parameterized (0 clean / 1 findings / 2 crash).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_INSTALL = os.path.join(REPO, "tools", "install-hooks.sh")
SRC_HOOK = os.path.join(REPO, "tools", "hooks", "pre-commit")

HIGH_LINE = ("rule=line-count severity=high file=docs/en/foo/index.md "
             "content lines 250 exceed 200")
MEDIUM_LINE = ("rule=anchor-check severity=medium file=docs/en/bar/index.md "
               "cross-reference anchor not found")

FAKE_TEMPLATE = """\
#!/usr/bin/env python3
# Fake tools/check_all.py honoring the hook contract:
# argv tolerates --root DIR; exit code and findings come from env vars.
import os, sys
sys.stdout.reconfigure(line_buffering=True)
rc = int(os.environ.get("FAKE_RC", "0"))
if rc == 1:
    for line in os.environ.get("FAKE_FINDINGS", "").splitlines():
        if line:
            print(line)
elif rc == 2:
    # NOTE: a truly uncaught Python exception would exit 1 (indistinguishable
    # from findings) — the contract requires the validator to CATCH and exit 2
    # deliberately, which is what this fake simulates.
    print("check_all: INTERNAL ERROR (fail-loud per contract)")
    print("RuntimeError: simulated validator crash")
    sys.exit(2)
sys.exit(rc)
"""


def _git(repo_dir, *args):
    return subprocess.run(
        ["git", *args], cwd=repo_dir,
        capture_output=True, text=True, check=True,
    ).stdout


def _make_repo():
    """Throwaway git repo with tools/ laid out like the real one."""
    d = tempfile.mkdtemp(prefix="hooks-test-")
    repo = os.path.join(d, "repo")
    os.makedirs(os.path.join(repo, "tools", "hooks"))
    _git(repo, "init", "-q")
    shutil.copy2(SRC_INSTALL, os.path.join(repo, "tools", "install-hooks.sh"))
    shutil.copy2(SRC_HOOK, os.path.join(repo, "tools", "hooks", "pre-commit"))
    return d, repo


def _install(repo):
    return subprocess.run(
        ["bash", "tools/install-hooks.sh"], cwd=repo,
        capture_output=True, text=True,
    )


def _write_fake(repo, rc, findings=""):
    with open(os.path.join(repo, "tools", "check_all.py"), "w") as fh:
        fh.write(FAKE_TEMPLATE)
    return {"FAKE_RC": str(rc), "FAKE_FINDINGS": findings}


def _run_hook(repo, env):
    full_env = dict(os.environ)
    full_env.update(env)
    return subprocess.run(
        ["bash", "tools/hooks/pre-commit"], cwd=repo,
        capture_output=True, text=True, env=full_env,
    )


def _set_block_mode(repo, on):
    flag = os.path.join(repo, "tools", "hooks", "block-mode.flag")
    if on:
        with open(flag, "w") as fh:
            fh.write("operator flip per plan sess-doc-reliability-algo\n")
    elif os.path.exists(flag):
        os.remove(flag)


class SourceFileSanity(unittest.TestCase):
    def test_hook_and_installer_are_executable_in_repo(self):
        for src in (SRC_HOOK, SRC_INSTALL):
            self.assertTrue(os.access(src, os.X_OK), f"{src} lacks +x")

    def test_hook_does_not_copy_into_git_hooks(self):
        with open(SRC_HOOK) as fh:
            text = fh.read()
        self.assertNotIn(".git/hooks", text)


class InstallHooks(unittest.TestCase):
    def setUp(self):
        self.tmp = _make_repo()
        self.repo = self.tmp[1]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_install_sets_hooks_path_locally(self):
        proc = _install(self.repo)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("self-check passed", proc.stdout)
        readback = _git(self.repo, "config", "--local", "--get", "core.hooksPath")
        self.assertEqual(readback.strip(), "tools/hooks")

    def test_install_self_check_passes_and_hook_stays_executable(self):
        proc = _install(self.repo)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(os.access(
            os.path.join(self.repo, "tools", "hooks", "pre-commit"), os.X_OK))

    def test_install_reports_warn_mode_by_default(self):
        proc = _install(self.repo)
        self.assertIn("WARN-ONLY", proc.stdout)
        self.assertIn("touch tools/hooks/block-mode.flag", proc.stdout)

    def test_install_reports_block_mode_when_flag_present(self):
        _set_block_mode(self.repo, True)
        proc = _install(self.repo)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("BLOCK", proc.stdout)
        self.assertNotIn("WARN-ONLY", proc.stdout)

    def test_install_outside_repo_fails_with_remediation(self):
        outside = tempfile.mkdtemp()
        try:
            proc = subprocess.run(
                ["bash", SRC_INSTALL], cwd=outside,
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 1)
            self.assertIn("remediation", proc.stderr)
        finally:
            shutil.rmtree(outside, ignore_errors=True)


class HookExitCodeContract(unittest.TestCase):
    """MODE × check_all-outcome → hook exit code (contract table).

    warn mode:  0→0, 1(high)→0, 1(medium)→0, 2→0, checker-absent→0
    block mode: 0→0, 1(high)→1, 1(medium)→0, 2→1, checker-absent→1
    """

    def setUp(self):
        self.tmp = _make_repo()
        self.repo = self.tmp[1]
        _install(self.repo)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _check(self, block, rc, findings="", checker=True):
        env = {}
        if checker:
            env = _write_fake(self.repo, rc, findings)
        else:
            p = os.path.join(self.repo, "tools", "check_all.py")
            if os.path.exists(p):
                os.remove(p)
        _set_block_mode(self.repo, block)
        return _run_hook(self.repo, env)

    # --- warn mode: never blocks, always loud ---

    def test_warn_clean_exit_0(self):
        proc = self._check(block=False, rc=0)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[pre-commit] documentation check: WARN-ONLY (soak)", proc.stdout)

    def test_warn_high_findings_exit_0_printed_verbatim(self):
        proc = self._check(block=False, rc=1, findings=HIGH_LINE)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(HIGH_LINE, proc.stdout)  # rule + file named

    def test_warn_medium_findings_exit_0(self):
        proc = self._check(block=False, rc=1, findings=MEDIUM_LINE)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(MEDIUM_LINE, proc.stdout)

    def test_warn_crash_exit_0_but_loud_banner(self):
        proc = self._check(block=False, rc=2)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("CHECK_ALL INTERNAL ERROR", proc.stderr)
        self.assertIn("do not debug the hook itself", proc.stderr)
        # crash details must still be visible (no silent failure): the hook
        # re-prints the checker's captured output verbatim
        self.assertIn("simulated validator crash", proc.stdout)

    def test_warn_checker_absent_exit_0_loud(self):
        proc = self._check(block=False, rc=None, checker=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("CHECK_ALL NOT RUN", proc.stderr)
        self.assertIn("remediation", proc.stderr)

    # --- block mode: high / crash / absent block; medium passes ---

    def test_block_clean_exit_0(self):
        proc = self._check(block=True, rc=0)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[pre-commit] documentation check: BLOCK", proc.stdout)

    def test_block_high_findings_exit_1_names_rule_and_file(self):
        proc = self._check(block=True, rc=1, findings=HIGH_LINE)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("BLOCKED", proc.stderr)
        # rejection message names the rule and the file (verbatim line above)
        self.assertIn(HIGH_LINE, proc.stdout + proc.stderr)
        self.assertIn("severity=high", proc.stdout)

    def test_block_mixed_findings_exit_1(self):
        proc = self._check(block=True, rc=1,
                           findings=MEDIUM_LINE + "\n" + HIGH_LINE)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn(HIGH_LINE, proc.stdout)

    def test_block_medium_only_exit_0_with_warning(self):
        proc = self._check(block=True, rc=1, findings=MEDIUM_LINE)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(MEDIUM_LINE, proc.stdout)
        self.assertIn("not blocking", proc.stdout)

    def test_block_crash_exit_1(self):
        proc = self._check(block=True, rc=2)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("CHECK_ALL INTERNAL ERROR", proc.stderr)

    def test_block_unexpected_exit_code_treated_as_crash(self):
        # Non-contract exit code (e.g. 3): loud + fail-closed in block mode.
        env = _write_fake(self.repo, 0)
        env["FAKE_RC"] = "3"
        _set_block_mode(self.repo, True)
        proc = _run_hook(self.repo, env)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("CHECK_ALL INTERNAL ERROR", proc.stderr)

    def test_block_checker_absent_exit_1_fail_closed(self):
        proc = self._check(block=True, rc=None, checker=False)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("CHECK_ALL NOT RUN", proc.stderr)
        self.assertIn("remediation", proc.stderr)


if __name__ == "__main__":
    unittest.main()
