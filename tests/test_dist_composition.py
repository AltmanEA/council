#!/usr/bin/env python3
"""test_dist_composition.py — self-contained unittests for Council distribution scripts.

Validates the Variant-B distribution composition: build.sh content set,
bytecode exclusion, dirty-tree guard, install.sh precheck + verification,
update.sh orphan-removal, and the dry-run test expectations.

Run from repo root:
    python3 -m unittest tests.test_dist_composition -v
"""

import os
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


def _run(cmd, **kw):
    """Run a command and return CompletedProcess."""
    return subprocess.run(
        cmd, capture_output=True, text=True, cwd=kw.pop("cwd", REPO), **kw
    )


def _clean_env():
    """Return env without COUNCIL_ALLOW_DIRTY so guards fire."""
    env = os.environ.copy()
    env.pop("COUNCIL_ALLOW_DIRTY", None)
    return env


# ---------------------------------------------------------------------------
# Helper: build a full distribution archive and return its path
# ---------------------------------------------------------------------------
class BuildHelper(unittest.TestCase):
    """Utilities for building distribution archives in temp dirs."""

    def build_archive(self, version, allow_dirty=True):
        """Run build.sh and return (archive_path, build_stdout).
        allow_dirty=True (default): sets COUNCIL_ALLOW_DIRTY=1.
        allow_dirty=False: leaves env clean → dirty tree → build fails.
        """
        env = os.environ.copy()
        if allow_dirty:
            env["COUNCIL_ALLOW_DIRTY"] = "1"
        result = _run(["bash", BUILD_SH, version], env=env)
        archive = os.path.join(DIST, "out", f"council-dist-{version}.tar.gz")
        self.assertTrue(
            os.path.isfile(archive),
            f"build.sh did not produce {archive}: {result.stderr}",
        )
        return archive, result.stdout


