#!/usr/bin/env python3
"""test_gen_engine.py — unit tests for tools/gen_engine.sh

Tests pin the behavior of gen_engine.sh (Acceptance Criteria 1–4):
  AC-1:  happy path — extracts fallback/.md files, adds ENGINE header,
         produces DIST-SOURCE with tag/tree/generated.
  AC-2:  idempotency — second run yields same file set and content
         modulo the generated= timestamp.
  AC-3:  errors — missing arg, unknown ref, ref without fallback/ → exit 2.
  AC-4:  version naming — exact tag → .engine/<tag>/, non-tag → .engine/<sha>/.

Every test creates a throwaway git repo in a TemporaryDirectory.
No network, no council-repo tags, no writes outside the tmpdir.
"""

import datetime
import difflib
import hashlib
import os
import re
import subprocess
import tempfile
import unittest

WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN_ENGINE = os.path.join(WORKTREE, "tools", "gen_engine.sh")


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


class TestGenEngineHappyPath(unittest.TestCase):
    """AC-1: gen_engine.sh extracts fallback/ .md files with header + DIST-SOURCE."""

    def test_fallback_files_copied_with_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            _run(["git", "tag", "test-tag"], cwd=repo)

            engine_dir = os.path.join(repo, ".engine", "test-tag")
            result = _run(["bash", GEN_ENGINE, "test-tag"], cwd=repo)
            self.assertEqual(result.returncode, 0, f"exit 0 expected, got {result.returncode}: {result.stderr}")

            md_file = os.path.join(engine_dir, "index.md")
            self.assertTrue(os.path.isfile(md_file), "fallback/index.md must be copied")

            with open(md_file) as f:
                content = f.read()
            # Must have ENGINE header before H1
            self.assertRegex(
                content,
                r"^ENGINE: test-tag @ [a-f0-9]+ — generated, do not edit\n",
                "First line must be ENGINE header",
            )
            # Blank line after header
            lines = content.split("\n", 1)
            self.assertEqual(len(lines), 2, "Header must be followed by a blank line, then content")
            self.assertIn("Hello World", lines[1], "Original content must follow header")

    def test_dist_source_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            _run(["git", "tag", "test-tag"], cwd=repo)

            engine_dir = os.path.join(repo, ".engine", "test-tag")
            _run(["bash", GEN_ENGINE, "test-tag"], cwd=repo)

            ds = os.path.join(engine_dir, "DIST-SOURCE")
            self.assertTrue(os.path.isfile(ds), "DIST-SOURCE must be created")

            with open(ds) as f:
                lines = f.read().strip().split("\n")

            keys = {}
            for line in lines:
                key, val = line.split("=", 1)
                keys[key.strip()] = val.strip()

            self.assertIn("tag", keys, "DIST-SOURCE must have tag=")
            self.assertIn("tree", keys, "DIST-SOURCE must have tree=")
            self.assertIn("commit", keys, "DIST-SOURCE must have commit=")
            self.assertIn("generated", keys, "DIST-SOURCE must have generated=")
            # Verify tag matches the ref
            self.assertEqual(keys["tag"], "test-tag", f"tag= must match ref, got {keys['tag']}")

    def test_multiple_fallback_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = os.path.join(tmpdir, "repo")
            os.makedirs(os.path.join(repo, "fallback"))
            with open(os.path.join(repo, "fallback", "a.md"), "w") as f:
                f.write("# A\n")
            with open(os.path.join(repo, "fallback", "b.md"), "w") as f:
                f.write("# B\n")
            _run(["git", "init"], cwd=repo)
            _run(["git", "config", "user.email", "test@test.com"], cwd=repo)
            _run(["git", "config", "user.name", "test"], cwd=repo)
            _run(["git", "add", "."], cwd=repo)
            _run(["git", "commit", "-m", "init"], cwd=repo)
            _run(["git", "tag", "multi"], cwd=repo)

            engine_dir = os.path.join(repo, ".engine", "multi")
            result = _run(["bash", GEN_ENGINE, "multi"], cwd=repo)
            self.assertEqual(result.returncode, 0)

            self.assertTrue(os.path.isfile(os.path.join(engine_dir, "a.md")))
            self.assertTrue(os.path.isfile(os.path.join(engine_dir, "b.md")))


