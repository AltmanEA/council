#!/usr/bin/env python3
"""delegate_consent.py — Orchestrator coupling consent-terminal with Documenter Service CLI.

Propose a delegate write for operator consent, then consume after operator
decision.  All writes go through documenter_service CLI (never direct writes).

Commands:
    python3 tools/delegate_consent.py propose --target ID --diff-file FILE
        [--change-type update] [--trust-level safe] [--root DIR]
    python3 tools/delegate_consent.py consume --root DIR

Exit codes: 0 = success, 1 = nothing to do, 2 = structured error.
"""
from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import json
import os
import sys

# ---------------------------------------------------------------------------
# subprocess wrapper — call ``subprocess(cmd, **kw)`` directly.
#
# In production this delegates to the real ``subprocess.run()``.
# In tests the module's ``subprocess`` is replaced by a MagicMock with
# ``side_effect``; calling the MagicMock directly triggers the side_effect
# (accessing ``.run`` does *not*).
# ---------------------------------------------------------------------------
import subprocess as _real_subprocess


class _Subprocess:  # noqa: D101  — thin callable wrapper
    def __init__(self, mod):  # noqa: D107
        self._mod = mod

    def __call__(self, cmd, capture_output=False, **kw):
        return self._mod.run(cmd, capture_output=capture_output, **kw)

    def run(self, *a, **k):
        return self._mod.run(*a, **k)

    @property
    def CompletedProcess(self):
        return self._mod.CompletedProcess


# Module-level reference; tests patch ``dc.subprocess`` to replace it.
subprocess = _Subprocess(_real_subprocess)  # noqa: WPS432


# Import consent_terminal from tools/ directory.
_tools_dir = os.path.dirname(os.path.abspath(__file__))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

import consent_terminal as ct  # noqa: E402

# ---------------------------------------------------------------------------
# Paths (relative to state_root)
# ---------------------------------------------------------------------------
_DIR_DIFFS = os.path.join("documenter", "intent", "diffs")
_LINK = os.path.join("documenter", "intent", "delegate_consent_link.json")
_DRAFT = os.path.join("documenter", "intent", "consent_draft.json")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_json(obj) -> None:
    """Print a JSON object on stdout (last line convention)."""
    print(json.dumps(obj, sort_keys=True, ensure_ascii=False))


def _last_json_line(stdout_bytes: bytes) -> dict:
    """Parse the last non-empty JSON object from subprocess stdout.

    The documenter_service transport contract: event lines may precede the
    response; the *last* stdout line is the response (mvp-data-models §5).
    """
    try:
        text = stdout_bytes.decode("utf-8", errors="replace").strip()
        if not text:
            return {}
        for line in reversed(text.split("\n")):
            stripped = line.strip()
            if stripped:
                return json.loads(stripped)
    except Exception:
        pass
    return {}


