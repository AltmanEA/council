#!/usr/bin/env python3
"""check_drift.py — Deterministic EN↔RU structural comparison tool.

Usage:
    python3 tools/check_drift.py <en_path> <ru_path> [--json]
    python3 tools/check_drift.py --files docs/en/scenario/index.md docs/ru/scenario/index-RU.md
    python3 tools/check_drift.py --phase4 <en_path> <ru_path> --report <run_report.json>
        [--glossary <glossary.md>] [--json]

Exit codes (per check_all contract):
    0  no findings
    1  findings present
    2  internal error (fail loud)
"""
from __future__ import annotations

import json
import os
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
    if not s: return True
    if s.startswith("#"): return True
    if re.match(r'^-{3,}\s*$', s): return True
    if re.match(r'^\|', s) and '-' in s: return True
    if s.startswith('```') or s.startswith('~~~'): return True
    if s.startswith('|') and set(s.lstrip()) <= set('|-: '): return True
    return False


def _is_structural_strict(line):
    """Strict phase4 parity: only blank/heading/hr/fence/TABLE-SEP are structural.
    Table body rows with prose or hyphens in text are NOT structural."""
    s = _strip_nl(line).strip()
    if not s: return True
    if s.startswith("#"): return True
    if re.match(r'^-{3,}\s*$', s): return True
    if s.startswith('```') or s.startswith('~~~'): return True
    if s.startswith('|') and set(s.lstrip()) <= set('|-: '): return True
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


def _collect_body_lines(lines, known_keys):
    """Return body line indices (0-based) for lines that are body content.

    Body = non-blank, non-structural, non-metadata, outside code fences.
    """
    in_fence = False
    body_indices = []
    for i, line in enumerate(lines):
        s = _strip_nl(line).strip()
        if s.startswith("```") or s.startswith("~~~"):
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
        body_indices.append(i)
    return body_indices


def _check_phase4_fail(report_path, ru_file):
    """Gate: phase4-fail — report JSON fail field must be 0."""
    if not os.path.isfile(report_path):
        print(f"ERROR: report file not found: {report_path}", file=sys.stderr)
        return 2, None
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)
    except (json.JSONDecodeError, OSError):
        print(f"ERROR: could not parse report: {report_path}", file=sys.stderr)
        return 2, None

    if not isinstance(report, dict) or "fail" not in report:
        print("ERROR: report missing 'fail' field", file=sys.stderr)
        return 2, None

    fail = report["fail"]
    if not isinstance(fail, int) or isinstance(fail, bool):
        print("ERROR: report 'fail' field must be integer", file=sys.stderr)
        return 2, None

    findings = []
    if fail > 0:
        _add(findings, "phase4-fail", ru_file,
             f"fail={fail} (expected 0)")
    return 0, findings


def _check_phase4_parity(en_lines, ru_lines, ru_file):
    """Gate: phase4-parity — 1:1 line parity between EN and RU."""
    findings = []
    if len(en_lines) != len(ru_lines):
        _add(findings, "phase4-parity", ru_file,
             f"line count: EN={len(en_lines)}, RU={len(ru_lines)}")
        # STOP: no positional checks when lengths differ
        return None, findings  # None = stop flag

    # Equal lengths: check structural divergence (strict)
    structural_mismatches = []
    for i, (en_line, ru_line) in enumerate(zip(en_lines, ru_lines)):
        en_struct = _is_structural_strict(en_line)
        ru_struct = _is_structural_strict(ru_line)
        if en_struct != ru_struct:
            structural_mismatches.append(i + 1)  # 1-based

    if structural_mismatches:
        lines_str = ", ".join(str(n) for n in structural_mismatches[:5])
        _add(findings, "phase4-parity", ru_file,
             f"structural divergence at lines: {lines_str}")

    return 0, findings  # 0 = continue


def _check_phase4_identity(en_lines, ru_lines, known_keys, ru_file):
    """Gate: phase4-identity — all body lines identical → EN copy detection."""
    findings = []

    en_body = _collect_body_lines(en_lines, known_keys)
    ru_body = _collect_body_lines(ru_lines, known_keys)

    if not en_body:
        return findings  # zero body → no finding

    if len(en_body) != len(ru_body):
        return findings  # different count → can't compare positionally

    # Compare body lines positionally
    en_body_texts = [en_lines[i].strip() for i in en_body]
    ru_body_texts = [ru_lines[i].strip() for i in ru_body]

    all_identical = all(e == r for e, r in zip(en_body_texts, ru_body_texts))
    any_differ = any(e != r for e, r in zip(en_body_texts, ru_body_texts))

    if all_identical and not any_differ:
        _add(findings, "phase4-identity", ru_file,
             "candidate is an EN copy")
    # Partial identity → NO finding

    return findings