class TestGenEngineIdempotency(unittest.TestCase):
    """AC-2: second run → same file set, same content modulo generated=."""

    def test_idempotent_except_generated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            _run(["git", "tag", "test-tag"], cwd=repo)

            engine_dir = os.path.join(repo, ".engine", "test-tag")

            # First run
            _run(["bash", GEN_ENGINE, "test-tag"], cwd=repo)
            ds1 = self._read_file(os.path.join(engine_dir, "DIST-SOURCE"))
            md1 = self._read_file(os.path.join(engine_dir, "index.md"))
            files1 = set(os.listdir(engine_dir))

            # Second run (same tag)
            _run(["bash", GEN_ENGINE, "test-tag"], cwd=repo)
            ds2 = self._read_file(os.path.join(engine_dir, "DIST-SOURCE"))
            md2 = self._read_file(os.path.join(engine_dir, "index.md"))
            files2 = set(os.listdir(engine_dir))

            # Same file set
            self.assertEqual(files1, files2, "File set must be identical")

            # Same .md content (header + body)
            self.assertEqual(md1, md2, "MD content must be identical")

            # DIST-SOURCE: same except generated= line
            self._compare_dist_source(ds1, ds2)

    def _read_file(self, path):
        with open(path) as f:
            return f.read()

    def _compare_dist_source(self, ds1, ds2):
        lines1 = [l for l in ds1.strip().split("\n") if not l.startswith("generated=")]
        lines2 = [l for l in ds2.strip().split("\n") if not l.startswith("generated=")]
        self.assertEqual(lines1, lines2, "DIST-SOURCE must be identical except for generated=")


