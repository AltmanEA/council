"""Tier 3 pattern auto-apply mechanism (mvp-contract §4 row 4).

Public functions:

  - pattern_metric(registry, *, pattern_id, now_iso, window_min=20160) -> dict
  - record_viewed(registry, *, approval_id, viewed=True) -> dict
  - check_quarantine(registry, pattern_id, *, quarantine_n=3) -> bool
  - apply_pattern_batch(root, manifest, registry, policy, events, engine,
                        *, pattern_id, proposals, operator_id, seams=None) -> dict

All failures per-item do NOT abort the batch (catch StructuredError per item).
Batch-level guards (tier, policy pattern missing, limit, expired) DO abort
with StructuredError.

Persisted via token_record with token_type == "pattern_usage":
  {token_type, token_value, bound_to, pattern_id, applied_at, approved_by}
"""
from __future__ import annotations

import base64
import fnmatch
import os
import re
from datetime import datetime, timezone

from .errors import StructuredError

__all__ = [
    "pattern_metric",
    "record_viewed",
    "check_quarantine",
    "apply_pattern_batch",
]

# -- Window constants --------------------------------------------------------

#: Default lookback window in minutes (14 days * 24h * 60m).
DEFAULT_WINDOW_MIN = 20160

# -- Helper: compute window boundary ----------------------------------------


def _window_cutoff(now_iso: str, window_min: int) -> datetime:
    """Return the datetime at which records older than this are excluded."""
    try:
        now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise StructuredError(
            "unknown",
            f"malformed now_iso timestamp: {now_iso!r}",
            next_action="escalate",
        )
    delta = now_dt.timestamp() - window_min * 60
    return datetime.fromtimestamp(delta, tz=timezone.utc)


# -- 1. pattern_metric -----------------------------------------------------


def pattern_metric(
    registry,
    *,
    pattern_id: str,
    now_iso: str,
    window_min: int = DEFAULT_WINDOW_MIN,
) -> dict:
    """Compute approval metric over viewed diffs for a pattern.

    Over approval token_records (token_type=="approval_id") that are RESOLVED
    and created within ``window_min`` minutes of ``now_iso``:
    restricted to approvals linked to this pattern (pattern entries carry a
    ``pattern_id`` key on the approval record when auto-applying).

    "viewed" = records with key ``viewed`` == True (see record_viewed).
    Metric counts ONLY viewed diffs (mvp-contract §4 row 4).

    Returns {"viewed": n_viewed, "approved": n_approved, "rejected": n_rejected,
             "approval_rate": approved/max(approved+rejected, 1),
             "promotable": approval_rate >= 0.90 and n_viewed >= 1}.
    """
    from ..core.registry import TOKEN_RECORD, APPROVAL_ID

    cutoff = _window_cutoff(now_iso, window_min)

    records, _ = registry.read_all()

    viewed = 0
    approved = 0
    rejected = 0

    for rec in records:
        if rec["record_type"] != TOKEN_RECORD:
            continue
        data = rec["data"]
        if data.get("token_type") != APPROVAL_ID:
            continue
        # Must carry the pattern_id link
        if data.get("pattern_id") != pattern_id:
            continue
        # Must be resolved (decision is not None)
        decision = data.get("decision")
        if decision is None:
            continue
        # Must be within the time window
        created_at = data.get("created_at")
        if not isinstance(created_at, str) or not created_at.endswith("Z"):
            continue
        try:
            created_dt = datetime.fromisoformat(
                created_at.replace("Z", "+00:00")
            )
        except (ValueError, TypeError):
            continue
        if created_dt < cutoff:
            continue

        # Count viewed
        if data.get("viewed"):
            viewed += 1
            if decision == "approved":
                approved += 1
            elif decision == "rejected":
                rejected += 1

    total = approved + rejected
    approval_rate = approved / max(total, 1)
    promotable = approval_rate >= 0.90 and viewed >= 1

    return {
        "viewed": viewed,
        "approved": approved,
        "rejected": rejected,
        "approval_rate": approval_rate,
        "promotable": promotable,
    }


