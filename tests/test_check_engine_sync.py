#!/usr/bin/env python3
"""test_check_engine_sync.py — unit tests for tools/check_engine_sync.py

Tests pin the advisory engine-pin check behavior (Acceptance Criteria 5):
  Verdicts: OK / MISMATCH / STALE / MISSING.
  Exit codes: 0 for all verdicts, 2 for usage errors.
  Always single-line stdout output.

Every test creates a throwaway git repo in a TemporaryDirectory.
No network, no council-repo tags, no writes outside the tmpdir.
"""

import datetime
import os
import re
import subprocess
import tempfile
import unittest

WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK_ENGINE = os.path.join(WORKTREE, "tools", "check_engine_sync.py")


def _run(cmd, cwd=None, env=None):
    """Run a command; return CompletedProcess."""
    return subprocess.run(
        cmd, capture_output=True, text=True, cwd=cwd, env=env,
    )


def _setup_repo(tmpdir, fallback_content="index.md"):
    """Create a minimal git repo with fallback/<content>.

    Returns the repo directory path.
    """
    repo = os.path.join(tmpdir, "repo")
    os.makedirs(os.path.join(repo, "fallback"))
    with open(os.path.join(repo, "fallback", fallback_content), "w") as f:
        f.write("# Hello World\n\nbody\n")
    _run(["git", "init"], cwd=repo)
    _run(["git", "config", "user.email", "test@test.com"], cwd=repo)
    _run(["git", "config", "user.name", "test"], cwd=repo)
    _run(["git", "add", "."], cwd=repo)
    _run(["git", "commit", "-m", "init"], cwd=repo)
    return repo


def _read_file(path):
    with open(path) as f:
        return f.read()


class TestCheckEngineSyncOK(unittest.TestCase):
    """Verdict: OK — pin commit matches resolved ref commit."""

    def test_ok_when_pin_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            _run(["git", "tag", "test-tag"], cwd=repo)
            commit_sha = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
            short = commit_sha[:8]

            engine_dir = os.path.join(repo, ".engine", "sync-ok")
            os.makedirs(engine_dir)
            with open(os.path.join(engine_dir, "DIST-SOURCE"), "w") as f:
                f.write(f"tag=test-tag\n")
                f.write(f"tree={commit_sha}^{'tree' if False else 'tree'}\n")
                f.write(f"commit={commit_sha}\n")
                f.write(f"generated={datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n")

            result = _run(["python3", CHECK_ENGINE, "--engine-dir", engine_dir, "--root", repo])
            self.assertEqual(result.returncode, 0, f"exit 0 required, got {result.returncode}: {result.stderr}")
            self.assertIn("engine-sync: OK", result.stdout.strip(), "Must output OK verdict")
            self.assertIn(f"pin=test-tag@{short}", result.stdout.strip(), "Must include pin")
            self.assertIn(f"current={short}", result.stdout.strip(), "Must include current commit")


class TestCheckEngineSyncMISMATCH(unittest.TestCase):
    """Verdict: MISMATCH — pin commit differs from resolved ref commit."""

    def test_mismatch_when_pin_differs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two repos with different content
            repo1 = _setup_repo(tmpdir, "index.md")
            _run(["git", "tag", "old-tag"], cwd=repo1)
            commit1 = _run(["git", "rev-parse", "HEAD"], cwd=repo1).stdout.strip()
            short1 = commit1[:8]

            # Create repo2 as a separate repo (so it's a different commit)
            repo2 = os.path.join(tmpdir, "repo2")
            os.makedirs(os.path.join(repo2, "fallback"))
            with open(os.path.join(repo2, "fallback", "index.md"), "w") as f:
                f.write("# Different\n")
            _run(["git", "init"], cwd=repo2)
            _run(["git", "config", "user.email", "test@test.com"], cwd=repo2)
            _run(["git", "config", "user.name", "test"], cwd=repo2)
            _run(["git", "add", "."], cwd=repo2)
            _run(["git", "commit", "-m", "init2"], cwd=repo2)
            _run(["git", "tag", "v1-latest"], cwd=repo2)
            commit2 = _run(["git", "rev-parse", "HEAD"], cwd=repo2).stdout.strip()
            short2 = commit2[:8]

            # Engine dir in repo2, but with DIST-SOURCE pointing to repo1's commit
            engine_dir = os.path.join(repo2, ".engine", "sync-mismatch")
            os.makedirs(engine_dir)
            with open(os.path.join(engine_dir, "DIST-SOURCE"), "w") as f:
                f.write(f"tag=old-tag\n")
                f.write(f"commit={commit1}\n")
                f.write(f"generated={datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n")

            result = _run(["python3", CHECK_ENGINE, "--engine-dir", engine_dir, "--ref", "v1-latest", "--root", repo2])
            self.assertEqual(result.returncode, 0, f"exit 0 required, got {result.returncode}: {result.stderr}")
            self.assertIn("engine-sync: MISMATCH", result.stdout.strip(), "Must output MISMATCH verdict")


