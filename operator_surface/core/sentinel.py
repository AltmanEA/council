"""Tier 2+ readiness sentinel — file creation and check.

Creates/verifies the readiness sentinel at ``<root>/documenter/.operator_surface_ready``.

Cross-package contract: ``SENTINEL_PATH`` must equal the value of
``documenter_service.core.policy.OPERATOR_SURFACE_SENTINEL`` so that the
documenter_service consumer and the operator surface agree on the sentinel file
location without importing each other.
"""
from __future__ import annotations

import os

# The sentinel path — must match documenter_service.core.policy.OPERATOR_SURFACE_SENTINEL.
SENTINEL_PATH = "documenter/.operator_surface_ready"


def ensure_sentinel(state_root: str) -> bool:
    """Create the readiness sentinel file under *state_root* if it does not exist.

    Returns True on success (file created or already present).
    Returns False if creation fails (directory-in-the-way, read-only parent,
    unwritable location) — never raises.

    The file is empty (touch semantics).  Idempotent: if the file already
    exists at the path, returns True without rewriting.
    """
    try:
        sentinel_path = os.path.join(state_root, SENTINEL_PATH)

        # If it's already a file, it's done.
        if os.path.isfile(sentinel_path):
            return True

        parent_dir = os.path.dirname(sentinel_path)

        # If a non-directory blocks the path (e.g. a regular file), fail.
        if os.path.exists(sentinel_path):
            return False

        # Create the directory tree.
        os.makedirs(parent_dir, exist_ok=True)

        # Touch the file with content.
        with open(sentinel_path, "w", encoding="utf-8") as fh:
            fh.write("operator_surface_ready\n")

        return True

    except Exception:
        # Directory in path, read-only, or any other OSError → False.
        return False


def operator_surface_ready(state_root: str) -> bool:
    """Check whether the readiness sentinel exists under *state_root*.

    Returns True if the sentinel file is present, False otherwise.
    """
    sentinel_path = os.path.join(state_root, SENTINEL_PATH)
    return os.path.isfile(sentinel_path)
