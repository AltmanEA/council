#!/usr/bin/env python3
"""check_forward_port.py — forward-port / premise-shift audit.

Usage:
    python3 tools/check_forward_port.py --base <ref> --branch <ref> --path <dir> \\
        [--source <ref>] [--against <dir>] [--root DIR] [--min-len N]
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

_MARKDOWN_SYNTAX = re.compile(r'^[#*_~`\-]+$')


class CheckErrorParser(argparse.ArgumentParser):
    """Argparse subclass that prefixes errors with 'check_forward_port: '."""

    def error(self, message):
        """Override to produce 'check_forward_port: <message>' on stderr."""
        self.exit(2, "check_forward_port: error: %s\n" % message)


def _run(cmd, cwd=None, check=False):
    """Run a command; return CompletedProcess."""
    return subprocess.run(
        cmd, capture_output=True, text=True, cwd=cwd, check=check,
    )


def _error(msg):
    """Print ERROR line to stdout and exit 0."""
    print("ERROR: " + msg, flush=True)
    sys.exit(0)


def parse_args():
    parser = CheckErrorParser(
        description="Forward-port / premise-shift audit.",
    )
    parser.add_argument(
        "--base", required=True,
        help="Starting-point ref (e.g. v1-stable).",
    )
    parser.add_argument(
        "--branch", required=True,
        help="Branch ref to audit backports on (e.g. v2-dev).",
    )
    parser.add_argument(
        "--path", required=True,
        help="Source-side directory prefix (e.g. fallback/).",
    )
    parser.add_argument(
        "--source", default="HEAD",
        help="Source ref to enumerate fix commits from (default: HEAD).",
    )
    parser.add_argument(
        "--against", default=None,
        help="Branch-side directory prefix for content search (default: --path).",
    )
    parser.add_argument(
        "--root", default=None,
        help="Git repository root (default: cwd).",
    )
    parser.add_argument(
        "--min-len", type=int, default=10,
        help="Minimum stripped line length for content check (default: 10).",
    )
    return parser.parse_args()


def _is_valid_commit_ref(ref, root):
    """Check if ref resolves to a valid commit in the repo."""
    out = _run(["git", "rev-parse", ref + "^{commit}"], cwd=root)
    return out.returncode == 0


def get_fix_commits(base, source, path, root):
    """Return list of SHA strings from git log, newest first."""
    out = _run(["git", "log", "--format=%H",
                base + ".." + source, "--", path],
               cwd=root)
    if out.returncode != 0:
        return None
    shas = out.stdout.strip().splitlines()
    return shas if shas else []


def _parse_commit_body(sha, root):
    """Parse a commit object into (subject, body_lines) tuple."""
    out = _run(["git", "cat-file", "-p", sha], cwd=root)
    if out.returncode != 0:
        return None, []
    lines = out.stdout.splitlines()
    # First line is the commit header
    subject = ""
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("tree "):
            # Header lines: tree, parent, author, committer
            body_start = i + 1
            # Subject is the first non-header line (after empty separator)
            for j in range(i + 1, len(lines)):
                if lines[j] == "":
                    body_start = j + 1
                    break
            break
    # Extract subject (first line of body)
    body_lines = lines[body_start:]
    if body_lines:
        subject = body_lines[0]
        body_lines = body_lines[1:]  # skip subject for trailer checks
    return subject, body_lines


def find_backport_commits(branch, sha, sha_prefix, root):
    """Find backport commits on branch referencing *sha* via backport-of trailer.

    Returns list of (commit_sha, subject) tuples.
    We get all commits on the branch and filter by their body for backport-of.
    """
    # Get all commit hashes on the branch
    out = _run(["git", "log", branch, "--format=%H"], cwd=root)
    if out.returncode != 0:
        return []

    shas = out.stdout.strip().splitlines()
    result = []
    for csha in shas:
        subject, body_lines = _parse_commit_body(csha, root)
        if subject is None:
            continue
        for bl in body_lines:
            if bl.startswith("backport-of: "):
                val = bl[len("backport-of: "):]
                if val == sha or val[:7] == sha_prefix:
                    result.append((csha, subject))
                    break
    return result


def check_premise_shift(body_lines):
    """Return True if premise-shift trailer is valid, False otherwise.

    body_lines: list of lines from commit body (after subject).
    """
    for line in body_lines:
        if line.startswith("premise-shift: "):
            val = line[len("premise-shift: "):]
            if val == "none":
                return True
            if re.match(r'^affects=.+$', val):
                return True
    return False


def get_branch_files(branch, against, root):
    """Return set of file paths under --against on the branch."""
    out = _run(["git", "ls-tree", "-r", "--name-only",
                branch, "--", against], cwd=root)
    if out.returncode != 0:
        return set()
    files = out.stdout.strip().splitlines()
    return set(f for f in files if f)


def get_file_lines(branch, path, root):
    """Return stripped lines of a file as it exists in branch tree."""
    out = _run(["git", "show", branch + ":" + path], cwd=root)
    if out.returncode != 0:
        return set()
    return set(l.rstrip() for l in out.stdout.splitlines())


def check_content(add_lines, branch, against, root, min_len):
    """Check that all added lines exist somewhere in branch --against tree.

    Returns (all_present, missing_count).
    """
    if not add_lines:
        return True, 0

    files_in_tree = get_branch_files(branch, against, root)

    # Collect all stripped lines from all files
    all_lines = set()
    for fpath in files_in_tree:
        content_lines = get_file_lines(branch, fpath, root)
        all_lines.update(content_lines)

    missing = 0
    for line in add_lines:
        if line not in all_lines:
            missing += 1
    return missing == 0, missing


def build_added_lines(sha, path, root, min_len):
    """Extract content-worthy added lines from a fix commit."""
    out = _run(["git", "show", sha, "--", path], cwd=root)
    if out.returncode != 0:
        return []
    add_lines = []
    for line in out.stdout.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            stripped = line[1:].strip()
            if len(stripped) < min_len:
                continue
            if _MARKDOWN_SYNTAX.match(stripped):
                continue
            add_lines.append(stripped)
    return add_lines


def main():
    args = parse_args()

    root = args.root or os.getcwd()
    against = args.against if args.against else args.path
    min_len = args.min_len

    # Verify we can resolve base and branch as commit refs
    for ref, label in [(args.base, "base"), (args.branch, "branch")]:
        if not _is_valid_commit_ref(ref, root):
            _error("unresolvable " + label + " '" + ref + "'")

    # Check if repo has commits
    out = _run(["git", "rev-parse", "HEAD"], cwd=root)
    if out.returncode != 0:
        _error("empty repository")

    # Also verify source resolves
    if not _is_valid_commit_ref(args.source, root):
        _error("unresolvable source '" + args.source + "'")

    # Get fix commits
    fix_shas = get_fix_commits(args.base, args.source, args.path, root)
    if fix_shas is None:
        _error("unable to resolve base..source range")

    findings = []

    for sha in fix_shas:
        sha8 = sha[:8]
        sha_prefix = sha[:7]

        # Get fix commit subject
        subject, _ = _parse_commit_body(sha, root)
        if not subject:
            subject = sha8

        # 1. Trailer check — find backport commits on branch via body search
        backports = find_backport_commits(args.branch, sha, sha_prefix, root)

        if not backports:
            findings.append("MISSING-TRAILER " + sha8 + " " + subject)
            continue

        # 2. Premise-shift check on every backport commit body
        for bp_sha, bp_subject in backports:
            _, bp_body = _parse_commit_body(bp_sha, root)
            if not check_premise_shift(bp_body):
                bp_sha8 = bp_sha[:8]
                findings.append("BAD-PREMISE-SHIFT " + bp_sha8)

        # 3. Content check — added lines must appear in branch --against tree
        add_lines = build_added_lines(sha, args.path, root, min_len)

        if add_lines:
            all_present, missing_count = check_content(
                add_lines, args.branch, against, root, min_len)
            if not all_present:
                findings.append("MISSING-CONTENT " + sha8 + " " +
                                str(missing_count) + " missing lines")

    for f in findings:
        print(f, flush=True)

    sys.exit(0)


if __name__ == "__main__":
    main()
