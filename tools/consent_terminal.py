#!/usr/bin/env python3
"""consent_terminal.py — Operator consent terminal for step-(5) changesets.

A file-based approval spool with HMAC-signed decisions, flock-protected JSONL
access, and a simple interactive review CLI.

Usage::

    python3 tools/consent_terminal.py request          # ingest draft → print review command
    python3 tools/consent_terminal.py review             # operator review one-shot
    python3 tools/consent_terminal.py review --request-id <id>

Importable API::

    import consent_terminal as ct
    record = ct.create_request(state_root_or_draft, state_root=repo_root)
    pending = ct.read_pending(state_root=repo_root)
    pruned = ct.prune_pending(state_root=repo_root)
    ok = ct.verify_decision(pending_record, decision_record, state_root=repo_root)
    changed = ct.mark_consumed(request_id, state_root=repo_root)
    result = ct.decide(record, ["y", "n"])
"""
from __future__ import annotations

import argparse
import datetime
import fcntl
import hashlib
import hmac
import json
import os
import random
import secrets
import shutil
import select
import sys
import termios
import tty

# ---------------------------------------------------------------------------
# Paths (relative to state_root)
# ---------------------------------------------------------------------------
_DIR_INTENT = os.path.join("documenter", "intent")
_DIR_DIFFS = os.path.join(_DIR_INTENT, "diffs")
_DIR_QUARANTINE = os.path.join(_DIR_INTENT, "quarantine")
_FILE_APPROVALS = os.path.join(_DIR_INTENT, "approvals.jsonl")
_FILE_DRAFT = os.path.join(_DIR_INTENT, "consent_draft.json")

# ---------------------------------------------------------------------------
# Repo root = parent of tools/
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_operator_id(state_root: str | None = None) -> str:
    """Return operator id from env or ~/.council file."""
    val = os.environ.get("COUNCIL_OPERATOR_ID")
    if val:
        return val.strip()
    cdir = os.path.expanduser("~/.council")
    fpath = os.path.join(cdir, "operator_id")
    if os.path.isfile(fpath):
        with open(fpath) as fh:
            line = fh.readline().strip()
            if line:
                return line
    return "agent"


def _get_operator_secret(state_root: str | None = None) -> str | None:
    """Return operator secret from env or ~/.council file, or None."""
    val = os.environ.get("COUNCIL_OPERATOR_SECRET")
    if val:
        return val
    cdir = os.path.expanduser("~/.council")
    fpath = os.path.join(cdir, "operator_secret")
    if os.path.isfile(fpath):
        with open(fpath) as fh:
            line = fh.readline().strip()
            if line:
                return line
    return None


# ---------------------------------------------------------------------------
# Helpers: JSONL flock read/write
# ---------------------------------------------------------------------------

def _jsonl_read_all(state_root: str) -> list[dict]:
    """Read all JSONL records from approvals.jsonl (shared-lock)."""
    path = os.path.join(state_root, _FILE_APPROVALS)
    if not os.path.exists(path):
        return []
    result: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_SH)
        try:
            for line in fh:
                stripped = line.strip()
                if stripped:
                    try:
                        result.append(json.loads(stripped))
                    except json.JSONDecodeError:
                        pass
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    return result


def _jsonl_write_all(state_root: str, records: list[dict]) -> None:
    """Rewrite the entire approvals.jsonl file under flock."""
    path = os.path.join(state_root, _FILE_APPROVALS)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        for rec in records:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
        fcntl.flock(fh, fcntl.LOCK_UN)