# -- 2. record_viewed ------------------------------------------------------


def record_viewed(registry, *, approval_id: str, viewed: bool = True) -> dict:
    """Append a copy of the approval token_record with ``viewed=True``.

    The original record is unchanged (append-only lifecycle).
    Returns the newly appended record data dict.

    Raises StructuredError("audit_mismatch") when ``approval_id`` was not
    issued by this registry.
    """
    from ..core.registry import TOKEN_RECORD, APPROVAL_ID

    approval = registry.find_approval(approval_id)
    if approval is None:
        raise StructuredError(
            "audit_mismatch",
            f"approval_id {approval_id!r} was not issued by this registry",
        )

    copy = dict(approval)
    copy["viewed"] = viewed
    return registry.append(TOKEN_RECORD, copy)["data"]


# -- 3. check_quarantine ---------------------------------------------------


def check_quarantine(
    registry, pattern_id: str, *, quarantine_n: int = 3
) -> bool:
    """Return True when the pattern is still in quarantine.

    Quarantine: the first N uses of a pattern require per-item approval
    (mvp-contract §4 row 4). True means "still in quarantine" — the count
    of pattern_usage records for pattern_id < quarantine_n.
    """
    from ..core.registry import TOKEN_RECORD

    records, _ = registry.read_all()
    count = 0
    for rec in records:
        if rec["record_type"] != TOKEN_RECORD:
            continue
        data = rec["data"]
        if data.get("token_type") == "pattern_usage" and \
                data.get("pattern_id") == pattern_id:
            count += 1
    return count < quarantine_n


# -- 4. apply_pattern_batch ------------------------------------------------


def apply_pattern_batch(
    root: str,
    manifest,
    registry,
    policy,
    events,
    engine,
    *,
    pattern_id: str,
    proposals: list,
    operator_id: str,
    seams: dict | None = None,
) -> dict:
    """Apply a batch of proposals under a pattern.

    Parameters
    ----------
    proposals : list[dict]
        Each item: {target_id, change_type, trust_level, diff_input(base64),
        audit_id, diff_hash(optional)}.
    seams : dict, optional
        Passed through to apply_write on failure injection.

    Returns
    -------
    dict with keys: pattern_id, results (list), applied_count,
    quarantine_active, next_action.

    Batch-level guards (abort ALL with StructuredError):
      1. check_tier3_authorized(policy, root) → tier_interlock
      2. policy entry must exist with type=="pattern", pattern_id == pattern_id
         → gate_failure "pattern not authorized by policy"
      3. application_limit reached → gate_failure
      4. expires_at in the past → gate_failure
      5. invalid canonical_diff_template regex → StructuredError("unknown")

    Per-item: StructuredError → results entry, file unchanged.
    """
    from ..core.policy import check_tier3_authorized, match_pattern, PolicyError
    from ..adapters.lock import DelegateLock
    from ..core.write import apply_write as _apply_write
    from ..core.registry import TOKEN_RECORD, APPROVAL_ID

    # --- Batch-level guard: tier3 authorization ---------------------------
    check_tier3_authorized(policy, root)

    # --- Batch-level guard: policy entry lookup ---------------------------
    entry = _find_pattern_entry(policy, pattern_id)
    if entry is None:
        raise StructuredError(
            "gate_failure",
            f"pattern {pattern_id!r} not authorized by policy "
            "(not found in allowed_operations)",
            next_action="preview_denied",
        )

    # --- Batch-level guard: expiry ----------------------------------------
    _check_expiry(entry, registry.now())

    # --- Batch-level guard: application limit -----------------------------
    _check_application_limit(
        registry, pattern_id, entry, now_iso=registry.now()
    )

    # --- Batch-level guard: canonical template regex compilation ----------
    canonical_template = _parse_canonical_template(entry)

    # --- Resolve the entry's match_criteria for per-item filtering --------
    match_criteria = entry.get("match_criteria") or {}

    # --- Process items sequentially ---------------------------------------
    in_quarantine = check_quarantine(registry, pattern_id)
    results = []
    applied_count = 0

    for proposal in proposals:
        try:
            item_result = _apply_pattern_item(
                root=root,
                manifest=manifest,
                registry=registry,
                policy=policy,
                events=events,
                engine=engine,
                proposal=proposal,
                pattern_id=pattern_id,
                entry=entry,
                canonical_template=canonical_template,
                match_criteria=match_criteria,
                operator_id=operator_id,
                in_quarantine=in_quarantine,
                seams=seams,
            )
            results.append(item_result)
            if item_result["status"] == "applied":
                applied_count += 1
        except StructuredError as exc:
            # Batch-level guard raises here (shouldn't happen inside the
            # loop since we checked above), but catch defensively:
            results.append({
                "target_id": proposal.get("target_id", ""),
                "status": "failed",
                "error_category": exc.error_category,
                "detail": exc.message,
            })
        except Exception as exc:
            results.append({
                "target_id": proposal.get("target_id", ""),
                "status": "failed",
                "error_category": "unknown",
                "detail": str(exc),
            })

    quarantine_active = check_quarantine(registry, pattern_id)
    next_action = "preview_only" if quarantine_active else "write_applied"

    return {
        "pattern_id": pattern_id,
        "results": results,
        "applied_count": applied_count,
        "quarantine_active": quarantine_active,
        "next_action": next_action,
    }


