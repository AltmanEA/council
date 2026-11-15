#!/usr/bin/env python3
"""session_status.py — Summarise Implementation Worker cycle statuses.

Scans a sessions directory (recursively) for ``impl-run-*/cycle-state.json``
files, prints a per-run status line sorted by run_id, and prints a final
summary.  Exit codes: 0 = all terminal / no runs, 1 = running or broken,
2 = directory not found / usage error.

Usage::

    python3 tools/session_status.py [--json] [--help] [sessions-dir]

If *sessions-dir* is omitted the default is ``sessions`` (relative to CWD).
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def _find_runs(sessions_dir: str) -> list[tuple[str, str]]:
    """Recursively find ``impl-run-*/cycle-state.json`` under *sessions_dir*.

    Returns a list of ``(run_id, state_path)`` tuples.
    """
    results: list[tuple[str, str]] = []
    for dirpath, _dirnames, filenames in os.walk(sessions_dir):
        if "cycle-state.json" not in filenames:
            continue
        # walk top-down; only accept files inside an ``impl-run-*`` dir.
        rel = os.path.relpath(dirpath, sessions_dir)
        parts = rel.split(os.sep) if rel != "." else []
        # The run directory is the last component (or the dir itself if one level).
        candidate = parts[-1] if parts else os.path.basename(dirpath)
        if candidate.startswith("impl-run-"):
            results.append((candidate, os.path.join(dirpath, "cycle-state.json")))
    return results


def _parse_run(run_id: str, path: str) -> dict | None:
    """Parse a single cycle-state.json.

    Returns ``None`` for the *no runs* sentinel; returns a dict with keys
    ``run_id``, ``status``, ``phase``, ``iteration``, ``fail_count``,
    ``progress`` on success; returns a dict with ``status`` == ``"BROKEN"``
    and the other fields set to ``None`` on parse failure.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {
            "run_id": run_id,
            "status": "BROKEN",
            "phase": None,
            "iteration": None,
            "fail_count": None,
            "progress": None,
        }

    # Validate required fields.
    if "status" not in data or "iteration" not in data:
        return {
            "run_id": run_id,
            "status": "BROKEN",
            "phase": data.get("phase"),
            "iteration": None,
            "fail_count": data.get("fail_count"),
            "progress": data.get("progress"),
        }

    return {
        "run_id": run_id,
        "status": data["status"],
        "phase": data.get("phase"),
        "iteration": data["iteration"],
        "fail_count": data.get("fail_count", 0),
        "progress": data.get("progress", 0),
    }


def _print_text(rows: list[dict]) -> None:
    """Print human-readable lines and a final summary."""
    counts: dict[str, int] = {}
    for row in rows:
        status = row["status"]
        counts[status] = counts.get(status, 0) + 1

    total = len(rows)

    # Per-run lines.
    for row in rows:
        if row["status"] == "BROKEN":
            print(f"{row['run_id']}  BROKEN")
        else:
            print(
                f"{row['run_id']}  {row['status']}  "
                f"phase={row['phase']}  "
                f"iter={row['iteration']}  "
                f"fail={row['fail_count']}  "
                f"progress={row['progress']}"
            )

    # Final summary (non-json mode).
    print(
        f"runs: {total}  "
        f"running: {counts.get('running', 0)}  "
        f"escalated: {counts.get('escalated', 0)}  "
        f"approved: {counts.get('operator-approved', 0)}  "
        f"completed: {counts.get('completed', 0)}  "
        f"broken: {counts.get('BROKEN', 0)}"
    )


def _print_json(rows: list[dict]) -> None:
    """Print a JSON array of run objects."""
    print(json.dumps(rows, ensure_ascii=False))


def main() -> int:
    """Entry point.  Returns the exit code."""
    parser = argparse.ArgumentParser(
        description="Summarise Implementation Worker cycle statuses from "
                    "cycle-state.json checkpoints.",
    )
    parser.add_argument(
        "sessions_dir",
        nargs="?",
        default=None,
        help="Path to the sessions directory (default: sessions).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Produce JSON output instead of human-readable text.",
    )
    args = parser.parse_args()

    sessions_dir = args.sessions_dir if args.sessions_dir is not None else "sessions"
    default_sessions = args.sessions_dir is None

    # Exit 2 if an explicit directory does not exist.
    # When using the default "sessions" path, treat a missing dir as
    # "no runs" (exit 0) rather than an error — it is a convenience default.
    if not os.path.isdir(sessions_dir):
        if default_sessions:
            if args.json:
                print("[]")
            else:
                print("no runs")
            return 0
        print(f"Error: '{sessions_dir}' is not a directory.", file=sys.stderr)
        return 2

    raw_runs = _find_runs(sessions_dir)

    if not raw_runs:
        if args.json:
            print("[]")
        else:
            print("no runs")
        return 0

    # Parse each run and sort by run_id.
    rows: list[dict] = []
    for run_id, path in raw_runs:
        parsed = _parse_run(run_id, path)
        if parsed is not None:
            rows.append(parsed)

    rows.sort(key=lambda r: r["run_id"])

    if args.json:
        _print_json(rows)
    else:
        _print_text(rows)

    # Exit code: 0 = all terminal, 1 = running or broken present.
    for row in rows:
        if row["status"] == "running":
            return 1
        if row["status"] == "BROKEN":
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