def _jsonl_append_locked(state_root: str, record: dict) -> None:
    """Append one record to approvals.jsonl under flock."""
    path = os.path.join(state_root, _FILE_APPROVALS)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.write(json.dumps(record, sort_keys=True) + "\n")
        fcntl.flock(fh, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# quarantine
# ---------------------------------------------------------------------------

def _quarantine(state_root: str, draft_path: str) -> None:
    """Move draft to documenter/intent/quarantine/<name>_<timestamp>."""
    qdir = os.path.join(state_root, _DIR_QUARANTINE)
    os.makedirs(qdir, exist_ok=True)
    base = os.path.basename(draft_path)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
    name = f"{base}_{ts}"
    dst = os.path.join(qdir, name)
    try:
        shutil.move(draft_path, dst)
    except shutil.Error:
        shutil.copy2(draft_path, dst)


# ---------------------------------------------------------------------------
# create_request — ingest draft → pending record
# ---------------------------------------------------------------------------

def create_request(
    state_root_or_draft: str,
    state_root: str | None = None,
    draft_path: str | None = None,
) -> dict:
    """Ingest a consent draft and create a pending approval request.

    The first positional argument is contextual. When state_root is provided
    as a keyword argument, it is used as the state directory root. Otherwise
    the first positional is treated as the state_root. The default draft
    location is ``documenter/intent/consent_draft.json`` under state_root.

    Parameters
    ----------
    state_root_or_draft : str
        State directory root, or a draft file path (when state_root kwarg
        is given this is ignored; state_root kwarg takes precedence).
    state_root : str, optional
        State directory root (keyword argument, overrides positional).
    draft_path : str, optional
        Relative path within state_root for the draft file.
        Defaults to "documenter/intent/consent_draft.json".

    Returns
    -------
    dict
        The pending record that was appended.

    Raises
    ------
    FileNotFoundError
        Draft file not found, or referenced diff file not found.
    ValueError
        Malformed JSON, missing/unknown keys, invalid tier, summary too long,
        diff too large (> 64 KB).
    """
    # Resolve actual state_root: kwarg wins, then positional
    actual_state_root = state_root or state_root_or_draft or _REPO_ROOT

    # Determine draft file path
    effective_draft_path = draft_path if draft_path is not None else _FILE_DRAFT
    draft_abs = os.path.join(actual_state_root, effective_draft_path)

    # --- Read draft file ---
    if not os.path.isfile(draft_abs):
        raise FileNotFoundError(f"Draft file not found: {draft_abs}")

    try:
        with open(draft_abs, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (json.JSONDecodeError, ValueError):
        _quarantine(actual_state_root, draft_abs)
        raise ValueError("Malformed JSON in draft file")

    if not isinstance(payload, dict):
        _quarantine(actual_state_root, draft_abs)
        raise ValueError("Draft is not a JSON object")

    # --- Validate required keys ---
    required_keys = {"target_path", "summary", "tier", "diff_file"}
    if not required_keys.issubset(payload.keys()):
        _quarantine(actual_state_root, draft_abs)
        missing = required_keys - payload.keys()
        raise ValueError(f"Missing required keys: {missing}")

    # --- Validate unknown keys ---
    allowed_keys = required_keys | {"expiry_minutes"}
    unknown = set(payload.keys()) - allowed_keys
    if unknown:
        _quarantine(actual_state_root, draft_abs)
        raise ValueError(f"Unknown draft keys: {unknown}")

    # --- Validate tier ---
    tier = payload["tier"]
    if tier not in ("safe", "review"):
        _quarantine(actual_state_root, draft_abs)
        raise ValueError(f"Invalid tier: {tier!r}; must be 'safe' or 'review'")

    # --- Validate summary length ---
    summary = payload["summary"]
    if len(summary) > 200:
        _quarantine(actual_state_root, draft_abs)
        raise ValueError(f"Summary too long ({len(summary)} > 200)")

    # --- Validate diff file ---
    diff_file = payload["diff_file"]
    diff_path = os.path.join(actual_state_root, _DIR_DIFFS, diff_file)
    if not os.path.isfile(diff_path):
        _quarantine(actual_state_root, draft_abs)
        raise FileNotFoundError(f"Diff file not found: {diff_path}")

    # --- Read diff content, check size ---
    with open(diff_path, "rb") as fh:
        diff_bytes = fh.read()

    if len(diff_bytes) > 64 * 1024:
        _quarantine(actual_state_root, draft_abs)
        raise ValueError(f"Diff file too large ({len(diff_bytes)} > 65536 bytes)")

    # --- Compute hash ---
    diff_hash = "sha256:" + hashlib.sha256(diff_bytes).hexdigest()

    # --- Generate request_id (hex8, collision-safe via secrets) ---
    _MAX_REROLL = 5
    for _attempt in range(_MAX_REROLL):
        request_id = secrets.token_hex(4)
        existing = _jsonl_read_all(actual_state_root)
        existing_ids = {r.get("request_id") for r in existing if r.get("request_id")}
        if request_id not in existing_ids:
            break
    else:
        request_id = secrets.token_hex(4)

    # --- Read diff as text ---
    diff_text = diff_bytes.decode("utf-8", errors="replace")

    # --- Compute expiry ---
    expiry_minutes = payload.get("expiry_minutes", 30)
    now = datetime.datetime.now(datetime.timezone.utc)
    created_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    deadline = now + datetime.timedelta(minutes=expiry_minutes)
    expiry_deadline = deadline.strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- Proposer id ---
    proposer = os.environ.get("COUNCIL_PROPOSER_ID", "agent")

    # --- Build record ---
    record = {
        "request_id": request_id,
        "target_path": payload["target_path"],
        "summary": summary,
        "tier": tier,
        "diff_hash": diff_hash,
        "diff_text": diff_text,
        "proposer_operator_id": proposer,
        "created_at": created_at,
        "expiry_deadline": expiry_deadline,
        "state": "pending",
        "single_use": True,
    }

    # --- Append to approvals.jsonl under flock ---
    _jsonl_append_locked(actual_state_root, record)

    # --- Remove draft ---
    if os.path.exists(draft_abs):
        os.remove(draft_abs)

    return record


# ---------------------------------------------------------------------------
# read_pending — latest-record-wins, ordered by created_at
# ---------------------------------------------------------------------------

def read_pending(state_root: str) -> list[dict]:
    """Read all records with latest-record-wins, ordered oldest-first.

    Parameters
    ----------
    state_root : str

    Returns
    -------
    list[dict]
        Records sorted by created_at ascending (oldest first).
        Latest record per request_id wins (append-only semantics).
    """
    records = _jsonl_read_all(state_root)

    # Latest-record-wins: for each request_id, keep the last record
    latest: dict[str, dict] = {}
    for rec in records:
        rid = rec.get("request_id")
        if rid:
            latest[rid] = rec

    result = list(latest.values())

    # Sort by created_at, oldest first
    result.sort(key=lambda r: r.get("created_at", ""))

    return result


# ---------------------------------------------------------------------------
# prune_pending — expire or integrity-fail → denied
# ---------------------------------------------------------------------------

def prune_pending(state_root: str) -> list[dict]:
    """Prune expired or integrity-failed records.

    Rewrites approvals.jsonl to remove pruned pending entries.

    Returns
    -------
    list[dict]
        List of denied records that replaced pruned pending entries.
    """
    now = datetime.datetime.now(datetime.timezone.utc)

    all_recs = _jsonl_read_all(state_root)

    # Latest-record-wins to find what each request_id looks like now
    latest: dict[str, dict] = {}
    for rec in all_recs:
        rid = rec.get("request_id")
        if rid:
            latest[rid] = rec

    pruned: list[dict] = []
    keep_recs: list[dict] = []

    for rid, rec in latest.items():
        if rec.get("state") != "pending":
            keep_recs.append(rec)
            continue

        reason = None

        # Check expiry first
        deadline_str = rec.get("expiry_deadline")
        if deadline_str:
            try:
                deadline = datetime.datetime.strptime(
                    deadline_str, "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=datetime.timezone.utc)
                if now > deadline:
                    reason = "expired"
            except (ValueError, TypeError):
                pass

        # Check integrity only if not already expired
        if reason is None:
            diff_text = rec.get("diff_text", "")
            diff_hash_val = rec.get("diff_hash", "")
            if diff_hash_val.startswith("sha256:"):
                expected = "sha256:" + hashlib.sha256(
                    diff_text.encode("utf-8", errors="replace")
                ).hexdigest()
                if not hmac.compare_digest(diff_hash_val, expected):
                    reason = "integrity_fail"

        if reason:
            denied = {
                "request_id": rec.get("request_id", ""),
                "state": "denied",
                "reason": reason,
                "original_diff_hash": rec.get("diff_hash", ""),
                "original_diff_text": rec.get("diff_text", ""),
                "signed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            keep_recs.append(denied)
            pruned.append(denied)
        else:
            keep_recs.append(rec)

    # Rewrite the file — pruned pending entries are gone
    _jsonl_write_all(state_root, keep_recs)

    return pruned


# ---------------------------------------------------------------------------
# verify_decision — HMAC verification of a decision record
# ---------------------------------------------------------------------------

def verify_decision(record: dict, decision: dict,
                    state_root: str | None = None) -> bool:
    """Verify a decision record's HMAC.

    Recomputes HMAC-SHA256 over the 5 signed fields using the operator
    secret, and compares with decision['hmac'].

    Parameters
    ----------
    record : dict
        The original pending record (provides fields when decision lacks them).
    decision : dict
        The decision record containing state and hmac.
    state_root : str, optional

    Returns
    -------
    bool
        True if the HMAC is valid, False otherwise.
    """
    if state_root is None:
        state_root = _REPO_ROOT

    secret = _get_operator_secret(state_root)
    if secret is None:
        return False

    # Build the 5 signed fields from the decision record
    signed_fields = {
        "created_at": decision.get("created_at", record.get("created_at", "")),
        "diff_hash": decision.get("diff_hash", record.get("diff_hash", "")),
        "proposer_operator_id": decision.get(
            "proposer_operator_id", record.get("proposer_operator_id", "")
        ),
        "request_id": decision.get("request_id", record.get("request_id", "")),
        "state": decision.get("state", record.get("state", "")),
    }

    canonical = json.dumps(signed_fields, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    expected = hmac.new(
        secret.encode("utf-8"), canonical, hashlib.sha256
    ).hexdigest()

    actual = decision.get("hmac", "")
    return hmac.compare_digest(actual, expected)


# ---------------------------------------------------------------------------
# mark_consumed — transition approved/denied → consumed
# ---------------------------------------------------------------------------

def mark_consumed(request_id: str, state_root: str) -> bool:
    """Mark a request as consumed if latest state is approved or denied.

    Parameters
    ----------
    request_id : str
    state_root : str

    Returns
    -------
    bool
        True if a consumed record was appended, False otherwise.
    """
    records = _jsonl_read_all(state_root)

    # Latest-record-wins
    latest: dict[str, dict] = {}
    for rec in records:
        rid = rec.get("request_id")
        if rid:
            latest[rid] = rec

    rec = latest.get(request_id)
    if rec is None:
        return False

    state = rec.get("state")
    if state not in ("approved", "denied"):
        return False

    consumed = {
        "request_id": request_id,
        "state": "consumed",
        "signed_at": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
    }
    _jsonl_append_locked(state_root, consumed)
    return True


# ---------------------------------------------------------------------------
# decide — pure function: record + keypresses → outcome
# ---------------------------------------------------------------------------

def decide(record: dict, keypresses: list[str]) -> str:
    """Evaluate a record against a list of keypresses (pure, no I/O).

    Returns one of: "approved", "denied", "no_decision", "confirming",
    "pending", "skipped_expired".

    Ctrl-C ("\\x03") and Ctrl-D ("\\x04") map to "denied". These are
    checked AFTER the expiry → skipped_expired guard but BEFORE tier
    logic, so an expired record cannot be overridden by a signal key.

    Parameters
    ----------
    record : dict
        The pending record.
    keypresses : list[str]
        Sequence of keypresses to process. Each call processes one.

    Returns
    -------
    str
        Decision outcome.
    """
    rec_state = record.get("state")
    tier = record.get("tier")

    # Missing state or tier → skip
    if rec_state not in ("pending",) or tier is None:
        return "skipped_expired"

    # Check expiry
    deadline_str = record.get("expiry_deadline")
    if deadline_str:
        try:
            deadline = datetime.datetime.strptime(
                deadline_str, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=datetime.timezone.utc)
            now = datetime.datetime.now(datetime.timezone.utc)
            if now > deadline:
                return "skipped_expired"
        except (ValueError, TypeError):
            pass

    if not keypresses:
        return "pending"

    k = keypresses[0]

    # Ctrl-C / Ctrl-D → denied (after expiry, before tier)
    if k in ("\x03", "\x04"):
        return "denied"

    if k == "q":
        return "no_decision"
    if k == "n":
        return "denied"
    if k == "y":
        if tier == "review":
            return "confirming"
        else:
            return "approved"
    if k == "\n":
        if tier == "review":
            return "approved"
        return "pending"

    # Unknown key
    return "pending"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="consent_terminal.py",
        description="Operator consent terminal for step-(5) documentation "
                    "changesets.",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser(
        "request",
        help="Ingest consent draft and print review command.",
    )

    review_p = sub.add_parser(
        "review",
        help="Operator review: present pending request, decide.",
    )
    review_p.add_argument(
        "--request-id", default=None,
        help="Specific request ID to review (default: oldest pending).",
    )

    return parser


def _cmd_request(state_root: str) -> int:
    """Handle the 'request' subcommand."""
    try:
        rec = create_request(state_root, state_root=state_root)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(
        f"tools/consent_review.sh --request-id {rec['request_id']}"
    )
    return 0


def _cmd_review(state_root: str, request_id: str | None = None) -> int:
    """Handle the 'review' subcommand."""
    pruned = prune_pending(state_root)
    print(f"Pruned {len(pruned)} items")

    records = read_pending(state_root)

    # F9 — present PENDING only (single-use)
    pending_records = [r for r in records if r.get("state") == "pending"]

    record = None
    if request_id:
        for r in pending_records:
            if r.get("request_id") == request_id:
                record = r
                break
    if record is None:
        record = pending_records[0] if pending_records else None

    if record is None:
        print("No pending requests.")
        return 0

    rid = record.get("request_id", "?")
    target = record.get("target_path", "?")
    tier = record.get("tier", "?")
    summary = record.get("summary", "?")
    diff_hash_full = record.get("diff_hash", "")
    diff_hash_prefix = (
        diff_hash_full.split(":", 1)[1][:8] if ":" in diff_hash_full else "?"
    )

    print(f"Request: {rid}")
    print(f"Target:  {target}")
    print(f"Tier:    {tier}")
    print(f"Diff:    {diff_hash_prefix}...")
    print(f"Summary: {summary}")

    # F4 — diff stats
    diff_text_raw = record.get("diff_text", "")
    add_count = sum(1 for ln in diff_text_raw.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
    del_count = sum(1 for ln in diff_text_raw.splitlines() if ln.startswith("-") and not ln.startswith("---"))
    print(f"Stats:   +{add_count} -{del_count}")

    # F4 — expiry countdown
    deadline_str = record.get("expiry_deadline")
    if deadline_str:
        try:
            deadline = datetime.datetime.strptime(
                deadline_str, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=datetime.timezone.utc)
            now = datetime.datetime.now(datetime.timezone.utc)
            delta = deadline - now
            if delta.total_seconds() > 0:
                total_seconds = int(delta.total_seconds())
                mm = total_seconds // 60
                ss = total_seconds % 60
                print(f"Expires: {deadline_str} ({mm}m {ss}s left)")
            else:
                print(f"Expires: {deadline_str} (expired)")
        except (ValueError, TypeError):
            print("Expires: ?")
    else:
        print("Expires: ?")

    op_id = _get_operator_id(state_root)
    op_secret = _get_operator_secret(state_root)

    if op_secret is None:
        print("Error: No operator secret found "
              "(COUNCIL_OPERATOR_SECRET env "
              "var or ~/.council/operator_secret)",
              file=sys.stderr)
        return 2

    outcome: str | None = None
    use_termios = False
    try:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        tty.setraw(fd)
        use_termios = True
    except (termios.error, OSError):
        use_termios = False

    # F6 — engagement gate
    confirming = False

    try:
        while outcome is None:
            print(f"\nDecision for {rid} [{tier}] "
                  f"(y/n/s/q, Enter to expand): ", end="", flush=True)
            try:
                if use_termios:
                    # F7 — raw mode: normalize Enter
                    if select.select([sys.stdin], [], [], None)[0]:
                        raw = os.read(sys.stdin.fileno(), 1)
                        k = raw.decode("ascii", errors="replace")
                        if k == "\r":
                            k = "\n"
                    else:
                        k = ""
                else:
                    # F8 — non-raw: EOF → denied, empty → Enter
                    try:
                        line = sys.stdin.readline()
                    except (KeyboardInterrupt, EOFError):
                        line = ""
                    if line == "":
                        outcome = "denied"
                        break
                    k = line.strip()
                    if k == "":
                        k = "\n"
            except (KeyboardInterrupt, EOFError):
                outcome = "denied"
                break

            # F5 — 's' shows verbatim diff (before decide)
            if k == "s":
                print("--- BEGIN DIFF (verbatim) ---")
                print(record.get("diff_text", ""), end="")
                print("--- END DIFF ---")
                continue

            # F6 — Enter: expand only unless confirming
            if k == "\n" and not confirming and tier == "review":
                print("--- BEGIN DIFF (verbatim) ---")
                print(record.get("diff_text", ""), end="")
                print("--- END DIFF ---")
                continue

            result = decide(record, [k])

            if result == "pending":
                continue
            if result == "skipped_expired":
                print("Record expired. Denied.")
                outcome = "denied"
                break
            if result == "confirming":
                confirming = True
                print("(confirm with Enter to approve)")
                continue
            if result in ("approved", "denied", "no_decision"):
                outcome = result
                break

    finally:
        if use_termios:
            try:
                termios.tcsetattr(
                    sys.stdin.fileno(), termios.TCSADRAIN, old_settings)
            except (termios.error, OSError):
                pass

    if outcome in ("approved", "denied"):
        now_str = datetime.datetime.now(
            datetime.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        signed = {
            "request_id": record["request_id"],
            "diff_hash": record["diff_hash"],
            "proposer_operator_id": record.get(
                "proposer_operator_id", ""),
            "state": outcome,
            "created_at": record.get("created_at", now_str),
        }
        canonical = json.dumps(
            signed, sort_keys=True, separators=(",", ":")).encode("utf-8")
        h = hmac.new(
            op_secret.encode("utf-8"), canonical, hashlib.sha256
        ).hexdigest()

        decision = {
            "request_id": record["request_id"],
            "state": outcome,
            "approver_operator_id": op_id,
            "diff_hash": record["diff_hash"],
            "proposer_operator_id": record.get(
                "proposer_operator_id", ""),
            "created_at": record.get("created_at", now_str),
            "hmac": h,
            "signed_at": now_str,
        }
        if outcome == "denied":
            decision["reason"] = "operator_deny"
        _jsonl_append_locked(state_root, decision)

        prefix = "APPROVED" if outcome == "approved" else "DENIED"
        diff_prefix = record["diff_hash"].split(":", 1)[1][:8]
        print(
            f"{prefix} | id={record['request_id']} "
            f"| target={record.get('target_path', '?')} "
            f"| diff={diff_prefix} "
            f"| time={now_str}"
        )

    return {"approved": 0, "denied": 1, "no_decision": 0, None: 0}.get(
        outcome, 2)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    state_root = _REPO_ROOT

    if args.command == "request":
        return _cmd_request(state_root)
    if args.command == "review":
        return _cmd_review(state_root, args.request_id)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
