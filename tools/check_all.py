#!/usr/bin/env python3
"""Deterministic documentation compliance rule suite (Stage B, plan
sess-doc-reliability-algo). Full-scan over <root>/docs/en per the consensus
decision. stdlib + PyYAML only, Python 3.11+.

Implements the deterministic subset of the compliance rules listed in
`docs/en/documenter-service/mvp-interfaces.md` §Compliance rules scanned:
per that list's closing sentence, "Rules 3 (glossary terms) and 5
(abstraction consistency) remain skill/AI-reserved judgments; rules 1, 2, 4,
6 and the naming/schema checks are deterministic". This module implements
ONLY the deterministic side:

  rule-1  line-count           high    content lines <= 200 per doc
                                          (formula: tests_helpers.content_line_count)
  rule-2  changelog-existence  delegated to docmeta.validate
                                          (changelog-path-missing / changelog-path-location)
  rule-4  cross-ref-anchors    file references: high when a referenced
                                          docs/en file is missing
                                          anchors (#fragment): medium
                                          §Name refs: see resolver posture
                                          (high / medium / low by context)
  rule-6  manifest-parity      high "manifest-drift" (regenerate-and-diff via
                                          gen_manifest, byte-compare) + high
                                          "orphan" (docs/en file absent from
                                          generated entries, not covered by an
                                          allow_non_index_paths parent index)
  naming  documentation-rules §7.1       high    kebab-case folders under docs/en,
                                          index.md convention unless
                                          allow_non_index_paths
  schema  docmeta.validate     native   frontmatter schema, version-format,
                                          last-modified-deprecated, unknown-key,
                                          references-non-index
  link-integrity (CI guard, consensus sess-operator-surface-split O-3):
          docs→manifest        high    a docs/en (or docs/ru) document references a
                                          docs/... path that does not exist or is
                                          not registered in docs-manifest.yaml
                                          (hard fail — ADR-003 precedent for a
                                          prose invariant enforced by CI)
          code→docs            warning comments/docstrings under scanned package
                                          dirs (LINK_INTEGRITY_CODE_DIRS; empty
                                          since the 2026-11-19 reconstruction)
                                          referencing a missing/unregistered docs/
                                          path: WARN-ONLY by contract (worktree
                                          drift must not block legitimate
                                          changesets); --strict-links promotes
                                          these to blocking for clean pre-merge
                                          runs

  core-root resolution (--core-root C): when a docs/en reference token fails to
                                          resolve within the audited host corpus,
                                          the tool falls back to <C>/docs/en/
                                          as a second, read-only resolution space.
                                          Core files are never merged into the
                                          host corpus (no parity/orphan checks
                                          on them).

NON-CLAIM (normative): rules 3 (glossary terms) and 5 (abstraction
consistency) are skill/AI-reserved and NOT implemented here. This tool NEVER
advertises coverage of "rules 1-6".

rule-4 resolver posture: pragmatic but tuned to keep the pre-commit gate
usable (alert fatigue drives operators to --no-verify). Relative paths
(`../x.md`, `x.md`) resolve against the containing FILE PATH first, then the
containing directory, then docs/en, then a corpus-unique basename; a
`<dir>/index.md`-style token also collapses to a flat `<dir>.md` sibling
(`error-management/index.md` -> `error-management.md`). §Name references
then resolve through a cascade: the *.md token immediately preceding the §
binds as the target file — hit against its headings/bold pseudo-headings
passes, miss is high "broken-anchor"; an implementation file
(AGENTS.md, fallback/, .agents/; AGENTS.md §1.6) is verified against that
real file and never exceeds LOW; otherwise the containing file and
canonical-id hints are checked, then a corpus-wide heading index — a unique
match passes, multiple matches yield LOW "ambiguous-section-reference"
(max 3 candidates), zero matches yield medium "unresolved-reference" (the
signal worth keeping); numeric §Names (§7.3, §2.2.3) are
implementation-style and never exceed LOW.

CLI:
  python3 tools/check_all.py [--root DIR] [--core-root DIR] [--json] [--severity low|medium|high|warning]
                             [--rule ID ...] [--strict] [--strict-links]

Exit codes:
  0  no reported findings (clean — silent when clean)
  1  reported findings present, none high-severity
  2  at least one high-severity reported (critical) — OR — internal error
     (crash, unreadable corpus), bad --rule token (fail loud, stderr has
     `check_all: INTERNAL ERROR` / `ERROR:` to distinguish from `🚨`).

--severity SEV sets the minimum severity that is REPORTED (default: low).
--strict is equivalent to --severity warning (report everything).

--json emits one JSON object per line (EventSink-shaped: flat, no document
text): {"rule", "severity", "file", "description"}.

The DEFAULT human-readable format obeys the token contract with
tools/hooks/pre-commit: one finding per line as
`rule=<rule-id> severity=<low|medium|high> file=<path> <description>`
(the hook greps the literal `severity=high` in block mode); no document
text appears on the line.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import io
import json
import os
import re
import sys
import tokenize
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import docmeta  # noqa: E402
import gen_manifest  # noqa: E402
import tests_helpers  # noqa: E402
from docmeta import DocMetaError  # noqa: E402

__all__ = ["Finding", "scan", "main"]

#: Maximum content lines per document (documentation-rules §7.3).
LINE_LIMIT = 200

#: Archive path prefixes: documents under these prefixes are silently
#: excluded from every check pass (documenter-service §Archive, §Audit tool).
_ARCHIVE_PREFIXES = ("docs/en/archive/", "docs/ru/archive/")


def is_archived(rel: str) -> bool:
    """True when *rel* is under an archive path prefix."""
    return rel.startswith(_ARCHIVE_PREFIXES)


#: --rule group tokens -> concrete finding-rule names they enable.
RULE_GROUPS = {
    "line-count": {"line-count"},
    "changelog": {"changelog-path-missing", "changelog-path-location"},
    "cross-ref": {"missing-reference", "broken-anchor", "unresolved-reference",
                  "ambiguous-section-reference"},
    "manifest-parity": {"manifest-drift", "orphan", "parity-skipped"},
    "naming": {"naming"},
    "link-integrity": {"docs-manifest-link", "code-docs-link"},
    "schema": {
        "frontmatter", "required-field", "version-format",
        "last-modified-deprecated", "unknown-key", "references-non-index",
    },
}

_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# Reference patterns (rule-4). Names are self-descriptive.
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_PATH_REF_RE = re.compile(r"(?<![\w/.-])(docs/en/[\w./-]+\.md)(?![\w-])")
# §Name references: leading uppercase/digit token, then further Capitalized or
# dotted-numeric tokens; stops at lowercase prose, punctuation, brackets.
_SECTION_TOK_RE = re.compile(r"[A-Z0-9][\w&'’/.-]*(?:[ \t]+[A-Z0-9][\w&'’/.-]*)*")
_SECTION_REF_RE = re.compile(r"§[ \t]*")
_BACKTICK_REF_RE = re.compile(r"`([^`\s]+\.md)`")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->")

#: Same-line file detection for §Name context (rule-4 resolver): bare
#: backticked tokens (including the markdown-link form) and paths with or
#: without backticks — `docs/en/<...>.md`, `<dir>/<file>.md`, bare
#: `<file>.md`. Trailing punctuation is stripped before resolution;
#: http/mailto schemes and generic names (index.md) are rejected downstream.
_BACKTICK_TOKEN_RE = re.compile(r"`([^`\s]+)`")
_SAMELINE_PATH_RE = re.compile(
    r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+\.md)(?![\w-])")

#: Bold pseudo-heading lead-ins `**Name:**` (the colon typically sits INSIDE
#: the closing asterisks in this corpus). Documents reference these in prose
#: (§Failure semantics, §Pre-audit gate, §Authority rule) but they are not
#: ATX headings. Captured text may contain a trailing colon; strip it.
_BOLD_LEAD_RE = re.compile(r"\*\*([^*\n:：]+?)\s*[:：]?\s*\*\*")

#: Bare file basenames that carry no targeting information on a reference
#: line (`index.md` alone says nothing about which document is meant).
_GENERIC_MD_NAMES = {"index.md", "readme.md"}

# ---------------------------------------------------------------------------
# link-integrity (consensus sess-operator-surface-split, O-3)
# ---------------------------------------------------------------------------

#: docs/... path token, anchored left on a non-path character so that prose
#: like `mvp-interfaces.md` is not mistaken for a path and `docs/en` inside
#: longer words is not partially matched. Shared by the docs side (markdown
#: body) and the code side (comments/docstrings).
_LINK_DOC_PATH_RE = re.compile(r"(?<![\w/.-])(docs/(?:en|ru)/[\w./-]+\.md)(?![\w-])")

#: Package directories whose Python comments/docstrings are scanned for
#: code→docs references. The Council service packages were deleted in the
#: 2026-11-19 reconstruction (sess-documenter-concept-revision); the list is
#: empty, so the code→docs pass is inert. Kept as an extension point.
LINK_INTEGRITY_CODE_DIRS = ()


def _registered_doc_paths(root: str) -> set:
    """Set of repo-relative docs paths registered in docs-manifest.yaml:
    every entry `path` plus every entry `has_translation` (RU mirrors).

    Registration truth is the ON-DISK manifest (the published index agents
    read documentation through, AGENTS.md §1): a file that exists on disk but
    is absent from the manifest is unregistered — that is precisely the
    docs→manifest divergence O-3 targets (manifest drift itself is rule-6's
    high-severity territory). Returns None (skip) when the manifest is
    missing or unparsable, so link-integrity never fails closed on a
    condition it cannot judge."""
    disk = os.path.join(root, "docs-manifest.yaml")
    if not os.path.exists(disk):
        return None
    import yaml  # PyYAML: the only third-party import permitted in tools/
    try:
        with open(disk, encoding="utf-8") as fh:  # OSError -> exit 2 by main
            data = yaml.safe_load(fh)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("documents"), list):
        return None
    registered = set()
    for entry in data["documents"]:
        if not isinstance(entry, dict):
            continue
        if isinstance(entry.get("path"), str):
            registered.add(entry["path"])
        if isinstance(entry.get("has_translation"), str):
            registered.add(entry["has_translation"])
    return registered


def _link_doc_findings(root: str, rel: str, text: str, registered,
                       core_texts: dict = None) -> list:
    """link-integrity docs-side findings for one markdown document body.

    A `docs/en/...md` or `docs/ru/...md` token is unresolved when the file
    does not exist under root OR it exists but is not registered in the
    manifest (rule-6 covers EN orphans; this closes the gap for RU files and
    frontmatter-registered paths). When *core_texts* is provided (core-root
    mode), a token missing from the host but present there passes instead of
    producing a finding (AC-1). Fence-aware; HTML comments stripped via
    _visible_lines. High severity: docs→manifest is a hard-fail contract
    (O-3; ADR-003 precedent)."""
    findings = []
    for idx, line in _visible_lines(text.splitlines()):
        for m in _LINK_DOC_PATH_RE.finditer(line):
            token = m.group(1)
            exists_host = os.path.isfile(os.path.join(root, *token.split("/")))
            registered_ok = registered is not None and token in registered
            if exists_host and registered_ok:
                continue
            # Core-root fallback: file missing from host but available there passes (AC-1)
            if core_texts is not None and token in core_texts:
                continue
            findings.append(_finding(
                "docs-manifest-link", "high", rel,
                f"link-integrity docs→manifest: {token!r} on line {idx + 1} is "
                f"{'not a file under root' if not exists_host else 'not registered in docs-manifest.yaml'}"
                f" — hard fail (O-3, ADR-003 precedent)"))
    return findings


def _code_comment_texts(abs_path: str):
    """(line_no, text) pairs of comments and docstrings in a Python file.

    Comments come from tokenize (COMMENT tokens); docstrings from the AST via
    ast.get_docstring on every Module/ClassDef/FunctionDef/AsyncFunctionDef.
    SyntaxError → fall back to `#`-prefixed raw lines (the file is broken for
    other tools too; link-integrity must not crash the suite)."""
    try:
        with open(abs_path, "rb") as fh:
            src_bytes = fh.read()
        source = src_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    out = []
    try:
        toks = list(tokenize.tokenize(io.BytesIO(src_bytes).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        for i, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                out.append((i, line))
        return out
    for tok in toks:
        if tok.type == tokenize.COMMENT:
            out.append((tok.start[0], tok.string))
    try:
        tree = ast.parse(source, filename=abs_path)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                start = getattr(node, "lineno", 1)
                if isinstance(node, ast.Module):
                    start = 1
                for off, dline in enumerate(doc.splitlines()):
                    out.append((start + off, dline))
    return out


def check_link_integrity(corpus: "_Corpus", strict_links: bool = False) -> list:
    """link-integrity step (O-3, sess-operator-surface-split).

    docs→manifest (high, blocking): documents under docs/en and docs/ru whose
    body references a docs/... path missing on disk or unregistered in
    docs-manifest.yaml. Manifest-registered paths and existing+registered
    RU mirrors pass; when the manifest cannot be built the docs side skips
    (medium parity-skipped) — frontmatter defects are rule-6's territory.

    code→docs (warning, non-blocking unless strict_links): comments and
    docstrings under LINK_INTEGRITY_CODE_DIRS referencing docs/... paths not
    registered in the manifest. Warn-only by contract: legitimate worktree
    drift must not block changesets; --strict-links promotes these for clean
    pre-merge runs (raising rank to 'low' keeps them out of the default
    blocking bar while making them visible to --strict and to the flag).
    """
    registered = _registered_doc_paths(corpus.root)
    findings = []

    # -- docs side --------------------------------------------------------
    if registered is None:
        findings.append(_finding(
            "parity-skipped", "medium", "docs-manifest.yaml",
            "link-integrity: skipped — docs-manifest.yaml is missing or "
            "unparsable, registration cannot be judged (manifest-drift from "
            "rule-6 owns the broken-manifest condition)"))
    else:
        for rel in corpus.docs:
            findings.extend(
                _link_doc_findings(corpus.root, rel, corpus.texts[rel], registered,
                                   core_texts=corpus._core_texts))
        # RU mirrors are outside _Corpus (which walks docs/en only): walk them here.
        ru_base = os.path.join(corpus.root, "docs", "ru")
        if os.path.isdir(ru_base):
            for dirpath, dirnames, filenames in os.walk(ru_base):
                dirnames.sort()
                for name in sorted(filenames):
                    if not name.endswith(".md"):
                        continue
                    abs_path = os.path.join(dirpath, name)
                    rel = os.path.relpath(abs_path, corpus.root).replace("\\", "/")
                    if is_archived(rel):
                        continue
                    with open(abs_path, encoding="utf-8") as fh:  # OSError -> exit 2
                        text = fh.read()
                    findings.extend(
                        _link_doc_findings(corpus.root, rel, text, registered,
                                           core_texts=corpus._core_texts))

    # -- code side ---------------------------------------------------------
    # Unbuildable manifest → registration is unknown; skip instead of
    # flooding warnings (the parity-skipped finding above carries the signal).
    if registered is None:
        return findings
    # --strict-links promotes warn-only code→docs findings to high so they
    # block under the default severity_min; without the flag they are
    # genuine warnings (severity rank 0, never blocking under any threshold
    # except --strict, which already promotes everything).
    severity = "high" if strict_links else "warning"
    for pkg in LINK_INTEGRITY_CODE_DIRS:
        base = os.path.join(corpus.root, *pkg.split("/"))
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
            for name in sorted(filenames):
                if not name.endswith(".py"):
                    continue
                abs_path = os.path.join(dirpath, name)
                rel = os.path.relpath(abs_path, corpus.root).replace("\\", "/")
                for lineno, text in _code_comment_texts(abs_path):
                    for m in _LINK_DOC_PATH_RE.finditer(text):
                        token = m.group(1)
                        if token in registered:
                            continue
                        if os.path.isfile(os.path.join(corpus.root,
                                                        *token.split("/"))):
                            # exists on disk but unregistered is a manifest
                            # concern; for warn-only code refs, existence is
                            # enough to pass (worktree drift tolerance)
                            if strict_links:
                                findings.append(_finding(
                                    "code-docs-link", severity, rel,
                                    f"link-integrity code→docs: {token!r} on "
                                    f"line {lineno} exists but is not "
                                    f"registered in docs-manifest.yaml "
                                    f"(promoted by --strict-links)"))
                            continue
                        findings.append(_finding(
                            "code-docs-link", severity, rel,
                            f"link-integrity code→docs: {token!r} on line "
                            f"{lineno} does not exist under root (warn-only; "
                            f"--strict-links promotes to blocking)"))
    return findings


def _finding(rule: str, severity: str, file: str, description: str) -> dict:
    """EventSink-shaped finding: flat dict, required keys, no document text."""
    return {"rule": rule, "severity": severity, "file": file, "description": description}


def _core_root_resolve(core_root: str, token: str) -> str:
    """Resolve a docs/en reference *token* against core_root/docs/en/.

    Returns the relative path (e.g. ``docs/en/foo/index.md``) if the file
    exists there, else ``None``.  Core lookups use only a direct relative path
    under ``docs/en/`` — no markdown-relative resolution, because core is
    read-only context (AC-3).
    """
    # If the token already starts with docs/en/, use it as-is.
    cand = token if token.startswith("docs/en/") else "docs/en/" + token
    cand = cand.strip("/").removeprefix("./")
    abs_path = os.path.join(core_root, *cand.split("/"))
    if os.path.isfile(abs_path):
        return cand
    # Try index.md collapse: dir/index.md for a directory-style token
    if not cand.endswith("/index.md"):
        alt = cand + "/index.md"
        alt_path = os.path.join(core_root, *alt.split("/"))
        if os.path.isfile(alt_path):
            return alt
    return None


class _Corpus:
    """Whole-corpus scan context: files, parsed headers, heading indexes."""

    def __init__(self, root: str, core_root: str = None):
        self.root = root
        self.core_root = core_root     # Optional second read-only resolution space
        self.docs = []                 # relative paths, sorted, e.g. docs/en/x/index.md
        self.texts = {}                # rel -> text  (host ONLY)
        self.lines = {}                # rel -> splitlines  (host ONLY)
        self.headers = {}              # rel -> HeaderData (absent when parse failed, host only)
        self.parse_errors = {}         # rel -> DocMetaError reason  (host only)
        # Core resolution cache: rel -> text  (read-only, consult on miss from host)
        self._core_texts = {}          # rel -> text  (core docs/en files)
        self._core_headers = {}        # rel -> HeaderData  (core documents)
        self._slug_index = {}
        self._heading_index = {}    # rel -> [heading texts] (ATX only)
        self._hbold_index = {}      # rel -> [headings + bold pseudo-headings]
        self._impl_texts = {}       # root-level rel -> text (implementation files)
        self._impl_listed = False
        self._impl_files = set()
        self._heading_unique = None  # normalized -> {rel}; lazy corpus-wide index
        self._basename_unique = None  # basename -> {rel}; lazy corpus-wide index
        self._title_unique = None    # normalized -> {rel}; lazy H1 title index
        self._docs_roots = None      # first-segment directory names under docs/en
        self._core_doc_ids = None     # lazy-cached set of core frontmatter ids

        base = os.path.join(root, "docs", "en")
        if not os.path.isdir(base):
            raise FileNotFoundError(
                f"{base}: no docs/en directory under --root {root!r}")
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames.sort()
            for name in sorted(filenames):
                if name.endswith(".md"):
                    abs_path = os.path.join(dirpath, name)
                    rel = os.path.relpath(abs_path, root).replace("\\", "/")
                    if is_archived(rel):
                        continue
                    self.docs.append(rel)
        self.docs.sort()

        for rel in self.docs:
            abs_path = os.path.join(root, *rel.split("/"))
            with open(abs_path, encoding="utf-8") as fh:  # OSError -> exit 2
                text = fh.read()
            self.texts[rel] = text
            self.lines[rel] = text.splitlines()
            try:
                self.headers[rel] = docmeta.parse_header(text, filename=rel)
            except DocMetaError as exc:
                # Corpus condition, not a validator bug: reported as finding.
                self.parse_errors[rel] = exc.reason

        # -- core root: read-only resolution space (not merged into self.docs)
        if core_root:
            core_base = os.path.join(core_root, "docs", "en")
            if not os.path.isdir(core_base):
                raise FileNotFoundError(
                    f"{core_base}: no docs/en directory under --core-root {core_root!r}")
            for dirpath, dirnames, filenames in os.walk(core_base):
                dirnames.sort()
                for name in sorted(filenames):
                    if name.endswith(".md"):
                        abs_path_c = os.path.join(dirpath, name)
                        rel_c = os.path.relpath(abs_path_c, core_root).replace("\\", "/")
                        if is_archived(rel_c):
                            continue
                        with open(abs_path_c, encoding="utf-8") as fh:  # OSError -> exit 2
                            ct = fh.read()
                        self._core_texts[rel_c] = ct
                        try:
                            self._core_headers[rel_c] = docmeta.parse_header(
                                ct, filename=rel_c)
                        except DocMetaError:
                            pass  # core parse errors ignored

    # -- heading/anchor indexes ------------------------------------------------

    def slugs(self, rel: str) -> set:
        if rel not in self._slug_index:
            self._slug_index[rel] = {
                tests_helpers.slugify(t)
                for t in tests_helpers.heading_texts(self.lines.get(rel, []))
            }
        return self._slug_index[rel]

    def _file_lines(self, rel: str):
        """splitlines for a docs/en file or an implementation file (cached)."""
        if rel in self.lines:
            return self.lines[rel]
        text = self._impl_texts.get(rel)
        if text is None:
            abs_path = os.path.join(self.root, *rel.split("/"))
            if not os.path.isfile(abs_path):
                return None
            with open(abs_path, encoding="utf-8") as fh:  # OSError -> exit 2
                text = fh.read()
            self._impl_texts[rel] = text
        return text.splitlines()

    def heading_and_bold_texts(self, rel: str) -> list:
        """ATX headings plus bold pseudo-headings (`**Name:**` lead-ins).

        Used for §Name resolution: corpus documents use bold run-in leads as
        de-facto section markers (§Failure semantics, §Pre-audit gate), so
        matching them avoids false unresolved-reference noise. Slug/anchor
        checks keep using ATX headings only (slugs()).
        """
        if rel not in self._hbold_index:
            lines = self._file_lines(rel)
            texts = tests_helpers.heading_texts(lines) if lines else []
            in_fence = False
            for _i, line in enumerate(lines or []):
                stripped = line.strip()
                if stripped.startswith("```") or stripped.startswith("~~~"):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                for bm in _BOLD_LEAD_RE.finditer(line):
                    label = bm.group(1).strip()
                    if label:
                        texts.append(label)
            self._hbold_index[rel] = texts
        return self._hbold_index[rel]

    def _ensure_corpus_indexes(self):
        """Lazy corpus-wide indexes: token-normalized heading text -> files,
        basename -> files, H1 title -> files, and the set of first-segment
        directory names under docs/en (for prose hints like 'operator-ingress')."""
        if self._heading_unique is not None:
            return
        self._heading_unique = {}
        self._basename_unique = {}
        self._title_unique = {}
        self._docs_roots = set()
        for rel in self.docs:
            base = rel.rsplit("/", 1)[-1]
            self._basename_unique.setdefault(base, set()).add(rel)
            seg = rel.split("/")
            if len(seg) > 2:
                self._docs_roots.add(seg[2])
            for h in self.heading_and_bold_texts(rel):
                key = " ".join(self._hit_tokens(h.strip().strip("*_`")))
                if key:
                    self._heading_unique.setdefault(key, set()).add(rel)
            for line in self.lines[rel][:3]:
                if line.startswith("# "):
                    key = " ".join(self._hit_tokens(line[2:].strip()))
                    if key:
                        self._title_unique.setdefault(key, set()).add(rel)
                    break

    # -- reference resolution ---------------------------------------------------

    def is_implementation_file(self, rel: str) -> bool:
        """True for operational .md files outside docs/en that §refs point at:
        root-level files (AGENTS.md), fallback/, .agents/ (AGENTS.md §1.6).
        These are out of manifest scope: their §ref findings are LOW at most."""
        self._ensure_impl_files()
        return rel in self._impl_files

    def _ensure_impl_files(self):
        """Lazy list of implementation-file .md paths (AGENTS.md §1.6 roots):
        repository-root *.md plus everything under fallback/ and .agents/."""
        if self._impl_listed:
            return
        self._impl_listed = True
        self._impl_files = set()
        for name in sorted(os.listdir(self.root)):
            if name.endswith(".md") and os.path.isfile(
                    os.path.join(self.root, name)):
                self._impl_files.add(name)
        for sub in ("fallback", ".agents"):
            base = os.path.join(self.root, sub)
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames.sort()
                for name in sorted(filenames):
                    if name.endswith(".md"):
                        abs_path = os.path.join(dirpath, name)
                        rel = os.path.relpath(abs_path, self.root).replace("\\", "/")
                        self._impl_files.add(rel)

    def _docs_candidates(self, token: str, source_rel: str) -> list:
        """Candidate docs/en paths for a file token, in order:
        containing-file-relative first (joined against the file path, so
        `../index.md` from `planned-architecture/layer-2.md` lands on
        `planned-architecture/index.md`), then directory-relative (markdown
        link semantics), then docs/en-relative (canonical identifier style),
        then corpus-unique basename; additionally, a token ending in
        `/<name>/index.md` collapses to `/<name>.md` (a folder-style
        identifier for a flat same-name file, e.g.
        `error-management/index.md` -> `error-management.md`). Paths that
        escape docs/en (normpath outside the tree) are rejected."""
        token = token.strip().strip("/").removeprefix("./")
        cands = []

        def add(cand):
            cand = cand.replace("\\", "/")
            if cand.startswith("docs/en/") and cand not in cands:
                cands.append(cand)
            flat = None
            if cand.endswith("/index.md"):
                flat = cand[: -len("/index.md")] + ".md"
            elif cand.endswith("/README.md"):
                flat = cand[: -len("/README.md")] + ".md"
            if flat and flat.startswith("docs/en/") and flat not in cands:
                cands.append(flat)

        add(os.path.normpath(os.path.join(source_rel, token)))
        add(os.path.normpath(os.path.join(os.path.dirname(source_rel), token)))
        add(token if token.startswith("docs/en/") else "docs/en/" + token)
        base = token.rsplit("/", 1)[-1]
        self._ensure_corpus_indexes()
        unique = self._basename_unique.get(base)
        if unique and len(unique) == 1:
            add(next(iter(unique)))
        return cands

    def _impl_candidates(self, token: str, source_rel: str) -> list:
        """Candidate implementation-file paths (repo-relative): repo-root
        first, then source-relative; corpus-unique basename restricted to the
        implementation roots (no cross-tree collisions with docs/en)."""
        token = token.strip().strip("/").removeprefix("./")
        cands = []
        for cand in (token, os.path.normpath(
                os.path.join(os.path.dirname(source_rel), token)).replace("\\", "/")):
            if cand.startswith("..") or not cand.endswith(".md"):
                continue
            if self.is_implementation_file(cand) and cand not in cands:
                cands.append(cand)
        return cands

    def resolve_file(self, token: str, source_rel: str):
        """Resolve a file-reference token to a corpus-relative docs/en path.

        Accepted forms (in order): a path relative to the source file's own
        directory (markdown relative links, e.g. `../index.md`); repo-relative
        `docs/en/...`; a path relative to docs/en (canonical identifier style,
        e.g. `documenter-service/x.md`); a corpus-unique bare basename.
        Returns relative path if the file exists on disk, else None.

        When --core-root was provided and the host lookup fails, falls back
        to the core root's <core_root>/docs/en/ as a read-only resolution space.
        """
        token = token.strip().strip("/").removeprefix("./")
        for cand in self._docs_candidates(token, source_rel):
            abs_path = os.path.join(self.root, *cand.split("/"))
            if os.path.isfile(abs_path):
                return cand
        # Core fallback: try the token as a direct docs/en path under core_root
        if self.core_root:
            resolved_core = _core_root_resolve(self.core_root, token)
            if resolved_core:
                return resolved_core
        return None

    def exists_anywhere(self, token: str, source_rel: str) -> bool:
        """True when token resolves to an existing file ANYWHERE under root
        (docs/en-relative, source-relative, or an implementation file such as
        `fallback/index.md` or `.agents/skills/.../SKILL.md`, AGENTS.md §1.6)."""
        token = token.strip().strip("/").removeprefix("./")
        for cand in (token,
                     "docs/en/" + token,
                     os.path.normpath(os.path.join(os.path.dirname(source_rel), token))):
            abs_path = os.path.join(self.root, *cand.split("/"))
            if os.path.isfile(abs_path):
                return True
        return bool(self._impl_candidates(token, source_rel))

    def manifest_ids(self) -> set:
        """ids from the generated manifest (empty when the corpus fails to parse)."""
        entries, errors = gen_manifest.build_entries(self.root)
        if errors:
            return set()
        return {e["id"] for e in entries}

    def core_doc_ids(self) -> set:
        """ids from the core corpus (read-only resolution space), derived from
        front-matter ``id`` fields of every document under <core_root>/docs/en.

        Cached on first call so repeated queries are O(1). Returns an empty
        set when ``core_root`` was not provided."""
        if self._core_doc_ids is not None:
            return self._core_doc_ids
        if self.core_root is None:
            self._core_doc_ids = set()
            return self._core_doc_ids
        ids = set()
        for hdr in self._core_headers.values():
            try:
                iid = hdr.fields["id"]
            except KeyError:
                continue
            if isinstance(iid, str) and iid:
                ids.add(iid)
        self._core_doc_ids = ids
        return self._core_doc_ids

    # -- §Name resolution --------------------------------------------------------

    @staticmethod
    def _hit_tokens(text: str) -> list:
        """Comparison tokens for a heading/label/§Name: camelCase split, then
        lowercase word tokens with section numbers dropped ('2. Policy File'
        -> policy, file; 'SessionManifest' -> session, manifest) so joined
        and spaced spellings match each other."""
        spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
        toks = re.split(r"[^a-z0-9]+", spaced.lower())
        toks = [t for t in toks if t and not re.fullmatch(r"\d+(?:\.\d+)*", t)]
        return toks

    @staticmethod
    def _tokens_contain(short: list, long: list) -> bool:
        """True when `short` occurs in `long` as a contiguous token run."""
        n = len(short)
        if n == 0 or n > len(long):
            return False
        return any(long[i:i + n] == short for i in range(len(long) - n + 1))

    @classmethod
    def _name_hit(cls, raw: str, texts: list) -> bool:
        """True when raw resolves against heading/bold texts at token
        boundaries, in either direction as a contiguous run:
          * a heading occurs inside raw — trailing prose does not cause
            spurious misses (`§Field Reference in ...` hits 'Field Reference');
          * raw occurs inside a heading — the reference abbreviates it
            (`§Session` hits 'Session workspace convention',
            §Zero hits 'Zero silent defaults policy (ADR-002)');
          * slug equality either way;
          * numeric section match (§4.2 / §5 against numbered headings like
            `5. Resolved Conflicts`) — matters for numbered implementation
            files (AGENTS.md §1.7) and numbered specs (mvp-contract §5)."""
        rest = raw.strip()
        if not rest:
            return True  # nothing to match: conservative pass
        ntoks = cls._hit_tokens(rest)
        for h in texts:
            h_clean = h.strip().strip("*_`")
            if not h_clean:
                continue
            htks = cls._hit_tokens(h_clean)
            if not htks or not ntoks:
                continue
            if (cls._tokens_contain(htks, ntoks)
                    or cls._tokens_contain(ntoks, htks)
                    or tests_helpers.slugify(h_clean) == tests_helpers.slugify(rest)):
                return True
        m = re.match(r"(\d+(?:\.\d+)*)", rest)
        if m:
            num = m.group(1)
            for h in texts:
                hm = re.match(r"\s*(\d+(?:\.\d+)*)[.)]?\s", h)
                if hm and hm.group(1) == num:
                    return True
        return False

    def _bound_file_before(self, line: str, pos: int):
        """Token of the *.md file immediately preceding line[pos] (only
        backticks/punctuation/spaces/parens in between), or None. Used to
        distinguish 'file.md ..., §Name' (the § targets that file) from a
        line that merely mentions some file elsewhere."""
        m = re.search(r"([\w./-]+\.md)[`\s,;:()]*$", line[:pos])
        return m.group(1) if m else None

    def _ref_files_for_line(self, line: str, rel: str):
        """Same-line file detection for §Name context.

        Returns (named_files, impl_named):
          * named_files — resolvable docs/en paths named on the line (paths
            with or without backticks, bare `<file>.md` included, trailing
            punctuation stripped, generic names like `index.md` skipped);
          * impl_named — resolvable implementation files (AGENTS.md,
            fallback/, .agents/) named on the line.
        """
        named, impl_named = [], []
        stripped_line = line.replace("`", "")
        tokens = []
        for m in _MD_LINK_RE.finditer(line):
            tokens.append(m.group(1).partition("#")[0])
        for m in _BACKTICK_TOKEN_RE.finditer(line):
            tokens.append(m.group(1))
        for m in _SAMELINE_PATH_RE.finditer(stripped_line):
            tokens.append(m.group(1))
        for tok in tokens:
            tok = tok.strip().strip("/").strip("`").rstrip(",.;:!?")
            tok = tok.rstrip(".,;:")
            if not tok.lower().endswith(".md"):
                continue
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", tok):
                continue  # external scheme (http:, mailto:)
            if tok.rsplit("/", 1)[-1] in _GENERIC_MD_NAMES:
                continue  # `index.md` etc. carry no targeting information
            resolved = self.resolve_file(tok, rel)
            if resolved:
                if resolved not in named:
                    named.append(resolved)
                continue
            impl = self._impl_candidates(tok, rel)
            if impl and impl[0] not in impl_named:
                impl_named.append(impl[0])
        return named, impl_named

    def _prose_hint_files(self, line: str) -> list:
        """Canonical ids mentioned on the line (bare or backticked), e.g.
        'protocol-core §Outcome-to-Transition' or '(`operator-ingress`)':
        tokens matching a first-level docs/en directory name resolve to that
        folder's index.md. Context hints only — never a missing-file signal."""
        self._ensure_corpus_indexes()
        if not self._docs_roots:
            return []
        out = []
        bare = _MD_LINK_RE.sub(" ", line)
        for tok in re.split(r"[^\w-]+", bare):
            if tok in self._docs_roots:
                cand = f"docs/en/{tok}/index.md"
                if cand not in out and os.path.isfile(
                        os.path.join(self.root, *cand.split("/"))):
                    out.append(cand)
        return out

    @staticmethod
    def _section_name(raw_after: str):
        """§Name to match: conservative token grammar (leading uppercase/digit
        token plus following Capitalized or dotted-numeric tokens) with
        punctuation-stopped continuation — 'Hash Store. ADR-010' stops at
        'Hash Store'. Returns None when nothing extractable (lowercase prose,
        e.g. '§ above') — such references pass conservatively."""
        tm = _SECTION_TOK_RE.match(raw_after.lstrip())
        if not tm:
            return None
        matched = tm.group(0)
        keep = []
        for part in re.split(r"([ \t]+)", matched):
            if part.strip() and re.search(r"[.,;:!?]$", part):
                keep.append(part.rstrip(".,;:!?"))
                break
            keep.append(part)
        name = "".join(keep).strip()
        return name or None

    def _match_name(self, name: str) -> set:
        """Corpus-wide files whose heading/bold pseudo-heading/H1 title
        contains the name's tokens as a contiguous run, or is itself
        contained in them ('Configuration Guide' -> 'Documenter
        Configuration Guide'; 'Zero' -> 'Zero silent defaults policy')."""
        self._ensure_corpus_indexes()
        ntoks = self._hit_tokens(name)
        if not ntoks:
            return set()
        files = set()
        for index in (self._heading_unique, self._title_unique):
            for k, fs in index.items():
                ktks = k.split()
                if (self._tokens_contain(ntoks, ktks)
                        or self._tokens_contain(ktks, ntoks)):
                    files |= fs
        return files

    def section_findings(self, rel: str, idx: int, line: str) -> list:
        """rule-4 §Name references for one line (resolver contract, see the
        rule-4 resolver-posture note in the module docstring):

        (b) the *.md token immediately preceding the § (only backticks,
            punctuation and spaces in between) binds as the target file:
            hit (headings + bold pseudo-headings) passes, miss is
            broken-anchor HIGH;
        (d) bound/line-named implementation file (AGENTS.md, fallback/,
            .agents/; AGENTS.md §1.6) -> hit passes, miss is LOW (never
            medium/high — out of manifest scope);
        (c) unbound: containing file + canonical-id prose hints first, then
            any *.md token mentioned elsewhere on the line; then a
            corpus-wide heading index — a non-empty match passes, multiple
            matches also yield LOW ambiguous-section-reference with
            candidates (max 3); zero matches yield medium
            unresolved-reference (the signal worth keeping).

        Numeric §Names (§7.3, §2.2.3) resolve only against numbered headings
        in the candidate context; unresolved numerics are LOW
        (implementation-style references, e.g. AGENTS.md conventions quoted
        in prose)."""
        out = []
        named, impl_named = self._ref_files_for_line(line, rel)
        prose = self._prose_hint_files(line)
        for m in _SECTION_REF_RE.finditer(line):
            raw_after = line[m.end():]
            name = self._section_name(raw_after)
            if name is None:
                continue  # nothing extractable: conservative pass
            numeric = bool(re.fullmatch(r"\d+(?:\.\d+)*", name))
            bound = self._bound_file_before(line, m.start())
            if bound:
                target = self.resolve_file(bound, rel)
                if target:
                    if self._name_hit(name,
                                      self.heading_and_bold_texts(target)):
                        continue
                    out.append(_finding(
                        "broken-anchor", "high", rel,
                        f"rule-4 cross-ref-anchors: §{name!r} on line {idx + 1} "
                        f"not found among headings of bound same-line file "
                        f"{target!r}"))
                    continue
                impl = self._impl_candidates(bound, rel)
                if impl:
                    if self._name_hit(name,
                                      self.heading_and_bold_texts(impl[0])):
                        continue
                    out.append(_finding(
                        "broken-anchor", "low", rel,
                        f"rule-4 cross-ref-anchors: §{name!r} on line {idx + 1} "
                        f"not found in implementation file {impl[0]} (AGENTS.md "
                        f"§1.6: out of manifest scope, LOW by contract)"))
                    continue
            cand = prose + [rel] + named + impl_named
            if any(self._name_hit(name, self.heading_and_bold_texts(c))
                   for c in cand):
                continue
            if numeric:
                out.append(_finding(
                    "unresolved-reference", "low", rel,
                    f"rule-4 cross-ref-anchors: numeric §{name} on line {idx + 1} "
                    f"matched no numbered heading in {', '.join(dict.fromkeys(cand))}; "
                    f"numeric section references are implementation-style, "
                    f"reported LOW"))
                continue
            matches = sorted(self._match_name(name))
            if len(matches) == 1:
                continue  # corpus-wide unique heading: resolve there, PASS
            if matches:
                shown = ", ".join(matches[:3])
                extra = "" if len(matches) <= 3 else " (+more)"
                out.append(_finding(
                    "ambiguous-section-reference", "low", rel,
                    f"rule-4 cross-ref-anchors: §{name!r} on line {idx + 1} is "
                    f"ambiguous — matched in {shown}{extra}; no file bound to "
                    f"the reference on the line"))
                continue
            out.append(_finding(
                "unresolved-reference", "medium", rel,
                f"rule-4 cross-ref-anchors: §{name!r} on line {idx + 1} matched no "
                f"heading corpus-wide (no file bound on the reference line); "
                f"unresolvable context is reported at medium (false positives "
                f"acceptable per design)"))
        return out


