#!/usr/bin/env python3
"""test_check_forward_port.py — unit tests for tools/check_forward_port.py

Tests pin the forward-port / premise-shift audit behavior (Acceptance Criteria 1-8):
  AC-1: Clean state → empty stdout, exit 0 (fix on source + paired backport
        on branch with backport-of: + premise-shift: none + content in draft/).
  AC-2: Missing backport commit → MISSING-TRAILER line, exit 0.
  AC-3: Backport without premise-shift trailer or with malformed value
        → BAD-PREMISE-SHIFT line, exit 0.
  AC-4: Backport present but fix content absent from --against tree
        → MISSING-CONTENT <sha8> N missing lines, exit 0.
  AC-5: --against draft/ maps content search to branch-side dir while
        --path fallback/ filters source commits (the fallback<->draft duality).
  AC-6: Content check: --min-len exemption, markdown-syntax-only lines skipped,
        multiple fix commits → per-commit violation lines (newest-first),
        sha-prefix (>=7 hex) trailer accepted.
  AC-7: Unresolvable refs / empty repo → ERROR: line on stdout, exit 0.
  AC-8: Usage errors (missing required flag, bad flag, bad --min-len value)
        → stderr check_forward_port:, exit 2.

Every test creates a throwaway git repo in a TemporaryDirectory.
No network, no council-repo tags, no writes outside the tmpdir.
"""

import os
import re
import subprocess
import tempfile
import unittest

WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK_FP = os.path.join(WORKTREE, "tools", "check_forward_port.py")


def _run(cmd, cwd=None, env=None):
    """Run a command; return CompletedProcess."""
    return subprocess.run(
        cmd, capture_output=True, text=True, cwd=cwd, env=env,
    )


def _git(repo, *args):
    """Run git command in repo; return CompletedProcess."""
    return _run(["git"] + list(args), cwd=repo)


def _setup_fixture(tmpdir, with_backport=True, backport_premise="none",
                   extra_draft_lines=None, extra_draft_files=None):
    """Build a two-branch fixture in a TemporaryDirectory.

    Structure:
      master - base commit -> fix commit (fallback/index.md)
      v2-dev - detached at base, backport commit (draft/index.md)

    Extra content in draft/ can be specified via extra_draft_lines (lines to add
    after base content) and extra_draft_files (dict of rel_path -> content).

    Returns (repo, master_sha) or (repo, master_sha, backport_sha).
    """
    repo = os.path.join(tmpdir, "repo")
    os.makedirs(repo)

    # Init
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "test")

    # Create base content directory and file
    fb_dir = os.path.join(repo, "fallback")
    dr_dir = os.path.join(repo, "draft")
    os.makedirs(fb_dir)
    os.makedirs(dr_dir)
    base_file = os.path.join(fb_dir, "index.md")
    with open(base_file, "w") as f:
        f.write("# Base\n\noriginal content\n")
    with open(os.path.join(dr_dir, "index.md"), "w") as f:
        f.write("# Base\n\noriginal content\n")

    # Base commit
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    _git(repo, "tag", "-a", "v1-stable", "-m", "base tag")

    # Fix commit on master (source)
    with open(base_file, "a") as f:
        f.write("NEW LINE: this is the fix body content\n")
    _git(repo, "add", "fallback/")
    _git(repo, "commit", "-m", "fix index")
    master_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    # Detach HEAD, create v2-dev at base, add backport
    _git(repo, "checkout", "-B", "v2-dev", "v1-stable")

    # Write base content to draft (always)
    with open(os.path.join(dr_dir, "index.md"), "w") as f:
        f.write("# Base\n\noriginal content\n")
    # Write base content to fallback on branch too (for content check with
    # default --against which equals --path)
    with open(os.path.join(fb_dir, "index.md"), "w") as f:
        f.write("# Base\n\noriginal content\n")

    # Auto-generate fix content on v2-dev depending on whether extra_draft_lines
    # was explicitly provided.  None (default) → both draft/ and fallback/ so
    # the content check passes with default --against.  Explicit [] or custom
    # list → draft/ only so the content check fails when --against defaults
    # to --path (fallback/).
    if with_backport and extra_draft_lines is None:
        fix_line = "NEW LINE: this is the fix body content\n"
        with open(os.path.join(dr_dir, "index.md"), "a") as f:
            f.write(fix_line)
        with open(os.path.join(fb_dir, "index.md"), "a") as f:
            f.write(fix_line)
    elif with_backport and extra_draft_lines is not None:
        with open(os.path.join(dr_dir, "index.md"), "a") as f:
            f.write("NEW LINE: this is the fix body content\n")

    if extra_draft_files:
        for rel_path, content in extra_draft_files.items():
            p = os.path.join(repo, rel_path)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write(content)

    if extra_draft_lines is not None:
        with open(os.path.join(dr_dir, "index.md"), "a") as f:
            for line in extra_draft_lines:
                f.write(line + "\n")

    if with_backport:
        _git(repo, "commit", "-m", "fix index",
             "-m", "backport-of: %s" % master_sha,
             "-m", "premise-shift: %s" % backport_premise,
             "--", "draft/", "fallback/")
        bp_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "checkout", "-q", "master")
        return repo, master_sha, bp_sha
    _git(repo, "checkout", "-q", "master")
    return repo, master_sha