# ---------------------------------------------------------------------------
# Test 1: Dirty-tree guard
# ---------------------------------------------------------------------------
class TestDirtyTreeGuard(BuildHelper):
    """build.sh refuses to build a dirty checkout (unless overridden)."""

    def test_dirty_guard_refuses(self):
        """The build.sh source must contain dirty-tree guard logic."""
        with open(BUILD_SH) as f:
            content = f.read()
        self.assertIn(
            "dirty", content.lower(),
            "build.sh must contain dirty-tree guard",
        )
        self.assertIn(
            "FATAL", content,
            "build.sh must mention FATAL for dirty-tree",
        )
        self.assertIn(
            "COUNCIL_ALLOW_DIRTY", content,
            "build.sh must support COUNCIL_ALLOW_DIRTY override",
        )

    def test_dirty_guard_scratch_repo(self):
        """In a scratch repo that's clean, build succeeds. After modifying
        dist/build.sh uncommitted, build fails. COUNCIL_ALLOW_DIRTY=1 overrides."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = os.path.join(tmpdir, "council")
            dist_dir = os.path.join(repo, "dist")

            os.makedirs(os.path.join(repo, "tools"))
            with open(os.path.join(repo, "tools", "check_all.py"), "w") as f:
                f.write("# check_all\n")
            os.makedirs(os.path.join(repo, ".agents", "skills"))
            os.makedirs(os.path.join(repo, "vendor", "techdoc-translator"))
            os.makedirs(os.path.join(repo, ".opencode", "agents"))
            with open(os.path.join(repo, ".opencode", "agents", "selector.md"), "w") as f:
                f.write("# selector\n")
            for d in [
                "docs/en/documentation-rules", "docs/en/documenter-service",
                "docs/en/translation-project", "docs/en/protocol-core",
                "docs/en/glossary", "docs/en/archive", "fallback", "defaults",
            ]:
                os.makedirs(os.path.join(repo, d), exist_ok=True)
            for fpath in [
                "docs/en/documentation-rules/index.md",
                "docs/en/documenter-service/index.md",
                "docs/en/documenter-service/impl-guide.md",
                "docs/en/translation-project/contract.md",
                "docs/en/protocol-core/index.md",
                "docs/en/glossary/index.md",
                "docs/en/archive/index.md",
                "fallback/index.md",
                "defaults/translation.lock",
            ]:
                with open(os.path.join(repo, fpath), "w") as f:
                    f.write("# test\n")
            with open(os.path.join(repo, "AGENTS.md"), "w") as f:
                f.write("# AGENTS.md\n")

            # Write a minimal build.sh with dirty-tree guard
            os.makedirs(dist_dir)
            build_sh_lines = [
                '#!/usr/bin/env bash',
                'set -euo pipefail',
                'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
                'ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"',
                'VERSION="${1:-}"',
                'OUT_DIR="$SCRIPT_DIR/out"',
                'DIST_NAME="council-dist"',
                'ARCHIVE="$DIST_NAME-$VERSION.tar.gz"',
                '',
                '# Dirty-tree guard',
                'if [[ "${COUNCIL_ALLOW_DIRTY:-0}" != "1" ]]; then',
                '  DIRTY=0',
                '  if ! git -C "$ROOT_DIR" diff --quiet HEAD -- dist/; then',
                '    echo "FATAL: Uncommitted changes in dist/"',
                '    DIRTY=1',
                '  fi',
                '  if ! git -C "$ROOT_DIR" diff --cached --quiet HEAD -- dist/; then',
                '    echo "FATAL: Staged changes in dist/"',
                '    DIRTY=1',
                '  fi',
                '  UNTRACKED=$(git -C "$ROOT_DIR" ls-files --others --exclude-standard dist/ 2>/dev/null || true)',
                '  if [[ -n "$UNTRACKED" ]]; then',
                '    echo "FATAL: Untracked files in dist/"',
                '    DIRTY=1',
                '  fi',
                '  if [[ "$DIRTY" -eq 1 ]]; then',
                '    echo "HINT: Set COUNCIL_ALLOW_DIRTY=1 to bypass"',
                '    exit 1',
                '  fi',
                'else',
                '  echo "WARNING: COUNCIL_ALLOW_DIRTY=1 — building despite dirty tree."',
                'fi',
                '',
                'mkdir -p "$OUT_DIR/$DIST_NAME/core"',
                'echo "$VERSION" > "$OUT_DIR/$DIST_NAME/core/version.txt"',
                'cd "$OUT_DIR/$DIST_NAME/core"',
                "find . -type f | sed 's|^\\./||' > \"../core-manifest.txt\"",
                'cd "$ROOT_DIR"',
                'cd "$OUT_DIR"',
                'tar czf "$ARCHIVE" "$DIST_NAME"',
                'echo "Built: $OUT_DIR/$ARCHIVE"',
            ]
            with open(os.path.join(dist_dir, "build.sh"), "w") as f:
                f.write("\n".join(build_sh_lines) + "\n")
            os.chmod(os.path.join(dist_dir, "build.sh"), 0o755)

            # Init git, commit everything
            _run(["git", "init"], cwd=repo)
            _run(["git", "config", "user.email", "test@test.com"], cwd=repo)
            _run(["git", "config", "user.name", "test"], cwd=repo)
            _run(["git", "add", "."], cwd=repo)
            _run(["git", "commit", "-m", "init"], cwd=repo)

            # --- Clean build should succeed ---
            build_env = _clean_env()
            result = _run(["bash", "dist/build.sh", "scratch-clean"], env=build_env, cwd=repo)
            archive = os.path.join(dist_dir, "out", "council-dist-scratch-clean.tar.gz")
            self.assertTrue(
                os.path.isfile(archive),
                f"Clean scratch build failed: {result.stderr}",
            )

            # --- Modify dist/build.sh uncommitted → build must fail ---
            with open(os.path.join(dist_dir, "build.sh"), "a") as f:
                f.write("\n# dirty\n")

            result = _run(["bash", "dist/build.sh", "scratch-dirty"], env=build_env, cwd=repo)
            self.assertNotEqual(
                result.returncode, 0,
                "build.sh must fail with dirty dist/",
            )
            self.assertIn(
                "FATAL", result.stdout,
                "build.sh must print FATAL for dirty tree",
            )

            # --- Override must succeed ---
            override_env = os.environ.copy()
            override_env["COUNCIL_ALLOW_DIRTY"] = "1"
            result2 = _run(["bash", "dist/build.sh", "scratch-override"], env=override_env, cwd=repo)
            archive2 = os.path.join(dist_dir, "out", "council-dist-scratch-override.tar.gz")
            self.assertTrue(
                os.path.isfile(archive2),
                f"COUNCIL_ALLOW_DIRTY=1 build should succeed: {result2.stderr}",
            )


# ---------------------------------------------------------------------------
# Test 2: Bytecode exclusion
# ---------------------------------------------------------------------------
class TestBytecodeExclusion(BuildHelper):
    """No __pycache__ or *.pyc files should be in the archive."""

    def test_no_pycache_in_archive(self):
        archive, _ = self.build_archive("no-pycache-test")
        with tarfile.open(archive, "r:gz") as tf:
            names = tf.getnames()
        pycache = [n for n in names if "__pycache__" in n]
        self.assertEqual(pycache, [], f"Found __pycache__ entries: {pycache}")
        pyc_files = [n for n in names if n.endswith(".pyc")]
        self.assertEqual(pyc_files, [], f"Found .pyc entries: {pyc_files}")

    def test_no_pycache_in_manifest(self):
        archive, _ = self.build_archive("manifest-no-pycache-test")
        tmpdir = tempfile.mkdtemp()
        try:
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(tmpdir)
            manifest_path = os.path.join(tmpdir, "council-dist", "core-manifest.txt")
            with open(manifest_path) as f:
                entries = f.read().strip().split("\n")
            pycache = [e for e in entries if "__pycache__" in e or e.endswith(".pyc")]
            self.assertEqual(pycache, [], f"Manifest lists pycache: {pycache}")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 3: Content set — core (Variant B)
# ---------------------------------------------------------------------------
class TestContentSetCore(BuildHelper):
    """The core manifest lists the correct files per Variant B.

    Per .council/ layout (AC-1): all manifest entries carry .council/ prefix.
    """

    @classmethod
    def setUpClass(cls):
        cls.archive_path = None
        env = os.environ.copy()
        env["COUNCIL_ALLOW_DIRTY"] = "1"
        result = _run(["bash", BUILD_SH, "composition-test"], env=env)
        cls.archive_path = os.path.join(DIST, "out", "council-dist-composition-test.tar.gz")
        cls.assertTrue(
            os.path.isfile(cls.archive_path),
            f"build.sh did not produce {cls.archive_path}: {result.stderr}",
        )

    def test_archive_core_contents(self):
        tmpdir = tempfile.mkdtemp()
        try:
            with tarfile.open(self.archive_path, "r:gz") as tf:
                tf.extractall(tmpdir)
            manifest_path = os.path.join(tmpdir, "council-dist", "core-manifest.txt")
            with open(manifest_path) as f:
                entries = sorted(f.read().strip().split("\n"))

            # Must contain tools (under .council/ prefix)
            self.assertTrue(any(".council/tools/" in e for e in entries))

            # defaults/translation.lock must be present (with .council/ prefix)
            self.assertTrue(
                any(".council/defaults/translation.lock" in e for e in entries),
                "defaults/translation.lock must be in core manifest",
            )

            # defaults/policy.yaml must NOT be present (with .council/ prefix check)
            self.assertFalse(
                any(".council/defaults/policy.yaml" in e for e in entries),
                "defaults/policy.yaml must NOT be in core manifest",
            )

            # docs/en/archive/index.md must be present (exactly 1 archive doc,
            # with .council/ prefix)
            self.assertTrue(
                any(".council/docs/en/archive/index.md" in e for e in entries),
                "docs/en/archive/index.md must be in core manifest",
            )

            # No other archive files (only .council/ entries in core manifest)
            archive_entries = [e for e in entries if ".council/docs/en/archive/" in e]
            self.assertEqual(
                archive_entries, [".council/docs/en/archive/index.md"],
                f"Archive subtree must have only index.md, got: {archive_entries}",
            )

            # NO docs/ru entries (in manifest)
            ru_entries = [e for e in entries if ".council/docs/ru/" in e]
            self.assertEqual(ru_entries, [], f"docs/ru entries found: {ru_entries}")

            # Check selector agent (with .council/ prefix)
            self.assertTrue(
                any(".council/.opencode/agents/selector.md" in e for e in entries),
                "selector agent must be in core",
            )

            # Check fallback (with .council/ prefix)
            self.assertTrue(
                any(".council/fallback/index.md" in e for e in entries),
                "fallback/index.md must be in core",
            )

            # Templates must NOT be in core manifest (they install to host root)
            self.assertFalse(
                any(e.startswith("templates/") for e in entries),
                "templates/ must not appear in core manifest",
            )

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 4: Content set — templates (Variant B)
# ---------------------------------------------------------------------------
class TestContentSetTemplates(BuildHelper):
    """The templates shipped match Variant B exactly."""

    def test_template_contents(self):
        archive, _ = self.build_archive("template-test")
        tmpdir = tempfile.mkdtemp()
        try:
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(tmpdir)

            tpl = os.path.join(tmpdir, "council-dist", "templates")

            # Must have: docs/en/project-concept/
            self.assertTrue(
                os.path.isdir(os.path.join(tpl, "docs", "en", "project-concept")),
                "project-concept template must exist",
            )

            # Must have: CHANGELOGS/project-concept.changes.md
            self.assertTrue(
                os.path.isfile(os.path.join(tpl, "CHANGELOGS", "project-concept.changes.md")),
                "project-concept.changes.md template must exist",
            )

            # Must have: AGENTS.md.template
            self.assertTrue(
                os.path.isfile(os.path.join(tpl, "AGENTS.md.template")),
                "AGENTS.md.template must exist",
            )

            # Must NOT have: v0.x docs that are purged
            for purge_path in [
                "docs/en/execution-runtime",
                "docs/en/operator-ingress",
                "docs/en/planned-architecture",
                "docs/en/project-reference",
                "docs/en/scenario",
                "docs/en/selector",
                "docs/en/service-contract",
                "docs/en/archive",
            ]:
                self.assertFalse(
                    os.path.exists(os.path.join(tpl, purge_path)),
                    f"{purge_path} must NOT be in templates",
                )

            # No bulk CHANGELOGS (only project-concept.changes.md)
            cl = os.path.join(tpl, "CHANGELOGS")
            self.assertTrue(os.path.isdir(cl), "CHANGELOGS dir must exist in templates")
            cl_files = [f for f in os.listdir(cl) if f.endswith(".changes.md")]
            self.assertEqual(
                cl_files, ["project-concept.changes.md"],
                f"Only project-concept.changes.md should be in CHANGELOGS, got: {cl_files}",
            )

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 5: Host installation — no docs/ru, guard exists, templates purge
# ---------------------------------------------------------------------------
class TestHostInstall(BuildHelper):
    """After install.sh on a clean host, the expected files/directories exist or don't.

    Per .council/ layout (AC-2):
    - Framework files under <host>/.council/
    - Host-owned templates at host root
    - No core docs at host root (only project-concept)
    - No docs/ru anywhere
    """

    def test_host_no_ru(self):
        archive, _ = self.build_archive("host-test")
        tmpdir = tempfile.mkdtemp()
        try:
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(tmpdir)

            host = os.path.join(tmpdir, "host")
            os.makedirs(host)
            # Run install
            dist_dir = os.path.join(tmpdir, "council-dist")
            result = _run(
                ["bash", "install.sh", "--target", host, "--mode", "init",
                 "--project-name", "testhost"],
                cwd=dist_dir,
            )
            self.assertEqual(result.returncode, 0, f"install.sh failed: {result.stderr}")

            # No docs/ru anywhere on host
            self.assertFalse(
                os.path.isdir(os.path.join(host, "docs", "ru")),
                "docs/ru must NOT exist on host",
            )

            # Core docs are under .council/ — NOT at host root docs/
            core_doc_dirs = [
                "documentation-rules",
                "glossary",
                "protocol-core",
                "documenter-service",
                "translation-project",
            ]
            host_docs_en = os.path.join(host, "docs", "en")
            for d in core_doc_dirs:
                self.assertFalse(
                    os.path.isdir(os.path.join(host_docs_en, d)),
                    f"host root must NOT contain core docs/ ({d}/)",
                )

            # Framework files under .council/
            self.assertTrue(
                os.path.isfile(os.path.join(host, ".council", "tools", "check_all.py")),
                ".council/tools/check_all.py must exist on host",
            )
            self.assertTrue(
                os.path.isfile(os.path.join(host, ".council", "update.sh")),
                ".council/update.sh must exist on host",
            )

            # defaults/translation.lock under .council/
            self.assertTrue(
                os.path.isfile(os.path.join(host, ".council", "defaults", "translation.lock")),
                ".council/defaults/translation.lock must exist on host",
            )

            # defaults/policy.yaml absent from .council/
            self.assertFalse(
                os.path.isfile(os.path.join(host, ".council", "defaults", "policy.yaml")),
                ".council/defaults/policy.yaml must NOT exist on host",
            )

            # Host-owned templates at host root
            self.assertTrue(
                os.path.isfile(os.path.join(host, "AGENTS.md")),
                "AGENTS.md (host template) must exist at host root",
            )
            self.assertTrue(
                os.path.isfile(os.path.join(host, "docs", "en", "project-concept", "index.md")),
                "docs/en/project-concept/index.md (host template) must exist at host root",
            )
            self.assertTrue(
                os.path.isfile(os.path.join(host, "CHANGELOGS", "project-concept.changes.md")),
                "CHANGELOGS/project-concept.changes.md (host template) must exist at host root",
            )

            # Templates purge
            self.assertFalse(
                os.path.isdir(os.path.join(host, "templates", "docs", "en", "operator-ingress")),
                "operator-ingress must NOT be in templates on host",
            )
            self.assertFalse(
                os.path.isdir(os.path.join(host, "templates", "docs", "en", "service-contract")),
                "service-contract must NOT be in templates on host",
            )

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 6: has_translation sanitization in staged EN files
# ---------------------------------------------------------------------------
class TestHasTranslationSanitization(BuildHelper):
    """build.sh removes has_translation: lines from staged EN files."""

    def test_has_translation_removed(self):
        archive, _ = self.build_archive("ht-test")
        tmpdir = tempfile.mkdtemp()
        try:
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(tmpdir)

            core = os.path.join(tmpdir, "council-dist", "core")

            # Check that has_translation: lines are absent from specific staged files
            checked_files = [
                "docs/en/documentation-rules/index.md",
                "docs/en/documenter-service/index.md",
                "docs/en/documenter-service/impl-guide.md",
                "docs/en/protocol-core/index.md",
                "docs/en/glossary/index.md",
            ]
            for rel in checked_files:
                fpath = os.path.join(core, rel)
                if os.path.isfile(fpath):
                    with open(fpath) as f:
                        content = f.read()
                    self.assertNotIn(
                        "has_translation:", content,
                        f"{rel} must not contain has_translation: line",
                    )

            # templates: docs/en/project-concept/index.md
            tpl = os.path.join(tmpdir, "council-dist", "templates", "docs", "en", "project-concept")
            self.assertTrue(os.path.isfile(os.path.join(tpl, "index.md")))
            with open(os.path.join(tpl, "index.md")) as f:
                content = f.read()
            self.assertNotIn(
                "has_translation:", content,
                "templates docs/en/project-concept/index.md must not contain has_translation:",
            )

            # Also check manifest: should list exactly 1 archive doc, no has_translation
            manifest_path = os.path.join(tmpdir, "council-dist", "core-manifest.txt")
            with open(manifest_path) as f:
                content = f.read()
            self.assertNotIn("has_translation", content)
            archive_entries = [l for l in content.strip().split("\n")
                               if ".council/docs/en/archive/" in l]
            self.assertEqual(
                archive_entries, [".council/docs/en/archive/index.md"],
            )

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 7: docs/ru path references sanitized in body text
# ---------------------------------------------------------------------------
class TestRUPathSanitization(BuildHelper):
    """docs/ru/<id>/...md body references are replaced with placeholder form."""

    def test_ru_paths_replaced(self):
        archive, _ = self.build_archive("ru-san-test")
        tmpdir = tempfile.mkdtemp()
        try:
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(tmpdir)

            core = os.path.join(tmpdir, "council-dist", "core")
            tpl = os.path.join(tmpdir, "council-dist", "templates")

            # Walk all .md files and check no concrete docs/ru/...md references
            all_files = []
            for root, dirs, files in os.walk(core):
                for fn in files:
                    if fn.endswith(".md"):
                        all_files.append(os.path.join(root, fn))
            for root, dirs, files in os.walk(tpl):
                for fn in files:
                    if fn.endswith(".md"):
                        all_files.append(os.path.join(root, fn))

            import re
            link_re = re.compile(
                r"(?<![\w/.-])(docs/(?:en|ru)/[\w./-]+\.md)(?![\w-])"
            )

            flagged = []
            for fpath in all_files:
                with open(fpath) as f:
                    for i, line in enumerate(f, 1):
                        for m in link_re.finditer(line):
                            token = m.group(0)
                            if "/ru/" in token:
                                # Must be a placeholder with angle brackets
                                if "<" not in token:
                                    flagged.append(
                                        f"{os.path.relpath(fpath, REPO)}:{i}: {token}"
                                    )

            self.assertEqual(
                flagged, [],
                f"Concrete docs/ru/ paths found in body text: {flagged[:10]}",
            )

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 8: install.sh — core/ missing → FATAL + no "installed successfully"
# ---------------------------------------------------------------------------
class TestInstallFatalPrecheck(BuildHelper):
    """install.sh refuses to install when core/ is missing."""

    def test_install_core_missing(self):
        archive, _ = self.build_archive("install-precheck-test")
        tmpdir = tempfile.mkdtemp()
        try:
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(tmpdir)

            dist_dir = os.path.join(tmpdir, "council-dist")
            # Remove core/ to simulate broken distribution
            shutil.rmtree(os.path.join(dist_dir, "core"))

            host = os.path.join(tmpdir, "host")
            os.makedirs(host)
            result = _run(
                ["bash", "install.sh", "--target", host, "--mode", "init",
                 "--project-name", "testhost"],
                cwd=dist_dir,
            )

            self.assertNotEqual(
                result.returncode, 0,
                "install.sh must fail when core/ is missing",
            )
            self.assertNotIn(
                "installed successfully", result.stdout.lower(),
                "install.sh must NOT print 'installed successfully' when core/ is missing",
            )

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 9: install.sh — host verification after clean install
# ---------------------------------------------------------------------------
class TestInstallVerification(BuildHelper):
    """After install.sh succeeds, all required files must exist on the host.

    Per .council/ layout (AC-2):
    - Framework files install under <host>/.council/
    - Host-owned templates (project-concept, AGENTS.md, CHANGELOGS) stay at host root
    """

    def test_install_verification(self):
        archive, _ = self.build_archive("verify-test")
        tmpdir = tempfile.mkdtemp()
        try:
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(tmpdir)

            host = os.path.join(tmpdir, "host")
            os.makedirs(host)
            dist_dir = os.path.join(tmpdir, "council-dist")
            result = _run(
                ["bash", "install.sh", "--target", host, "--mode", "init",
                 "--project-name", "testhost", "--skip-deps-check"],
                cwd=dist_dir,
            )
            self.assertEqual(
                result.returncode, 0, f"install.sh failed: {result.stderr}"
            )

            # Framework files under .council/
            required_files = [
                ".council/tools/check_all.py",
                ".council/update.sh",
                ".council/fallback/index.md",
                ".council/docs/en/documentation-rules/index.md",
            ]
            for rel in required_files:
                fpath = os.path.join(host, rel)
                self.assertTrue(
                    os.path.isfile(fpath), f"Missing after install: {rel}"
                )

            # Host-owned templates at host root (not under .council/)
            host_templates = [
                "AGENTS.md",
                "CHANGELOGS/project-concept.changes.md",
                "docs/en/project-concept/index.md",
            ]
            for rel in host_templates:
                fpath = os.path.join(host, rel)
                self.assertTrue(
                    os.path.isfile(fpath), f"Host template missing: {rel}"
                )

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 10: update.sh UNION-based orphan removal (MF-3 regression test)
# ---------------------------------------------------------------------------
class TestUpdateOrphanRemoval(unittest.TestCase):
    """update.sh must remove files listed in old manifest but absent from
    the new archive's manifest (UNION-based orphan removal, MF-3).

    This test builds a minimal fake archive containing only the updated
    files plus a manifest listing only those files — a file present in the
    old host manifest but NOT in the new manifest must be [removed]'d.
    """

    def test_orphan_removal_with_manifest(self):
        # 1. Set up a fake host project
        tmpdir = tempfile.mkdtemp()
        try:
            host = os.path.join(tmpdir, "host")
            os.makedirs(host)

            # .council/
            os.makedirs(os.path.join(host, ".council"))
            with open(os.path.join(host, ".council", "version.lock"), "w") as f:
                f.write("v1.0.0\n")
            with open(os.path.join(host, ".council", "core-manifest.txt"), "w") as f:
                f.write("tools/keep.txt\n")
                f.write("tools/orphan.txt\n")
            # Copy update.sh into .council/ (as install.sh would)
            shutil.copy2(UPDATE_SH, os.path.join(host, ".council", "update.sh"))
            os.chmod(os.path.join(host, ".council", "update.sh"), 0o755)

            # Host files
            os.makedirs(os.path.join(host, "tools"))
            with open(os.path.join(host, "tools", "keep.txt"), "w") as f:
                f.write("OLD KEEP\n")
            with open(os.path.join(host, "tools", "orphan.txt"), "w") as f:
                f.write("ORPHAN\n")

            # .agents/ (required so update.sh doesn't fail on checks)
            os.makedirs(os.path.join(host, ".agents", "skills"))

            # 2. Build a minimal fake archive (no SHA256SUMS → use --force)
            archive_dir = tempfile.mkdtemp()
            arch_content = os.path.join(archive_dir, "council-dist")
            os.makedirs(os.path.join(arch_content, "core", "tools"))
            with open(os.path.join(arch_content, "core", "tools", "keep.txt"), "w") as f:
                f.write("NEW KEEP\n")
            with open(os.path.join(arch_content, "core-manifest.txt"), "w") as f:
                f.write("tools/keep.txt\n")
            with open(os.path.join(arch_content, "version.txt"), "w") as f:
                f.write("v2.0.0\n")

            # Copy update.sh into the archive so update.sh updates itself
            shutil.copy2(UPDATE_SH, os.path.join(arch_content, "update.sh"))

            archive_path = os.path.join(archive_dir, "council-dist-test.tar.gz")
            with tarfile.open(archive_path, "w:gz") as tf:
                tf.add(arch_content, arcname="council-dist")

            # 3. Run update.sh --force from the host
            result = _run(
                ["bash", ".council/update.sh", archive_path, "--force"],
                cwd=host,
            )

            self.assertEqual(
                result.returncode, 0,
                f"update.sh failed (exit {result.returncode}):\n"
                f"stdout: {result.stdout[:2000]}\n"
                f"stderr: {result.stderr[:2000]}",
            )

            # 4. Verify [removed] reported
            self.assertIn(
                "[removed] tools/orphan.txt", result.stdout,
                "update.sh must report [removed] for the orphaned file",
            )

            # 5. Verify orphan.txt is deleted
            self.assertFalse(
                os.path.isfile(os.path.join(host, "tools", "orphan.txt")),
                "tools/orphan.txt must be deleted after update",
            )

            # 6. Verify keep.txt was updated
            with open(os.path.join(host, "tools", "keep.txt")) as f:
                self.assertEqual(f.read().strip(), "NEW KEEP", "tools/keep.txt must be updated")

            # 7. Verify version.lock updated
            with open(os.path.join(host, ".council", "version.lock")) as f:
                self.assertEqual(f.read().strip(), "v2.0.0")

            # 8. Verify orphan.txt preserved in backup
            backup_dirs = [
                d for d in os.listdir(os.path.join(host, ".council"))
                if d.startswith("backup-")
            ]
            self.assertTrue(len(backup_dirs) >= 1, "backup dir must exist")
            backup_path = os.path.join(host, ".council", backup_dirs[0])
            self.assertTrue(
                os.path.isfile(os.path.join(backup_path, "tools", "orphan.txt")),
                f"orphan.txt must exist in backup {backup_dirs[0]}",
            )
            with open(os.path.join(backup_path, "tools", "orphan.txt")) as f:
                self.assertEqual(f.read().strip(), "ORPHAN", "backup must contain original orphan content")

            # 9. Verify new core-manifest.txt updated
            with open(os.path.join(host, ".council", "core-manifest.txt")) as f:
                entries = [l.strip() for l in f if l.strip()]
            self.assertEqual(entries, ["tools/keep.txt"])

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 11: check_all.py passes on fresh host (regression test)
# ---------------------------------------------------------------------------
class TestCheckAllOnHost(unittest.TestCase):
    """On a freshly installed host, check_all.py must exit 0 on the host corpus.

    Per .council/ layout: invoke with --root . (host root) and --core-root .council
    so it audits only the host's project-concept (clean) instead of the core corpus
    (which has unrelated low §-refs).
    """

    @unittest.skipUnless(
        subprocess.run(
            ["python3", "-c", "import yaml"], capture_output=True
        ).returncode == 0,
        "PyYAML not available — skipping",
    )
    def test_check_all_clean(self):
        # Build and install
        tmpdir = tempfile.mkdtemp()
        try:
            env = os.environ.copy()
            env["COUNCIL_ALLOW_DIRTY"] = "1"
            result = _run(["bash", BUILD_SH, "checkall-test"], env=env)
            archive = os.path.join(DIST, "out", "council-dist-checkall-test.tar.gz")

            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(tmpdir)

            host = os.path.join(tmpdir, "host")
            os.makedirs(host)
            dist_dir = os.path.join(tmpdir, "council-dist")
            _run(
                ["bash", "install.sh", "--target", host, "--mode", "init",
                 "--project-name", "testhost"],
                cwd=dist_dir,
            )

            # AC-4: the installer itself must have generated the host manifest at root
            self.assertTrue(
                os.path.isfile(os.path.join(host, "docs-manifest.yaml")),
                "install.sh must generate host docs-manifest.yaml at host root (AC-4)",
            )
            self.assertTrue(
                os.path.isfile(os.path.join(host, ".council", "docs-manifest.yaml")),
                "install.sh must generate core manifest at .council/docs-manifest.yaml (AC-4)",
            )

            # On a fresh install, host has no root-level docs-manifest.yaml yet.
            # Generate it (real-world first step) so check_all can audit cleanly.
            _run(
                ["python3", ".council/tools/gen_manifest.py", "--root", ".", "--write"],
                cwd=host,
            )

            # Audit HOST corpus (not core) with --core-root resolving core docs
            result = _run(
                ["python3", ".council/tools/check_all.py", "--root", ".",
                 "--core-root", ".council"],
                cwd=host,
            )
            self.assertEqual(
                result.returncode, 0,
                f"check_all.py failed on host corpus (exit {result.returncode}):\n"
                f"{result.stderr[:2000]}",
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