def _visible_lines(lines: list) -> list:
    """(index, line) pairs outside fenced code blocks and HTML comments."""
    out = []
    in_fence = False
    in_comment = False
    for i, line in enumerate(lines):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        text = line
        if in_comment:
            if "-->" in text:
                text = text.split("-->", 1)[1]
                in_comment = False
            else:
                continue
        text = _HTML_COMMENT_RE.sub("", text)
        if "<!--" in text:
            text = text.split("<!--", 1)[0]
            in_comment = True
        out.append((i, text))
    return out


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def check_rule1_line_count(corpus: _Corpus) -> list:
    """rule-1 line-count (high): content lines <= 200, documentation-rules §7.3."""
    findings = []
    for rel in corpus.docs:
        n = tests_helpers.content_line_count(corpus.texts[rel])
        if n > LINE_LIMIT:
            findings.append(_finding(
                "line-count", "high", rel,
                f"rule-1 line-count: {n} content lines exceed the {LINE_LIMIT}-line "
                f"limit (documentation-rules §7.3) — split or condense"))
    return findings


def check_rule2_changelog(corpus: _Corpus) -> list:
    """rule-2 changelog-existence: delegated to docmeta.validate."""
    findings = []
    for rel, header in corpus.headers.items():
        for f in docmeta.validate(header, file=rel, root=corpus.root):
            if f["rule"] in ("changelog-path-missing", "changelog-path-location"):
                findings.append(f)
    return findings