class TestForwardPortCleanState(unittest.TestCase):
    """AC-1: Clean state → empty stdout, exit 0.

    Fix on source + paired backport on branch with backport-of: +
    premise-shift: none + content present in draft/.
    """

    def test_clean_forward_port_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo, master_sha, bp_sha = _setup_fixture(tmpdir, with_backport=True,
                                                       backport_premise="none")

            result = _run([
                "python3", CHECK_FP,
                "--base", "v1-stable",
                "--branch", "v2-dev",
                "--path", "fallback/",
                "--root", repo,
            ])
            self.assertEqual(result.returncode, 0,
                             f"exit 0 required, got {result.returncode}: {result.stderr}")
            self.assertEqual(result.stdout.strip(), "",
                             f"Clean audit must produce empty stdout, got: {result.stdout!r}")


class TestForwardPortMissingTrailer(unittest.TestCase):
    """AC-2: Missing backport commit → MISSING-TRAILER line, exit 0."""

    def test_missing_trailer_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo, master_sha = _setup_fixture(tmpdir, with_backport=False)

            result = _run([
                "python3", CHECK_FP,
                "--base", "v1-stable",
                "--branch", "v2-dev",
                "--path", "fallback/",
                "--root", repo,
            ])
            self.assertEqual(result.returncode, 0,
                             f"exit 0 required, got {result.returncode}: {result.stderr}")
            self.assertIn("MISSING-TRAILER", result.stdout,
                          "Must report MISSING-TRAILER for unbackported fix")
            sha8 = master_sha[:8]
            self.assertIn(sha8, result.stdout, "Must include fix sha8")
            self.assertIn("fix index", result.stdout, "Must include fix subject")


class TestForwardPortBadPremiseShift(unittest.TestCase):
    """AC-3: Backport without premise-shift trailer or with malformed value
    → BAD-PREMISE-SHIFT line, exit 0."""

    def test_bad_premise_shift_value(self):
        """Malformed premise-shift value (not 'none' or 'affects=<non-empty>')."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo, master_sha, bp_sha = _setup_fixture(tmpdir, with_backport=True,
                                                       backport_premise="changed")
            sha8 = master_sha[:8]
            bp_sha8 = bp_sha[:8]

            result = _run([
                "python3", CHECK_FP,
                "--base", "v1-stable",
                "--branch", "v2-dev",
                "--path", "fallback/",
                "--root", repo,
            ])
            self.assertEqual(result.returncode, 0,
                             f"exit 0 required, got {result.returncode}: {result.stderr}")
            self.assertIn("BAD-PREMISE-SHIFT", result.stdout,
                          "Must report BAD-PREMISE-SHIFT for invalid value")
            self.assertIn(bp_sha8, result.stdout, "Must include backport sha8")

    def test_missing_premise_shift_trailer(self):
        """Backport commit lacks premise-shift trailer entirely."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo, master_sha = _setup_fixture(tmpdir, with_backport=False)

            # Create backport commit manually without premise-shift trailer,
            # on the BRANCH side (fixture returns HEAD on master; the backport
            # must live on v2-dev, and the invocation must run with HEAD==master
            # so the default --source HEAD sees the fix commit).
            _git(repo, "checkout", "-q", "v2-dev")
            dr_dir = os.path.join(repo, "draft")
            with open(os.path.join(dr_dir, "index.md"), "w") as f:
                f.write("# Base\n\noriginal content\n")
                f.write("NEW LINE: this is the fix body content\n")
            _git(repo, "add", "draft/")
            _git(repo, "commit", "-m", "fix index", "-m",
                 "backport-of: %s" % master_sha, "--", "draft/")

            bp_sha8 = _git(repo, "rev-parse", "HEAD").stdout.strip()[:8]
            _git(repo, "checkout", "-q", "master")

            result = _run([
                "python3", CHECK_FP,
                "--base", "v1-stable",
                "--branch", "v2-dev",
                "--path", "fallback/",
                "--root", repo,
            ])
            self.assertEqual(result.returncode, 0)
            self.assertIn("BAD-PREMISE-SHIFT", result.stdout,
                          "Missing premise-shift trailer is a violation")
            self.assertIn(bp_sha8, result.stdout)


