#!/usr/bin/env python3
"""Deterministic version-change writer (Stage D, plan sess-doc-reliability-algo).

Model: "AI proposes, algorithm records". The caller supplies the bump kind;
this tool never decides it, never interprets text, never runs git. One version
change is applied across exactly three artifacts in normative order:
(1) document frontmatter `Version:` line, (2) changelog entry prepended
(newest-first) at frontmatter changelog-path, (3) docs-manifest.yaml,
regenerated last via tools/gen_manifest.py. The note is operator wording taken
strictly from argv and written verbatim into the changelog entry (never read
from stdin or a file, never post-processed).

Preconditions are checked before any write; on failure nothing is modified.
Each write is atomic (tempfile.mkstemp + os.replace, as in gen_manifest.write);
the three originals are kept in memory and any failed write or failed
post-write self-check rolls the already-written files back (explicit list).

Exit codes (also printed by --help):
    0  success (or --dry-run: plan printed, zero filesystem changes)
    2  usage / validation / precondition failure, or rollback after a failed
       write or failed post-write self-check (all files restored)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import docmeta  # noqa: E402
import gen_manifest  # noqa: E402
from docmeta import DocMetaError  # noqa: E402

__all__ = ["BumpError", "bump_version", "main"]

_HELP = ("Record a version bump for one document across frontmatter, changelog, "
         "and manifest (Stage D). Exit codes: 0 = success or --dry-run; "
         "2 = usage/validation/precondition failure or rolled-back write.")

#: Matches a frontmatter `Version:` line inside the metadata block.
_VERSION_LINE_RE = re.compile(r"^(?P<indent>[ \t]*)Version:[ \t]*(?P<rest>[^\r\n]*)(?P<eol>\r\n|\n|\r)?$")


class BumpError(Exception):
    """Fatal refusal: validation, precondition, or post-write self-check."""


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bump_version(version: str, kind: str) -> str:
    """Return ``version`` bumped by ``kind`` (patch|minor|major).

    A trailing ``-draft`` suffix is preserved verbatim. Missing numeric
    components are treated as 0; the result always has 3 components.
    Raises BumpError for versions not matching docmeta._VERSION_RE.
    """
    if not docmeta._VERSION_RE.match(version):
        raise BumpError(f"version {version!r} does not match (X|X.Y|X.Y.Z)(-draft)?")
    draft = version.endswith("-draft")
    parts = [int(p) for p in (version[:-6] if draft else version).split(".")]
    parts += [0] * (3 - len(parts))
    major, minor, patch = parts
    if kind == "patch":
        patch += 1
    elif kind == "minor":
        minor, patch = minor + 1, 0
    elif kind == "major":
        major, minor, patch = major + 1, 0, 0
    else:  # pragma: no cover - argparse restricts choices
        raise BumpError(f"unknown bump kind: {kind!r}")
    return f"{major}.{minor}.{patch}" + ("-draft" if draft else "")


def _read_text(path: str) -> str:
    """Read a file preserving line endings verbatim (universal newlines off)."""
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _rewrite_document_version(text: str, new_version: str, file: str) -> str:
    """Return ``text`` with ONLY the metadata-block Version line replaced.

    The metadata block is defined exactly as docmeta.parse_header does: the
    first `# ` line, then blank-line skip, then the contiguous non-blank run.
    """
    lines = text.splitlines(keepends=True)
    try:
        h1 = next(i for i, ln in enumerate(lines) if ln.startswith("# "))
    except StopIteration:
        raise BumpError(f"{file}: no H1 heading (`# ` title line) found") from None
    i = h1 + 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    start = i
    while i < len(lines) and lines[i].strip():
        i += 1
    hits = [j for j in range(start, i) if _VERSION_LINE_RE.match(lines[j])]
    if len(hits) != 1:
        raise BumpError(f"{file}: expected exactly one `Version:` line in the metadata "
                        f"block, found {len(hits)} (line-based rewrite unsupported here)")
    m = _VERSION_LINE_RE.match(lines[hits[0]])
    lines[hits[0]] = f"{m.group('indent')}Version: {new_version}{m.group('eol') or ''}"
    return "".join(lines)


def _prepend_changelog(text: str, entry_line: str) -> str:
    """Insert ``entry_line`` as the first line (changelogs are newest-first,
    verified in CHANGELOGS/*.changes.md), preserving the file's newline style."""
    eol = "\r\n" if "\r\n" in text else ("\r" if "\r" in text and "\n" not in text else "\n")
    return entry_line + eol + text


def _atomic_write(path: str, data: bytes) -> None:
    """Atomic binary write (mkstemp in target dir + os.replace); bytes exact."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path),
                               prefix="." + os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _build_plan(root: str, doc_id: str, kind: str, note: str) -> dict:
    """Resolve targets and compute all new content; no filesystem writes.

    Raises BumpError on any usage/validation/precondition failure.
    """
    entries, errors = gen_manifest.build_entries(root)
    if errors:
        raise BumpError("manifest build errors: " + "; ".join(errors))
    entry = next((e for e in entries if e["id"] == doc_id), None)
    if entry is None:
        raise BumpError(f"unknown document id: {doc_id!r} (not in manifest entries)")
    doc_rel = entry["path"]
    doc_abs = os.path.join(root, *doc_rel.split("/"))
    if not os.path.isfile(doc_abs):
        raise BumpError(f"manifest path {doc_rel!r} does not resolve under {root}")
    try:
        header = docmeta.parse_header(_read_text(doc_abs), filename=doc_rel)
    except DocMetaError as exc:
        raise BumpError(f"{exc.filename}: {exc.reason}") from exc
    high = [f for f in docmeta.validate(header, file=doc_rel, root=root)
            if f["severity"] == "high"]
    if high:
        raise BumpError("high findings refuse the bump: "
                        + "; ".join(f"{f['rule']}: {f['description']}" for f in high))
    version = str(header.fields["Version"])
    if not docmeta._VERSION_RE.match(version):
        raise BumpError(f"Version {version!r} does not match docmeta._VERSION_RE")
    cl_rel = str(header.fields["changelog-path"])
    cl_abs = os.path.join(root, *cl_rel.replace("\\", "/").split("/"))
    if not os.path.isfile(cl_abs):
        raise BumpError(f"changelog-path {cl_rel!r} does not resolve to an existing file")

    new_version = bump_version(version, kind)
    entry_line = f"<!-- CHANGES v{new_version}: {note} -->"
    doc_new = _rewrite_document_version(_read_text(doc_abs), new_version, doc_rel)
    try:
        check = docmeta.parse_header(doc_new, filename=doc_rel)
    except DocMetaError as exc:
        raise BumpError(f"{exc.filename}: rewritten document no longer parses: {exc.reason}") from exc
    if str(check.fields["Version"]) != new_version:
        raise BumpError("internal error: rewritten Version != planned new version")
    return {
        "root": root, "id": doc_id, "kind": kind,
        "old_version": version, "new_version": new_version,
        "doc_rel": doc_rel, "doc_abs": doc_abs, "doc_new": doc_new,
        "cl_rel": cl_rel, "cl_abs": cl_abs,
        "cl_new": _prepend_changelog(_read_text(cl_abs), entry_line),
        "cl_entry_line": entry_line,
        "manifest_abs": os.path.join(root, "docs-manifest.yaml"),
    }


def _restore(written: list, originals: dict) -> None:
    """Roll back every already-written file from its in-memory original."""
    for path in reversed(written):
        raw = originals[path]
        if raw is None:
            if os.path.exists(path):
                os.remove(path)
        else:
            _atomic_write(path, raw)


def _post_check(plan: dict, manifest_text: str) -> None:
    """Self-check after all writes; raises BumpError on any failure."""
    root = plan["root"]
    try:
        header = docmeta.parse_header(_read_text(plan["doc_abs"]), filename=plan["doc_rel"])
    except DocMetaError as exc:
        raise BumpError(f"post-check parse failed: {exc.filename}: {exc.reason}") from exc
    if str(header.fields["Version"]) != plan["new_version"]:
        raise BumpError("post-check: document Version != planned new version")
    high = [f["rule"] for f in docmeta.validate(header, file=plan["doc_rel"], root=root)
            if f["severity"] == "high"]
    if high:
        raise BumpError("post-check: high findings after rewrite: " + "; ".join(high))
    lines = _read_text(plan["cl_abs"]).splitlines()
    if not lines or lines[0] != plan["cl_entry_line"]:
        raise BumpError("post-check: new changelog entry is not the first line")
    regenerated, errors = gen_manifest.generate(root)
    if errors:
        raise BumpError("post-check: manifest regeneration errors: " + "; ".join(errors))
    if regenerated != manifest_text:
        raise BumpError("post-check: regenerated manifest is not byte-identical to written")
    entries, _ = gen_manifest.build_entries(root)
    entry = next((e for e in entries if e["id"] == plan["id"]), None)
    if entry is None or entry["version"] != plan["new_version"]:
        raise BumpError("post-check: manifest version for id does not match new version")


def _report(plan: dict, dry: bool) -> None:
    if dry:
        print("DRY RUN — no files will be changed")
    print(f"{plan['id']}: {plan['old_version']} -> {plan['new_version']} ({plan['kind']})")
    print(f"  document:  {plan['doc_rel']}  (Version line only)")
    print(f"  changelog: {plan['cl_rel']}  (prepend, newest-first)")
    print(f"    + {plan['cl_entry_line']}")
    print("  manifest:  docs-manifest.yaml  (regenerated via gen_manifest)")


def _execute(plan: dict) -> int:
    """Apply the plan with the normative write order and explicit rollback."""
    targets = [plan["doc_abs"], plan["cl_abs"], plan["manifest_abs"]]
    originals = {}
    for p in targets:
        if os.path.isfile(p):
            with open(p, "rb") as fh:
                originals[p] = fh.read()
        else:
            originals[p] = None
    written: list = []
    manifest_text = None
    try:
        for path, data in ((plan["doc_abs"], plan["doc_new"]),
                           (plan["cl_abs"], plan["cl_new"])):
            _atomic_write(path, data.encode("utf-8"))
            written.append(path)
        # (3) manifest — always last; abort (rollback) on build errors
        manifest_text, errors = gen_manifest.generate(plan["root"])
        if errors:
            raise BumpError("manifest regeneration failed: " + "; ".join(errors))
        _atomic_write(plan["manifest_abs"], manifest_text.encode("utf-8"))
        written.append(plan["manifest_abs"])
        _post_check(plan, manifest_text)
    except BaseException as exc:
        _restore(written, originals)
        print(f"ERROR: {exc}; all files rolled back", file=sys.stderr)
        return 2
    _report(plan, dry=False)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="bump_version.py", description=_HELP)
    parser.add_argument("--id", required=True,
                        help="manifest document id (resolved via gen_manifest.build_entries)")
    parser.add_argument("--kind", required=True, choices=("patch", "minor", "major"),
                        help="bump kind, chosen by the caller (AI proposes, algorithm records)")
    parser.add_argument("--note", required=True,
                        help="verbatim operator wording, written verbatim into the changelog entry")
    parser.add_argument("--root", default=_repo_root(),
                        help="repository root (default: parent of tools/)")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="print the plan (versions, paths, changelog line); zero filesystem changes")
    args = parser.parse_args(argv)

    if not args.note.strip():
        print("ERROR: --note must be non-empty", file=sys.stderr)
        return 2
    try:
        plan = _build_plan(args.root, args.id, args.kind, args.note)
    except BumpError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        _report(plan, dry=True)
        return 0
    return _execute(plan)


if __name__ == "__main__":
    sys.exit(main())