def check_rule4_cross_refs(corpus: _Corpus) -> list:
    """rule-4 cross-ref-anchors (see module docstring for resolver posture)."""
    findings = []
    for rel in corpus.docs:
        for idx, line in _visible_lines(corpus.lines[rel]):
            findings.extend(_refs_from_line(corpus, rel, idx, line))
    # dedupe identical (rule, severity, file, description) tuples
    seen, deduped = set(), []
    for f in findings:
        key = (f["rule"], f["severity"], f["file"], f["description"])
        if key not in seen:
            seen.add(key)
            deduped.append(f)
    return deduped


def _refs_from_line(corpus: _Corpus, rel: str, idx: int, line: str) -> list:
    out = []

    # (a) markdown links [text](target)
    for m in _MD_LINK_RE.finditer(line):
        target = m.group(1)
        path_part, _, fragment = target.partition("#")
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", path_part):
            continue  # external scheme (http:, mailto:)
        if path_part:
            resolved = corpus.resolve_file(path_part, rel)
            if resolved is None:
                out.append(_finding(
                    "unresolved-reference", "medium", rel,
                    f"rule-4 cross-ref-anchors: link target {path_part!r} on line "
                    f"{idx + 1} does not resolve to a file under docs/en"))
                continue
            if fragment and fragment not in corpus.slugs(resolved):
                out.append(_finding(
                    "broken-anchor", "medium", rel,
                    f"rule-4 cross-ref-anchors: anchor {fragment!r} on line {idx + 1} "
                    f"not found among ATX-heading slugs of {resolved}"))
        else:
            if fragment and fragment not in corpus.slugs(rel):
                out.append(_finding(
                    "broken-anchor", "medium", rel,
                    f"rule-4 cross-ref-anchors: same-file anchor {fragment!r} on "
                    f"line {idx + 1} not found among ATX-heading slugs"))

    # (b) docs/en/<path>.md mentions (inline code or plain path) — high if missing
    for m in _PATH_REF_RE.finditer(line):
        token = m.group(1)
        if corpus.resolve_file(token, rel) is None:
            out.append(_finding(
                "missing-reference", "high", rel,
                f"rule-4 cross-ref-anchors: referenced file {token!r} on line "
                f"{idx + 1} does not exist under docs/en"))

    # (c) Cross-References sections: canonical identifiers `dir/file.md` or
    #     bare kebab ids that are not paths. References to existing
    #     implementation files (AGENTS.md §1.6: fallback/, .agents/, tools/)
    #     are legal and not flagged.
    if _in_cross_references_section(corpus, rel, idx):
        for m in _BACKTICK_REF_RE.finditer(line):
            token = m.group(1)
            if token.startswith("docs/en/") or "/" not in token:
                continue
            if not token.startswith(("docs/", "CHANGELOGS/", "tools/", "tests/")):
                if (corpus.resolve_file(token, rel) is None
                        and not corpus.exists_anywhere(token, rel)):
                    out.append(_finding(
                        "missing-reference", "high", rel,
                        f"rule-4 cross-ref-anchors: canonical identifier {token!r} "
                        f"on line {idx + 1} does not resolve to a file under docs/en"))
        # Bullet-list cross-reference identifier check (restored per audit contract):
        # bare kebab-id like `- \`foo\`` must be a known doc id — host manifest
        # first; when --core-root is set, core frontmatter ids are accepted too.
        stripped = line.strip()
        m = re.match(r"^\s*[-*]\s+`([\w][\w-]*)`\s*$", stripped)
        if m:
            ident = m.group(1)
            known_ids = corpus.manifest_ids() | corpus.core_doc_ids()
            if ident not in known_ids:
                out.append(_finding(
                    "missing-reference", "high", rel,
                    f"rule-4 cross-ref-anchors: cross-reference identifier "
                    f"{ident!r} on line {idx + 1} is not a known document id"))

    # (d) §Name references: full resolver cascade (see _Corpus.section_findings).
    out.extend(corpus.section_findings(rel, idx, line))
    return out


