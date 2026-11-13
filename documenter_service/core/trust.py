"""Trust classification for delegate(preview) — mvp-interfaces §2, §Trust table.

The effective trust level is assigned by Documenter, not the caller (index.md
§Trust Classification): on the scale safe < review the invariant is
`requested >= derived`; a lower request is rejected with `trust_mismatch`
before any approval stage. Policy may raise the floor, never lower it.

MVP static floors (mvp-interfaces §2 Trust classification table):

    update    -> safe   (static floor; dynamic derivation applies when a diff
                         is available: safe only if every changed line is
                         mechanical, else review)
    split     -> review
    create_ru -> review (RU auto-fix banned in MVP)
    custom    -> review (default when indeterminate)

MVP now implements dynamic derivation for `update` per mvp-interfaces
§Trust classification: when diff_text is provided, every changed line is
classified as mechanical or not — `safe` only if all changed lines are
mechanical, otherwise `review`. Static floor is kept as the documented
fallback when diff is unavailable (diff_text is None).
"""
from __future__ import annotations

import re

from ..core.errors import StructuredError

__all__ = ["STATIC_FLOORS", "CHANGE_TYPES", "TRUST_LEVELS", "derive_trust",
           "check_invariant", "is_mechanical_line"]

#: change_type enum (mvp-interfaces §2 request table).
CHANGE_TYPES = ("update", "split", "create_ru", "custom")

#: trust_level enum (safe < review).
TRUST_LEVELS = ("safe", "review")

#: Static floor per change_type (policy-reference validator/authority rule).
STATIC_FLOORS = {
    "update": "safe",
    "split": "review",
    "create_ru": "review",
    "custom": "review",
}

_RANK = {"safe": 0, "review": 1}

# Compiled regexes for mechanical-line classification.
_RE_CHANGELOG_PATH = re.compile(r"^changelog-path:\s*\S.*$")
_RE_LAST_MODIFIED = re.compile(r"^Last Modified:\s*.*$")


def is_mechanical_line(body: str) -> bool:
    """Return True when ``body`` is a purely mechanical diff change.

    Mechanical patterns (case-sensitive, conservative):

      a. empty line (insertion/removal of a blank line);
      b. table row: starts with ``|`` and ends with ``|``;
      c. table separator: starts with ``|`` and consists only of
         ``|``, ``-``, ``:``, `` `` characters;
      d. changelog frontmatter key matching ``^changelog-path:\\s*\\S.*$``;
      e. last-modified frontmatter key matching ``^Last Modified:\\s*.*$``.
    """
    # (a) empty line
    if not body:
        return True
    # (b) table row
    if body.startswith("|") and body.endswith("|"):
        return True
    # (c) table separator: only pipe, dash, colon, space
    if body.startswith("|") and re.fullmatch(r"[|\-: ]+", body):
        return True
    # (d) changelog-path frontmatter key
    if _RE_CHANGELOG_PATH.match(body):
        return True
    # (e) last-modified frontmatter key (deprecated, removed per AGENTS.md §7.2)
    if _RE_LAST_MODIFIED.match(body):
        return True
    return False


