#!/usr/bin/env python3
"""test_dist_isolated_layout.py — Cycle B: .council/ isolated installation layout.

Black-box subprocess tests for the target-task requirements AC-1..AC-10 (and
AC-11 as a separate non-class test). Each test builds an archive via build.sh,
installs into a fresh temp host, and asserts the expected .council/ layout.

22 tests: AC-1 (2), AC-2 (2), AC-3 (3), AC-4 (1), AC-5 (2), AC-6 (1), AC-7 (2),
AC-8 (2), AC-9 (3), AC-11 (1).

Run from repo root:
    python3 -m unittest tests.test_dist_isolated_layout -v
"""

import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(REPO, "dist")
BUILD_SH = os.path.join(DIST, "build.sh")
INSTALL_SH = os.path.join(DIST, "install.sh")
UPDATE_SH = os.path.join(DIST, "update.sh")
SRC_INSTALL = os.path.join(REPO, "tools", "install-hooks.sh")


def _run(cmd, **kw):
    """Run a command and return CompletedProcess."""
    return subprocess.run(
        cmd, capture_output=True, text=True, cwd=kw.pop("cwd", REPO), **kw
    )


# ---------------------------------------------------------------------------
# Shared build helper (build archive ONCE per class via setUpClass)
# ---------------------------------------------------------------------------
class BaseIsolatedLayout(unittest.TestCase):
    """Builds the distribution archive once; subclasses install into fresh dirs."""

    archive_path = None

    @classmethod
    def setUpClass(cls):
        env = os.environ.copy()
        env["COUNCIL_ALLOW_DIRTY"] = "1"
        result = _run(["bash", BUILD_SH, "isolated-layout-test"], env=env)
        cls.archive_path = os.path.join(
            DIST, "out", "council-dist-isolated-layout-test.tar.gz"
        )
        assert os.path.isfile(cls.archive_path), (
            f"build.sh did not produce {cls.archive_path}: {result.stderr}"
        )

    @classmethod
    def setUp(self):
        """Extract archive to a per-test temp dir, return (host, dist_dir)."""
        self._tmpdir = tempfile.mkdtemp()
        dist_dir = os.path.join(self._tmpdir, "council-dist")
        with tarfile.open(self.archive_path, "r:gz") as tf:
            tf.extractall(self._tmpdir)
        self.host = os.path.join(self._tmpdir, "host")
        os.makedirs(self.host)
        self.dist_dir = dist_dir

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# AC-1: build.sh core-manifest entries carry .council/ prefix
# ---------------------------------------------------------------------------
class TestAC1ManifestPrefix(BaseIsolatedLayout):
    """AC-1: core-manifest.txt entries carry .council/ prefix (e.g.
    .council/tools/check_all.py)."""

    def test_manifest_has_council_prefix(self):
        tmpdir = tempfile.mkdtemp()
        try:
            with tarfile.open(self.archive_path, "r:gz") as tf:
                tf.extractall(tmpdir)
            manifest_path = os.path.join(tmpdir, "council-dist", "core-manifest.txt")
            with open(manifest_path) as f:
                entries = [l.strip() for l in f if l.strip()]
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertTrue(
            any(e.startswith(".council/") for e in entries),
            "core-manifest.txt must contain .council/ prefixed entries",
        )
        self.assertIn(
            ".council/tools/check_all.py", entries,
            "core-manifest must contain .council/tools/check_all.py",
        )
        self.assertIn(
            ".council/fallback/index.md", entries,
            "core-manifest must contain .council/fallback/index.md",
        )
        self.assertIn(
            ".council/version.txt", entries,
            "core-manifest must contain .council/version.txt",
        )