def _in_cross_references_section(corpus: _Corpus, rel: str, idx: int) -> bool:
    """True when line idx sits under a heading containing 'cross-reference'."""
    for i in range(idx - 1, -1, -1):
        line = corpus.lines[rel][i]
        if _FENCE_RE.match(line):
            continue
        m = tests_helpers.ATX_RE.match(line)
        if m:
            return "cross-reference" in m.group(2).lower()
    return False


def check_rule6_manifest_parity(corpus: _Corpus) -> list:
    """rule-6 manifest-parity: regenerate-and-diff + orphan detection."""
    findings = []
    entries, errors = gen_manifest.build_entries(corpus.root)
    if errors:
        findings.append(_finding(
            "parity-skipped", "medium", "docs-manifest.yaml",
            "rule-6 manifest-parity: skipped — corpus has parse errors "
            f"({len(errors)} file(s)); fix frontmatter findings first"))
    else:
        generated = gen_manifest.render(entries)
        disk_path = os.path.join(corpus.root, "docs-manifest.yaml")
        on_disk = ""
        if os.path.exists(disk_path):
            with open(disk_path, encoding="utf-8") as fh:  # OSError -> exit 2
                on_disk = fh.read()
        if generated != on_disk:
            diff_lines = list(difflib.unified_diff(
                on_disk.splitlines(), generated.splitlines(),
                fromfile="docs-manifest.yaml (on disk)",
                tofile="docs-manifest.yaml (generated)"))
            findings.append(_finding(
                "manifest-drift", "high", "docs-manifest.yaml",
                f"rule-6 manifest-parity: on-disk manifest differs from generated "
                f"output ({len(diff_lines)} diff lines) — run "
                f"`python3 tools/gen_manifest.py --write`"))

    # Orphan detection: docs/en .md files absent from generated entries and
    # not covered by an allow_non_index_paths parent index (documentation-rules §2.1).
    listed = {e["path"] for e in entries}
    for rel in corpus.docs:
        if rel in listed:
            continue
        parent_index = os.path.dirname(rel) + "/index.md"
        parent = corpus.headers.get(parent_index)
        if parent is not None and parent.fields.get("allow_non_index_paths") is True:
            continue
        findings.append(_finding(
            "orphan", "high", rel,
            "rule-6 manifest-parity: file under docs/en is not present in the "
            "generated manifest and not covered by an allow_non_index_paths "
            "parent index"))
    return findings


