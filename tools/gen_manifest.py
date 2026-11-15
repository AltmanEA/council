#!/usr/bin/env python3
"""Manifest generator (Stage A, plan sess-doc-reliability-algo).

Sole writer of docs-manifest.yaml (documentation-rules §2.2): frontmatter is the truth,
the manifest is its printout. Walks docs/en/**/*.md under --root, parses each
document header via tools/docmeta.py, and emits a deterministic YAML
manifest: preserved preamble comments + GENERATED marker + `documents` list
sorted by id.

Modes:
  --write   atomic temp+rename regeneration of <root>/docs-manifest.yaml
  --check   regenerate to string, byte-compare against on-disk file;
            exit 0 equal, exit 1 with unified diff on stderr (rule 6)

Parse failures fail loud: every bad file is listed on stderr as
"ERROR <filename>: <reason>" and the process exits 2 without writing.
"""
from __future__ import annotations

import argparse
import difflib
import os
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import docmeta  # noqa: E402
from docmeta import DocMetaError  # noqa: E402

#: Verbatim preamble comment block of the current docs-manifest.yaml
#: (lines 1-9, including the trailing blank separator line 9).
GEN_PREAMBLE = (
    "# Documentation Manifest\n"
    "# Single source of truth for project documentation layout.\n"
    "#\n"
    "# Language layout: English originals under docs/en/, Russian translations under docs/ru/.\n"
    "# Translations use mirrored directory structure (same nesting as English).\n"
    "# has_translation field uses relative path from manifest location to the RU file.\n"
    "# Schema change v0.2: has_translation changed from bare filename to relative path\n"
    "# to support separated language directories (ru-restructure consensus, 2026-11-10).\n"
    "# Schema change v0.3: entries carry changelog-path when the frontmatter\n"
    "# declares it (fix plan sess-documenter-fixes, 2026-11-14, decision A).\n"
    "\n"
)

GEN_MARKER = "# GENERATED — DO NOT EDIT (sole writer: tools/gen_manifest.py; see documentation-rules §2.2)\n"


class _Dumper(yaml.SafeDumper):
    """SafeDumper with non-indentless block sequences (list items indented)."""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _walk_docs_en(root: str) -> list:
    """All .md files under <root>/docs/en, deterministic (sorted) order."""
    base = os.path.join(root, "docs", "en")
    paths = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames.sort()
        for name in sorted(filenames):
            if name.endswith(".md"):
                paths.append(os.path.join(dirpath, name))
    return sorted(paths)


def build_entries(root: str) -> tuple:
    """Build manifest entry dicts from the corpus under ``root``.

    Returns (entries, errors); errors is a list of "filename: reason" strings
    for files that failed to parse. entries is sorted by id.
    """
    entries = []
    errors = []
    for abs_path in _walk_docs_en(root):
        rel = os.path.relpath(abs_path, root).replace("\\", "/")
        with open(abs_path, encoding="utf-8") as fh:
            text = fh.read()
        try:
            header = docmeta.parse_header(text, filename=rel)
        except DocMetaError as exc:
            errors.append(f"{exc.filename}: {exc.reason}")
            continue
        f = header.fields
        entry = {
            "id": str(f["id"]),
            "path": rel,
            "title": str(f.get("title") or header.h1_title),
            "version": str(f["Version"]),
            "status": str(f["Status"]),
            "abstraction": str(f["Abstraction"]),
        }
        if f.get("has_translation"):
            entry["has_translation"] = str(f["has_translation"])
        if f.get("changelog-path"):
            entry["changelog-path"] = str(f["changelog-path"])
        if f.get("references"):
            entry["references"] = list(f["references"])
        if f.get("allow_non_index_paths") is True:
            entry["allow_non_index_paths"] = True
        entries.append(entry)
    entries.sort(key=lambda e: e["id"])
    return entries, errors


def render(entries: list) -> str:
    """Render the full manifest text: preamble + marker + documents YAML."""
    body = yaml.dump(
        {"documents": entries},
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=10**6,
        indent=2,
    )
    # Match historical hand-authored layout: blank line between entries
    # (but none between `documents:` and the first entry).
    head, sep, tail = body.partition("\n  - id: ")
    body = head + sep + tail.replace("\n  - id: ", "\n\n  - id: ")
    return GEN_PREAMBLE + GEN_MARKER + body


def generate(root: str) -> tuple:
    """Generate manifest text for ``root``; returns (text, errors)."""
    entries, errors = build_entries(root)
    if errors:
        return None, errors
    return render(entries), []


def _read_on_disk(root: str) -> str:
    path = os.path.join(root, "docs-manifest.yaml")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def check(root: str) -> int:
    """Regenerate and byte-compare against on-disk manifest (rule 6).

    Exit 0 if identical, 1 with unified diff on stderr otherwise.
    """
    text, errors = generate(root)
    if errors:
        for err in errors:
            print(f"ERROR {err}", file=sys.stderr)
        return 2
    on_disk = _read_on_disk(root)
    if text == on_disk:
        return 0
    diff = difflib.unified_diff(
        on_disk.splitlines(keepends=True),
        text.splitlines(keepends=True),
        fromfile="docs-manifest.yaml (on disk)",
        tofile="docs-manifest.yaml (generated)",
    )
    sys.stderr.writelines(diff)
    return 1


def write(root: str) -> int:
    """Atomic regeneration into <root>/docs-manifest.yaml. No partial writes."""
    text, errors = generate(root)
    if errors:
        for err in errors:
            print(f"ERROR {err}", file=sys.stderr)
        return 2
    target = os.path.join(root, "docs-manifest.yaml")
    fd, tmp = tempfile.mkstemp(dir=root, prefix=".docs-manifest.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate docs-manifest.yaml from frontmatter.")
    parser.add_argument("--root", default=_repo_root(),
                        help="repository root (default: parent of tools/)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="atomically regenerate the manifest")
    group.add_argument("--check", action="store_true",
                       help="byte-compare generated manifest against on-disk file")
    args = parser.parse_args(argv)
    if args.check:
        return check(args.root)
    return write(args.root)


if __name__ == "__main__":
    sys.exit(main())
