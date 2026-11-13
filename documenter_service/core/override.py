"""Core override_gate + post_mortems — mvp-contract §2.2.6, §4 (Tier 2+).

override_gate(root, data_dir, registry, policy, events, *, target_id,
    diff_hash, reason, operator_id, audit_id=None) -> dict

Guard order (fail-closed):
  1. operator_id_valid() → else "unknown".
  2. check_tier2_authorized() → tier_interlock (MVP runtime stays locked).
  3. reason non-empty str ≤ 500 chars → else "unknown".
  4. diff_hash matches ^sha256:[0-9a-f]{64}$ → else "unknown".
  5. CRITICAL GUARD: the governing audit record must contain NO finding with
     severity "critical" for target_id (or corpus-level subject when target
     not found among findings).  → StructuredError("blocking_finding",
     next_action="resolve_finding").
  6. Registry corrupt → gate_failure.
  7. One consumption: token_record with token_type="override_gate" bound to
     (target_id, diff_hash); dedup against existing unconsumed active tokens.
  8. Consume semantics: single invocation = one-shot (dedup then consume).
  9. events.emit("documenter.override_gate", ...) — schema already declared.
 10. Return {"override_id": uuid, target_id, diff_hash, reason, operator_id,
      emitted_at, next_action="rerun_audit"}.

post_mortems — durable mechanism (currently unreached by MVP because no
critical producers + §4 bans critical override).  Keeps writer ready.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid

from .errors import StructuredError

# Lazy imports to avoid circular deps (audit.py imports check_all).
def _get_operator_id_valid():
    from .policy import operator_id_valid as _f
    return _f

def _get_check_tier2_authorized():
    from .policy import check_tier2_authorized as _f
    return _f

SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def override_gate(root, data_dir, registry, policy, events, *, target_id,
                  diff_hash, reason, operator_id, audit_id=None):
    """Gate an override invocation (mvp-contract §2.2.6, §4).

    Bound to one (target_id, diff_hash); one consumption; emits event;
    unavailable for critical findings.

    Returns {"override_id", "target_id", "diff_hash", "reason", "operator_id",
             "emitted_at", "next_action": "rerun_audit"}.

    next_action is "rerun_audit" because after an override the caller must
    re-audit/re-propose — the override authorises re-proposal, not silent
    retry.
    """
    # 1. operator_id_valid
    operator_id_valid = _get_operator_id_valid()
    if not operator_id_valid(operator_id):
        raise StructuredError(
            "unknown",
            f"malformed operator_id {operator_id!r} — "
            "expected format ^op-[a-z0-9][a-z0-9-]{{2,63}}$")

    # 2. check_tier2_authorized (MVP runtime stays locked — the override
    # escape hatch must not be more powerful than the write path it unlocks).
    check_tier2 = _get_check_tier2_authorized()
    check_tier2(policy, root)

    # 3. reason non-empty str ≤ 500 chars
    if (not isinstance(reason, str) or not reason or len(reason) > 500):
        raise StructuredError(
            "unknown",
            f"reason must be a non-empty string ≤ 500 chars, got "
            f"{type(reason).__name__}")

    # 4. diff_hash matches sha256:<64-hex>
    if not SHA256_RE.match(diff_hash):
        raise StructuredError(
            "unknown",
            f"diff_hash must match ^sha256:[0-9a-f]{{64}}$, got {diff_hash!r}")

    # 5. CRITICAL GUARD — the governing audit_record must contain NO finding
    # with severity "critical" for the target_id (or corpus-level subject).
    audit = registry.find_audit(audit_id) if audit_id else registry.last_audit()
    if audit is not None:
        findings = audit.get("findings", [])
        for f in findings:
            if f.get("severity") != "critical":
                continue
            subject = f.get("subject_id", "")
            # Direct match: finding is about the target
            if subject == target_id:
                raise StructuredError(
                    "blocking_finding",
                    "override is unavailable for critical findings "
                    "(mvp-contract §4); critical findings require post-mortem "
                    "remediation, not override",
                    next_action="resolve_finding")
            # Corpus-level: finding subject is a file path, and target maps to
            # a manifest entry whose path is a sub-path of the subject.
            if _is_corpus_level_finding(subject, target_id, registry, root):
                raise StructuredError(
                    "blocking_finding",
                    "override is unavailable for critical findings "
                    "(mvp-contract §4); critical findings require post-mortem "
                    "remediation, not override",
                    next_action="resolve_finding")

    # 6. Registry corrupt → gate_failure.
    if registry.status() == "corrupt":
        raise StructuredError(
            "gate_failure",
            "audit registry is corrupt — restore the registry from git; "
            "status() reports details")

    # 7. One consumption: dedup against existing unconsumed active tokens
    # for the same (target_id, diff_hash).
    _check_override_dedup(registry, policy, target_id, diff_hash)

    # 8. Consume semantics: one-shot per pair.
    now = registry.now()
    override_id = str(uuid.uuid4())

    # Append the token_record (consumed=True immediately — one invocation =
    # one consumption).
    token_data = {
        "token_type": "override_gate",
        "token_value": override_id,
        "bound_to": {
            "audit_id": audit_id,
            "target_id": target_id,
        },
        "diff_hash": diff_hash,
        "reason": reason,
        "operator_id": operator_id,
        "consumed": True,
        "consumed_at": now,
        "created_at": now,
    }
    registry.append("token_record", token_data)

    # 9. Emit event (schema already declared in EVENT_SCHEMAS).
    events.emit("documenter.override_gate", {
        "reason": reason,
        "operator_id": operator_id,
        "target_id": target_id,
    })

    # 10. Return result — next_action is "rerun_audit" because the override
    # authorises re-proposal only; the caller must re-audit/re-propose.
    return {
        "override_id": override_id,
        "target_id": target_id,
        "diff_hash": diff_hash,
        "reason": reason,
        "operator_id": operator_id,
        "emitted_at": now,
        "next_action": "rerun_audit",
    }


def _is_corpus_level_finding(subject_id, target_id, registry, root):
    """Return True when the subject is a corpus-level path that covers target."""
    # A corpus-level subject is a file system path (contains '/') not a
    # simple document ID like "alpha".
    if "/" not in subject_id:
        return False
    # The target must not itself be a corpus-level subject, and must map to
    # a manifest entry whose path is a sub-path of the subject.
    manifest = registry.__dict__.get("_manifest_for_override")
    if manifest is None:
        # No manifest available: check if subject looks like a corpus path
        # and target looks like a simple doc ID.
        if "/" not in target_id:
            return True
        return False
    # Try to resolve target to a manifest entry, then compare paths.
    try:
        from ..ports import ManifestSource
        is_manifest_source = isinstance(manifest, ManifestSource)
        if is_manifest_source:
            entry = manifest.resolve(target_id)
        elif isinstance(manifest, dict):
            entry = manifest.get(target_id)
        else:
            entry = getattr(manifest, "resolve", lambda self, _t: None)(target_id)
        if entry and isinstance(entry, dict) and "path" in entry:
            target_path = entry["path"]
            return (subject_id.startswith(target_path.split("/")[0] + "/")
                    or target_path.startswith(subject_id.split("/")[0] + "/"))
    except Exception:
        pass
    return False


def _check_override_dedup(registry, policy, target_id, diff_hash):
    """Raise token_replay when an active override exists for (target, hash).

    Contract mvp-contract §4: one consumption per (target_id, diff_hash).
    Every invocation consumes immediately (consumed=True at append), so
    "active" is any override token for the pair created within
    approval_expiry_window — regardless of the consumed flag, otherwise the
    one-shot bound would be vacuous (an unlimited re-override loop). After
    the window expires the pair may be overridden again (re-propose).
    """
    records, _ = registry.read_all()
    expiry_min = (int(policy.get("approval_expiry_window")) if policy
                  else 30)
    now = registry.now()

    for rec in records:
        if rec["record_type"] != "token_record":
            continue
        data = rec["data"]
        if data.get("token_type") != "override_gate":
            continue
        bound = data.get("bound_to", {})
        if bound.get("target_id") != target_id:
            continue
        # Check diff_hash match.
        if data.get("diff_hash") != diff_hash:
            continue
        # Check expiry: created_at within policy's approval_expiry_window.
        from .registry import approval_is_expired
        if approval_is_expired(data, now, expiry_min):
            # This token has expired — skip it (it's no longer active).
            continue
        raise StructuredError(
            "token_replay",
            "an active override already exists for (target_id={!r}, "
            "diff_hash={}) — overrides are one-shot per pair; re-propose "
            "after it is consumed or expires".format(
                target_id, diff_hash),
            next_action="rerun_audit")


# ---------------------------------------------------------------------------
# Post-mortems — durable mechanism for critical-finding context
# ---------------------------------------------------------------------------


def write_post_mortem(data_dir, *, audit_id, findings, reason, operator_id):
    """Write a post-mortem record to documenter/post_mortems/<uuid>.json.

    Uses temp+rename+fsync durability (mirror apply_write pattern).

    Returns the path of the written file.
    """
    postmortems_dir = os.path.join(data_dir, "post_mortems")
    os.makedirs(postmortems_dir, exist_ok=True)

    pm_id = str(uuid.uuid4())
    filename = f"{pm_id}.json"
    file_path = os.path.join(postmortems_dir, filename)

    # Redacted findings: subject_id, severity, description, suggested_action
    # only (mvp-contract §2.2.6, service-contract redaction rules).
    redacted_findings = []
    for f in (findings or []):
        redacted_findings.append({
            "subject_id": f.get("subject_id", ""),
            "severity": f.get("severity", ""),
            "description": f.get("description", ""),
            "suggested_action": f.get("suggested_action", ""),
        })

    now = None  # lazy import to avoid circular dep
    pm_data = {
        "post_mortem_id": pm_id,
        "audit_id": audit_id,
        "findings": redacted_findings,
        "reason": reason,
        "operator_id": operator_id,
        "created_at": registry_now(data_dir),
    }

    # temp+rename+fsync (mvp-contract §2.2.4 durability sequence).
    tmp_path = file_path + ".tmp"
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, json.dumps(pm_data, sort_keys=True,
                                  ensure_ascii=False).encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.rename(tmp_path, file_path)
        dir_fd = os.open(postmortems_dir, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise

    return file_path


def list_post_mortems(data_dir):
    """Return parsed post-mortem dicts sorted by created_at (ascending)."""
    postmortems_dir = os.path.join(data_dir, "post_mortems")
    if not os.path.isdir(postmortems_dir):
        return []
    result = []
    for fname in os.listdir(postmortems_dir):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(postmortems_dir, fname)
        try:
            with open(path, encoding="utf-8") as fh:
                result.append(json.load(fh))
        except (json.JSONDecodeError, OSError):
            pass  # skip corrupt / temp files
    result.sort(key=lambda pm: pm.get("created_at", ""))
    return result


def registry_now(data_dir):
    """Get a UTC ISO 8601 timestamp.  Uses registry adapter when available.

    Falls back to datetime.now() if no registry is available at data_dir.
    """
    # Try to import registry helper from data_dir
    try:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ImportError:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