def check_naming(corpus: _Corpus) -> list:
    """naming/schema (documentation-rules §7.1): kebab-case folders, index.md convention."""
    findings = []
    bad_dirs = set()
    for rel in corpus.docs:
        segments = rel.split("/")
        for seg in segments[2:-1]:  # folders under docs/en
            if seg in bad_dirs:
                continue
            if not _KEBAB_RE.match(seg):
                bad_dirs.add(seg)
                findings.append(_finding(
                    "naming", "high", rel,
                    f"naming (documentation-rules §7.1): folder segment {seg!r} under docs/en "
                    f"is not kebab-case (^[a-z0-9]+(-[a-z0-9]+)*$)"))
    for rel in corpus.docs:
        parent_index = os.path.dirname(rel) + "/index.md"
        if rel.endswith("/index.md") or parent_index in set(corpus.docs):
            continue  # canonical index, or sibling index governs the folder
        parent = corpus.headers.get(parent_index)
        if parent is None or parent.fields.get("allow_non_index_paths") is not True:
            findings.append(_finding(
                "naming", "high", rel,
                "naming (documentation-rules §7.1): non-index document in a folder without an "
                "index.md carrying allow_non_index_paths: true"))
    return findings


def check_schema(corpus: _Corpus) -> list:
    """naming/schema: frontmatter findings via docmeta.validate + parse errors.

    changelog-* findings are delegated to check_rule2_changelog and filtered
    here to avoid duplicates.
    """
    findings = []
    for rel, reason in sorted(corpus.parse_errors.items()):
        findings.append(_finding(
            "frontmatter", "high", rel,
            f"schema: header parse error (DocMetaError): {reason}"))
    for rel, header in corpus.headers.items():
        for f in docmeta.validate(header, file=rel, root=corpus.root):
            if f["rule"] in ("changelog-path-missing", "changelog-path-location"):
                continue  # rule-2 owns these
            findings.append(f)
    return findings