class TestForwardPortMissingContent(unittest.TestCase):
    """AC-4: Backport present but fix content absent from --against tree
    → MISSING-CONTENT <sha8> N missing lines, exit 0."""

    def test_missing_content_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo, master_sha, bp_sha = _setup_fixture(tmpdir, with_backport=True,
                                                       backport_premise="none",
                                                       extra_draft_lines=[])
            sha8 = master_sha[:8]

            result = _run([
                "python3", CHECK_FP,
                "--base", "v1-stable",
                "--branch", "v2-dev",
                "--path", "fallback/",
                "--root", repo,
            ])
            self.assertEqual(result.returncode, 0,
                             f"exit 0 required, got {result.returncode}: {result.stderr}")
            self.assertIn("MISSING-CONTENT", result.stdout,
                          "Must report MISSING-CONTENT for absent fix text")
            self.assertIn(sha8, result.stdout, "Must include fix sha8")

    def test_missing_content_with_count(self):
        """Verify the missing line count in MISSING-CONTENT output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo, master_sha, bp_sha = _setup_fixture(
                tmpdir, with_backport=True, backport_premise="none",
                extra_draft_lines=[])
            sha8 = master_sha[:8]

            result = _run([
                "python3", CHECK_FP,
                "--base", "v1-stable",
                "--branch", "v2-dev",
                "--path", "fallback/",
                "--root", repo,
            ])
            self.assertIn("MISSING-CONTENT %s" % sha8, result.stdout,
                          "MISSING-CONTENT line must contain fix sha8")
            self.assertRegex(
                result.stdout,
                r"MISSING-CONTENT %s \d+ missing lines" % re.escape(sha8),
                "Must have format MISSING-CONTENT <sha8> N missing lines",
            )


class TestForwardPortAgainstDuality(unittest.TestCase):
    """AC-5: --against draft/ maps content search to branch-side dir while
    --path fallback/ filters source commits (the fallback<->draft duality).

    Also verifies default --against equals --path value.
    """

    def test_default_against_equals_path(self):
        """Without explicit --against, content is searched under fallback/ (path).
        Backport is in draft/ only (extra_draft_lines=[]) so content check fails
        when --against defaults to --path (fallback/)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo, master_sha, bp_sha = _setup_fixture(tmpdir, with_backport=True,
                                                       backport_premise="none",
                                                       extra_draft_lines=[])

            # --against not specified; defaults to --path = fallback/
            # Draft content is in draft/, NOT fallback/ → content check fails
            result = _run([
                "python3", CHECK_FP,
                "--base", "v1-stable",
                "--branch", "v2-dev",
                "--path", "fallback/",
                "--root", repo,
            ])
            self.assertEqual(result.returncode, 0)
            self.assertIn("MISSING-CONTENT", result.stdout,
                          "Default --against should fall back to path (fallback/)")

    def test_explicit_against_duality(self):
        """Explicit --against draft/ correctly maps content search to branch dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo, master_sha, bp_sha = _setup_fixture(tmpdir, with_backport=True,
                                                       backport_premise="none")

            result = _run([
                "python3", CHECK_FP,
                "--base", "v1-stable",
                "--branch", "v2-dev",
                "--path", "fallback/",
                "--against", "draft/",
                "--root", repo,
            ])
            self.assertEqual(result.returncode, 0,
                             f"exit 0 required, got {result.returncode}: {result.stderr}")
            self.assertEqual(result.stdout.strip(), "",
                             f"With correct --against, must be clean, got: {result.stdout!r}")


class TestForwardPortMinLenExemption(unittest.TestCase):
    """AC-6a: --min-len exemption: added lines shorter than --min-len are skipped."""

    def test_short_lines_exempted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = os.path.join(tmpdir, "repo")
            os.makedirs(repo)
            _git(repo, "init")
            _git(repo, "config", "user.email", "test@test.com")
            _git(repo, "config", "user.name", "test")

            fb_dir = os.path.join(repo, "fallback")
            dr_dir = os.path.join(repo, "draft")
            os.makedirs(fb_dir)
            os.makedirs(dr_dir)
            with open(os.path.join(fb_dir, "index.md"), "w") as f:
                f.write("# Base\n")
            with open(os.path.join(dr_dir, "index.md"), "w") as f:
                f.write("# Base\n")
            _git(repo, "add", ".")
            _git(repo, "commit", "-m", "base")
            _git(repo, "tag", "-a", "v1-stable", "-m", "base tag")

            # Fix: line stripped = 21 chars (default min-len=10, so normally checked)
            with open(os.path.join(fb_dir, "index.md"), "a") as f:
                f.write("NEW LINE: short fix line\n")
            _git(repo, "add", "fallback/")
            _git(repo, "commit", "-m", "fix short")
            master_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

            # Detach HEAD, create v2-dev at base, add backport with same content
            _git(repo, "checkout", "-B", "v2-dev", "v1-stable")
            with open(os.path.join(dr_dir, "index.md"), "a") as f:
                f.write("NEW LINE: short fix line\n")
            _git(repo, "commit", "-m", "fix short",
                 "-m", "backport-of: %s" % master_sha,
                 "-m", "premise-shift: none",
                 "--", "draft/")

            # With --min-len 100: the added line (21 chars) is exempt (21 < 100)
            result = _run([
                "python3", CHECK_FP,
                "--base", "v1-stable",
                "--branch", "v2-dev",
                "--path", "fallback/",
                "--against", "draft/",
                "--min-len", "100",
                "--root", repo,
            ])
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "",
                             f"With high --min-len, short lines exempt, empty stdout")


class TestForwardPortMarkdownLinesSkipped(unittest.TestCase):
    """AC-6b: Markdown-syntax-only lines are skipped from content check."""

    def test_markdown_only_lines_skipped(self):
        """Fix commit adds only markdown syntax lines → no MISSING-CONTENT."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = os.path.join(tmpdir, "repo")
            os.makedirs(repo)
            _git(repo, "init")
            _git(repo, "config", "user.email", "test@test.com")
            _git(repo, "config", "user.name", "test")

            fb_dir = os.path.join(repo, "fallback")
            dr_dir = os.path.join(repo, "draft")
            os.makedirs(fb_dir)
            os.makedirs(dr_dir)
            with open(os.path.join(fb_dir, "index.md"), "w") as f:
                f.write("# Base\n\n")
            with open(os.path.join(dr_dir, "index.md"), "w") as f:
                f.write("# Base\n\n")
            _git(repo, "add", ".")
            _git(repo, "commit", "-m", "base")
            _git(repo, "tag", "-a", "v1-stable", "-m", "base tag")

            # Add only markdown syntax lines (asterisks and hashes)
            with open(os.path.join(fb_dir, "index.md"), "a") as f:
                f.write("***\n")  # 3 chars, short
                f.write("#######\n")  # 7 chars
            _git(repo, "add", "fallback/")
            _git(repo, "commit", "-m", "add markdown lines")
            master_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

            # Detach HEAD, create v2-dev at base, add backport with same content
            _git(repo, "checkout", "-B", "v2-dev", "v1-stable")
            with open(os.path.join(dr_dir, "index.md"), "a") as f:
                f.write("***\n#######\n")
            _git(repo, "commit", "-m", "fix",
                 "-m", "backport-of: %s" % master_sha,
                 "-m", "premise-shift: none",
                 "--", "draft/")

            result = _run([
                "python3", CHECK_FP,
                "--base", "v1-stable",
                "--branch", "v2-dev",
                "--path", "fallback/",
                "--against", "draft/",
                "--root", repo,
            ])
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "",
                             f"Markdown-only content must be skipped, got: {result.stdout!r}")