class TestCheckEngineSyncSTALE(unittest.TestCase):
    """Verdict: STALE — DIST-SOURCE generated time > 14 days old AND != resolved."""

    def test_stale_when_old_generated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            _run(["git", "tag", "v1-latest"], cwd=repo)
            commit_sha = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

            engine_dir = os.path.join(repo, ".engine", "sync-stale")
            os.makedirs(engine_dir)
            # Set generated date to 30 days ago (older than 14-day threshold)
            stale_date = datetime.datetime(2026, 10, 24, 12, 0, 0, tzinfo=datetime.timezone.utc)
            with open(os.path.join(engine_dir, "DIST-SOURCE"), "w") as f:
                f.write(f"tag=old-tag\n")
                f.write(f"commit=0000000000000000000000000000000000000000\n")
                f.write(f"generated={stale_date.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")

            result = _run(["python3", CHECK_ENGINE, "--engine-dir", engine_dir, "--ref", "v1-latest", "--root", repo])
            self.assertEqual(result.returncode, 0, f"exit 0 required, got {result.returncode}: {result.stderr}")
            self.assertIn("engine-sync: STALE", result.stdout.strip(), "Must output STALE verdict (not MISMATCH)")
            # STALE should be emitted instead of MISMATCH when age > 14 days
            self.assertNotIn("MISMATCH", result.stdout.strip()[:50], "STALE must replace MISMATCH for old sources")


class TestCheckEngineSyncMISSING(unittest.TestCase):
    """Verdict: MISSING — no DIST-SOURCE found / engine dir absent."""

    def test_missing_no_engine_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")

            engine_dir = os.path.join(repo, ".engine", "nonexistent")
            result = _run(["python3", CHECK_ENGINE, "--engine-dir", engine_dir])
            self.assertEqual(result.returncode, 0, f"exit 0 required, got {result.returncode}: {result.stderr}")
            self.assertIn("engine-sync: MISSING", result.stdout.strip(), "Must output MISSING verdict")

    def test_missing_no_dist_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")

            engine_dir = os.path.join(repo, ".engine", "empty-engine")
            os.makedirs(engine_dir)
            # Engine dir exists but DIST-SOURCE is absent

            result = _run(["python3", CHECK_ENGINE, "--engine-dir", engine_dir])
            self.assertEqual(result.returncode, 0, f"exit 0 required, got {result.returncode}: {result.stderr}")
            self.assertIn("engine-sync: MISSING", result.stdout.strip(), "Must output MISSING verdict")


