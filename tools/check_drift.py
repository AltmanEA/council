#!/usr/bin/env python3
"""check_drift.py — Deterministic EN↔RU structural comparison tool.

Usage:
    python3 tools/check_drift.py <en_path> <ru_path> [--json]
    python3 tools/check_drift.py --files docs/en/scenario/index.md docs/ru/scenario/index-RU.md

Exit codes (per check_all contract):
    0  no findings
    1  findings present
    2  internal error (fail loud)
"""
from __future__ import annotations

import json
import re
import sys

DETERMINISTIC_RULES = {
    "heading-count": ("high", "headings count mismatch"),
    "heading-depth": ("high", "heading depth at position mismatch"),
    "table-row-count": ("high", "table row count mismatch"),
    "table-blocks": ("high", "table block count mismatch"),
    "code-fence-count": ("high", "code fence count mismatch"),
    "code-fence-pos": ("high", "code fence position mismatch"),
    "list-marker": ("high", "list marker missing in RU"),
    "inline-code-count": ("high", "inline code span count mismatch"),
    "inline-code-set": ("high", "inline code set mismatch"),
    "hr-count": ("high", "hr count mismatch"),
    "hr-pos": ("high", "hr position mismatch"),
    "metadata-fingerprint": ("high", "metadata line mismatch"),
    "en-leakage": ("medium", "Cyrillic absence in RU body text"),
}


def _add(finding_list, rule, file, description):
    finding_list.append({
        "rule": rule,
        "severity": DETERMINISTIC_RULES.get(rule, ("high", ""))[0],
        "file": file,
        "description": description,
    })