def _classify_diff(diff_text: str):
    """Classify every changed line in a unified diff.

    Returns ``(levels, hunk_counts, reason)`` where:
      * levels — list of ("mech"|"non-mech") for each changed line (in order);
      * hunk_counts — {hunk_number: count_of_changed_lines};
      * reason — short explanation (indeterminate or all-mechanical).
    """
    hunk_number = 0
    levels = []
    hunk_counts: dict[int, int] = {}
    current_hunk = 1

    for line in diff_text.split("\n"):
        # Skip diff metadata headers — these are NOT changed lines.
        if line.startswith("--- ") or line.startswith("+++ ") or line.startswith("diff "):
            continue
        # Count hunk boundaries.
        if line.startswith("@@"):
            hunk_number += 1
            current_hunk = hunk_number

        # Changed lines: the only ones that affect classification.
        if line.startswith("+") or line.startswith("-"):
            # Line body after stripping the leading +/- character.
            body = line[1:].strip()
            mechanical = is_mechanical_line(body)
            levels.append("mech" if mechanical else "non-mech")
            hunk_counts[current_hunk] = hunk_counts.get(current_hunk, 0) + 1

    total_changed = len(levels)
    if total_changed == 0:
        return ("review",
                "diff contains no changed lines — "
                "indeterminate classification (no content changed) → review")

    all_mechanical = all(l == "mech" for l in levels)
    if all_mechanical:
        types_found = set()
        for line in diff_text.split("\n"):
            if line.startswith("--- ") or line.startswith("+++ ") or line.startswith("diff "):
                continue
            if not (line.startswith("+") or line.startswith("-")):
                continue
            body = line[1:].strip()
            if not body:
                types_found.add("blank lines")
            elif body.startswith("|") and body.endswith("|"):
                types_found.add("table rows")
            elif body.startswith("|") and re.fullmatch(r"[|\-: ]+", body):
                types_found.add("table separators")
            elif _RE_CHANGELOG_PATH.match(body):
                types_found.add("changelog-path frontmatter key")
            elif _RE_LAST_MODIFIED.match(body):
                types_found.add("last-modified frontmatter key")

        types_str = ", ".join(sorted(types_found))
        hunks_str = ", ".join(str(h) for h in sorted(hunk_counts))
        reason = (f"every changed line across hunk(s) "
                  f"({hunks_str}) is mechanical: {types_str}")
        return ("safe", reason)

    # Find first non-mechanical hunk.
    first_non_mech_hunk = None
    hunk_number = 0
    current_hunk = 1
    for line in diff_text.split("\n"):
        if line.startswith("--- ") or line.startswith("+++ ") or line.startswith("diff "):
            continue
        if line.startswith("@@"):
            hunk_number += 1
            current_hunk = hunk_number
        if line.startswith("+") or line.startswith("-"):
            body = line[1:].strip()
            if not is_mechanical_line(body):
                if hunk_counts.get(current_hunk, 0) > 0:
                    first_non_mech_hunk = current_hunk
                    break

    quote = ""
    hunk_number = 0
    current_hunk = 1
    for line in diff_text.split("\n"):
        if line.startswith("--- ") or line.startswith("+++ ") or line.startswith("diff "):
            continue
        if line.startswith("@@"):
            hunk_number += 1
            current_hunk = hunk_number
        if line.startswith("+") or line.startswith("-"):
            body = line[1:].strip()
            if not is_mechanical_line(body):
                quote = (" → " + body[:40]) if body else ""
                break

    reason = (f"hunk {first_non_mech_hunk} changes a non-mechanical "
              f"(normative) line{quote} → review")
    return ("review", reason)


def derive_trust(change_type: str, diff_text: str | None = None) -> tuple:
    """Return (derived_level, reason) for ``change_type``.

    MVP dynamic derivation (mvp-interfaces §Trust classification table):
    for ``update`` with a provided ``diff_text``, every changed line is
    classified as mechanical or not — ``safe`` only when all are mechanical,
    otherwise ``review``. Unknown change_type raises StructuredError(unknown):
    enum enforcement is a defect, not operator action.
    """
    if change_type not in STATIC_FLOORS:
        raise StructuredError(
            "unknown", f"unknown change_type: {change_type!r} "
                       "(closed enum: " + ", ".join(CHANGE_TYPES) + ")")
    floor = STATIC_FLOORS[change_type]

    # Non-update types always use the static floor — dynamic analysis cannot
    # lower a review floor.
    if change_type != "update":
        return floor, f"static floor for change_type {change_type!r} is {floor!r} " \
                      "(mvp-interfaces §2 Trust classification table)"

    # No diff provided — return the static floor.
    if diff_text is None:
        return floor, f"static floor for change_type {change_type!r} is {floor!r} " \
                      "(mvp-interfaces §2 Trust classification table)"

    # Dynamic derivation for update with a diff.
    derived, reason = _classify_diff(diff_text)
    return derived, reason


def check_invariant(change_type: str, trust_level: str,
                    diff_text: str | None = None) -> tuple:
    """Validate the request against the derived floor; returns (level, reason).

    Raises StructuredError("trust_mismatch") when requested < derived, and
    StructuredError("unknown") for an unknown trust_level value.
    """
    if trust_level not in _RANK:
        raise StructuredError(
            "unknown", f"unknown trust_level: {trust_level!r} "
                       "(closed enum: " + ", ".join(TRUST_LEVELS) + ")")
    derived, reason = derive_trust(change_type, diff_text)
    if _RANK[trust_level] < _RANK[derived]:
        raise StructuredError(
            "trust_mismatch",
            f"requested trust_level {trust_level!r} is below the derived floor "
            f"{derived!r} for change_type {change_type!r}: {reason}")
    return derived, reason