class TestForwardPortMultipleFixCommits(unittest.TestCase):
    """AC-6c: Multiple fix commits → one violation line per violating commit,
    newest-first order."""

    def test_per_commit_violation_lines_newest_first(self):
        """Two fix commits on master: first clean, second MISSING-CONTENT.
        Output: second fix first (newest), then first fix (missing trailer)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = os.path.join(tmpdir, "repo")
            os.makedirs(repo)
            _git(repo, "init")
            _git(repo, "config", "user.email", "test@test.com")
            _git(repo, "config", "user.name", "test")

            fb_dir = os.path.join(repo, "fallback")
            dr_dir = os.path.join(repo, "draft")
            os.makedirs(fb_dir)
            os.makedirs(dr_dir)
            with open(os.path.join(fb_dir, "index.md"), "w") as f:
                f.write("# Base\n\n")
            with open(os.path.join(dr_dir, "index.md"), "w") as f:
                f.write("# Base\n\n")
            _git(repo, "add", ".")
            _git(repo, "commit", "-m", "base")
            _git(repo, "tag", "-a", "v1-stable", "-m", "base tag")

            # Fix 1 (older): no backport on v2-dev → MISSING-TRAILER
            with open(os.path.join(fb_dir, "index.md"), "a") as f:
                f.write("FIX1: first fix adds valid content here\n")
            _git(repo, "add", "fallback/")
            _git(repo, "commit", "-m", "fix first")
            sha1 = _git(repo, "rev-parse", "HEAD").stdout.strip()

            # Fix 2 (newer): backport present but content differs → MISSING-CONTENT
            with open(os.path.join(fb_dir, "index.md"), "a") as f:
                f.write("FIX2: second fix adds content absent from draft\n")
            _git(repo, "add", "fallback/")
            _git(repo, "commit", "-m", "fix second")
            sha2 = _git(repo, "rev-parse", "HEAD").stdout.strip()

            # Create v2-dev at v1-stable, backport fix2 with stale content only
            _git(repo, "checkout", "-B", "v2-dev", "v1-stable")
            with open(os.path.join(dr_dir, "index.md"), "w") as f:
                f.write("# Base\n\nFIX1: first fix adds valid content here\n")
            _git(repo, "add", "draft/")
            _git(repo, "commit", "-m", "backport second",
                 "-m", "backport-of: %s" % sha2,
                 "-m", "premise-shift: none",
                 "--", "draft/")
            _git(repo, "checkout", "-q", "master")  # invocation HEAD == source

            sha1_8 = sha1[:8]
            sha2_8 = sha2[:8]

            result = _run([
                "python3", CHECK_FP,
                "--base", "v1-stable",
                "--branch", "v2-dev",
                "--path", "fallback/",
                "--against", "draft/",
                "--root", repo,
            ])
            self.assertEqual(result.returncode, 0)
            lines = [l for l in result.stdout.strip().split("\n") if l]
            self.assertEqual(len(lines), 2, "Must have exactly 2 violation lines")
            # Newest (fix2) first
            self.assertIn("MISSING-CONTENT %s" % sha2_8, lines[0],
                          "Newest violation must appear first")
            # Older (fix1) second
            self.assertIn("MISSING-TRAILER %s" % sha1_8, lines[1],
                          "Older violation must appear second")


class TestForwardPortShaPrefixTrailer(unittest.TestCase):
    """AC-6d: SHA prefix (>=7 hex) in backport-of trailer is accepted."""

    def test_sha_prefix_accepted(self):
        """Backport commit uses 7-char hex prefix in backport-of instead of full SHA."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = os.path.join(tmpdir, "repo")
            os.makedirs(repo)
            _git(repo, "init")
            _git(repo, "config", "user.email", "test@test.com")
            _git(repo, "config", "user.name", "test")

            fb_dir = os.path.join(repo, "fallback")
            dr_dir = os.path.join(repo, "draft")
            os.makedirs(fb_dir)
            os.makedirs(dr_dir)
            with open(os.path.join(fb_dir, "index.md"), "w") as f:
                f.write("# Base\n\n")
            with open(os.path.join(dr_dir, "index.md"), "w") as f:
                f.write("# Base\n\n")
            _git(repo, "add", ".")
            _git(repo, "commit", "-m", "base")
            _git(repo, "tag", "-a", "v1-stable", "-m", "base tag")

            # Fix commit
            with open(os.path.join(fb_dir, "index.md"), "a") as f:
                f.write("PREFIX FIX: content added by prefix backport\n")
            _git(repo, "add", "fallback/")
            _git(repo, "commit", "-m", "fix prefix")
            master_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
            sha_prefix = master_sha[:7]  # 7 hex chars

            # Detach HEAD, create v2-dev at base, backport with sha-prefix
            _git(repo, "checkout", "-B", "v2-dev", "v1-stable")
            with open(os.path.join(dr_dir, "index.md"), "w") as f:
                f.write("# Base\n\nPREFIX FIX: content added by prefix backport\n")
            _git(repo, "commit", "-m", "fix prefix",
                 "-m", "backport-of: %s" % sha_prefix,
                 "-m", "premise-shift: none",
                 "--", "draft/")

            result = _run([
                "python3", CHECK_FP,
                "--base", "v1-stable",
                "--branch", "v2-dev",
                "--path", "fallback/",
                "--against", "draft/",
                "--root", repo,
            ])
            self.assertEqual(result.returncode, 0,
                             f"exit 0 required, got {result.returncode}: {result.stderr}")
            self.assertEqual(result.stdout.strip(), "",
                             f"SHA-prefix trailer accepted, empty stdout")


