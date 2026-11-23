#!/usr/bin/env python3
"""record_vendor_patch.py — Record the current vendored-engine deviation.

Writes the working-tree diff of the vendored distribution (defaults/
translation.lock -> local_path) to
documenter/artifacts/translation/patches/<name>.patch and reminds the
operator to keep the '# patched:' annotation in the lock file.

This makes a local vendor patch visible to tools/check_all.py's
vendor-integrity rule instead of leaving it as a silent working-tree edit
(AGENTS.md §1.7 vendoring model; OP-1 informational, never gating).

Usage:
    python3 tools/record_vendor_patch.py <name>
        # name: kebab-case, e.g. glossary-list-parser

Exit codes: 0 written, 1 usage error, 2 no deviation / git error.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1 or not KEBAB_RE.match(argv[0]):
        print("Usage: record_vendor_patch.py <kebab-case-name>",
              file=sys.stderr)
        return 1
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lock = os.path.join(root, "defaults", "translation.lock")
    if not os.path.isfile(lock):
        print(f"ERROR: no lock file: {lock}", file=sys.stderr)
        return 2
    local_rel = None
    with open(lock, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("local_path:"):
                local_rel = line.split(":", 1)[1].strip()
                break
    if not local_rel:
        print("ERROR: lock has no local_path", file=sys.stderr)
        return 2
    prefix = local_rel.rstrip("/") + "/"
    proc = subprocess.run(["git", "diff", "--", prefix], cwd=root,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"ERROR: git diff failed: {proc.stderr.strip()}", file=sys.stderr)
        return 2
    if not proc.stdout.strip():
        print("No working-tree deviation in the vendored tree — nothing to "
              "record.")
        return 2
    patch_dir = os.path.join(root, "documenter", "artifacts", "translation",
                             "patches")
    os.makedirs(patch_dir, exist_ok=True)
    out = os.path.join(patch_dir, f"{argv[0]}.patch")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(proc.stdout)
    print(f"Wrote {os.path.relpath(out, root)} "
          f"({len(proc.stdout.splitlines())} lines)")
    print("Next: add a '# patched:' annotation to defaults/translation.lock "
          "and a README note in the patches/ directory.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
