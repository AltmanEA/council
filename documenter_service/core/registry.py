"""Audit registry core — envelope, chain, retention (mvp-data-models §1).

Pure, filesystem-free building blocks shared by the JSONL adapter:
record envelope {record_type, prev_hash, data}, prev_hash = sha256 of the
previous record's canonical JSON (sorted keys, compact separators, no trailing
newline; null on the first record), chain verification, retention (10,000
records) and the checkpoint-before-truncation rule.

Threat model (mvp-data-models §Purpose): the chain is a cheap corruption
DETECTION aid, not an anti-tamper mechanism.

NOTE: token_record data may carry additional keys beyond the five fields of
mvp-data-models §1 (token_type, token_value, bound_to, consumed, consumed_at).
This applies to approval_id tokens which carry diff_hash, proposer_id,
decision, resolved_at, and resolved_by alongside the base fields. The schema
is append-only additive; parse_line only validates envelope keys (VAL.001
relaxed for token_record.data — extra keys are carried through).
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

__all__ = [
    "RETENTION_MAX",
    "RECORD_TYPES",
    "AUDIT_RECORD",
    "TOKEN_RECORD",
    "CHECKPOINT_RECORD",
    "INTENT_RECORD",
    "APPROVAL_ID",
    "SCAN_CURSOR",
    "OPERATOR_ID_RE",
    "canonical_json",
    "record_hash",
    "make_envelope",
    "parse_line",
    "intent_key",
    "verify_chain",
    "segment_hash",
    "make_checkpoint_data",
    "plan_truncation",
    "approval_is_expired",
]

#: Maximum records retained in the registry (mvp-data-models §1 Retention).
RETENTION_MAX = 10000

AUDIT_RECORD = "audit_record"
TOKEN_RECORD = "token_record"
INTENT_RECORD = "intent_record"
CHECKPOINT_RECORD = "checkpoint_record"
APPROVAL_ID = "approval_id"  #: token_type value for approval tokens (mvp-data-models §1)
SCAN_CURSOR = "scan_cursor"  #: token_type value for scan cursors (mvp-data-models §1)

#: Closed enum of envelope record_type values (mvp-data-models §1). intent_record
#: is a reserved Tier 2+ schema: the type is recognized on READ (a foreign
#: writer's record must not read as corrupt) but no MVP code path appends it.
RECORD_TYPES = (AUDIT_RECORD, TOKEN_RECORD, INTENT_RECORD, CHECKPOINT_RECORD)

#: Envelope keys — exactly these three, VAL.001 style.
ENVELOPE_KEYS = frozenset({"record_type", "prev_hash", "data"})

_HEX64 = "0123456789abcdef"

#: Operator ID format (mvp-interfaces §5): ``^op-[a-z0-9][a-z0-9-]{2,63}$``
OPERATOR_ID_RE = re.compile(r"^op-[a-z0-9][a-z0-9-]{2,63}$")

#: SHA256 hash pattern (with prefix): ``sha256:<64-hex>``
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def canonical_json(record: dict) -> str:
    """Canonical JSON for hashing: sorted keys, compact separators, no newline."""
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


def record_hash(record: dict) -> str:
    """sha256 hex digest of a record's canonical JSON (no trailing newline)."""
    return hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()


def make_envelope(record_type: str, data: dict, prev_hash: str | None) -> dict:
    """Build one envelope record {record_type, prev_hash, data}.

    Raises ValueError for an unknown record_type (closed enum). prev_hash is
    the sha256 hex of the PREVIOUS record's canonical JSON; None on the first
    record (mvp-data-models §1).

    Schema note: audit_record data carries exactly the seven fields of the
    mvp-data-models §1 table (audit_id, issued_at, scope, findings,
    scanned_ids, has_remaining, scan_cursor). Within one logical (possibly
    paginated) scan, `scanned_ids` and `findings` are CUMULATIVE — the ids
    covered and the findings known as of that record — so a resumed batch can
    report honest coverage from its bound predecessor alone, with no extra
    envelope fields.
    """
    if record_type not in RECORD_TYPES:
        raise ValueError(f"unknown record_type: {record_type!r}")
    return {"record_type": record_type, "prev_hash": prev_hash, "data": data}