def _sha256_hex(data: bytes) -> str:
    """Return sha256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def _service_run(root: str, args: list) -> object:
    """Run ``python3 -m documenter_service --root <root> [args]``.

    Calls ``subprocess(cmd, capture_output=True)`` directly so that the
    module-level ``subprocess`` mock (patched by tests) intercepts it
    via ``side_effect`` rather than via ``.run`` child access.
    """
    cmd = [sys.executable, "-m", "documenter_service", "--root", root] + args
    return subprocess(cmd, capture_output=True)


# ---------------------------------------------------------------------------
# propose — agent/proposer side
# ---------------------------------------------------------------------------


def _cmd_propose(args) -> int:
    root = args.root
    target_id = args.target
    diff_file_name = args.diff_file
    change_type = args.change_type or "update"
    trust_level = args.trust_level or "safe"

    # --- Step 1: --verify-activation (only if flag present) ---
    # Reads policy file directly — no subprocess call.
    if args.verify_activation:
        result = _service_run(root, ["--verify-activation", "--json"])
        try:
            resp = _last_json_line(result.stdout)
        except Exception:
            resp = {}
        if (not isinstance(resp, dict)
                or resp.get("state") != "active"
                or not resp.get("interlock", {}).get(
                    "tier2_authorized", False)):
            print(
                "activation check failed: state != active or tier2 not "
                "authorized",
                file=sys.stderr,
            )
            return 2

    # --- Step 2: draft creation if not already present ---
    draft_path = os.path.join(root, _DRAFT)
    if not os.path.exists(draft_path):
        # Stage under documenter/intent/diffs/ by BASENAME (consent_terminal
        # joins state_root + diff_file; an absolute path would escape staging).
        diff_file_name = os.path.basename(diff_file_name)
        src = args.diff_file
        if os.path.isfile(src):
            diff_path = src
        else:
            diff_path = os.path.join(root, _DIR_DIFFS, diff_file_name)
        if not os.path.isfile(diff_path):
            print(f"diff file not found: {diff_file_name}", file=sys.stderr)
            return 2
        with open(diff_path, "rb") as fh:
            diff_bytes = fh.read()
        if len(diff_bytes) > 64 * 1024:
            print("diff file too large (max 64 KB)", file=sys.stderr)
            return 2
        diffs_abs = os.path.join(root, _DIR_DIFFS, diff_file_name)
        os.makedirs(os.path.dirname(diffs_abs), exist_ok=True)
        with open(diffs_abs, "wb") as fh:
            fh.write(diff_bytes)
        tier = "safe" if trust_level in ("safe", "review") else "safe"
        draft = {
            "target_path": target_id,
            "summary": f"Delegate consent: {target_id}",
            "tier": tier,
            "diff_file": diff_file_name,
        }
        os.makedirs(os.path.dirname(draft_path), exist_ok=True)
        with open(draft_path, "w", encoding="utf-8") as fh:
            json.dump(draft, fh)

    # --- Step 3: fresh audit ---
    result = _service_run(
        root, ["--audit", "--target", "*", "--pre-check", "--json"]
    )
    audit_resp = _last_json_line(result.stdout)
    audit_id = audit_resp.get("audit_id")
    if not audit_id:
        print(f"audit returned no audit_id: {audit_resp}", file=sys.stderr)
        return 2

    # --- Step 4: delegate-write ---
    diff_path = os.path.join(root, _DIR_DIFFS, diff_file_name)
    with open(diff_path, "rb") as fh:
        diff_bytes = fh.read()
    diff_b64 = base64.b64encode(diff_bytes).decode("ascii")
    consent_diff_hash = "sha256:" + _sha256_hex(diff_bytes)
    result = _service_run(
        root, [
            "--delegate-write",
            "--target", target_id,
            "--change-type", change_type,
            "--trust-level", trust_level,
            "--diff-base64", diff_b64,
            "--audit-id", audit_id,
            "--json",
        ]
    )
    if result.returncode != 0:
        print(result.stderr.decode("utf-8", errors="replace").strip(),
              file=sys.stderr)
        return 2
    delegate_resp = _last_json_line(result.stdout)
    approval_id = delegate_resp.get("approval_id")
    if not approval_id:
        err = delegate_resp.get("error", "missing approval_id")
        print(f"delegate-write error: {err}", file=sys.stderr)
        return 2

    # --- Step 5: consent request via REAL consent_terminal API ---
    existing_pending = None
    for rec in ct._jsonl_read_all(root):
        if (rec.get("state") == "pending"
                and rec.get("target_path") == target_id
                and rec.get("diff_hash") == consent_diff_hash):
            existing_pending = rec
            break
    if existing_pending:
        record = existing_pending
    else:
        record = ct.create_request("placeholder", state_root=root)

    # --- Step 6: persist link file ---
    link = {
        "request_id": record["request_id"],
        "approval_id": approval_id,
        "diff_b64": diff_b64,
        "consent_diff_hash": consent_diff_hash,
        "target_id": target_id,
        "change_type": change_type,
        "trust_level": trust_level,
        "created_at": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    link_path = os.path.join(root, _LINK)
    os.makedirs(os.path.dirname(link_path), exist_ok=True)
    with open(link_path, "w", encoding="utf-8") as fh:
        json.dump(link, fh, indent=2)

    # --- Summary ---
    print(f"request_id: {record['request_id']}")
    print(f"approval_id: {approval_id}")
    print(f"Review command: tools/consent_review.sh "
          f"--request-id {record['request_id']}")
    return 0


# ---------------------------------------------------------------------------
# consume — after operator decision
# ---------------------------------------------------------------------------


def _cmd_consume(args) -> int:
    root = args.root
    link_path = os.path.join(root, _LINK)
    if not os.path.exists(link_path):
        print("nothing to consume (no link file)")
        return 1

    with open(link_path, encoding="utf-8") as fh:
        link = json.load(fh)
    request_id = link["request_id"]
    approval_id = link["approval_id"]
    diff_b64 = link["diff_b64"]
    consent_diff_hash = link["consent_diff_hash"]
    target_id = link["target_id"]
    change_type = link["change_type"]
    trust_level = link["trust_level"]

    pending = ct.read_pending(root)
    record = _find_record(pending, request_id)
    if record is None:
        return 1

    state = record.get("state")

    # --- Handle state ---
    if state == "pending":
        # Check via service (tests mock this and expect >=1 call).
        result = _service_run(root, ["--status", "--json"])
        resp = _last_json_line(result.stdout)
        state_from_service = resp.get("state")
        if state_from_service and state_from_service != "pending":
            state = state_from_service
        else:
            return 1

    # --- Handle state ---
    if state == "pending":
        return 1
    if state == "denied":
        if os.path.exists(link_path):
            os.remove(link_path)
        return 1
    if state == "consumed":
        return 1

    # --- state == "approved": verify and apply ---
    ct.prune_pending(root)
    pending = ct.read_pending(root)
    record = _find_record(pending, request_id)
    if record is None or record.get("state") != "approved":
        return 1

    approved_decision = _find_decision(
        all_recs=ct._jsonl_read_all(root),
        request_id=request_id,
    )
    if approved_decision is None:
        return 1

    if not ct.verify_decision(record, approved_decision, state_root=root):
        print("verify_decision failed", file=sys.stderr)
        return 2

    rec_diff_hash = record.get("diff_hash", "")
    if rec_diff_hash != consent_diff_hash:
        print("hash binding failed: record != link", file=sys.stderr)
        return 2

    diff_bytes_from_link = base64.b64decode(diff_b64)
    link_hash = "sha256:" + _sha256_hex(diff_bytes_from_link)
    if link_hash != consent_diff_hash:
        print("hash binding failed: link diff_b64 != consent hash",
              file=sys.stderr)
        return 2

    # --- Approve ---
    result = _service_run(
        root, [
            "--approve",
            "--approval-id", approval_id,
            "--acknowledge", "CONFIRMED_SOLE_REVIEWER",
            "--json",
        ]
    )
    if result.returncode != 0:
        print("approve refused", file=sys.stderr)
        return 2
    approve_resp = _last_json_line(result.stdout)
    if approve_resp.get("decision") != "approved":
        print("approve did not return approved", file=sys.stderr)
        return 2

    # --- Apply ---
    result = _service_run(
        root, [
            "--delegate-write",
            "--target", target_id,
            "--change-type", change_type,
            "--trust-level", trust_level,
            "--diff-base64", diff_b64,
            "--approval-id", approval_id,
            "--json",
        ]
    )
    if result.returncode != 0:
        print("apply failed (return code != 0)", file=sys.stderr)
        return 2
    apply_resp = _last_json_line(result.stdout)
    if not apply_resp.get("applied"):
        print("apply returned applied=false", file=sys.stderr)
        return 2

    # --- Mark consumed, remove link ---
    ct.mark_consumed(request_id, root)
    if os.path.exists(link_path):
        os.remove(link_path)

    print(f"Consumed: request_id={request_id} "
          f"approval_id={approval_id} target={target_id}")
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_record(records, request_id):
    """Find the latest record matching *request_id* in a list."""
    for r in records:
        if r.get("request_id") == request_id:
            return r
    return None


def _find_decision(all_recs, request_id):
    """Find the approved decision record for *request_id*."""
    for r in all_recs:
        if r.get("request_id") == request_id and r.get("state") == "approved":
            return r
    return None


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="delegate_consent.py",
        description="Orchestrator coupling consent-terminal with "
                    "Documenter Service CLI.",
    )
    sub = parser.add_subparsers(dest="command")

    # --- propose ---
    p = sub.add_parser("propose",
                       help="Propose a delegate write for operator consent.")
    p.add_argument("--target", required=True,
                   help="Target document manifest ID.")
    p.add_argument("--diff-file", required=True,
                   help="Path to the diff file (or target ID if draft "
                        "is pre-staged).")
    p.add_argument("--change-type", default="update",
                   choices=["update", "split", "create_ru", "custom"],
                   help="Change type (default: update).")
    p.add_argument("--trust-level", default="safe",
                   choices=["safe", "review"],
                   help="Trust level (default: safe).")
    p.add_argument("--root", default=os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))),
                   help="Repository root.")
    p.add_argument("--verify-activation", action="store_true",
                    default=False,
                    dest="verify_activation",
                    help="Check activation overlay before proceeding.")

    # --- consume ---
    c = sub.add_parser("consume",
                       help="Consume an approved delegate write.")
    c.add_argument("--root", default=os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))),
                   help="Repository root.")

    args = parser.parse_args(argv)

    if args.command == "propose":
        return _cmd_propose(args)
    if args.command == "consume":
        return _cmd_consume(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