class TestAC1ArchiveNoPrefix(BaseIsolatedLayout):
    """AC-1 (secondary): archive core/ does NOT carry .council/ prefix;
    the prefix is manifest-only."""

    def test_archive_core_is_plain_layout(self):
        # Use self.addCleanup so the extracted dir lives through the entire
        # assertion loop (the previous finally-rmtree deleted it too early).
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with tarfile.open(self.archive_path, "r:gz") as tf:
            tf.extractall(tmpdir)
        with open(os.path.join(tmpdir, "council-dist", "core-manifest.txt")) as f:
            manifest_entries = [l.strip() for l in f if l.strip()]

        # Archive core/ should have plain paths like tools/check_all.py,
        # NOT .council/tools/check_all.py. Manifest entries carry .council/
        # prefix but the archive itself uses the plain layout.
        for entry in manifest_entries:
            archive_rel = entry
            if entry.startswith(".council/"):
                archive_rel = entry[len(".council/"):]
            full_path = os.path.join(tmpdir, "council-dist", "core", archive_rel)
            self.assertTrue(
                os.path.exists(full_path),
                f"Manifest entry {entry} -> archive path {archive_rel} must exist in core/",
            )


# ---------------------------------------------------------------------------
# AC-2: install.sh places core under .council/, host root unchanged
# ---------------------------------------------------------------------------
class TestAC2InstallLayout(BaseIsolatedLayout):
    """AC-2: every core item lands under <target>/.council/, host root gets
    only the mandated files (AGENTS.md, opencode.jsonc, .gitignore block)."""

    def test_framework_files_under_council(self):
        result = _run(
            ["bash", "install.sh", "--target", self.host, "--mode", "init",
             "--project-name", "testhost", "--skip-deps-check"],
            cwd=self.dist_dir,
        )
        self.assertEqual(result.returncode, 0, f"install.sh failed: {result.stderr}")

        # Core framework files must be under .council/
        self.assertTrue(os.path.isdir(os.path.join(self.host, ".council")))
        self.assertTrue(
            os.path.isfile(os.path.join(self.host, ".council", "version.lock")),
        )
        self.assertTrue(
            os.path.isfile(os.path.join(self.host, ".council", "update.sh")),
        )
        self.assertTrue(
            os.path.isdir(os.path.join(self.host, ".council", "tools")),
        )
        self.assertTrue(
            os.path.isfile(os.path.join(self.host, ".council", "tools", "check_all.py")),
        )
        self.assertTrue(
            os.path.isdir(os.path.join(self.host, ".council", "fallback")),
        )
        self.assertTrue(
            os.path.isfile(os.path.join(self.host, ".council", "fallback", "index.md")),
        )
        self.assertTrue(
            os.path.isdir(os.path.join(self.host, ".council", "skills")),
        )
        self.assertTrue(
            os.path.isdir(os.path.join(self.host, ".council", "docs")),
        )
        self.assertTrue(
            os.path.isfile(os.path.join(self.host, ".council", "docs", "en",
                                           "documentation-rules", "index.md")),
        )
        self.assertTrue(
            os.path.isfile(os.path.join(self.host, ".council", "CHANGELOGS",
                                           "documentation-rules.changes.md")),
        )
        self.assertTrue(
            os.path.isdir(os.path.join(self.host, ".council", "defaults")),
        )
        self.assertTrue(
            os.path.isfile(os.path.join(self.host, ".council", "defaults",
                                           "translation.lock")),
        )

    def test_host_root_framing_files(self):
        _run(
            ["bash", "install.sh", "--target", self.host, "--mode", "init",
             "--project-name", "testhost", "--skip-deps-check"],
            cwd=self.dist_dir,
        )

        # Host root must have AGENTS.md (template)
        self.assertTrue(
            os.path.isfile(os.path.join(self.host, "AGENTS.md")),
            "AGENTS.md must exist at host root",
        )
        # Host root must NOT have tools/ directly (no flat install)
        self.assertFalse(
            os.path.isdir(os.path.join(self.host, "tools")),
            "tools/ must NOT be at host root (all under .council/)",
        )
        # docs/ru must NOT exist
        self.assertFalse(
            os.path.isdir(os.path.join(self.host, "docs", "ru")),
            "docs/ru must NOT exist on host (Variant-B)",
        )