# -- Internal helpers -------------------------------------------------------


def _find_pattern_entry(policy, pattern_id: str):
    """Find the pattern-type entry matching pattern_id, or None."""
    if not policy:
        return None
    for entry in (policy.get("allowed_operations") or []):
        if entry.get("type", "operation") == "pattern" and \
                entry.get("pattern_id") == pattern_id:
            return entry
    return None


def _check_expiry(entry, now_iso: str) -> None:
    """Raise if the pattern's expires_at is in the past."""
    expires_at = entry.get("expires_at")
    if not expires_at:
        return
    try:
        exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise StructuredError(
            "unknown",
            f"pattern expires_at {expires_at!r} is malformed",
            next_action="escalate",
        )
    try:
        now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise StructuredError(
            "unknown",
            f"malformed now_iso: {now_iso!r}",
            next_action="escalate",
        )
    if now_dt > exp_dt:
        raise StructuredError(
            "gate_failure",
            f"pattern {entry.get('pattern_id', '')!r} expired at {expires_at}",
            next_action="preview_denied",
        )


def _check_application_limit(registry, pattern_id, entry, *, now_iso) -> None:
    """Raise if current usage count >= limit."""
    limit = entry.get("application_limit")
    if not limit:
        return
    from ..core.registry import TOKEN_RECORD

    records, _ = registry.read_all()
    count = 0
    for rec in records:
        if rec["record_type"] != TOKEN_RECORD:
            continue
        data = rec["data"]
        if data.get("token_type") == "pattern_usage" and \
                data.get("pattern_id") == pattern_id:
            count += 1
    if count >= limit:
        raise StructuredError(
            "gate_failure",
            f"pattern {pattern_id!r} application limit reached "
            f"({count}/{limit})",
            next_action="preview_denied",
        )


def _parse_canonical_template(entry):
    """Return (regex_compiled_or_None, expected_hunk_count_or_None).

    If the entry carries optional canonical_diff_template with
    expected_hunk_count and changed_line_regex, compile the regex here.
    Invalid regex → raises StructuredError("unknown").
    If template fields absent, return (None, None) — fallback to weaker
    class-bound match (file_pattern + change_type) is permitted because
    the policy explicitly enumerated the pattern.
    """
    tmpl = entry.get("canonical_diff_template")
    if not tmpl or not isinstance(tmpl, dict):
        return None, None
    changed_line_regex = tmpl.get("changed_line_regex")
    if changed_line_regex is not None:
        try:
            compiled = re.compile(changed_line_regex)
        except re.error as exc:
            raise StructuredError(
                "unknown",
                f"pattern {entry.get('pattern_id', '')!r} has invalid "
                f"canonical_diff_template changed_line_regex: {exc}",
                next_action="escalate",
            )
        return compiled, tmpl.get("expected_hunk_count")
    return None, None


