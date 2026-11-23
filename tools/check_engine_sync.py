#!/usr/bin/env python3
"""check_engine_sync.py — advisory engine-pin consistency check.

Usage:
    python3 tools/check_engine_sync.py [--engine-dir DIR] [--ref REF] [--root DIR]

Reads DIST-SOURCE from the engine directory, resolves the expected commit from
the git ref, and emits a single-line verdict:

    engine-sync: OK|MISMATCH|STALE|MISSING | dir=... pin=... current=...

Verdicts:
    OK       pin commit == resolved ref commit
    MISMATCH DIST-SOURCE commit differs from resolved ref commit
    STALE    same as MISMATCH but generated timestamp > 14 days old
             (STALE replaces MISMATCH when age > 14 days)
    MISSING  no DIST-SOURCE found / engine dir absent

Exit codes:
    0  verdict emitted (always, warn-only per OP-1)
    2  usage error (bad flags)

Always single-line stdout.  Never writes, never modifies.

Ref resolution:
    --ref  default v1-latest (falls back to v1-stable if v1-latest missing).
    Resolution:  git rev-parse <ref>^{commit}
    Tolerates missing refs / detached HEAD → MISSING or ERROR line, exit 0.
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import subprocess
import sys


def _run(cmd, cwd=None, check=False):
    """Run a command; return CompletedProcess."""
    return subprocess.run(
        cmd, capture_output=True, text=True, cwd=cwd, check=check,
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Advisory engine-pin consistency check.",
    )
    parser.add_argument(
        "--engine-dir", default=None,
        help="Engine directory containing DIST-SOURCE.",
    )
    parser.add_argument(
        "--ref", default="v1-latest",
        help="Git ref to resolve against (default: v1-latest).",
    )
    parser.add_argument(
        "--root", default=None,
        help="Git repository root (default: cwd).",
    )
    return parser.parse_args()


def find_dist_source(engine_dir):
    """Read DIST-SOURCE from the engine dir. Returns parsed dict or None."""
    if not engine_dir or not os.path.isdir(engine_dir):
        return None
    ds_path = os.path.join(engine_dir, "DIST-SOURCE")
    if not os.path.isfile(ds_path):
        return None
    result = {}
    with open(ds_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line:
                key, val = line.split("=", 1)
                result[key.strip()] = val.strip()
    return result if result else None


def resolve_ref_commit(ref, root, pin_tag=None):
    """Resolve a git ref to its commit SHA. Returns sha8 string or None.
    
    Falls back to pin_tag (from DIST-SOURCE) if the primary ref fails.
    """
    if not root:
        root = os.getcwd()
    for candidate in [ref] + ([pin_tag] if pin_tag else []):
        try:
            out = _run(
                ["git", "rev-parse", candidate + "^{commit}"],
                cwd=root, check=True,
            )
            sha = out.stdout.strip()
            return sha[:8]
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return None


def check_engine_sync(engine_dir, ref, root):
    """Main check logic. Returns (verdict, details_string, exit_code)."""
    root = root or os.getcwd()

    # Determine engine directory if not specified
    if not engine_dir:
        # Find first DIST-SOURCE under root/.engine/ lexicographically
        engine_root = os.path.join(root, ".engine")
        if os.path.isdir(engine_root):
            candidates = sorted(
                os.path.join(engine_root, d)
                for d in os.listdir(engine_root)
                if os.path.isdir(os.path.join(engine_root, d))
            )
            for d in candidates:
                ds = os.path.join(d, "DIST-SOURCE")
                if os.path.isfile(ds):
                    engine_dir = d
                    break

    if not engine_dir:
        return (
            "MISSING",
            f"dir=none pin=none current=none",
            0,
        )

    ds = find_dist_source(engine_dir)
    if ds is None:
        return (
            "MISSING",
            f"dir={engine_dir} pin=none current=none",
            0,
        )

    pin_tag = ds.get("tag", "unknown")
    pin_commit = ds.get("commit", "")
    short_pin = pin_commit[:8] if pin_commit else "unknown"
    generated_str = ds.get("generated", "")

    # Resolve current commit from ref (with pin tag fallback)
    current_commit = resolve_ref_commit(ref, root, pin_tag=pin_tag if pin_tag != "unknown" else None)

    if current_commit is None:
        return (
            "MISSING",
            f"dir={engine_dir} pin={pin_tag}@{short_pin} current=none",
            0,
        )

    # Check generated age for STALE detection
    is_stale = False
    if generated_str:
        try:
            gen_time = datetime.datetime.strptime(
                generated_str, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=datetime.timezone.utc)
            now = datetime.datetime.now(datetime.timezone.utc)
            age = (now - gen_time).total_seconds()
            if age > 14 * 24 * 3600:
                is_stale = True
        except (ValueError, TypeError):
            pass

    # Compare commits (short form comparison)
    short_pin = pin_commit[:8] if pin_commit else "unknown"
    if pin_commit and current_commit and pin_commit[:8] == current_commit:
        return (
            "OK",
            f"dir={engine_dir} pin={pin_tag}@{short_pin} current={current_commit}",
            0,
        )

    if is_stale:
        return (
            "STALE",
            f"dir={engine_dir} pin={pin_tag}@{short_pin} current={current_commit}",
            0,
        )

    return (
        "MISMATCH",
        f"dir={engine_dir} pin={pin_tag}@{short_pin} current={current_commit}",
        0,
    )


def main():
    args = parse_args()

    engine_dir = args.engine_dir
    ref = args.ref
    root = args.root

    verdict, details, exit_code = check_engine_sync(engine_dir, ref, root)

    line = f"engine-sync: {verdict} | {details}"
    print(line, flush=True)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