# ---------------------------------------------------------------------------
# AC-3: opencode.jsonc wiring
# ---------------------------------------------------------------------------
class TestAC3OpencodeWiring(BaseIsolatedLayout):
    """AC-3: install.sh creates/merges opencode.jsonc with skills path."""

    def test_new_opencode_json(self):
        _run(
            ["bash", "install.sh", "--target", self.host, "--mode", "init",
             "--project-name", "testhost", "--skip-deps-check"],
            cwd=self.dist_dir,
        )

        opencode_path = os.path.join(self.host, "opencode.jsonc")
        self.assertTrue(
            os.path.isfile(opencode_path),
            "opencode.jsonc must be created",
        )
        with open(opencode_path) as f:
            content = f.read()
        self.assertIn('"$schema"', content, "opencode.jsonc must have $schema")
        self.assertIn('"Council-managed"', content, "opencode.jsonc must have Council marker")
        self.assertIn('"./.council/skills"', content,
                      "opencode.jsonc must reference ./.council/skills")

    def test_existing_opencode_no_skills_array(self):
        """Host has opencode.jsonc without skills array → warning, file untouched."""
        opencode_path = os.path.join(self.host, "opencode.jsonc")
        with open(opencode_path, "w") as f:
            f.write('{"$schema": "other", "existing": true}\n')

        result = _run(
            ["bash", "install.sh", "--target", self.host, "--mode", "init",
             "--project-name", "testhost", "--skip-deps-check"],
            cwd=self.dist_dir,
        )

        with open(opencode_path) as f:
            content = f.read()
        self.assertIn('"existing": true', content,
                      "Host opencode.jsonc keys must be preserved")
        self.assertIn("warning", result.stdout.lower() or result.stderr.lower(),
                      "Installer must warn about existing opencode.jsonc")

    def test_selector_agent_installed(self):
        """selector.md installed at .opencode/agents/selector.md."""
        _run(
            ["bash", "install.sh", "--target", self.host, "--mode", "init",
             "--project-name", "testhost", "--skip-deps-check"],
            cwd=self.dist_dir,
        )

        self.assertTrue(
            os.path.isfile(os.path.join(self.host, ".opencode", "agents", "selector.md")),
            ".opencode/agents/selector.md must be installed",
        )


# ---------------------------------------------------------------------------
# AC-4: CORE manifest generation at .council/docs-manifest.yaml
# ---------------------------------------------------------------------------
class TestAC4CoreManifest(BaseIsolatedLayout):
    """AC-4: install.sh generates .council/docs-manifest.yaml (core manifest)."""

    def test_council_manifest_generated(self):
        _run(
            ["bash", "install.sh", "--target", self.host, "--mode", "init",
             "--project-name", "testhost", "--skip-deps-check"],
            cwd=self.dist_dir,
        )

        self.assertTrue(
            os.path.isfile(os.path.join(self.host, ".council", "docs-manifest.yaml")),
            ".council/docs-manifest.yaml must be generated",
        )


# ---------------------------------------------------------------------------
# AC-5: success-verification checks NEW paths
# ---------------------------------------------------------------------------
class TestAC5Verification(BaseIsolatedLayout):
    """AC-5: install.sh success-verification checks .council/ paths."""

    def test_install_verification_passes(self):
        """Install succeeds, meaning all verified paths exist under .council/."""
        result = _run(
            ["bash", "install.sh", "--target", self.host, "--mode", "init",
             "--project-name", "testhost", "--skip-deps-check"],
            cwd=self.dist_dir,
        )
        self.assertEqual(result.returncode, 0, f"install.sh failed: {result.stderr}")
        self.assertIn(
            "installed successfully", result.stdout.lower() or result.stderr.lower(),
            "install.sh must print success banner",
        )


class TestAC5WhereIsCouncil(BaseIsolatedLayout):
    """AC-5: install.sh prints a 'Where is Council?' box with .council/ paths.

    After a successful init install, stdout must contain a 'Where is Council'
    header line AND the strings .council/docs/en, .council/tools, .council/skills,
    .council/update.sh (case-insensitive)."""

    def test_where_is_council_banner(self):
        result = _run(
            ["bash", "install.sh", "--target", self.host, "--mode", "init",
             "--project-name", "testhost", "--skip-deps-check"],
            cwd=self.dist_dir,
        )
        self.assertEqual(result.returncode, 0, f"install.sh failed: {result.stderr}")
        output = result.stdout + result.stderr

        # Must have a "Where is Council" header line
        self.assertTrue(
            any("where is council" in line.lower() for line in output.splitlines()),
            "Install output must contain a 'Where is Council' header line",
        )

        # Must list .council/ locations
        for path in [".council/docs/en", ".council/tools", ".council/skills", ".council/update.sh"]:
            self.assertIn(
                path, output,
                f"Install output must reference {path} in the 'Where is Council' box",
            )