def _check_phase4_glossary(en_lines, ru_lines, known_keys,
                           glossary_path, ru_file):
    """Gate: phase4-glossary — EN-body terms must have RU equivalents (stem-prefix)."""
    findings = []

    if not os.path.isfile(glossary_path):
        return findings  # no glossary → nothing to check

    glossary_re = re.compile(r'^\*\*([^*]+)\*\*\s*\(([^)]+)\)')
    terms = {}
    try:
        with open(glossary_path, "r", encoding="utf-8") as f:
            for line in f:
                m = glossary_re.match(line.strip())
                if m: terms[m.group(1).strip()] = m.group(2).strip()
    except OSError:
        return findings

    en_body_idx = _collect_body_lines(en_lines, known_keys)
    ru_body_idx = _collect_body_lines(ru_lines, known_keys)
    _ic = lambda s: re.sub(r'`[^`]+`', '', s)  # strip inline code
    en_body_text = " ".join(_ic(en_lines[i].strip()) for i in en_body_idx).lower()
    ru_body_text = " ".join(_ic(ru_lines[i].strip()) for i in ru_body_idx).lower()

    missing = []
    for term, ru_equiv in terms.items():
        word_re = re.compile(r'(?:^|\s)' + re.escape(term) + r'(?:$|\s|[^\w-])', re.IGNORECASE)
        if not word_re.search(en_body_text):
            continue
        all_match = True
        for ru_word in ru_equiv.split():
            stem = ru_word.lower()[:min(4, len(ru_word) - 1)]
            if not re.search(r'\b' + re.escape(stem), ru_body_text):
                all_match = False
                break
        if not all_match:
            missing.append(term)

    if missing:
        _add(findings, "phase4-glossary", ru_file,
             f"glossary terms untranslated: {', '.join(missing[:5])}")
    return findings


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


def print_results_phase4(findings, gate_rules, json_output):
    """Print findings in human-readable or JSON format for phase4 mode."""
    if json_output:
        for f in findings:
            print(json.dumps(f, ensure_ascii=False))
    else:
        if findings:
            for f in findings:
                print(f"rule={f['rule']} severity={f['severity']} "
                      f"file={f['file']} {f['description']}")

        print()
        print(f"coverage: deterministic=({', '.join(gate_rules)})")


def _run_phase4(en_path, ru_path, report_path, glossary_path, json_output):
    """Run the four phase4 gate rules."""
    # Import KNOWN_KEYS (same as drift mode)
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from docmeta import KNOWN_KEYS
    except ImportError:
        KNOWN_KEYS = ("id", "Version", "Status", "Abstraction", "changelog-path",
                      "title", "has_translation", "references",
                      "allow_non_index_paths", "Last Modified")

    try:
        en_lines = _read_lines(en_path)
        ru_lines = _read_lines(ru_path)
    except OSError as e:
        print(f"ERROR: could not read files: {e}", file=sys.stderr)
        return 2, None

    findings = []
    ru_file = ru_path

    # Gate 1: phase4-fail
    err, gate_findings = _check_phase4_fail(report_path, ru_file)
    if err == 2:
        return 2, None
    findings.extend(gate_findings)

    # Gate 2: phase4-parity
    stop, gate_findings = _check_phase4_parity(en_lines, ru_lines, ru_file)
    if stop is None:
        # Length mismatch → STOP further checks (no identity/glossary)
        findings.extend(gate_findings)
        print_results_phase4(findings, ["phase4-fail", "phase4-parity"], json_output)
        return 1 if findings else 0, findings
    findings.extend(gate_findings)

    # Gate 3: phase4-identity
    findings.extend(_check_phase4_identity(en_lines, ru_lines, KNOWN_KEYS, ru_file))

    # Gate 4: phase4-glossary
    findings.extend(_check_phase4_glossary(en_lines, ru_lines, KNOWN_KEYS, glossary_path, ru_file))

    gate_rules = ["phase4-fail", "phase4-parity", "phase4-identity", "phase4-glossary"]
    print_results_phase4(findings, gate_rules, json_output)
    return 1 if findings else 0, findings


def main():
    args = sys.argv[1:]

    if args and args[0] == "--phase4":
        # Phase 4 mode
        args = args[1:]

        phase4_json_output = "--json" in args
        if phase4_json_output:
            args.remove("--json")

        report_path = None
        glossary_path = None

        i = 0
        while i < len(args):
            if args[i] == "--report" and i + 1 < len(args):
                report_path = args.pop(i + 1)
                args.pop(i)
            elif args[i] == "--glossary" and i + 1 < len(args):
                glossary_path = args.pop(i + 1)
                args.pop(i)
            else:
                i += 1

        if len(args) != 2:
            print("Usage: check_drift.py --phase4 <en_path> <ru_path> "
                  "--report <report.json> [--glossary <glossary.md>] [--json]",
                  file=sys.stderr)
            sys.exit(2)

        en_path, ru_path = args

        if report_path is None:
            print("ERROR: --report is required in --phase4 mode", file=sys.stderr)
            sys.exit(2)

        tools_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.dirname(tools_dir)
        if not glossary_path:
            glossary_path = os.path.join(repo_root, "docs", "en", "glossary", "index.md")

        exit_code, _ = _run_phase4(en_path, ru_path, report_path, glossary_path,
                                   phase4_json_output)
        sys.exit(exit_code)

    # Existing drift mode (unchanged)
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
    main()
