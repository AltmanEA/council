#!/usr/bin/env python3
"""Version-bump classifier (Stage C, plan sess-doc-reliability-algo).

Model: "AI proposes, algorithm records". This tool only PROPOSES a bump kind
for a candidate document; it never writes document content, changelogs, or the
manifest. Pipeline: the Documentation Worker skill prepares a candidate (the
FULL new text of the document, frontmatter included) -> classify_bump.py
classifies the disk->candidate diff -> operator Approves -> the skill calls
bump_version.py --kind <approved> --note <verbatim>. The only file this tool
ever writes is its own JSONL decision log under tools/state/ (suppressed with
--no-log; never written in --report mode).

Classifier per consensus sess-doc-reliability-algo (SUBJ-003): first rule
match wins, top-down: major (external-heading-removed / required-key-removed /
abstraction-changed) -> patch (token-overlap-patch) -> minor
(structural-minor) -> ambiguous-default-minor. Ambiguous defaults to minor
with an explicit warning citing documentation-rules §7.5 ("never silent patch").
Escalated outcomes (major or ambiguous) are printed in the documentation-rules §6
format (options + recommendation). The --report gate enforces the HCD metric:
escalation rate > ESCALATION_RATE_MAX => "classifier requires redesign".

The §-reference resolver is REUSED from check_all._Corpus as-is (never
forked); document paths are resolved ONLY via gen_manifest.build_entries
(no blind filesystem scans). stdlib + PyYAML (via docmeta) only, Python 3.11+.

CLI:
    python3 tools/classify_bump.py --id <doc-id> --candidate <file|->
        [--root DIR] [--json] [--log <path>] [--no-log]
    python3 tools/classify_bump.py --report [--root DIR] [--json] [--log <path>]

Exit codes (also printed by --help):
    0  classification succeeded, identical candidate, or --report within gate
    2  usage/refusal: unknown id (not in build_entries), unreadable candidate,
       candidate fails docmeta.parse_header (identical is checked first), or a
       corpus read error
    3  only --report: escalation rate exceeds ESCALATION_RATE_MAX
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_all  # noqa: E402
import docmeta  # noqa: E402
import gen_manifest  # noqa: E402
import tests_helpers  # noqa: E402
from docmeta import DocMetaError  # noqa: E402

__all__ = ["ClassifyError", "classify", "report", "main"]

_HELP = ("Read-only diff->bump classifier: proposes patch|minor|major for a "
         "full candidate document (never writes, logs decisions only). "
         "Exit codes: 0 = classification/identical/report-within-gate; "
         "2 = usage/refusal; 3 = --report escalation-rate gate exceeded.")

#: Minimum token-overlap ratio for a replace-pair to count as patch-clean.
TOKEN_OVERLAP_MIN = 0.85

#: Maximum acceptable escalation rate before the classifier itself is
#: declared wrong (HCD metric, adopted). Reference:
#: sessions/sess-doc-reliability-algo/consensus-doc.md (HCD metric, adopted).
ESCALATION_RATE_MAX = 0.20

#: Decision log, relative to the repository root.
LOG_REL = os.path.join("tools", "state", "classify_log.jsonl")

#: Markdown line markers that disqualify a replace-pair from patch purity
#: (a touched marker line means list/quote/table semantics moved, not prose).
_MARKER_PREFIXES = ("- ", "* ", "+ ", "> ", "|")

_ABSTRACTION_LINE_RE = re.compile(r"^Abstraction:[ \t]*(.*?)[ \t]*$")
_META_KEY_LINE_RES = {
    key: re.compile(r"(?m)^" + re.escape(key) + r":[ \t]*\S")
    for key in docmeta.REQUIRED_KEYS
}


class ClassifyError(Exception):
    """Fatal refusal: usage, unknown id, unreadable input, or corpus error."""


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_text(path: str) -> str:
    """Read a file preserving line endings verbatim (universal newlines off)."""
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _split_sections(text: str) -> list:
    """Split ``text`` into sections: list of (heading_text|None, [lines]).

    Sections start at ATX heading lines (tests_helpers.ATX_RE), skipping
    fenced code blocks the same way tests_helpers.heading_texts does; the
    leading preamble before the first heading is the (None, [...]) section.
    """
    lines = text.splitlines()
    sections = [(None, [])]
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            sections[-1][1].append(line)
            continue
        m = None if in_fence else tests_helpers.ATX_RE.match(line)
        if m:
            sections.append((m.group(2).strip(), []))
        else:
            sections[-1][1].append(line)
    return sections


def _heading_and_bold_texts_of(text: str) -> list:
    """ATX headings + bold pseudo-headings for an in-memory text, built with
    the same primitives check_all._Corpus.heading_and_bold_texts uses (its
    resolver logic is reused as-is; only the source is in-memory here)."""
    lines = text.splitlines()
    texts = tests_helpers.heading_texts(lines)
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for bm in check_all._BOLD_LEAD_RE.finditer(line):
            label = bm.group(1).strip()
            if label:
                texts.append(label)
    return texts


def _heading_key(corpus: check_all._Corpus, heading: str) -> str:
    """Normalization key identical to the corpus heading index key form
    (check_all._Corpus._ensure_corpus_indexes): joined _hit_tokens."""
    return " ".join(corpus._hit_tokens(heading.strip().strip("*_`")))


def _pair_ratio(a: str, b: str) -> float:
    """Token-overlap ratio between two lines (tokens = line.split())."""
    return difflib.SequenceMatcher(None, a.split(), b.split()).ratio()


def _external_section_refs(corpus: check_all._Corpus, target_rel: str,
                           heading_texts: list) -> list:
    """External §-references resolving to ``target_rel``: tuples
    (source_rel, line_number, section_name).

    Reuses the check_all._Corpus resolver as-is: visible lines from
    check_all._visible_lines, name extraction via Corpus._section_name, hit
    testing via Corpus._name_hit against the target's heading/bold texts.
    Only lines from OTHER docs/en files (rel != target_rel) are considered.
    """
    refs = []
    for rel in corpus.docs:
        if rel == target_rel:
            continue
        for idx, line in check_all._visible_lines(corpus.lines[rel]):
            if "§" not in line:
                continue
            for m in check_all._SECTION_REF_RE.finditer(line):
                name = corpus._section_name(line[m.end():])
                if name is None:
                    continue
                if corpus._name_hit(name, heading_texts):
                    refs.append((rel, idx + 1, name))
    return refs


def _is_touched_by_patch_rule(line: str) -> bool:
    """True when ``line`` disqualifies a replace-pair from patch purity:
    ATX heading, fence delimiter, or markdown marker line. Frontmatter
    membership is positional and checked by the caller."""
    stripped = line.strip()
    if tests_helpers.ATX_RE.match(line):
        return True
    if stripped.startswith("```") or stripped.startswith("~~~"):
        return True
    return bool(re.match(r"^\s*(?:[-*+]\s|>\s|\|)", line))


def _meta_key_present(text: str, key: str) -> bool:
    """True when a `Key: value` line occurs inside the canonical metadata
    block span of ``text`` (geometry from tests_helpers.meta_block_span)."""
    lines = text.splitlines()
    start, end = tests_helpers.meta_block_span(lines)
    return any(_META_KEY_LINE_RES[key].match(ln) for ln in lines[start:end])


def _abstraction_value(text: str):
    """Value of the `Abstraction:` line inside the metadata block, or None
    when the key line is absent."""
    lines = text.splitlines()
    start, end = tests_helpers.meta_block_span(lines)
    for ln in lines[start:end]:
        m = _ABSTRACTION_LINE_RE.match(ln)
        if m:
            return m.group(1)
    return None


def _frontmatter_major_rules(disk_text: str, candidate_text: str) -> list:
    """Major rules b/c evaluated on frontmatter lines BEFORE strict parsing
    of the candidate (a removed required key would otherwise surface as an
    unparsable-candidate refusal instead of a major verdict)."""
    rules = []
    for key in docmeta.REQUIRED_KEYS:
        if _meta_key_present(disk_text, key) and not _meta_key_present(candidate_text, key):
            rules.append("required-key-removed")
            break
    disk_abstraction = _abstraction_value(disk_text)
    cand_abstraction = _abstraction_value(candidate_text)
    if (disk_abstraction is not None and cand_abstraction is not None
            and disk_abstraction != cand_abstraction):
        rules.append("abstraction-changed")
    return rules


def _major_heading_removal(corpus, target_rel: str, disk_text: str,
                           candidate_text: str) -> list:
    """Major rule a: a disk heading/bold pseudo-heading removed (or renamed
    away) in the candidate that carries an external §-reference from another
    corpus document. Returns the removed headings that are referenced."""
    disk_headings = corpus.heading_and_bold_texts(target_rel)
    refs = _external_section_refs(corpus, target_rel, disk_headings)
    if not refs:
        return []
    cand_keys = {_heading_key(corpus, h) for h in _heading_and_bold_texts_of(candidate_text)}
    hit = []
    for h in disk_headings:
        if _heading_key(corpus, h) in cand_keys:
            continue
        if any(corpus._name_hit(name, [h]) for _, _, name in refs):
            hit.append(h)
    return hit


def _classify_verdict(opcodes, disk_text: str, candidate_text: str) -> tuple:
    """Apply rules 2-4 (patch / minor / ambiguous) to nonzero opcodes.

    First rule match wins: pure replace-pair diff that is patch-clean ->
    token-overlap-patch; insert/delete opcodes with only patch-clean
    replaces -> structural-minor; any dirty replace-pair (low ratio, unequal
    replace block, heading/fence/marker/frontmatter line) -> the diff is not
    confidently classifiable -> ambiguous default minor.

    Returns (verdict, rules_triggered, ambiguous, warnings).
    """
    nonzero = [op for op in opcodes if op[0] != "equal"]
    if not nonzero:
        return "none", [], False, []
    has_insdel = any(op[0] in ("insert", "delete") for op in nonzero)
    old_lines = disk_text.splitlines()
    new_lines = candidate_text.splitlines()
    disk_span = tests_helpers.meta_block_span(old_lines)
    cand_span = tests_helpers.meta_block_span(new_lines)
    patch_clean = True
    for tag, i1, i2, j1, j2 in nonzero:
        if tag != "replace":
            continue
        a_lines = old_lines[i1:i2]
        b_lines = new_lines[j1:j2]
        if len(a_lines) != len(b_lines):
            patch_clean = False
            break
        for k, (a, b) in enumerate(zip(a_lines, b_lines)):
            if _pair_ratio(a, b) < TOKEN_OVERLAP_MIN:
                patch_clean = False
                break
            if (tests_helpers.ATX_RE.match(a) or tests_helpers.ATX_RE.match(b)
                    or _is_touched_by_patch_rule(a) or _is_touched_by_patch_rule(b)
                    or disk_span[0] <= i1 + k < disk_span[1]
                    or cand_span[0] <= j1 + k < cand_span[1]):
                patch_clean = False
                break
        if not patch_clean:
            break
    if patch_clean and not has_insdel:
        return "patch", ["token-overlap-patch"], False, []
    if patch_clean and has_insdel:
        return "minor", ["structural-minor"], False, []
    warning = ("ambiguous diff: defaulting to minor per documentation-rules §7.5 "
               "(never silent patch) — operator must confirm the kind")
    return "minor", ["ambiguous-default-minor"], True, [warning]


def _escalation_block(ambiguous: bool) -> dict:
    """Deterministic §6-format escalation payload for escalated outcomes."""
    if ambiguous:
        return {
            "options": [
                "option 1: minor — safe default per consensus (never silent patch)",
                "option 2: review the diff manually and select patch or major explicitly",
            ],
            "recommendation": "minor (per consensus default), operator confirms",
        }
    return {
        "options": [
            "option 1: major — external section references break, "
            "headings must be re-anchored",
            "option 2: keep heading names, apply changes as minor",
        ],
        "recommendation": "major",
    }


def classify(root: str, doc_id: str, candidate_text: str) -> dict:
    """Classify the disk->candidate diff for ``doc_id``; pure, no writes.

    Returns the result dict {id, verdict, ambiguous, escalated,
    rules_triggered, warnings, escalation}. Raises ClassifyError (mapped to
    exit 2 by main) on unknown id, corpus errors, or an unparsable candidate
    (the identical case is detected before candidate frontmatter validation).
    """
    entries, errors = gen_manifest.build_entries(root)
    if errors:
        raise ClassifyError("manifest build errors: " + "; ".join(errors))
    entry = next((e for e in entries if e["id"] == doc_id), None)
    if entry is None:
        raise ClassifyError(f"unknown document id: {doc_id!r} (not in manifest entries)")
    doc_rel = entry["path"]
    doc_abs = os.path.join(root, *doc_rel.split("/"))
    try:
        disk_text = _read_text(doc_abs)
    except OSError as exc:
        raise ClassifyError(f"cannot read manifest path {doc_rel!r}: {exc}") from exc

    old_lines = disk_text.splitlines(keepends=True)
    new_lines = candidate_text.splitlines(keepends=True)
    opcodes = difflib.SequenceMatcher(None, old_lines, new_lines).get_opcodes()
    if all(op[0] == "equal" for op in opcodes):
        return {"id": doc_id, "verdict": "none", "ambiguous": False,
                "escalated": False, "rules_triggered": [], "warnings": [],
                "escalation": None}
    # Structural sanity BEFORE classification: without an H1 the metadata
    # geometry is undefined, so positional frontmatter rules are unreliable.
    if not any(ln.startswith("# ") for ln in new_lines):
        raise ClassifyError(f"{doc_rel}: candidate has no H1 heading (`# ` title line)")

    try:
        corpus = check_all._Corpus(root)
    except OSError as exc:
        raise ClassifyError(f"corpus read error under {root!r}: {exc}") from exc
    except FileNotFoundError as exc:
        raise ClassifyError(str(exc)) from exc

    rules = []
    major_headings = _major_heading_removal(corpus, doc_rel, disk_text, candidate_text)
    if major_headings:
        rules.append("external-heading-removed")
    rules.extend(_frontmatter_major_rules(disk_text, candidate_text))

    if not rules:
        # Candidate frontmatter must still be a valid parse (defensive check;
        # removed required keys are already covered by major above).
        try:
            docmeta.parse_header(candidate_text, filename=doc_rel)
        except DocMetaError as exc:
            raise ClassifyError(f"{exc.filename}: {exc.reason}") from exc
        verdict, sub_rules, ambiguous, warnings = _classify_verdict(
            opcodes, disk_text, candidate_text)
        rules = sub_rules
    else:
        verdict, ambiguous = "major", False
        warnings = [
            "removed section heading(s) referenced externally: "
            + ", ".join(repr(h) for h in major_headings)
        ] if major_headings else []
        ambiguous = False

    escalated = verdict != "none" and (ambiguous or verdict == "major")
    escalation = _escalation_block(ambiguous) if escalated else None
    return {"id": doc_id, "verdict": verdict, "ambiguous": ambiguous,
            "escalated": escalated, "rules_triggered": rules,
            "warnings": warnings, "escalation": escalation}


def _append_log(log_path: str, result: dict) -> None:
    """Append one JSONL decision line (ISO UTC seconds); no other writes."""
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "id": result["id"],
        "verdict": result["verdict"],
        "ambiguous": result["ambiguous"],
        "escalated": result["escalated"],
        "rules_triggered": result["rules_triggered"],
    }
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def report(log_path: str, json_mode: bool = False) -> int:
    """Escalation-rate gate over the JSONL decision log.

    Reads the log (missing file = empty), ignores malformed lines with a
    stderr warning. Exit 0 within the gate, 3 when the escalation rate
    exceeds ESCALATION_RATE_MAX (HCD metric, adopted; see
    sessions/sess-doc-reliability-algo/consensus-doc.md).
    """
    total = escalated = 0
    if os.path.exists(log_path):
        with open(log_path, encoding="utf-8") as fh:
            for n, raw in enumerate(fh, 1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                    flag = bool(rec["escalated"])
                    total += 1
                    escalated += 1 if flag else 0
                except (ValueError, KeyError, TypeError):
                    print(f"WARNING: {log_path}:{n}: malformed log line ignored",
                          file=sys.stderr)
    rate = (escalated / total) if total else 0.0
    requires = rate > ESCALATION_RATE_MAX
    if json_mode:
        print(json.dumps({"total": total, "escalated": escalated,
                          "escalation_rate": rate, "requires_redesign": requires},
                         sort_keys=True))
    else:
        print(f"total: {total}")
        print(f"escalated: {escalated}")
        print(f"rate: {rate * 100:.1f}%")
        if requires:
            print(f"classifier requires redesign (escalation rate "
                  f"{rate * 100:.1f}% > {ESCALATION_RATE_MAX * 100:.0f}%)")
    return 3 if requires else 0


def _print_human(result: dict) -> None:
    """Deterministic human-readable classification output."""
    print(f"id: {result['id']}")
    print(f"verdict: {result['verdict']}"
          + (" (ambiguous)" if result["ambiguous"] else ""))
    print("rules_triggered: " + (", ".join(result["rules_triggered"]) or "none"))
    for w in result["warnings"]:
        print(f"warning: {w}")
    if result["escalation"] is not None:
        print("ESCALATION (documentation-rules §6 format):")
        for option in result["escalation"]["options"]:
            print(f"  {option}")
        print(f"  recommendation: {result['escalation']['recommendation']}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="classify_bump.py", description=_HELP)
    parser.add_argument("--id", help="manifest document id (resolved via "
                                     "gen_manifest.build_entries)")
    parser.add_argument("--candidate",
                        help="path to the FULL candidate document text, or - "
                             "for stdin (required unless --report)")
    parser.add_argument("--root", default=_repo_root(),
                        help="repository root (default: parent of tools/)")
    parser.add_argument("--json", action="store_true", dest="json_mode",
                        help="emit exactly one JSON object on stdout "
                             "(fixed keys; no timestamp)")
    parser.add_argument("--log", default=None,
                        help="JSONL decision log path (default: "
                             "<root>/tools/state/classify_log.jsonl)")
    parser.add_argument("--no-log", action="store_true", dest="no_log",
                        help="suppress the JSONL decision log entry")
    parser.add_argument("--report", action="store_true",
                        help="gate mode: summarize the log, exit 3 when the "
                             "escalation rate exceeds the HCD threshold")
    args = parser.parse_args(argv)

    log_path = args.log or os.path.join(args.root, *LOG_REL.split(os.sep))

    if args.report:
        return report(log_path, json_mode=args.json_mode)

    if not args.id or not args.candidate:
        print("ERROR: --id and --candidate are required (except --report mode)",
              file=sys.stderr)
        return 2
    if args.candidate == "-":
        candidate_text = sys.stdin.read()
    else:
        try:
            candidate_text = _read_text(args.candidate)
        except OSError as exc:
            print(f"ERROR: cannot read candidate {args.candidate!r}: {exc}",
                  file=sys.stderr)
            return 2

    try:
        result = classify(args.root, args.id, candidate_text)
    except ClassifyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if result["verdict"] != "none" and not args.no_log:
        _append_log(log_path, result)

    if args.json_mode:
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    else:
        _print_human(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