def parse_line(raw: str) -> dict:
    """Parse one JSONL line into a validated envelope.

    Raises ValueError (mapped to registry status `corrupt` by callers) when the
    line is not JSON, not an object, has envelope keys other than
    {record_type, prev_hash, data}, an unknown record_type, or a prev_hash
    that is neither null nor a 64-char lowercase hex digest.
    """
    try:
        obj = json.loads(raw)
    except ValueError as exc:
        raise ValueError(f"malformed JSON line: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError("envelope is not a JSON object")
    if frozenset(obj.keys()) != ENVELOPE_KEYS:
        raise ValueError(f"envelope keys {sorted(obj)} != "
                         f"{sorted(ENVELOPE_KEYS)}")
    if obj["record_type"] not in RECORD_TYPES:
        raise ValueError(f"unknown record_type: {obj['record_type']!r}")
    if not isinstance(obj["data"], dict):
        raise ValueError("envelope data is not a JSON object")
    ph = obj["prev_hash"]
    if ph is not None and not (
            isinstance(ph, str) and len(ph) == 64
            and all(c in _HEX64 for c in ph)):
        raise ValueError(f"prev_hash is not null or 64-char lowercase hex: {ph!r}")
    return obj


def intent_key(data: dict) -> tuple:
    """Stable identity of a logical intent_record.

    An append-only registry records the resolution of an intent by appending
    a copy with ``resolved=True``; both records describe the same staging
    operation and must collapse to one logical intent on read. New-format
    (changeset) intents carry ``tx_id``; legacy intents are identified by
    their target set, staging timestamp, and per-file source hashes.
    """
    tx_id = data.get("tx_id")
    if tx_id:
        return ("tx_id", tx_id)
    per_file = data.get("per_file_sha256") or {}
    return (
        "legacy",
        tuple(data.get("target_ids") or ()),
        data.get("staged_at"),
        tuple(sorted(per_file.items())),
    )


def _is_sha_hex(value) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in _HEX64 for c in value))


def verify_chain(records: list) -> str:
    """Chain/retention verdict over parsed envelopes: healthy|degraded.

    `degraded` (mvp-interfaces §3): a prev_hash break at any position other
    than an authorized compaction head, or a size above RETENTION_MAX without
    a trailing checkpoint_record. Corruption verdicts (unparsable input) are
    raised by parse_line, not returned here.

    Authorized compaction head: after a checkpoint-governed truncation, the
    first retained record's prev_hash points to a removed record and is
    unverifiable by construction (conflict C5) — it is accepted when the file
    ENDS with a checkpoint_record (truncated_count > 0) and the head carries a
    well-formed hex prev_hash. Everywhere else prev_hash is checked strictly.
    """
    if len(records) > RETENTION_MAX:
        if not records or records[-1]["record_type"] != CHECKPOINT_RECORD:
            return "degraded"
    for i, rec in enumerate(records):
        if i == 0:
            if rec["prev_hash"] is None:
                continue
            tail = records[-1]
            compacted = (
                tail["record_type"] == CHECKPOINT_RECORD
                and isinstance(tail["data"].get("truncated_count"), int)
                and tail["data"]["truncated_count"] > 0
                and _is_sha_hex(rec["prev_hash"]))
            if not compacted:
                return "degraded"
            continue
        if rec["prev_hash"] != record_hash(records[i - 1]):
            return "degraded"
    return "healthy"


def segment_hash(truncated_records: list) -> str:
    """sha256 over all records being truncated (canonical JSONs concatenated).

    checkpoint_record.segment_hash per mvp-data-models §1.
    """
    joined = "".join(canonical_json(r) for r in truncated_records)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def make_checkpoint_data(truncated_records: list) -> dict:
    """checkpoint_record payload {segment_hash, truncated_count}."""
    return {
        "segment_hash": segment_hash(truncated_records),
        "truncated_count": len(truncated_records),
    }


def plan_truncation(records: list, count: int):
    """Return the records to remove, or raise ValueError.

    Truncation without a PRECEDING checkpoint_record is prohibited
    (mvp-data-models §1 Retention): the LAST record must be a
    checkpoint_record whose truncated_count equals ``count`` and whose
    segment_hash covers exactly the ``count`` oldest records. The checkpoint
    itself survives the truncation and moves to the tail of the retained
    segment. Removing the entire file is refused (empty = corrupt-adjacent
    state is only legal via 0-byte fresh files).
    """
    if not isinstance(count, int) or count <= 0:
        raise ValueError(f"truncated_count must be a positive int, got {count!r}")
    if not records:
        raise ValueError("cannot truncate an empty registry")
    if count >= len(records):
        raise ValueError("cannot truncate all records: at least one must remain")
    checkpoint = records[-1]
    if checkpoint["record_type"] != CHECKPOINT_RECORD:
        raise ValueError(
            "truncation requires a preceding checkpoint_record "
            "(mvp-data-models §1 Retention)")
    expected = make_checkpoint_data(records[:count])
    if (checkpoint["data"].get("truncated_count") != expected["truncated_count"]
            or checkpoint["data"].get("segment_hash") != expected["segment_hash"]):
        raise ValueError(
            "trailing checkpoint_record does not match the records being truncated")
    return records[:count]


def approval_is_expired(approval: dict, now_iso: str, expiry_min: int) -> bool:
    """Return True when the approval's created_at is older than ``expiry_min``
    minutes from ``now_iso``.

    Parses ISO 8601 ``Z`` timestamps (mvp-interfaces §5).  Fail-closed:
    returns True when ``created_at``/``issued_at`` is absent or malformed,
    or when ``now_iso`` is malformed — callers must treat such approvals as
    expired.
    """
    created = approval.get("created_at") or approval.get("issued_at")
    if not isinstance(created, str) or not created.endswith("Z"):
        return True
    try:
        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return True
    try:
        now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return True
    delta = (now_dt - created_dt).total_seconds()
    return delta >= expiry_min * 60