class TestForwardPortErrors(unittest.TestCase):
    """AC-7: Unresolvable refs / empty repo → ERROR: line on stdout, exit 0."""

    def test_unresolvable_ref(self):
        """Bad --base ref that cannot be resolved → ERROR line, exit 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo, _ = _setup_fixture(tmpdir, with_backport=False)

            result = _run([
                "python3", CHECK_FP,
                "--base", "nonexistent-ref",
                "--branch", "v2-dev",
                "--path", "fallback/",
                "--root", repo,
            ])
            self.assertEqual(result.returncode, 0,
                             f"exit 0 required for error, got {result.returncode}")
            self.assertIn("ERROR:", result.stdout,
                          "Unresolvable ref must produce ERROR line")

    def test_empty_repo(self):
        """Empty git repo (no commits) → ERROR line, exit 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = os.path.join(tmpdir, "repo")
            os.makedirs(repo)
            _git(repo, "init")
            _git(repo, "config", "user.email", "test@test.com")
            _git(repo, "config", "user.name", "test")

            result = _run([
                "python3", CHECK_FP,
                "--base", "v1-stable",
                "--branch", "v2-dev",
                "--path", "fallback/",
                "--root", repo,
            ])
            self.assertEqual(result.returncode, 0,
                             f"exit 0 required for error, got {result.returncode}")
            self.assertIn("ERROR:", result.stdout,
                          "Empty repo must produce ERROR line")


