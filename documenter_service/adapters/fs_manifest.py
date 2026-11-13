"""ManifestSource adapter over the generated manifest — AGENTS.md §2.2.

Document paths and ids are resolved ONLY through `tools/gen_manifest.build_entries`
(the generator walks docs/en frontmatter; it is the single normative projection
of the manifest, whose sole writer is gen_manifest --write). A blind
filesystem scan for manifest data is prohibited; this adapter has no other
resolution path by construction.
"""
from __future__ import annotations

import os
import sys

_TOOLS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import gen_manifest  # noqa: E402

from ..core.errors import StructuredError  # noqa: E402
from ..ports import ManifestSource  # noqa: E402

__all__ = ["FsManifestSource"]


class FsManifestSource(ManifestSource):
    """Manifest view built by calling gen_manifest.build_entries as-is."""

    def __init__(self, root: str) -> None:
        self.root = os.path.abspath(root)

    def entries(self) -> list:
        entries, errors = gen_manifest.build_entries(self.root)
        if errors:
            # Manifest build errors are a corpus condition the delegate/audit
            # scope resolver cannot proceed over: fail closed, escalate.
            raise StructuredError(
                "unknown", "manifest build errors: " + "; ".join(errors))
        return entries

    def resolve(self, target_id: str):
        for entry in self.entries():
            if entry["id"] == target_id:
                return entry
        return None
