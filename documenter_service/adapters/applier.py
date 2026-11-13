"""Pure unified-diff applier.

apply_unified_diff(original, diff_text) -> str

Parse hunk headers @@ -old_start[,old_count] +new_start[,new_count] @@ and
apply each hunk AT ITS DECLARED POSITION: untouched lines between hunks are
copied verbatim, context/removed lines must match the original exactly
(verbatim comparison), added lines are inserted. The --- / +++ / diff headers
are ignored (the caller verifies path binding separately). Supports multiple
hunks, pure insertions (@@ -N,0 +... @@), deletions, blank lines anywhere.

Blank-line model: StdDiffEngine.normalize rstrips every line, so a blank
CONTEXT line arrives as "" (its single leading space was trailing
whitespace). Inside a hunk body "" is therefore a blank context line, never
an end marker — trailing blank lines of the payload itself were already
folded by normalize (single final newline).

Guards: unparseable header, context/removed mismatch, hunk start beyond EOF,
overlapping/out-of-order hunks, old_count inconsistency (when non-zero) —
each raises StructuredError("unknown", "diff does not apply cleanly ...").
Deterministic, pure, no I/O.
"""
from __future__ import annotations

import re

from ..core.errors import StructuredError

__all__ = ["apply_unified_diff"]

# Compiled regex for hunk header: @@ -old_start[,old_count] +new_start[,new_count] @@
_RE_HUNK = re.compile(
    r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@"
)


def _mismatch(detail: str, header: str) -> StructuredError:
    return StructuredError(
        "unknown",
        f"diff does not apply cleanly to <file>: {detail} ({header})")


def apply_unified_diff(original: str, diff_text: str) -> str:
    """Apply a unified diff to the original text, returning the new content.

    Parameters
    ----------
    original : str
        The original file text.
    diff_text : str
        A normalized unified diff whose --- / +++ headers are ignored.

    Returns
    -------
    str
        The new file content after applying all hunks at their declared
        positions.

    Raises
    ------
    StructuredError("unknown", ...) on any structural violation (context
    mismatch, bad hunk position, inconsistent counts).
    """
    # Git-like line model: text ending with "\n" has NO phantom final line;
    # "" has no lines. Output re-adds a single final newline when non-empty
    # (documents are newline-terminated by convention). Trailing "" artifacts
    # in the diff payload are never real blank context lines: normalize()
    # folds trailing blank lines, so a blank context line can never be the
    # last payload line.
    def _split(text: str) -> list:
        if text == "":
            return []
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        return lines

    original_lines = _split(original)
    diff_lines = _split(diff_text)

    result_lines: list[str] = []
    original_pos = 0  # next original line not yet copied
    i = 0

    while i < len(diff_lines):
        line = diff_lines[i]
        if line.startswith(("--- ", "+++ ", "diff ")):
            i += 1
            continue
        if not line.startswith("@@"):
            i += 1
            continue

        m = _RE_HUNK.match(line)
        if not m:
            raise _mismatch(f"unparseable hunk header {line!r}", line)
        old_start = int(m.group(1))
        old_count = int(m.group(2)) if m.group(2) is not None else 1

        # Hunk body: everything until the next @@ header (or end of payload).
        body: list[str] = []
        j = i + 1
        while j < len(diff_lines) and not diff_lines[j].startswith("@@"):
            body.append(diff_lines[j])
            j += 1

        # Position: @@ -N,0 @@ inserts AFTER line N; otherwise start AT N.
        if old_count == 0:
            target_pos = old_start
        else:
            target_pos = old_start - 1
        if target_pos < original_pos:
            raise _mismatch(
                f"hunk starts at original line {target_pos + 1} but lines up to "
                f"{original_pos} were already consumed (overlapping or "
                "out-of-order hunks)", line)
        if target_pos > len(original_lines):
            raise _mismatch(
                f"hunk starts at original line {target_pos + 1}, beyond end of "
                f"file ({len(original_lines)} lines)", line)

        # Copy untouched lines up to the declared position.
        while original_pos < target_pos:
            result_lines.append(original_lines[original_pos])
            original_pos += 1

        consumed_old = 0
        saw_old_line = False
        for dl in body:
            if dl.startswith("+"):
                result_lines.append(dl[1:])
            elif dl.startswith("-"):
                if original_pos >= len(original_lines):
                    raise _mismatch(
                        f"not enough lines in original to remove at line "
                        f"{original_pos + 1}", line)
                if dl[1:] != original_lines[original_pos]:
                    raise _mismatch(
                        f"removed line mismatch at original line "
                        f"{original_pos + 1}: expected {dl[1:]!r}, got "
                        f"{original_lines[original_pos]!r}", line)
                original_pos += 1
                consumed_old += 1
                saw_old_line = True
            else:
                # Context line: " " prefix, or "" for a blank context line
                # (normalize rstripped it). Never an end marker.
                ctx = dl[1:] if dl.startswith(" ") else ""
                if dl and not dl.startswith(" "):
                    # Non-blank, unprefixed line inside a hunk body: malformed.
                    raise _mismatch(
                        f"unexpected line in hunk body: {dl!r}", line)
                if original_pos >= len(original_lines):
                    raise _mismatch(
                        f"context mismatch at original line {original_pos + 1} "
                        "(reached end of original)", line)
                if ctx != original_lines[original_pos]:
                    raise _mismatch(
                        f"context mismatch at original line "
                        f"{original_pos + 1}: expected {ctx!r}, got "
                        f"{original_lines[original_pos]!r}", line)
                result_lines.append(ctx)
                original_pos += 1
                consumed_old += 1
                saw_old_line = True

        if old_count > 0 and consumed_old != old_count:
            raise _mismatch(
                f"hunk declares {old_count} old line(s) but consumed "
                f"{consumed_old}", line)
        if old_count == 0 and saw_old_line:
            raise _mismatch(
                "hunk declares a pure insertion (@@ -N,0) but contains "
                "context/removed lines", line)

        i = j

    # Copy the tail after the last hunk.
    while original_pos < len(original_lines):
        result_lines.append(original_lines[original_pos])
        original_pos += 1

    if not result_lines:
        return ""
    return "\n".join(result_lines) + "\n"
