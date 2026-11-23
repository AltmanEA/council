#!/usr/bin/env python3
"""test_build_exact_match.py — unit tests for dist/build.sh exact-match guard

Tests pin the modified build.sh behavior (Acceptance Criterion 6):
  AC-6: When called WITHOUT an explicit VERSION argument:
        - Untagged commit → exit 1 + FATAL message.
        - Exact tag → success (exit 0).
        When VERSION is passed explicitly → unchanged behavior (any string accepted).

Every test creates a throwaway git repo in a TemporaryDirectory and copies
the build.sh script into the repo's dist/ directory.
No network, no council-repo tags.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_SH_SRC = os.path.join(WORKTREE, "dist", "build.sh")
DIST_SRC = os.path.join(WORKTREE, "dist")
TOOLS_SRC = os.path.join(WORKTREE, "tools")
DOCS_SRC = os.path.join(WORKTREE, "docs")
FALLBACK_SRC = os.path.join(WORKTREE, "fallback")
DEFAULTS_SRC = os.path.join(WORKTREE, "defaults")
AGENTS_SRC = os.path.join(WORKTREE, ".agents")
OPENCODE_SRC = os.path.join(WORKTREE, ".opencode")


def _run(cmd, cwd=None, env=None):
    """Run a command; return CompletedProcess."""
    return subprocess.run(
        cmd, capture_output=True, text=True, cwd=cwd, env=env,
    )


def _setup_build_repo(tmpdir):
    """Create a git repo with build.sh and all required files.

    Returns (repo, build_sh) — the repo directory and the build.sh path inside it.
    """
    repo = os.path.join(tmpdir, "repo")
    os.makedirs(repo)

    # Copy build.sh source tree items into the repo (skip files that break isolation)
    for name in os.listdir(WORKTREE):
        if name in (".git", ".impl-whitelist", "artifacts", "__pycache__"):
            continue
        src = os.path.join(WORKTREE, name)
        dst = os.path.join(repo, name)
        if name == "dist":
            continue
        _copy_item(src, dst)

    # Copy dist/ content except build.sh (we'll write it separately)
    dist_dir = os.path.join(repo, "dist")
    os.makedirs(dist_dir)
    for name in os.listdir(DIST_SRC):
        if name == "build.sh":
            continue
        src = os.path.join(DIST_SRC, name)
        _copy_item(src, os.path.join(dist_dir, name))

    # Write build.sh with COUNCIL_ALLOW_DIRTY=1
    build_sh = os.path.join(dist_dir, "build.sh")
    with open(BUILD_SH_SRC, "r") as src:
        build_content = src.read()
    with open(build_sh, "w") as f:
        f.write("#!/usr/bin/env bash\n")
        f.write('export COUNCIL_ALLOW_DIRTY=1\n')
        f.write(build_content)
    os.chmod(build_sh, 0o755)

    # Init git repo
    _run(["git", "init"], cwd=repo)
    _run(["git", "config", "user.email", "test@test.com"], cwd=repo)
    _run(["git", "config", "user.name", "test"], cwd=repo)
    _run(["git", "add", "."], cwd=repo)
    _run(["git", "commit", "-m", "init"], cwd=repo)

    # Verify isolation: no pre-existing tags, root dir matches expected repo
    _tags_result = _run(["git", "tag", "-l"], cwd=repo)
    _top_result = _run(["git", "rev-parse", "--show-toplevel"], cwd=repo)
    assert (
        _tags_result.returncode == 0 and _tags_result.stdout.strip() == "" and
        _top_result.returncode == 0 and _top_result.stdout.strip() == repo
    ), (
        f"Repo isolation check failed: tags={_tags_result.stdout.strip()!r}, "
        f"toplevel={_top_result.stdout.strip()!r}"
    )

    return repo, build_sh


def _copy_item(src, dst):
    """Copy file or directory if it exists."""
    if os.path.exists(src):
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git"))
        else:
            shutil.copy2(src, dst)


class TestBuildExactMatchUntagged(unittest.TestCase):
    """Bare build.sh on an untagged commit must fail with exit 1 + FATAL message."""

    def test_untagged_exits_1(self):
        """When HEAD has no tag, bare invocation → exit 1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo, build_sh = _setup_build_repo(tmpdir)
            # No tags → untagged

            result = _run(["bash", build_sh], cwd=repo)
            self.assertEqual(
                result.returncode, 1,
                f"Untagged commit must exit 1, got {result.returncode}: {result.stderr[:500]}",
            )
            self.assertIn(
                "FATAL", result.stderr,
                "Must print FATAL message to stderr",
            )
            self.assertIn(
                "tagged", result.stderr.lower(),
                "FATAL message must mention 'tagged'",
            )

    def test_untagged_message_content(self):
        """The FATAL message must mention passing VERSION explicitly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo, build_sh = _setup_build_repo(tmpdir)

            result = _run(["bash", build_sh], cwd=repo)
            self.assertIn(
                "VERSION", result.stderr,
                "FATAL message must mention VERSION argument",
            )


class TestBuildExactMatchWithTagged(unittest.TestCase):
    """Bare build.sh on an exact tag commit must succeed (exit 0)."""

    def test_tagged_exits_0(self):
        """When HEAD has an exact tag, bare invocation succeeds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo, build_sh = _setup_build_repo(tmpdir)
            _run(["git", "tag", "v1.0.0"], cwd=repo)

            result = _run(["bash", build_sh], cwd=repo)
            self.assertEqual(
                result.returncode, 0,
                f"Tagged commit must exit 0, got {result.returncode}: {result.stderr[:500]}",
            )


class TestBuildExactMatchExplicitVersion(unittest.TestCase):
    """When VERSION is passed explicitly, behavior is unchanged (any string accepted)."""

    def test_explicit_version_succeeds(self):
        """Explicit VERSION argument bypasses the tag check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo, build_sh = _setup_build_repo(tmpdir)
            # No tags — explicit VERSION should still work

            result = _run(["bash", build_sh, "custom-version"], cwd=repo)
            self.assertEqual(
                result.returncode, 0,
                f"Explicit VERSION must succeed even without tags, got {result.returncode}: {result.stderr[:500]}",
            )


if __name__ == "__main__":
    unittest.main()