class TestCheckEngineSyncAlwaysExit0(unittest.TestCase):
    """check_engine_sync always exits 0 for verdicts (warn-only per OP-1)."""

    def test_ok_exits_0(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            _run(["git", "tag", "test-tag"], cwd=repo)
            commit_sha = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

            engine_dir = os.path.join(repo, ".engine", "ok")
            os.makedirs(engine_dir)
            with open(os.path.join(engine_dir, "DIST-SOURCE"), "w") as f:
                f.write(f"tag=test-tag\n")
                f.write(f"commit={commit_sha}\n")
                f.write(f"generated=2026-11-23T12:00:00Z\n")

            result = _run(["python3", CHECK_ENGINE, "--engine-dir", engine_dir])
            self.assertEqual(result.returncode, 0)

    def test_mismatch_exits_0(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            _run(["git", "tag", "v1-latest"], cwd=repo)
            engine_dir = os.path.join(repo, ".engine", "mismatch")
            os.makedirs(engine_dir)
            with open(os.path.join(engine_dir, "DIST-SOURCE"), "w") as f:
                f.write("tag=old-tag\n")
                f.write("commit=0000000000000000000000000000000000000000\n")
                f.write("generated=2026-11-23T12:00:00Z\n")

            result = _run(["python3", CHECK_ENGINE, "--engine-dir", engine_dir, "--ref", "v1-latest", "--root", repo])
            self.assertEqual(result.returncode, 0)

    def test_stale_exits_0(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            _run(["git", "tag", "v1-latest"], cwd=repo)
            engine_dir = os.path.join(repo, ".engine", "stale")
            os.makedirs(engine_dir)
            stale_date = datetime.datetime(2026, 10, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
            with open(os.path.join(engine_dir, "DIST-SOURCE"), "w") as f:
                f.write(f"tag=old\ncommit=dead00000000000000000000000000000000\n")
                f.write(f"generated={stale_date.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")

            result = _run(["python3", CHECK_ENGINE, "--engine-dir", engine_dir, "--ref", "v1-latest", "--root", repo])
            self.assertEqual(result.returncode, 0)

    def test_missing_exits_0(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run(["python3", CHECK_ENGINE, "--engine-dir", "/nonexistent/engine"])
            self.assertEqual(result.returncode, 0)


class TestCheckEngineSyncUsageError(unittest.TestCase):
    """Usage error → exit 2."""

    def test_bad_flag_exits_2(self):
        """Unknown flag should trigger usage error."""
        result = _run(["python3", CHECK_ENGINE, "--bad-flag"])
        self.assertEqual(result.returncode, 2, f"exit 2 for usage error, got {result.returncode}")


class TestCheckEngineSyncOutputFormat(unittest.TestCase):
    """Output is always a single line starting with engine-sync:"""

    def test_single_line_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            engine_dir = os.path.join(repo, ".engine", "fmt")
            os.makedirs(engine_dir)
            # DIST-SOURCE missing → MISSING

            result = _run(["python3", CHECK_ENGINE, "--engine-dir", engine_dir])
            self.assertEqual(result.returncode, 0)
            lines = [l for l in result.stdout.strip().split("\n") if l]
            self.assertEqual(len(lines), 1, f"Output must be a single line, got: {lines}")

    def test_output_starts_with_engine_sync(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            engine_dir = os.path.join(repo, ".engine", "prefix")
            os.makedirs(engine_dir)

            result = _run(["python3", CHECK_ENGINE, "--engine-dir", engine_dir])
            self.assertTrue(
                result.stdout.strip().startswith("engine-sync:"),
                f"Output must start with 'engine-sync:', got: {result.stdout.strip()[:50]}",
            )


class TestCheckEngineSyncGenEngineIntegration(unittest.TestCase):
    """Integration: engine produced by gen_engine.sh (annotated tag) must be
    reported OK by check_engine_sync.py (iter-3 defect: DIST-SOURCE commit= was
    the tag-object sha, producing false MISMATCH for annotated tags)."""

    def test_generated_engine_matches_annotated_tag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            _run(["git", "tag", "-a", "v1.0.2", "-m", "release"], cwd=repo)

            gen = os.path.join(WORKTREE, "tools", "gen_engine.sh")
            result = _run(["bash", gen, "v1.0.2"], cwd=repo)
            self.assertEqual(result.returncode, 0, result.stderr)

            engine_dir = os.path.join(repo, ".engine", "v1.0.2")
            result = _run([
                "python3", CHECK_ENGINE,
                "--engine-dir", engine_dir, "--ref", "v1.0.2", "--root", repo,
            ])
            self.assertEqual(result.returncode, 0)
            self.assertIn(
                "engine-sync: OK",
                result.stdout,
                f"legit engine on annotated tag must be OK, got: {result.stdout.strip()}",
            )

    def test_generated_engine_alias_pin_resolves_ok(self):
        """Alias ref (v1-latest-style): gen_engine names dir by short sha,
        check_engine_sync with --ref <alias> still says OK."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            _run(["git", "tag", "-a", "v1.0.2", "-m", "release"], cwd=repo)
            _run(["git", "tag", "-a", "v1-latest", "-m", "alias"], cwd=repo)

            gen = os.path.join(WORKTREE, "tools", "gen_engine.sh")
            result = _run(["bash", gen, "v1-latest"], cwd=repo)
            self.assertEqual(result.returncode, 0, result.stderr)

            short_sha = _run(
                ["git", "rev-parse", "--short=7", "v1-latest^{commit}"], cwd=repo
            ).stdout.strip()
            engine_dir = os.path.join(repo, ".engine", short_sha)
            result = _run([
                "python3", CHECK_ENGINE,
                "--engine-dir", engine_dir, "--ref", "v1-latest", "--root", repo,
            ])
            self.assertEqual(result.returncode, 0)
            self.assertIn(
                "engine-sync: OK",
                result.stdout,
                f"alias-pinned engine must be OK, got: {result.stdout.strip()}",
            )


if __name__ == "__main__":
    unittest.main()