def _compute_diff_hash(engine, diff_input: str, max_diff_bytes: int = 524288):
    """Decode, normalize, hash — returns diff_hash string."""
    from ..adapters.diff_engine import decode_diff_input

    text = decode_diff_input(diff_input, max_diff_bytes)
    normalized = engine.normalize(text)
    return engine.diff_hash(normalized), normalized


def _apply_pattern_item(
    root, manifest, registry, policy, events, engine,
    proposal, pattern_id, entry, canonical_template,
    match_criteria, operator_id, in_quarantine, seams,
):
    """Apply a single proposal item; return result dict.

    Per-item guards:
      - quarantine: require an already-approved diff_hash in registry;
        unapproved → status "await_approval", file unchanged.
      - canonical template check: normalized diff, after removing +/- line
        CONTENT, must consist only of lines matching the pattern's canonical
        template (if present).
      - file_pattern fallback: if canonical template absent, require
        match_criteria.file_pattern covers the target path and change_type
        matches.

    Successful apply appends pattern_usage {approved_by: operator_id, auto: False}
    or {approved_by: None, auto: True} (auto from quarantine bypass).
    """
    from ..core.write import apply_write as _apply_write
    from ..core.registry import TOKEN_RECORD

    target_id = proposal["target_id"]
    change_type = proposal["change_type"]
    trust_level = proposal.get("trust_level", "safe")
    diff_input = proposal["diff_input"]
    audit_id = proposal.get("audit_id")

    # Resolve manifest entry to get the file path for path matching.
    target_entry = manifest.resolve(target_id)
    if target_entry is None:
        raise StructuredError(
            "unknown",
            f"manifest entry for target_id {target_id!r} not found",
        )
    target_path = os.path.join(root, target_entry["path"])

    # Compute diff_hash from the diff_input.
    diff_hash, normalized = _compute_diff_hash(engine, diff_input)

    # --- Canonical template check (content-bound: never class-only) -------
    if canonical_template[0] is not None:
        # Validate the diff against the canonical template.
        _validate_canonical_diff(
            normalized.decode("utf-8"),
            canonical_template[0],
            canonical_template[1],
        )

    # --- Fallback: file_pattern + change_type (only when template absent)
    elif canonical_template[0] is None:
        file_pattern = match_criteria.get("file_pattern", "")
        if file_pattern:
            rel_path = target_entry.get("path", "")
            if not fnmatch.fnmatchcase(rel_path, file_pattern):
                raise StructuredError(
                    "gate_failure",
                    f"target {target_id!r} path {rel_path!r} does not match "
                    f"pattern file_pattern {file_pattern!r}",
                    next_action="preview_denied",
                )
        if match_criteria.get("change_type") and \
                match_criteria["change_type"] != change_type:
            raise StructuredError(
                "gate_failure",
                f"change_type {change_type!r} does not match "
                f"pattern criteria {match_criteria['change_type']!r}",
                next_action="preview_denied",
            )

    # --- Quarantine: per-item approval check ----------------------------
    if in_quarantine:
        # Check if there is an already-resolved-approved token for this exact
        # diff_hash in the registry.
        has_approval = _has_approved_diff_hash(
            registry, diff_hash, pattern_id
        )
        if not has_approval:
            # No approved diff_hash → skip, file unchanged.
            # Do NOT count towards usage (await_approval items don't consume).
            return {
                "target_id": target_id,
                "status": "await_approval",
            }
        # Quarantine bypass: we have an approved diff_hash, so we proceed
        # with auto: True (approved_by: None means auto-approved).
        approved_by = None
        auto = True
    else:
        approved_by = operator_id
        auto = False

    # --- Apply the write ------------------------------------------------
    # Out-of-quarantine items need an approval record for apply_write.
    # Quarantine items that pass the diff_hash check already have one.
    if not _has_approved_diff_hash(registry, diff_hash, pattern_id):
        # Issue self-approval so apply_write finds it.
        from ..core.registry import TOKEN_RECORD, APPROVAL_ID
        approval_data = {
            "token_type": APPROVAL_ID,
            "token_value": diff_hash,
            "bound_to": {"audit_id": audit_id, "target_id": target_id},
            "consumed": False,
            "consumed_at": None,
            "target_ids": [target_id],
            "diff_hash": diff_hash,
            "proposer_id": operator_id,
            "created_at": registry.now(),
            "decision": "approved",
            "resolved_at": registry.now(),
            "resolved_by": operator_id,
            "pattern_id": pattern_id,
        }
        registry.append(TOKEN_RECORD, approval_data)

    try:
        result = _apply_write(
            root, manifest, registry, policy, events, engine,
            approval_id=diff_hash,  # use diff_hash as approval_id (per-pattern)
            operator_id=operator_id,
            diff_input=diff_input,
            data_dir=registry.data_dir,
            seams=seams,
        )
    except StructuredError as exc:
        raise exc

    # Record pattern_usage (append-only).
    now_iso = registry.now()
    usage_data = {
        "token_type": "pattern_usage",
        "token_value": target_id,
        "bound_to": {"audit_id": audit_id, "target_id": target_id},
        "pattern_id": pattern_id,
        "applied_at": now_iso,
        "approved_by": approved_by,
        "auto": auto,
    }
    registry.append(TOKEN_RECORD, usage_data)

    return {
        "target_id": target_id,
        "status": "applied",
        "detail": "write_applied",
    }


