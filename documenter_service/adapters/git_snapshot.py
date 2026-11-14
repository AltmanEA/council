"""Pre-change git snapshot adapter (mvp-contract §2.2, line 64).

Capture the repository state before write operations so that
rollback via ``git restore`` is possible (ADR-007).

Fail-closed: ``git`` must be available and the working directory must
be a ``git`` repository.  If not → StructuredError("gate_failure")
with next_action="escalate".

Public API
----------
capture_git_snapshot(root: str) -> dict
    Returns {"head": <40-hex>, "status": [<str>, ...]}.
    May also carry a "captured_at" ISO timestamp (not required).
"""
from __future__ import annotations

import subprocess
import time
from typing import Any, List

from ..core.errors import StructuredError

__all__ = ["capture_git_snapshot"]

#: Maximum wall-clock budget for the entire snapshot operation.
_CAPTURE_TIMEOUT = 10  # seconds


def capture_git_snapshot(root: str) -> dict:
    """Capture a pre-change git snapshot of ``root``.

    Executes:
      * ``git rev-parse HEAD``           → *head* (stripped)
      * ``git status --porcelain
        --untracked-files=all``          → *status* list

    Returns {"head": <str>, "status": [<str>, ...]}.

    Fail-closed: if ``git`` is not installed, the directory is not
    a repository, or any command exits non-zero → raise
    StructuredError("gate_failure", ...) with next_action="escalate".

    This function is the ONLY subprocess entry-point in this module,
    making it easy for tests to monkey-patch.
    """
    try:
        head_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=_CAPTURE_TIMEOUT,
            cwd=root, shell=False,
        )
    except FileNotFoundError as exc:
        raise StructuredError(
            "gate_failure",
            "pre-change git snapshot failed (git unavailable): "
            "rollback (git restore, ADR-007) requires git — write denied",
            next_action="escalate",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise StructuredError(
            "gate_failure",
            "pre-change git snapshot failed (git timed out): "
            "rollback (git restore, ADR-007) requires git — write denied",
            next_action="escalate",
        ) from exc

    if head_result.returncode != 0:
        stderr = head_result.stderr.strip() or "unknown"
        raise StructuredError(
            "gate_failure",
            f"pre-change git snapshot failed ({stderr}): "
            "rollback (git restore, ADR-007) requires git — write denied",
            next_action="escalate",
        )

    head = head_result.stdout.strip()

    status_result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        capture_output=True, text=True, timeout=_CAPTURE_TIMEOUT,
        cwd=root, shell=False,
    )
    if status_result.returncode != 0:
        stderr = status_result.stderr.strip() or "unknown"
        raise StructuredError(
            "gate_failure",
            f"pre-change git snapshot failed ({stderr}): "
            "rollback (git restore, ADR-007) requires git — write denied",
            next_action="escalate",
        )

    status_lines = [
        line
        for line in status_result.stdout.splitlines()
        if line  # skip empty trailing lines
    ]

    return {
        "head": head,
        "status": status_lines,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