class TestGenEngineErrors(unittest.TestCase):
    """AC-3: error cases all produce exit 2."""

    def test_missing_argument(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run(["bash", GEN_ENGINE])
            self.assertEqual(result.returncode, 2, f"exit 2 for missing arg, got {result.returncode}")
            self.assertIn("gen_engine:", result.stderr, "Error prefix on stderr")

    def test_unknown_ref(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            result = _run(["bash", GEN_ENGINE, "nonexistent-ref"], cwd=repo)
            self.assertEqual(result.returncode, 2, f"exit 2 for unknown ref, got {result.returncode}")
            self.assertIn("gen_engine:", result.stderr, "Error prefix on stderr")

    def test_ref_without_fallback(self):
        """A ref that has no fallback/ directory → exit 2."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = os.path.join(tmpdir, "repo")
            os.makedirs(repo)
            with open(os.path.join(repo, "README.md"), "w") as f:
                f.write("# README\n")
            _run(["git", "init"], cwd=repo)
            _run(["git", "config", "user.email", "test@test.com"], cwd=repo)
            _run(["git", "config", "user.name", "test"], cwd=repo)
            _run(["git", "add", "."], cwd=repo)
            _run(["git", "commit", "-m", "init"], cwd=repo)

            # Add fallback, tag, then remove fallback and create another commit
            os.makedirs(os.path.join(repo, "fallback"))
            with open(os.path.join(repo, "fallback", "index.md"), "w") as f:
                f.write("# Hello\n")
            _run(["git", "add", "."], cwd=repo)
            _run(["git", "commit", "-m", "add fallback"], cwd=repo)
            _run(["git", "tag", "has-fb"], cwd=repo)

            # Create a commit that removes fallback/
            import shutil
            shutil.rmtree(os.path.join(repo, "fallback"))
            _run(["git", "add", "."], cwd=repo)
            _run(["git", "commit", "-m", "remove fallback"], cwd=repo)
            _run(["git", "tag", "no-fb"], cwd=repo)

            result = _run(["bash", GEN_ENGINE, "no-fb"], cwd=repo)
            self.assertEqual(result.returncode, 2, f"exit 2 for ref without fallback/, got {result.returncode}")
            self.assertIn("gen_engine:", result.stderr, "Error prefix on stderr")


class TestGenEngineVersionNaming(unittest.TestCase):
    """AC-4: exact tag → .engine/<tag>/, non-tag ref → .engine/<short-sha>/."""

    def test_exact_tag_naming(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            _run(["git", "tag", "v1.0.0"], cwd=repo)

            _run(["bash", GEN_ENGINE, "v1.0.0"], cwd=repo)

            engine_dir = os.path.join(repo, ".engine", "v1.0.0")
            self.assertTrue(
                os.path.isdir(engine_dir),
                f"Exact tag must use .engine/<tag>/, got: {os.listdir(os.path.join(repo, '.engine'))}",
            )

    def test_non_tag_ref_naming(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            # No tags — the ref will be a commit SHA (HEAD)
            head_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True,
            ).stdout.strip()
            short_sha = head_sha[:7]

            _run(["bash", GEN_ENGINE, "HEAD"], cwd=repo)

            engine_dir = os.path.join(repo, ".engine", short_sha)
            self.assertTrue(
                os.path.isdir(engine_dir),
                f"Non-tag ref must use .engine/<short-sha>/, got: {os.listdir(os.path.join(repo, '.engine'))}",
            )


class TestGenEngineAnnotatedTag(unittest.TestCase):
    """AC-7: annotated tag peels to the COMMIT sha (not the tag-object sha)."""

    def _keys(self, ds_path):
        keys = {}
        with open(ds_path) as f:
            for line in f.read().strip().split("\n"):
                if "=" in line:
                    k, v = line.split("=", 1)
                    keys[k.strip()] = v.strip()
        return keys

    def test_annotated_tag_commit_is_commit_sha(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            _run(["git", "tag", "-a", "v1.0.2", "-m", "release"], cwd=repo)
            commit_sha = _run(["git", "rev-parse", "v1.0.2^{commit}"], cwd=repo).stdout.strip()
            tag_obj_sha = _run(["git", "rev-parse", "v1.0.2"], cwd=repo).stdout.strip()

            result = _run(["bash", GEN_ENGINE, "v1.0.2"], cwd=repo)
            self.assertEqual(result.returncode, 0, result.stderr)

            engine_dir = os.path.join(repo, ".engine", "v1.0.2")
            keys = self._keys(os.path.join(engine_dir, "DIST-SOURCE"))
            self.assertEqual(
                keys["commit"], commit_sha,
                "commit= must be the peels-to-commit sha for annotated tags",
            )
            self.assertNotEqual(keys["commit"], "", "commit= non-empty")
            if tag_obj_sha != commit_sha:
                self.assertNotEqual(
                    keys["commit"], tag_obj_sha,
                    "commit= must NOT be the tag-object sha",
                )

    def test_annotated_tag_tree_is_sha(self):
        """AC-8: tree= is a 40-hex sha equal to rev-parse <ref>^{tree} (annotated)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            _run(["git", "tag", "-a", "v1.0.2", "-m", "release"], cwd=repo)
            tree_sha = _run(["git", "rev-parse", "v1.0.2^{tree}"], cwd=repo).stdout.strip()

            result = _run(["bash", GEN_ENGINE, "v1.0.2"], cwd=repo)
            self.assertEqual(result.returncode, 0, result.stderr)

            engine_dir = os.path.join(repo, ".engine", "v1.0.2")
            keys = self._keys(os.path.join(engine_dir, "DIST-SOURCE"))
            self.assertRegex(
                keys["tree"], r"^[0-9a-f]{40}$",
                f"tree= must be a 40-hex sha, got {keys['tree']!r}",
            )
            self.assertEqual(keys["tree"], tree_sha, "tree= must equal <ref>^{tree}")

    def test_lightweight_tag_tree_is_sha(self):
        """AC-8 (lightweight tags keep working)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            _run(["git", "tag", "v0.6.1"], cwd=repo)
            tree_sha = _run(["git", "rev-parse", "v0.6.1^{tree}"], cwd=repo).stdout.strip()

            result = _run(["bash", GEN_ENGINE, "v0.6.1"], cwd=repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            keys = self._keys(os.path.join(repo, ".engine", "v0.6.1", "DIST-SOURCE"))
            self.assertEqual(keys["tree"], tree_sha)


class TestGenEngineAliasDirNaming(unittest.TestCase):
    """AC-9: moving/anchor aliases must not appear in the default engine path
    (operator decision 4: semver or short sha in the path; aliases only in pin)."""

    def test_alias_tag_names_dir_by_short_sha(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            # annotated semver tag FIRST, then alias tag — alias wins describe (iter-3 repro)
            _run(["git", "tag", "-a", "v1.0.2", "-m", "release"], cwd=repo)
            _run(["git", "tag", "-a", "v1-latest", "-m", "alias"], cwd=repo)
            short_sha = _run(["git", "rev-parse", "--short=7", "v1-latest^{commit}"], cwd=repo).stdout.strip()

            result = _run(["bash", GEN_ENGINE, "v1-latest"], cwd=repo)
            self.assertEqual(result.returncode, 0, result.stderr)

            self.assertFalse(
                os.path.isdir(os.path.join(repo, ".engine", "v1-latest")),
                "alias v1-latest must NOT be the engine dir name (decision 4)",
            )
            self.assertFalse(
                os.path.isdir(os.path.join(repo, ".engine", "v1-stable")),
                "alias dir must not exist",
            )
            self.assertTrue(
                os.path.isdir(os.path.join(repo, ".engine", short_sha)),
                f"alias must name the dir by short commit sha {short_sha}, got {os.listdir(os.path.join(repo, '.engine'))}",
            )
            # DIST-SOURCE still records the requested alias ref
            with open(os.path.join(repo, ".engine", short_sha, "DIST-SOURCE")) as f:
                ds = f.read()
            self.assertIn("tag=v1-latest", ds)

    def test_semver_tag_names_dir_by_tag(self):
        """Exact semver-shaped tag (no alias) → .engine/<tag>/ still works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _setup_repo(tmpdir, "index.md")
            _run(["git", "tag", "-a", "v1.0.3", "-m", "release"], cwd=repo)

            result = _run(["bash", GEN_ENGINE, "v1.0.3"], cwd=repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(os.path.isdir(os.path.join(repo, ".engine", "v1.0.3")))


if __name__ == "__main__":
    unittest.main()