class TestForwardPortUsageErrors(unittest.TestCase):
    """AC-8: Usage errors → exit 2, check_forward_port: on stderr."""

    def test_missing_required_flag(self):
        """Missing --base (required flag) → exit 2, check_forward_port: on stderr."""
        result = _run([
            "python3", CHECK_FP,
            "--branch", "v2-dev",
            "--path", "fallback/",
        ])
        self.assertEqual(result.returncode, 2,
                         f"exit 2 for missing required flag, got {result.returncode}")
        self.assertIn("check_forward_port:", result.stderr,
                      "Usage error must prefix with check_forward_port: on stderr")

    def test_unknown_flag(self):
        """Unknown flag → exit 2, check_forward_port: on stderr."""
        result = _run([
            "python3", CHECK_FP,
            "--base", "v1-stable",
            "--branch", "v2-dev",
            "--path", "fallback/",
            "--unknown-flag",
        ])
        self.assertEqual(result.returncode, 2,
                         f"exit 2 for unknown flag, got {result.returncode}")
        self.assertIn("check_forward_port:", result.stderr,
                      "Usage error must prefix with check_forward_port: on stderr")

    def test_bad_min_len(self):
        """--min-len with non-integer value → exit 2."""
        result = _run([
            "python3", CHECK_FP,
            "--base", "v1-stable",
            "--branch", "v2-dev",
            "--path", "fallback/",
            "--min-len", "abc",
        ])
        self.assertEqual(result.returncode, 2,
                         f"exit 2 for bad --min-len, got {result.returncode}")
        self.assertIn("check_forward_port:", result.stderr,
                      "Usage error must prefix with check_forward_port: on stderr")


    def test_default_source_is_head(self):
        """--source omitted → fix commits enumerated from HEAD (AC: CLI contract).

        Fixture ends on v2-dev; checking out master (where the fix commit is
        ahead of v1-stable) and omitting --source must still find the fix
        (MISSING-TRAILER with with_backport=False). If the default were a
        literal branch name like 'master' or 'main', behavior on a detached
        or differently-named HEAD would differ; here HEAD==master is checked
        out explicitly and the finding must appear.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            repo, master_sha = _setup_fixture(tmpdir, with_backport=False)
            _git(repo, "checkout", "master")
            result = _run([
                "python3", CHECK_FP,
                "--base", "v1-stable",
                "--branch", "v2-dev",
                "--path", "fallback/",
                "--root", repo,
            ])
            self.assertEqual(result.returncode, 0)
            self.assertIn(
                "MISSING-TRAILER " + master_sha[:8],
                result.stdout,
                f"--source default must be HEAD (on master): {result.stdout!r}",
            )


if __name__ == "__main__":
    unittest.main()