RULE_DISPATCH = [
    ("line-count", check_rule1_line_count),
    ("changelog", check_rule2_changelog),
    ("cross-ref", check_rule4_cross_refs),
    ("manifest-parity", check_rule6_manifest_parity),
    ("naming", check_naming),
    ("schema", check_schema),
    ("link-integrity", check_link_integrity),
]


def scan(root: str, rules=None, strict_links: bool = False, core_root: str = None) -> list:
    """Run enabled rule groups over the whole corpus; return findings (dicts).

    `rules` is an iterable of --rule group tokens or None for all. Unreadable
    files and missing docs/en raise OSError (mapped to exit 2 by main()).
    `strict_links` promotes link-integrity code→docs warnings to blocking
    (consensus sess-operator-surface-split O-3, clean pre-merge mode).
    `core_root` is an optional second read-only resolution space; when set,
    reference tokens that fail within the host corpus fall back to
    ``<core_root>/docs/en/`` (dual-root cross-resolution).
    """
    if rules is None:
        enabled = {name for name, _ in RULE_DISPATCH}
    else:
        enabled = set()
        for r in rules:
            key = r.strip().lower().replace("_", "-")
            if key in ("all",):
                enabled = {name for name, _ in RULE_DISPATCH}
            elif key in RULE_GROUPS:
                enabled.add(key)
            else:
                raise ValueError(f"unknown --rule {r!r}; valid: "
                                 + ", ".join(sorted(RULE_GROUPS)) + ", all")
    corpus = _Corpus(root, core_root=core_root)
    findings = []
    for name, fn in RULE_DISPATCH:
        if name in enabled:
            if name == "link-integrity":
                findings.extend(fn(corpus, strict_links=strict_links))
            else:
                findings.extend(fn(corpus))
    findings.sort(key=lambda f: (-tests_helpers.severity_rank(f["severity"]),
                                 f["file"], f["rule"], f["description"]))
    return findings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