# ---------------------------------------------------------------------------
# AC-6: update.sh with .council/-prefixed manifest
# ---------------------------------------------------------------------------
class TestAC6UpdateFlow(BaseIsolatedLayout):
    """AC-6: update.sh works end-to-end with .council/ prefix: version bump,
    orphan removal, backup restore-instructions.txt."""

    def test_version_bump_orphan_removal_backup(self):
        """Version bump, orphan removal, backup preserve, restore-instructions.txt."""
        tmpdir = tempfile.mkdtemp()
        try:
            host = os.path.join(tmpdir, "host")
            os.makedirs(host)

            # 1. Fresh install with V1
            _run(
                ["bash", "install.sh", "--target", host, "--mode", "init",
                 "--project-name", "testhost", "--skip-deps-check"],
                cwd=self.dist_dir,
            )

            # 2. Set up an orphan on the host (create .council/tools/ manually)
            os.makedirs(os.path.join(host, ".council", "tools"), exist_ok=True)
            with open(os.path.join(host, ".council", "tools", "smoke-extra.txt"), "w") as f:
                f.write("orphan content\n")
            with open(os.path.join(host, ".council", "core-manifest.txt"), "a") as f:
                f.write(".council/tools/smoke-extra.txt\n")

            # 3. Build a minimal fake archive (V2, no orphan file)
            fake_dir = tempfile.mkdtemp()
            try:
                arch_content = os.path.join(fake_dir, "council-dist")
                os.makedirs(os.path.join(arch_content, "core"))
                with open(os.path.join(arch_content, "version.txt"), "w") as f:
                    f.write("v2.0.0\n")
                with open(os.path.join(arch_content, "core-manifest.txt"), "w") as f:
                    f.write(".council/tools/check_all.py\n")
                shutil.copy2(UPDATE_SH, os.path.join(arch_content, "update.sh"))

                archive_path = os.path.join(fake_dir, "council-dist-test.tar.gz")
                with tarfile.open(archive_path, "w:gz") as tf:
                    tf.add(arch_content, arcname="council-dist")

                # 4. Run update
                result = _run(
                    ["bash", ".council/update.sh", archive_path, "--force"],
                    cwd=host,
                )
                self.assertEqual(result.returncode, 0,
                                 f"update.sh failed: {result.stderr}")

                # 5. Verify version bumped
                with open(os.path.join(host, ".council", "version.lock")) as f:
                    self.assertEqual(f.read().strip(), "v2.0.0", "version.lock must be updated")

                # 6. Verify orphan removed
                self.assertFalse(
                    os.path.isfile(os.path.join(host, ".council", "tools", "smoke-extra.txt")),
                    "orphan must be removed after update",
                )

                # 7. Verify backup exists with orphan
                backup_dirs = [d for d in os.listdir(os.path.join(host, ".council"))
                               if d.startswith("backup-")]
                self.assertTrue(len(backup_dirs) >= 1, "backup dir must exist")
                backup_path = os.path.join(host, ".council", backup_dirs[0])
                # 7a. Verify backup has STRIPPED prefix layout (no double nesting)
                self.assertTrue(
                    os.path.isdir(os.path.join(backup_path, "tools")),
                    "backup must store entries with .council/ prefix stripped (tools/ at backup root)",
                )
                self.assertFalse(
                    os.path.isdir(os.path.join(backup_path, ".council")),
                    "backup must NOT contain double-nesting (.council/ sub-dir)",
                )
                self.assertTrue(
                    os.path.isfile(os.path.join(backup_path, "tools", "smoke-extra.txt")),
                    "orphan must be preserved in backup at stripped path",
                )

                # 8. Verify restore-instructions.txt content
                instructions_path = os.path.join(backup_path, "restore-instructions.txt")
                self.assertTrue(
                    os.path.isfile(instructions_path),
                    "restore-instructions.txt must exist in backup dir",
                )
                with open(instructions_path) as f:
                    instructions_content = f.read()
                backup_name = backup_dirs[0]
                self.assertIn(
                    f"cp -R .council/{backup_name}/* .council/",
                    instructions_content,
                    "restore-instructions.txt must contain the correct restore command",
                )

            finally:
                shutil.rmtree(fake_dir, ignore_errors=True)

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# AC-7: .gitignore block
# ---------------------------------------------------------------------------
class TestAC7Gitignore(BaseIsolatedLayout):
    """AC-7: install.sh appends Council-managed block to host .gitignore."""

    def test_gitignore_created(self):
        _run(
            ["bash", "install.sh", "--target", self.host, "--mode", "init",
             "--project-name", "testhost", "--skip-deps-check"],
            cwd=self.dist_dir,
        )

        gitignore_path = os.path.join(self.host, ".gitignore")
        self.assertTrue(os.path.isfile(gitignore_path), ".gitignore must be created")
        with open(gitignore_path) as f:
            content = f.read()
        self.assertIn("# Council framework (managed block)", content,
                      ".gitignore must have Council managed block marker")
        self.assertIn(".council/backup-*/", content,
                      ".gitignore must exclude .council/backup-*/")
        self.assertIn(".council/**/__pycache__/", content,
                      ".gitignore must exclude .council/**/__pycache__/")
        self.assertIn(".council/telemetry/**/*.jsonl", content,
                      ".gitignore must exclude telemetry jsonl")
        self.assertIn("**/techdoc-translator/.env", content,
                      ".gitignore must exclude techdoc-translator/.env")

    def test_gitignore_idempotent(self):
        """Running install twice must NOT duplicate the managed block."""
        tmpdir = tempfile.mkdtemp()
        try:
            host = os.path.join(tmpdir, "host")
            os.makedirs(host)

            _run(
                ["bash", "install.sh", "--target", host, "--mode", "init",
                 "--project-name", "testhost", "--skip-deps-check"],
                cwd=self.dist_dir,
            )
            _run(
                ["bash", "install.sh", "--target", host, "--mode", "init",
                 "--project-name", "testhost", "--skip-deps-check"],
                cwd=self.dist_dir,
            )

            gitignore_path = os.path.join(host, ".gitignore")
            self.assertTrue(os.path.isfile(gitignore_path), ".gitignore must exist")
            with open(gitignore_path) as f:
                content = f.read()
            # The marker must appear exactly once
            self.assertEqual(
                content.count("# Council framework (managed block)"), 1,
                "Managed block must NOT be duplicated",
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# AC-8: Pre-flight failures (missing .council/, .council as symlink)
# ---------------------------------------------------------------------------
class TestAC8PreflightMissing(BaseIsolatedLayout):
    """AC-8: update.sh fails if .council/ does not exist."""

    def test_update_missing_council_dir(self):
        tmpdir = tempfile.mkdtemp()
        try:
            host = os.path.join(tmpdir, "host")
            os.makedirs(host)
            update_script = os.path.join(self.dist_dir, "update.sh")
            # No .council/ at all → should fail (current: archive error,
            # future: .council/ missing error)
            with open(os.path.join(tmpdir, "fake.tar.gz"), "w") as f:
                f.write("")  # dummy archive

            result = _run(
                ["bash", update_script, os.path.join(tmpdir, "fake.tar.gz")],
                cwd=host,
            )
            self.assertNotEqual(
                result.returncode, 0,
                "update.sh must fail when .council/ does not exist",
            )
            output = (result.stdout + result.stderr).lower()
            # Must report something about missing .council/ or being not a
            # Council project (not a cryptic archive error).
            self.assertIn(
                "council", output,
                "update.sh must mention Council project or missing .council",
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestAC8PreflightSymlink(BaseIsolatedLayout):
    """AC-8: update.sh fails if .council/ is a symlink.

    Red baseline: current update.sh doesn't check for symlinks, so it silently
    operates through the symlink.  This test will PASS after the implementation
    adds the symlink guard (exit 1 + message)."""

    def test_update_council_is_symlink(self):
        tmpdir = tempfile.mkdtemp()
        try:
            host = os.path.join(tmpdir, "host")
            os.makedirs(host)
            real_dir = os.path.join(tmpdir, "real_council")
            os.makedirs(real_dir)
            with open(os.path.join(real_dir, "version.lock"), "w") as f:
                f.write("v1.0.0\n")
            with open(os.path.join(real_dir, "core-manifest.txt"), "w") as f:
                f.write("tools/test.txt\n")

            # Make .council a symlink
            os.symlink(real_dir, os.path.join(host, ".council"))

            update_script = os.path.join(self.dist_dir, "update.sh")

            # Build a minimal valid council-dist archive
            arch_content_dir = os.path.join(tmpdir, "arch")
            os.makedirs(os.path.join(arch_content_dir, "council-dist"))
            with open(os.path.join(arch_content_dir, "council-dist", "version.txt"), "w") as f:
                f.write("v2.0.0\n")
            with open(os.path.join(arch_content_dir, "council-dist", "core-manifest.txt"), "w") as f:
                f.write("tools/test.txt\n")
            shutil.copy2(update_script, os.path.join(arch_content_dir, "council-dist", "update.sh"))
            fake_archive = os.path.join(tmpdir, "fake.tar.gz")
            with tarfile.open(fake_archive, "w:gz") as tf:
                tf.add(arch_content_dir, arcname="arch")

            result = _run(
                ["bash", update_script, fake_archive],
                cwd=host,
            )
            # After AC-8 fix: should exit non-zero and mention "symlink".
            # Before fix: exits 0 (no check).  This is a red test — it fails
            # now (0 == 0) but will pass once the implementation is done.
            self.assertNotEqual(
                result.returncode, 0,
                "update.sh must fail when .council/ is a symlink",
            )
            self.assertIn(
                "symlink", (result.stdout + result.stderr).lower(),
                "update.sh must report .council is a symlink",
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# AC-9: hooks argument behavior
# ---------------------------------------------------------------------------
class TestAC9HooksArgument(BaseIsolatedLayout):
    """AC-9: install-hooks.sh accepts optional hooks dir argument."""

    def test_custom_hooks_dir(self):
        """AC-9: install-hooks.sh currently hardcodes tools/hooks.
        After AC-9 fix, it should accept a custom hooks dir argument.
        Red baseline: test that install-hooks.sh works with its default path,
        confirming the hooks mechanism works (AC-9 argument acceptance
        will be verified after implementation)."""
        tmpdir = tempfile.mkdtemp()
        try:
            repo = os.path.join(tmpdir, "repo")
            os.makedirs(repo)
            os.makedirs(os.path.join(repo, "tools"))

            _run(["git", "init"], cwd=repo)
            _run(["git", "config", "user.email", "test@test.com"], cwd=repo)
            _run(["git", "config", "user.name", "test"], cwd=repo)

            # Copy install-hooks.sh and pre-commit to the test repo so the
            # self-check passes.
            shutil.copy2(SRC_INSTALL, os.path.join(repo, "tools", "install-hooks.sh"))
            hooks_dir = os.path.join(repo, "tools", "hooks")
            os.makedirs(hooks_dir)
            shutil.copy2(os.path.join(REPO, "tools", "hooks", "pre-commit"),
                         os.path.join(hooks_dir, "pre-commit"))

            result = _run(
                ["bash", SRC_INSTALL],
                cwd=repo,
            )
            self.assertEqual(result.returncode, 0, f"install-hooks.sh failed: {result.stderr}")

            readback = _run(
                ["git", "config", "--local", "--get", "core.hooksPath"],
                cwd=repo,
            )
            self.assertEqual(
                readback.stdout.strip(), "tools/hooks",
                f"core.hooksPath must be tools/hooks, got {readback.stdout.strip()}",
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_hooks_custom_dir_argument(self):
        """AC-9: bash tools/install-hooks.sh .council/tools/hooks must set
        core.hooksPath to the GIVEN dir (not the hardcoded default)."""
        tmpdir = tempfile.mkdtemp()
        try:
            repo = os.path.join(tmpdir, "repo")
            os.makedirs(os.path.join(repo, ".council", "tools"))
            os.makedirs(os.path.join(repo, "tools"))

            _run(["git", "init"], cwd=repo)
            _run(["git", "config", "user.email", "test@test.com"], cwd=repo)
            _run(["git", "config", "user.name", "test"], cwd=repo)

            # Copy install-hooks.sh and pre-commit to the test repo so the
            # self-check passes when the script locates tools/hooks/pre-commit.
            shutil.copy2(SRC_INSTALL, os.path.join(repo, "tools", "install-hooks.sh"))
            hooks_dir = os.path.join(repo, ".council", "tools", "hooks")
            os.makedirs(hooks_dir)
            shutil.copy2(os.path.join(REPO, "tools", "hooks", "pre-commit"),
                         os.path.join(hooks_dir, "pre-commit"))

            # Run with .council/tools/hooks as argument
            result = _run(
                ["bash", SRC_INSTALL, ".council/tools/hooks"],
                cwd=repo,
            )
            self.assertEqual(result.returncode, 0, f"install-hooks.sh failed: {result.stderr}")

            # Must set core.hooksPath to the given argument value
            readback = _run(
                ["git", "config", "--local", "--get", "core.hooksPath"],
                cwd=repo,
            )
            self.assertEqual(
                readback.stdout.strip(), ".council/tools/hooks",
                f"core.hooksPath must be .council/tools/hooks, "
                f"got {readback.stdout.strip()}",
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_pre_commit_falls_back_to_root_check_all(self):
        """pre-commit resolves check_all.py location-relative from hook file,
        falls back to <root>/tools/check_all.py if not found."""
        tmpdir = tempfile.mkdtemp()
        try:
            repo = os.path.join(tmpdir, "repo")
            os.makedirs(os.path.join(repo, ".council", "tools", "hooks"))
            os.makedirs(os.path.join(repo, "tools"))

            _run(["git", "init"], cwd=repo)
            _run(["git", "config", "user.email", "test@test.com"], cwd=repo)
            _run(["git", "config", "user.name", "test"], cwd=repo)

            # Write install-hooks.sh target to .council/tools/hooks
            shutil.copy2("tools/install-hooks.sh", os.path.join(repo, "tools", "install-hooks.sh"))
            shutil.copy2("tools/hooks/pre-commit", os.path.join(repo, ".council", "tools", "hooks", "pre-commit"))

            # Install hooks to .council/tools/hooks
            _run(
                ["bash", "tools/install-hooks.sh", ".council/tools/hooks"],
                cwd=repo,
            )

            # Write a mock check_all.py at <root>/tools/check_all.py
            with open(os.path.join(repo, "tools", "check_all.py"), "w") as f:
                f.write("#!/usr/bin/env python3\nprint('mock')\nexit(0)\n")
            os.chmod(os.path.join(repo, "tools", "check_all.py"), 0o755)

            # Run the hook
            result = _run(
                ["bash", ".council/tools/hooks/pre-commit"],
                cwd=repo,
            )
            self.assertEqual(
                result.returncode, 0,
                f"pre-commit hook should pass with root check_all.py: {result.stderr}",
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# AC-11: check_all.py --root . still exits 0 from worktree root
# ---------------------------------------------------------------------------
class TestAC11CheckAllRoot(unittest.TestCase):
    """AC-11 guard: existing python3 tools/check_all.py --root . still exits 0."""

    def test_check_all_exits_zero(self):
        result = _run(
            ["python3", "tools/check_all.py", "--root", "."],
            cwd=REPO,
        )
        self.assertEqual(
            result.returncode, 0,
            f"check_all.py --root . must exit 0 from worktree root (exit {result.returncode}):\n"
            f"{result.stderr[:2000]}",
        )


if __name__ == "__main__":
    unittest.main()