def _read_lines(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.readlines()


def _strip_nl(line):
    r"""Strip trailing newline(s) but keep the line for comparison."""
    return line.rstrip("\n").rstrip("\r")


def _is_body_line(line):
    s = _strip_nl(line).strip()
    return bool(s) and not _is_structural(line)


def _is_structural(line):
    s = _strip_nl(line).strip()
    if not s:
        return True
    if s.startswith("#"):
        return True
    if re.match(r'^-{3,}\s*$', s):
        return True
    if re.match(r'^\|', s) and '-' in s:
        return True
    if s.startswith('```') or s.startswith('~~~'):
        return True
    if s.startswith('|') and set(s.lstrip()) <= set('|-: '):
        return True
    return False


def _is_meta_line(line, known_keys):
    s = _strip_nl(line).strip()
    for key in known_keys:
        if s.startswith(key):
            return True
    return False


def _check_heading_count(en_lines, ru_lines, findings, en_file, ru_file):
    """Rule 1: heading counts and depth hierarchy at matching positions."""
    def get_headings(lines):
        headings = []
        in_fence = False
        for line in lines:
            s = _strip_nl(line).strip()
            if s.startswith("```") or s.startswith("~~~"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            m = re.match(r'^(#{1,6})\s+', _strip_nl(line))
            if m:
                headings.append((len(m.group(1)), _strip_nl(line)))
        return headings

    en_h = get_headings(en_lines)
    ru_h = get_headings(ru_lines)

    if len(en_h) != len(ru_h):
        _add(findings, "heading-count", ru_file,
             f"headings count: EN={len(en_h)}, RU={len(ru_h)}")
        return

    for i, ((depth_e, _), (depth_r, _)) in enumerate(zip(en_h, ru_h)):
        if depth_e != depth_r:
            _add(findings, "heading-depth", ru_file,
                 f"heading depth at position {i}: EN=#{depth_e}, RU=#{depth_r}")


def _check_table_rows(en_lines, ru_lines, findings, ru_file):
    """Rule 2: table row counts and table block counts."""
    def count_table_lines(lines):
        rows = []
        blocks = []
        in_table = False
        block_start = 0
        for i, line in enumerate(lines):
            s = _strip_nl(line).strip()
            if s.startswith("```") or s.startswith("~~~"):
                if in_table:
                    blocks.append((block_start, i))
                    in_table = False
                continue
            if s.startswith('|') and i + 1 < len(lines):
                next_s = _strip_nl(lines[i + 1]).strip()
                if re.match(r'^\|[\s:-]+$', next_s) or s.count('|') >= 2:
                    if not in_table:
                        block_start = i
                        in_table = True
                    rows.append(i)
                    continue
            if in_table and not s.startswith('|'):
                blocks.append((block_start, i - 1))
                in_table = False

        if in_table:
            blocks.append((block_start, len(lines) - 1))

        return len(rows), len(blocks)

    en_rows, en_blocks = count_table_lines(en_lines)
    ru_rows, ru_blocks = count_table_lines(ru_lines)

    if en_rows != ru_rows:
        _add(findings, "table-row-count", ru_file,
             f"table rows: EN={en_rows}, RU={ru_rows}")
    if en_blocks != ru_blocks:
        _add(findings, "table-blocks", ru_file,
             f"table blocks: EN={en_blocks}, RU={ru_blocks}")


def _check_code_fences(lines, label, findings, ru_file):
    """Rule 3: code fence count and positions."""
    positions = []
    in_fence = False
    for i, line in enumerate(lines):
        s = _strip_nl(line).strip()
        if s.startswith("```") or s.startswith("~~~"):
            if not in_fence:
                positions.append(i)
            in_fence = not in_fence

    return positions


def _check_list_markers(en_lines, ru_lines, findings, ru_file):
    """Rule 4: list markers on same lines."""
    list_re = re.compile(r'^(\s*)([-*+]|\d+\.)\s')

    for i, (en_line, ru_line) in enumerate(zip(en_lines, ru_lines)):
        en_match = list_re.match(en_line)
        ru_match = list_re.match(ru_line)

        if en_match and not ru_match:
            _add(findings, "list-marker", ru_file,
                 f"line {i+1}: EN has list marker, RU does not")


def _check_inline_code(en_lines, ru_lines, findings, ru_file):
    """Rule 5: inline-code span count and identity.
    Extracted per-line, only OUTSIDE code fences (fences are structural
    and must not contribute pseudo-spans from joined text)."""
    inline_re = re.compile(r'`([^`]+)`')

    def collect(lines):
        spans = []
        in_fence = False
        for line in lines:
            s = _strip_nl(line)
            if s.lstrip().startswith('```') or s.lstrip().startswith('~~~'):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            spans.extend(inline_re.findall(s))
        return spans

    en_spans = collect(en_lines)
    ru_spans = collect(ru_lines)
    en_set, ru_set = set(en_spans), set(ru_spans)

    if len(en_spans) != len(ru_spans):
        _add(findings, "inline-code-count", ru_file,
             f"inline code spans: EN={len(en_spans)}, RU={len(ru_spans)}")

    diff_missing = en_set - ru_set
    diff_extra = ru_set - en_set
    if diff_missing or diff_extra:
        parts = []
        if diff_missing:
            parts.append(f"missing EN: {', '.join(sorted(diff_missing)[:5])}")
        if diff_extra:
            parts.append(f"extra RU: {', '.join(sorted(diff_extra)[:5])}")
        _add(findings, "inline-code-set", ru_file,
             f"inline code set mismatch: {'; '.join(parts)}")


def _check_hr(en_lines, ru_lines, findings, ru_file):
    """Rule 6: horizontal rule count and positions."""
    def get_hr_positions(lines):
        positions = []
        in_fence = False
        for i, line in enumerate(lines):
            s = _strip_nl(line).strip()
            if s.startswith("```") or s.startswith("~~~"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            if re.match(r'^-{3,}\s*$', s):
                positions.append(i)
        return positions

    en_pos = get_hr_positions(en_lines)
    ru_pos = get_hr_positions(ru_lines)

    if len(en_pos) != len(ru_pos):
        _add(findings, "hr-count", ru_file,
             f"hr count: EN={len(en_pos)}, RU={len(ru_pos)}")
        return

    for i, (ep, rp) in enumerate(zip(en_pos, ru_pos)):
        if ep != rp:
            _add(findings, "hr-pos", ru_file,
                 f"hr position at {i}: EN line {ep+1}, RU line {rp+1}")


def _check_metadata(en_lines, ru_lines, known_keys, findings, ru_file):
    """Rule 7: metadata fingerprint (EN metadata lines must be identical in RU)."""
    extra_meta_keys = ("has_translation:",)  # translation-specific additions

    all_keys = known_keys + extra_meta_keys

    en_meta_lines = []
    for line in en_lines:
        s = _strip_nl(line).strip()
        if _is_meta_line(line, all_keys):
            en_meta_lines.append(s)

    for meta_line in en_meta_lines:
        found = False
        for line in ru_lines:
            if _strip_nl(line).strip() == meta_line:
                found = True
                break
        if not found:
            _add(findings, "metadata-fingerprint", ru_file,
                 f"metadata missing in RU: {meta_line[:80]}")


def _check_en_leakage(ru_lines, known_keys, findings, ru_file):
    """Rule 8: EN-leakage — body lines in RU with no Cyrillic characters.
    Lines inside code fences are structural content and are exempt."""
    has_cyrillic = re.compile(r'[\u0400-\u04FF\u0500-\u052F]')
    in_fence = False

    for i, line in enumerate(ru_lines):
        s = _strip_nl(line).strip()
        if s.startswith('```') or s.startswith('~~~'):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not s:
            continue
        if _is_structural(line):
            continue
        if _is_meta_line(line, known_keys):
            continue
        if not has_cyrillic.search(s):
            # Check: line might contain only inline-code, URL, numbers
            # If it has any Latin text that isn't inline-code/URL/number → finding
            has_text = bool(re.search(r'[A-Za-z]{2,}', s))
            has_inline_code = '`' in s
            has_url = bool(re.search(r'https?://', s))
            if has_text and not has_inline_code and not has_url:
                _add(findings, "en-leakage", ru_file,
                     f"line {i+1} has no Cyrillic: {s[:80]}")


def check_drift(en_path, ru_path, known_keys, json_output=False):
    """Run all drift checks. Returns (findings_list, coverage_dict)."""
    try:
        en_lines = _read_lines(en_path)
        ru_lines = _read_lines(ru_path)
    except OSError as e:
        print(f"ERROR: could not read files: {e}", file=sys.stderr)
        return None, None

    findings = []
    en_file = en_path
    ru_file = ru_path

    _check_heading_count(en_lines, ru_lines, findings, en_file, ru_file)
    _check_table_rows(en_lines, ru_lines, findings, ru_file)
    _check_list_markers(en_lines, ru_lines, findings, ru_file)
    _check_inline_code(en_lines, ru_lines, findings, ru_file)
    _check_hr(en_lines, ru_lines, findings, ru_file)
    _check_metadata(en_lines, ru_lines, known_keys, findings, ru_file)
    _check_en_leakage(ru_lines, known_keys, findings, ru_file)

    # Code fences: check both count and position
    en_fences = _check_code_fences(en_lines, "en", findings, ru_file)
    ru_fences = _check_code_fences(ru_lines, "ru", findings, ru_file)
    if len(en_fences) != len(ru_fences):
        _add(findings, "code-fence-count", ru_file,
             f"code fences: EN={len(en_fences)}, RU={len(ru_fences)}")
    else:
        for i, (ep, rp) in enumerate(zip(en_fences, ru_fences)):
            if ep != rp:
                _add(findings, "code-fence-pos", ru_file,
                     f"code fence position at {i}: EN line {ep+1}, RU line {rp+1}")

    coverage = {
        "deterministic": [
            "heading-count", "heading-depth",
            "table-row-count", "table-blocks",
            "code-fence-count", "code-fence-pos",
            "list-marker",
            "inline-code-count", "inline-code-set",
            "hr-count", "hr-pos",
            "metadata-fingerprint",
            "en-leakage",
        ],
        "ai_reserved": [
            "line-parity(Phase4)",
            "glossary",
            "abstraction",
        ],
    }

    return findings, coverage


def print_results(findings, coverage, json_output):
    """Print findings in human-readable or JSON format."""
    if json_output:
        for f in findings:
            print(json.dumps(f, ensure_ascii=False))
    else:
        if findings:
            for f in findings:
                print(f"rule={f['rule']} severity={f['severity']} "
                      f"file={f['file']} {f['description']}")

        print()
        det = ", ".join(coverage["deterministic"])
        ai = ", ".join(coverage["ai_reserved"])
        print(f"coverage: deterministic=({det})")
        print(f"coverage: ai_reserved=({ai})")


def main():
    args = sys.argv[1:]

    if "--json" in args:
        args.remove("--json")
        json_output = True
    else:
        json_output = False

    if args and args[0] == "--files":
        args = args[1:]

    if len(args) != 2:
        print(f"Usage: {sys.argv[0]} <en_path> <ru_path> [--json]", file=sys.stderr)
        sys.exit(2)

    en_path, ru_path = args

    # Import KNOWN_KEYS from docmeta (with fallback for testing)
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from docmeta import KNOWN_KEYS
    except ImportError:
        # Fallback: known metadata keys (must stay in sync)
        KNOWN_KEYS = ("id", "Version", "Status", "Abstraction", "changelog-path",
                      "title", "has_translation", "references",
                      "allow_non_index_paths", "Last Modified")

    findings, coverage = check_drift(en_path, ru_path, KNOWN_KEYS, json_output)

    if findings is None:
        print("ERROR: internal error during drift check", file=sys.stderr)
        sys.exit(2)

    print_results(findings, coverage, json_output)

    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    import os
    main()