EPILOG = """\
Rule coverage (mvp-interfaces.md §Compliance rules scanned):
  implemented (deterministic): rule-1 line-count, rule-2 changelog-existence,
  rule-4 cross-ref-anchors, rule-6 manifest-parity, naming/schema,
  link-integrity (docs→manifest hard fail; code→docs warn-only, --strict-links
  promotes; consensus sess-operator-surface-split O-3).
  NOT implemented: rule 3 (glossary terms) and rule 5 (abstraction
  consistency) are skill/AI-reserved judgments; this tool makes no claim to
  cover "rules 1-6".

Exit codes (computed over REPORTED findings after severity filter):
  0  clean — no reported findings.
  1  findings reported, none high.
  2  at least one high finding reported (critical) — OR — internal error
     (crash, unreadable corpus) / bad --rule token (distinguished on output).

--json emits one JSON object per line (EventSink-shaped: flat, no document
text): {"rule", "severity", "file", "description"}.

The DEFAULT human-readable format obeys the token contract with
tools/hooks/pre-commit: one finding per line as
`rule=<rule-id> severity=<sev> file=<path> <description>`
(the hook greps the literal `severity=high` in block mode); no document
text appears on the line.
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_all.py",
        description="Deterministic documentation compliance rule suite "
                    "(rules 1, 2, 4, 6 + naming/schema). Rules 3 (glossary "
                    "terms) and 5 (abstraction consistency) are skill/AI-"
                    "reserved and NOT implemented here — coverage of "
                    "'rules 1-6' is never claimed.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", default=None,
                        help="repository root (default: parent of tools/)")
    parser.add_argument("--json", action="store_true",
                        help="emit one JSON object per line: "
                             "{rule, severity, file, description} (EventSink-shaped)")
    parser.add_argument("--severity", choices=["low", "medium", "high", "warning"],
                        default="low", metavar="SEV",
                        help="minimum severity that is REPORTED (default: low; "
                             "medium/high reported, warnings hidden unless "
                             "asked via --strict or --severity warning)")
    parser.add_argument("--rule", action="append", dest="rules", metavar="ID",
                        help="restrict to a rule group (repeatable); default: all. "
                             "Note: changelog=rule-2, cross-ref=rule-4, "
                             "manifest-parity=rule-6")
    parser.add_argument("--strict", action="store_true",
                        help="report every finding regardless of severity "
                             "(equivalent to --severity warning)")
    parser.add_argument("--strict-links", action="store_true",
                        help="promote link-integrity code→docs warnings to "
                             "blocking (clean pre-merge runs); docs→manifest "
                             "findings are always blocking")
    parser.add_argument("--core-root", default=None, metavar="DIR",
                        help="second read-only resolution space: a reference token "
                             "that fails within the host corpus falls back to "
                             "<DIR>/docs/en/ (dual-root cross-resolution)")
    args = parser.parse_args(argv)

    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Validate core_root early — must contain docs/en directory (AC-5).
    core_root = args.core_root
    if core_root is not None:
        core_base = os.path.join(core_root, "docs", "en")
        if not os.path.isdir(core_base):
            print(f"ERROR: {core_base}: no docs/en directory under --core-root "
                  f"{core_root!r}", file=sys.stderr)
            return 2

    try:
        findings = scan(root, rules=args.rules, strict_links=args.strict_links,
                        core_root=core_root)
    except ValueError as exc:  # bad --rule token: usage error
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception:
        print("check_all: INTERNAL ERROR (fail-loud per contract). Corpus at "
              f"{root!r}. Remediation: fix the reported path (permissions, "
              "encoding, file-vs-directory) or file a validator bug report "
              "with the traceback below.", file=sys.stderr)
        traceback.print_exc()
        return 2

    # Filter: --severity means minimum REPORTED severity.
    # --strict is equivalent to --severity warning (report all).
    min_reported = "warning" if args.strict else args.severity
    min_rank = tests_helpers.severity_rank(min_reported)
    reported = [f for f in findings
                if tests_helpers.severity_rank(f["severity"]) >= min_rank]

    # Exit code computed over REPORTED findings only.
    has_high = any(f["severity"] == "high" for f in reported)
    if has_high:
        rc = 2
    elif reported:
        rc = 1
    else:
        rc = 0

    if args.json:
        for f in reported:
            print(json.dumps({"rule": f["rule"], "severity": f["severity"],
                              "file": f["file"], "description": f["description"]},
                             ensure_ascii=False))
    else:
        if reported:
            # Human rendering per frozen audit contract §4:
            # Header line(s) based on high severity, then hint lines.
            n_high = sum(1 for f in reported if f["severity"] == "high")
            if n_high:
                print(f"\U0001f6a8 critical: {n_high}")
            print(f"\u26a0 findings: {len(reported)}")
            # Hint lines sorted by severity (high → medium → low → warning),
            # each carrying the stable token contract.
            for f in reported:
                print(f"rule={f['rule']} severity={f['severity']} "
                      f"file={f['file']} {f['description']}")
        # Clean: no output at all (silent when clean).

    return rc


if __name__ == "__main__":
    sys.exit(main())