def _validate_canonical_diff(
    diff_text: str, regex: re.Pattern, expected_hunk_count: int | None
) -> None:
    """Validate that a diff matches the canonical template.

    The content-bound check: after removing +/- line CONTENT (stripping the
    +/- prefix), the remaining lines must match the regex. The hunk count
    must also match if expected_hunk_count is provided.
    """
    import re as _re

    lines = diff_text.split("\n")
    hunk_count = 0
    for line in lines:
        if line.startswith("@@"):
            hunk_count += 1
            continue
        if line.startswith(("-", "+")):
            stripped = line[1:]  # remove +/- prefix
            if not regex.fullmatch(stripped):
                raise StructuredError(
                    "unknown",
                    f"diff line {line!r} (stripped: {stripped!r}) does not "
                    f"match pattern canonical template regex",
                    next_action="preview_denied",
                )

    if expected_hunk_count is not None and hunk_count != expected_hunk_count:
        raise StructuredError(
            "unknown",
            f"diff has {hunk_count} hunk(s), expected {expected_hunk_count} "
            f"(canonical template mismatch)",
            next_action="preview_denied",
        )


def _has_approved_diff_hash(registry, diff_hash: str, pattern_id: str) -> bool:
    """Check if there is a resolved-approved token for this diff_hash.

    Look through approval token_records: find one with the matching diff_hash
    and a "pattern_id" field matching the given pattern_id, with decision==
    "approved".
    """
    from ..core.registry import TOKEN_RECORD, APPROVAL_ID

    records, _ = registry.read_all()
    for rec in records:
        if rec["record_type"] != TOKEN_RECORD:
            continue
        data = rec["data"]
        if data.get("token_type") != APPROVAL_ID:
            continue
        if data.get("diff_hash") != diff_hash:
            continue
        if data.get("pattern_id") != pattern_id:
            continue
        if data.get("decision") == "approved":
            return True
    return False
