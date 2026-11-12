#!/usr/bin/env python3
"""Shared helpers for deterministic compliance tooling (tools/check_all.py)
and its unit tests (tests/test_check_all.py).

Kept dependency-free (stdlib only) so both the checker and the unittest
suite import the SAME slugification / line-accounting rules — drift between
"what the tool checks" and "what the tests assert" is itself a defect.
"""
from __future__ import annotations

import re

__all__ = [
    "SEVERITY_LEVELS",
    "severity_rank",
    "ATX_RE",
    "heading_texts",
    "slugify",
    "meta_block_span",
    "content_line_count",
]

#: Severity ordering used across the tool. ``warning`` is informational and
#: never blocking (legacy mapping in mvp-interfaces would fold it into medium,
#: but docmeta emits genuine warnings, e.g. last-modified-deprecated).
SEVERITY_LEVELS = {"warning": 0, "low": 1, "medium": 2, "high": 3}


def severity_rank(severity: str) -> int:
    """Numeric rank for a severity label; unknown labels rank as high (fail loud)."""
    return SEVERITY_LEVELS.get(severity, 3)


#: ATX headings only (per mvp-interfaces rule 4: "ATX headings").
#: Group 1: hashes; group 2: heading text.
ATX_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")


def heading_texts(lines) -> list:
    """Texts of all ATX headings, skipping fenced code blocks (``` or ~~~)."""
    texts = []
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = ATX_RE.match(line)
        if m:
            texts.append(m.group(2).strip())
    return texts


def slugify(heading: str) -> str:
    """GitHub-style anchor slug: lowercase, spaces -> hyphens, strip punctuation.

    Deliberately mirrors the three steps named in the Stage B plan; it is a
    pragmatic approximation (e.g. non-ASCII is kept, underscores kept) — false
    negatives are reported as medium findings, never high.
    """
    s = heading.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    return s.replace(" ", "-")


def meta_block_span(lines) -> tuple:
    """Span (start, end) of the metadata block in the canonical header layout.

    Same geometry tools/docmeta.py parses: first `# ` H1 line, then blank
    lines, then a contiguous run of non-blank lines. Returns (start, end)
    where end is EXCLUSIVE; (0, 0) when no H1 exists (file is a parse error
    anyway; counted as 0 metadata lines).
    """
    h1_index = None
    for i, line in enumerate(lines):
        if line.startswith("# "):
            h1_index = i
            break
    if h1_index is None:
        return (0, 0)
    i = h1_index + 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    start = i
    while i < len(lines) and lines[i].strip():
        i += 1
    return (start, i)


def content_line_count(text: str) -> int:
    """Content lines for rule-1 (line-count). FORMULA:

        content_lines = total_lines - metadata_block_lines - blank_lines

    where total_lines = len(text.splitlines()); metadata_block_lines = the
    contiguous `Key: value` block located by meta_block_span() (the H1 line
    itself counts as content); blank_lines = lines that are empty or
    whitespace-only, excluding those already inside the metadata block.
    """
    lines = text.splitlines()
    start, end = meta_block_span(lines)
    total = len(lines)
    meta = end - start
    blank = sum(
        1 for i, ln in enumerate(lines)
        if not ln.strip() and not (start <= i < end)
    )
    return total - meta - blank
