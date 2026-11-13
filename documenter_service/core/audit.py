"""audit() / delegate(preview) cores — read-only, over tools/check_all.scan.

Rule coverage: this module executes `tools/check_all.scan(root)` and, through
it, `tools/docmeta.validate` AS-IS (AGENTS.md §8, mvp-interfaces §Compliance
rules scanned). Deterministic rules 1, 2, 4, 6 plus naming/schema are covered;
rules 3 (glossary terms) and 5 (abstraction consistency) are skill/AI-reserved
and are NOT implemented here in any form. No finding-rule name is invented:
every rule name a Finding carries comes from check_all.RULE_GROUPS (its
dispatch's declared name sets).

Severity mapping at the audit() boundary (mvp-interfaces §1 legacy mappings:
info→low, warning→medium, error→high): the internal tools layer emits
warning|low|medium|high, so `warning` is promoted to `medium` on output and
`low` stays `low`. `critical` has NO producer in the MVP (the enum keeps it;
read-only diagnostics cannot establish data-integrity compromise semantics).

Pagination: `rescan_batch_ceiling` documents per invocation. The compliance
scan itself is corpus-wide (rules 4 and 6 cannot run per-document), so the
ceiling pages the REPORT: document findings are delivered in scope batches;
scanned_ids and findings accumulate in the registry per batch so a resumed
scan reports honest cumulative coverage. A partial batch issues a single-use
scan_cursor token bound to (audit_id, target_id). Corpus-level findings
(the manifest file itself, orphan files) are not tied to one document and
report on the first pass — pagination cannot hide manifest drift.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

_TOOLS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))),
    "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import check_all  # noqa: E402
import tests_helpers  # noqa: E402

from ..adapters.diff_engine import MAX_DIFF_BYTES_DEFAULT, decode_diff_input  # noqa: E402
from ..adapters.jsonl_registry import new_token  # noqa: E402
from . import registry as reg  # noqa: E402
from .errors import StructuredError  # noqa: E402
from .trust import check_invariant  # noqa: E402

__all__ = ["audit", "delegate_preview", "pre_audit_gate", "SEVERITY_MAP",
           "AUDIT_RULE_NAMES", "PARTIAL_WRITE_DECISION_NOTE",
           "DESCRIPTION_MAX_LEN"]

#: audit() severity enum (mvp-interfaces §1).
SEVERITY_ENUM = ("low", "medium", "high", "critical")

#: Legacy severity mapping at the audit() boundary.
SEVERITY_MAP = {"info": "low", "warning": "medium", "error": "high",
                "low": "low", "medium": "medium", "high": "high"}

#: description bound (mvp-interfaces §1).
DESCRIPTION_MAX_LEN = 500

#: Mandatory statement when coverage.status == partial (mvp-interfaces §1
#: Coverage rule). `has_remaining` alone is insufficient.
PARTIAL_WRITE_DECISION_NOTE = (
    "PARTIAL SCAN: this report does not cover the full scope; a write "
    "decision cannot be made on this report — re-invoke audit() with the "
    "returned scan_cursor until coverage.status is complete.")

#: Complete-scan report header (also the standing rule-coverage non-claim).
COMPLETE_REPORT_HEADER = (
    "Coverage: deterministic rules 1, 2, 4, 6 + naming/schema via "
    "tools/check_all.scan. Rules 3 (glossary terms) and 5 (abstraction "
    "consistency) are skill/AI-reserved and NOT checked here.")

#: suggested_action by finding rule name; fallback is the generic action.
_SUGGESTED_ACTIONS = {
    "line-count": "split or condense the document (AGENTS.md §7.3)",
    "changelog-path-missing": "create or repoint the changelog file under CHANGELOGS/",
    "changelog-path-location": "repoint changelog-path under CHANGELOGS/",
    "manifest-drift": "regenerate docs-manifest.yaml via tools/gen_manifest.py --write",
    "parity-skipped": "fix frontmatter parse errors, then regenerate the manifest",
    "orphan": "add the file to the manifest or cover it via allow_non_index_paths",
    "naming": "rename to kebab-case / restore the index.md convention (AGENTS.md §7.1)",
    "missing-reference": "fix the referenced path or create the file",
    "broken-anchor": "retarget the anchor to an existing heading slug",
    "unresolved-reference": "retarget the reference to an existing heading or file",
    "ambiguous-section-reference": "disambiguate the section reference with a bound file",
    "frontmatter": "fix the document header (docmeta REQUIRED_KEYS)",
    "required-field": "add the missing required frontmatter key",
    "version-format": "fix Version to match (X|X.Y|X.Y.Z)(-draft)?",
    "last-modified-deprecated": "remove the deprecated Last Modified key",
    "unknown-key": "remove or rename the unrecognized frontmatter key",
    "references-non-index": "set allow_non_index_paths or move the reference (AGENTS.md §2.1)",
}
_GENERIC_ACTION = "resolve the finding per AGENTS.md documentation rules"


def audit_rule_names() -> frozenset:
    """Every finding-rule name the tools layer can actually produce.

    Derived from check_all.RULE_GROUPS (the dispatch's declared name sets) —
    the single source, never a hand-copied list.
    """
    names = set()
    for group_names in check_all.RULE_GROUPS.values():
        names |= group_names
    return frozenset(names)


AUDIT_RULE_NAMES = audit_rule_names()


def _utc(value) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc)


def _sanitize_description(text: str) -> str:
    """1–500 chars, no full document text (mvp-interfaces §1 redaction):
    collapse whitespace and hard-truncate. check_all descriptions are already
    flat summaries (identifiers, counts, short quotes); truncation is the
    bounded last line of defense."""
    collapsed = " ".join(str(text).split())
    if not collapsed:
        collapsed = "(empty description)"
    return collapsed[:DESCRIPTION_MAX_LEN]


def _map_severity(internal: str) -> str:
    mapped = SEVERITY_MAP.get(internal)
    if mapped is None:
        # Unknown internal label: fail loud (a new tools-layer severity is a
        # contract event; mvp-interfaces §1 legacy mappings are closed).
        raise StructuredError(
            "unknown", f"unmapped severity label from tools layer: {internal!r}")
    return mapped


def _raw_findings(root: str) -> list:
    """Run check_all.scan as-is; return the raw finding dicts (one scan)."""
    try:
        return check_all.scan(root)
    except FileNotFoundError as exc:
        raise StructuredError("unknown", f"corpus unreadable: {exc}") from exc
    except OSError as exc:
        raise StructuredError("unknown", f"corpus read error: {exc}") from exc


def _finding_from_raw(raw: dict, path_to_id: dict) -> dict:
    """Map ONE raw check_all finding to the Finding shape (+ rule tag).

    The `rule` key is kept for the no-rule-fork invariant test and stripped
    before the response/registry: a Finding is exactly
    {subject_id, severity, description, suggested_action} (mvp-interfaces §1).
    subject_id = manifest id when the file is manifest-tracked, else the
    repository-relative path (corpus-level finding: manifest drift, orphan).
    """
    rid = path_to_id.get(raw["file"])
    return {
        "subject_id": rid if rid is not None else raw["file"],
        "severity": _map_severity(raw["severity"]),
        "description": _sanitize_description(raw["description"]),
        "suggested_action": _SUGGESTED_ACTIONS.get(raw["rule"], _GENERIC_ACTION),
        "rule": raw["rule"],
    }


def _finding_public(finding: dict) -> dict:
    """Strip the internal rule tag → the contract Finding shape."""
    return {
        "subject_id": finding["subject_id"],
        "severity": finding["severity"],
        "description": finding["description"],
        "suggested_action": finding["suggested_action"],
    }


def _findings_for_batch(raw: list, path_to_id: dict, *, batch_set=None,
                        min_rank: int = 1) -> list:
    """Findings for a full-scope ('*') audit batch (tagged shape).

    Document findings are attributed to ``batch_set`` (None = every document);
    corpus-level findings (subject = a path, not a manifest id) report in the
    first pass so pagination cannot hide manifest drift. Severity filtered by
    min_rank at the audit() boundary.
    """
    ids = set(path_to_id.values())
    out = []
    for raw_f in raw:
        mapped = _finding_from_raw(raw_f, path_to_id)
        if mapped["subject_id"] in ids and batch_set is not None \
                and mapped["subject_id"] not in batch_set:
            continue
        if tests_helpers.severity_rank(mapped["severity"]) < min_rank:
            continue
        out.append(mapped)
    return out


def _findings_for_target(raw: list, path_to_id: dict, target_id: str) -> list:
    """Findings relevant to one target (delegate preview response)."""
    return [_finding_public(_finding_from_raw(f, path_to_id))
            for f in raw
            if path_to_id.get(f["file"]) == target_id]


def _resolve_scope(manifest, target_id: str) -> tuple:
    """Validate target against the manifest; return (entries, scope_ids).

    "*" = every manifest document; a concrete id must exist (off-manifest →
    unknown/escalate, mvp-interfaces §MVP scope boundary).
    """
    entries = manifest.entries()
    if target_id == "*":
        return entries, [e["id"] for e in entries]
    if manifest.resolve(target_id) is None:
        raise StructuredError(
            "unknown",
            f"target_id {target_id!r} is not a manifest document id "
            "(Documenter operates only on manifest-tracked artifacts)")
    return entries, [target_id]


def audit(root: str, registry, manifest, events, *,
          target_id: str = "*", severity_min: str = "low",
          pre_check: bool = False, scan_cursor: str | None = None,
          rescan_batch_ceiling: int = 50) -> dict:
    """Execute one audit invocation (fresh or resumed); persist to registry.

    Returns the mvp-interfaces §1 response:
    {audit_id, report: {header, findings}, has_remaining, scan_cursor,
     coverage: {scanned_count, total_count, status}}.
    Raises StructuredError for an off-manifest target (unknown/escalate),
    an unknown/replayed/mis-bound scan_cursor, or a bad severity_min.
    """
    if severity_min not in SEVERITY_ENUM:
        raise StructuredError(
            "unknown", f"severity_min {severity_min!r} not in "
                       f"{list(SEVERITY_ENUM)}")

    entries, scope_ids = _resolve_scope(manifest, target_id)
    path_to_id = {e["path"]: e["id"] for e in entries}
    min_rank = tests_helpers.severity_rank(severity_min)

    # -- resolve fresh vs resumed --------------------------------------------
    if scan_cursor:
        token = registry.consume_token(scan_cursor, target_id)
        audit_id = token["bound_to"]["audit_id"]
        prev = registry.find_audit(audit_id)
        scanned_ids = list(prev["scanned_ids"]) if prev else []
        carried = list(prev["findings"]) if prev else []
    else:
        audit_id = str(uuid.uuid4())
        scanned_ids = []
        carried = []

    offset = len(scanned_ids)
    batch_ids = scope_ids[offset:offset + rescan_batch_ceiling]
    has_remaining = offset + len(batch_ids) < len(scope_ids)

    # -- ONE tools-layer scan; report pagination only (never a rule fork) -----
    raw = _raw_findings(root)
    if target_id == "*":
        batch = _findings_for_batch(raw, path_to_id,
                                    batch_set=set(batch_ids), min_rank=min_rank)
    else:
        batch = [m for m in _findings_for_batch(raw, path_to_id,
                                                min_rank=min_rank)
                 if m["subject_id"] == target_id]

    new_findings = [_finding_public(m) for m in batch]
    for f in new_findings:
        events.emit("documenter.issue", {
            "audit_id": audit_id,
            "subject_id": f["subject_id"],
            "severity": f["severity"],
            "description": f["description"],
        })

    all_findings = carried + new_findings
    all_scanned = scanned_ids + batch_ids
    scan_cursor_out = None
    if has_remaining:
        scan_cursor_out = new_token()
        registry.issue_token("scan_cursor", scan_cursor_out,
                             {"audit_id": audit_id, "target_id": target_id})

    registry.append(reg.AUDIT_RECORD, {
        "audit_id": audit_id,
        "issued_at": registry.now(),
        "scope": target_id,
        "findings": all_findings,
        "scanned_ids": all_scanned,
        "has_remaining": has_remaining,
        "scan_cursor": scan_cursor_out,
    })

    coverage_status = "partial" if has_remaining else "complete"
    header = PARTIAL_WRITE_DECISION_NOTE if coverage_status == "partial" \
        else COMPLETE_REPORT_HEADER

    if pre_check:
        blocking = sorted({f["severity"] for f in all_findings
                           if f["severity"] in ("high", "critical")})
        if blocking:
            events.emit("precheck.failed", {
                "audit_id": audit_id, "target_id": target_id,
                "blocking_severities": blocking})
        else:
            events.emit("precheck.passed",
                        {"audit_id": audit_id, "target_id": target_id})

    return {
        "audit_id": audit_id,
        "report": {"header": header, "findings": all_findings},
        "has_remaining": has_remaining,
        "scan_cursor": scan_cursor_out,
        "coverage": {
            "scanned_count": len(all_scanned),
            "total_count": len(scope_ids),
            "status": coverage_status,
        },
    }


def delegate_preview(root: str, manifest, *, target_id: str, change_type: str,
                     trust_level: str, diff_input: str, preview, engine,
                     max_diff_bytes: int = MAX_DIFF_BYTES_DEFAULT,
                     audit_id: str | None = None, registry=None,
                     audit_freshness_min: int = 30) -> dict:
    """delegate(preview: true) — minimal MVP preview contour (no write branch).

    Flow (mvp-interfaces §2): preview MUST be exactly true (false/absent →
    tier_interlock/preview_denied) → the same scope resolver a write path uses
    (off-manifest target → unknown, so preview cannot become a reconnaissance
    primitive) → [when audit_id is provided] pre-audit gate rules 1–5 run
    verbatim (mvp-interfaces §Pre-audit gate; mvp-interfaces §4: audit_mismatch
    → rerun_audit, blocking_finding → resolve_finding or rescan_to_completion)
    → decode base64 (size-capped BEFORE processing) → normalize →
    trust floor check (requested >= derived, else trust_mismatch) using the
    normalized diff to derive the effective trust level → diff_hash over
    canonical bytes → render diff_text → findings relevant to target_id.

    diff_text is returned in the RESPONSE only: it never enters an event or
    the registry (mvp-data-models §3 redaction rule). Policy load failures
    never block preview (mvp-data-models §2 preview exemption); the caller
    supplies max_diff_bytes from the policy when it loaded, else the
    documented 512 KiB default is used. The pre-audit gate guards the write
    branch only — preview is exempt by contract when no audit_id is supplied;
    when audit_id is provided, the 5 gate rules run verbatim.
    The trust derivation now uses the normalized diff for dynamic classification.
    """
    if preview is not True:
        raise StructuredError(
            "tier_interlock",
            "delegate() write intent is refused in the MVP build: the write "
            "branch is structurally absent (mvp-contract §MVP boundary). "
            "Invoke with preview: true.")
    entries, _ = _resolve_scope(manifest, target_id)
    path_to_id = {e["path"]: e["id"] for e in entries}
    # Pre-audit gate: only when caller supplies audit_id.
    if audit_id is not None:
        if registry is None:
            raise StructuredError(
                "unknown",
                "audit_id supplied but registry unavailable to evaluate the "
                "pre-audit gate — this is a bug, not operator action")
        record = registry.find_audit(audit_id)
        now = registry.now()
        err = pre_audit_gate(record, target_id, now, audit_freshness_min)
        if err:
            raise err
    text = decode_diff_input(diff_input, max_diff_bytes)
    normalized = engine.normalize(text)
    derived, reason = check_invariant(change_type, trust_level,
                                      diff_text=normalized.decode("utf-8"))
    diff_hash = engine.diff_hash(normalized)
    diff_text = engine.render(normalized)
    findings = _findings_for_target(_raw_findings(root), path_to_id, target_id)
    resp = {
        "diff_hash": diff_hash,
        "diff_text": diff_text,
        "derived_trust_level": derived,
        "derived_trust_reason": reason,
        "next_action": "preview_only",
        "findings": findings,
    }
    if audit_id is not None:
        resp["gate"] = {"audit_id": audit_id, "verdict": "passed"}
    return resp


# ---------------------------------------------------------------------------
# Pre-audit gate (index.md §delegate Pre-audit gate rules 1–5), pure function.
# The MVP has NO write branch, so this gate is exercised by tests only; the
# Tier 2+ delegate() will call it verbatim (mvp-contract §4). Kept here — next
# to the audit core that produces the records it consumes — as a pure
# (no-I/O) evaluator over a looked-up audit_record.
# ---------------------------------------------------------------------------

def pre_audit_gate(audit_record, target_id: str, now,
                   audit_freshness_min: int):
    """Evaluate the 5 gate rules; return None (pass) or StructuredError.

    audit_record   — audit_record data dict, or None when the audit_id is not
                     in the registry (rule 1).
    target_id      — delegate target; scope must cover it (rule 3).
    now            — datetime (aware) or ISO-8601 'Z' string for freshness.
    audit_freshness_min — policy field; 0 disables the gate entirely
                     (policy-reference §Field Reference).
    Rules 1–3 → audit_mismatch/rerun_audit; rules 4–5 → blocking_finding
    (canonical category split, mvp-interfaces §4).
    """
    if audit_freshness_min == 0:
        return None
    # Rule 1: audit_id must exist.
    if audit_record is None:
        return StructuredError(
            "audit_mismatch",
            "audit_id missing from the registry (gate rule 1) — "
            "re-run audit() for the target and retry")
    # Rule 2: issued_at within audit_freshness.
    age_min = (_utc(now) - _utc(audit_record["issued_at"])).total_seconds() / 60.0
    if age_min > audit_freshness_min:
        return StructuredError(
            "audit_mismatch",
            f"audit_id is {age_min:.1f} min old, beyond audit_freshness="
            f"{audit_freshness_min} min (gate rule 2) — re-run audit()")
    # Rule 3: scope fully covers target_id ('*' matches any, else exact).
    scope = audit_record.get("scope")
    if scope != "*" and scope != target_id:
        return StructuredError(
            "audit_mismatch",
            f"audit scope {scope!r} does not cover target {target_id!r} "
            "(gate rule 3) — re-run audit() for the target")
    # Rule 4: no high/critical finding for target_id.
    blocking = sorted({f["severity"] for f in audit_record.get("findings", [])
                       if f.get("subject_id") == target_id
                       and f.get("severity") in ("high", "critical")})
    if blocking:
        return StructuredError(
            "blocking_finding",
            f"blocking findings {blocking} present for target {target_id!r} "
            "(gate rule 4) — resolve the finding, then re-run audit()",
            next_action="resolve_finding")
    # Rule 5: scan must have completed (has_remaining false).
    if audit_record.get("has_remaining"):
        return StructuredError(
            "blocking_finding",
            "the registered scan is incomplete (has_remaining=true; gate "
            "rule 5) — resume with audit(scan_cursor=...) to completion",
            next_action="rescan_to_completion")
    return None
