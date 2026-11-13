"""CLI wrapper for the Documenter Service MVP — same core as the MCP path.

mvp-contract §1: "a CLI wrapper exposes the same core so MCP and CLI results
cannot diverge". The MCP stdio transport is reserved (the MVP build ships no
server entry point); this module's Service is the composition root the future
MCP adapter must reuse unchanged — CLI --audit / --status / --delegate-preview
call the very core functions, no parallel logic.

Usage:
    python3 -m documenter_service --status [--json]
    python3 -m documenter_service --audit --target "*" [--severity-min low]
                                  [--pre-check] [--scan-cursor TOKEN] [--json]
    python3 -m documenter_service --delegate-preview --target <id>
                                  --change-type update --trust-level review
                                  --diff-base64 <b64> | --diff-file <path|->

Environment (mvp-data-models §5): DOCUMENTER_POLICY_PATH (default
documenter_policy.yml), DOCUMENTER_DATA_DIR (default documenter/),
DOCUMENTER_LOG_LEVEL.

Exit codes (fixed here and in README):
    0  success — the operation completed (findings do NOT change the exit
       code: audit is read-only diagnostics, not a gate; the gate semantics
       live in severity/next_action)
    2  structured refusal — a StructuredError was raised (off-manifest target,
       tier interlock, token replay, gate/policy failure, corrupt registry
       refusal...): one JSON error object on stdout, next_action inside
    3  internal error — an unexpected defect (fail loud with traceback on
       stderr; this is `unknown`-territory: a bug, not operator action)

stdout discipline: event lines ({"event_type": ..., "payload": ...}) may
interleave before the final response line; the LAST stdout line is the
response (human text, or one JSON object with --json).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

from .adapters.diff_engine import MAX_DIFF_BYTES_DEFAULT, StdDiffEngine
from .adapters.fs_manifest import FsManifestSource
from .adapters.jsonl_registry import JsonlAuditRegistry
from .adapters.stdout_events import StdoutEventSink
from .adapters.worker_stub import InterlockedWorkerStub
from .core.audit import audit, delegate_preview
from .core.errors import StructuredError
from .core.policy import PolicyError, load_policy
from .core.status import status as status_core

__all__ = ["Service", "main"]

_HELP = ("Documenter Service MVP scaffold (Tier 0-1, read-only): audit(), "
         "documenter.status(), delegate(preview: true). Exit codes: 0 success; "
         "2 structured refusal; 3 internal error.")


def _env_path(root: str, name: str, default_rel: str, env=None) -> str:
    environ = os.environ if env is None else env
    value = environ.get(name) or default_rel
    return value if os.path.isabs(value) else os.path.join(root, value)


class Service:
    """Composition root: ports → adapters → core functions.

    The MCP stdio server (reserved) will construct THIS class, not a second
    wiring, so CLI and MCP results cannot diverge (mvp-contract §1 transport
    rationale).
    """

    def __init__(self, root: str, *, events=None, registry=None,
                 manifest=None, env=None) -> None:
        self.root = os.path.abspath(root)
        self._env = os.environ if env is None else env
        data_dir = _env_path(self.root, "DOCUMENTER_DATA_DIR",
                             os.path.join("documenter"), self._env)
        self.registry = registry or JsonlAuditRegistry(data_dir)
        self.manifest = manifest or FsManifestSource(self.root)
        self.events = events or StdoutEventSink()
        self.engine = StdDiffEngine()
        self.worker = InterlockedWorkerStub()  # Tier 2+ stub, always locked

    # -- policy (degradation-tolerant: audit/status never blocked by it) ----

    def load_policy_safe(self):
        """Return (policy, PolicyError|None). Callers surface the error via
        delegate()/CLI stderr — audit() and status() proceed regardless."""
        manifest_ids = None
        try:
            manifest_ids = {e["id"] for e in self.manifest.entries()}
        except StructuredError:
            pass  # rule 5 target validation is skipped without manifest ids
        try:
            return load_policy(self.root, env=self._env,
                               manifest_ids=manifest_ids), None
        except PolicyError as exc:
            return None, exc

    # -- operations -----------------------------------------------------------

    def audit(self, **kwargs) -> dict:
        if self.registry.status() == "corrupt":
            raise StructuredError(
                "gate_failure",
                "audit registry is corrupt — audit_record persistence is "
                "impossible, so audit() fails closed (restore the registry "
                "from git; mvp-data-models §1). status() reports details.")
        policy, _ = self.load_policy_safe()
        ceiling = kwargs.pop(
            "rescan_batch_ceiling",
            int(policy.get("rescan_batch_ceiling")) if policy else 50)
        return audit(self.root, self.registry, self.manifest, self.events,
                     rescan_batch_ceiling=ceiling, **kwargs)

    def status(self, target_id=None) -> dict:
        policy, _ = self.load_policy_safe()
        return status_core(self.registry, policy, target_id=target_id)

    def delegate(self, *, target_id, change_type, trust_level, diff_input,
                 preview) -> dict:
        """delegate(preview: true) only — no write branch exists.

        Order of refusals (structural interlock supersedes policy-level gates,
        mvp-contract §MVP boundary): non-preview write intent → tier_interlock
        /preview_denied WITHOUT consulting policy; corrupt registry →
        gate_failure (mvp-interfaces §3: "On corrupt, delegate() returns
        gate_failure"); then preview proceeds, exempt from policy state — a
        broken policy only downgrades max_diff_bytes to the documented 512 KiB
        default (stderr warning). The gate_failure mapping of PolicyError
        (policy_structured_error) is kept for the Tier 2+ write branch and is
        exercised by unit tests directly.
        """
        if preview is not True:
            raise StructuredError(
                "tier_interlock",
                "delegate() write intent is refused in the MVP build: the "
                "write branch is structurally absent (mvp-contract §MVP "
                "boundary). Invoke with preview: true.")
        if self.registry.status() == "corrupt":
            raise StructuredError(
                "gate_failure",
                "audit registry is corrupt — delegate() denied (restore the "
                "registry from git; status() reports details). The MVP has "
                "no override path (override_gate is Tier 2+, structurally "
                "absent).")
        policy, policy_err = self.load_policy_safe()
        if policy_err is not None:
            print(f"WARNING: policy unavailable for delegate(preview) — "
                  f"using default max_diff_bytes: {policy_err.reason}",
                  file=sys.stderr)
        cap = int(policy.get("max_diff_bytes")) if policy else MAX_DIFF_BYTES_DEFAULT
        return delegate_preview(self.root, self.manifest,
                                target_id=target_id, change_type=change_type,
                                trust_level=trust_level, diff_input=diff_input,
                                preview=preview, engine=self.engine,
                                max_diff_bytes=cap)


def _print_json(obj) -> None:
    print(json.dumps(obj, sort_keys=True, ensure_ascii=False))


def _print_status_human(resp: dict) -> None:
    reg = resp["registry"]
    print(f"active_tier: {resp['active_tier']}")
    print(f"registry.status: {reg['status']}")
    la = reg["last_audit"]
    if la:
        print(f"registry.last_audit: {la['audit_id']} "
              f"issued_at={la['issued_at']} fresh={la['fresh']}")
    else:
        print("registry.last_audit: none")
    print(f"registry.staged_files: {len(reg['staged_files'])}")
    print(f"registry.override_counter: {reg['override_counter']}")
    ss = resp["scan_status"]
    print(f"scan_status.has_pending_scan: {ss['has_pending_scan']}")
    print(f"tier_interlock.tier_2_plus_locked: "
          f"{resp['tier_interlock']['tier_2_plus_locked']}")
    print(f"tier_interlock.reason: {resp['tier_interlock']['reason']}")


def _print_audit_human(resp: dict) -> None:
    print(resp["report"]["header"])
    for f in resp["report"]["findings"]:
        print(f"subject={f['subject_id']} severity={f['severity']} "
              f"{f['description']} -> {f['suggested_action']}")
    cov = resp["coverage"]
    print(f"coverage: {cov['scanned_count']}/{cov['total_count']} "
          f"{cov['status']}; has_remaining={resp['has_remaining']}")


def _print_delegate_human(resp: dict) -> None:
    print(f"diff_hash: {resp['diff_hash']}")
    print(f"derived_trust_level: {resp['derived_trust_level']}")
    print(f"derived_trust_reason: {resp['derived_trust_reason']}")
    print(f"next_action: {resp['next_action']}")
    for f in resp["findings"]:
        print(f"finding: subject={f['subject_id']} severity={f['severity']} "
              f"{f['description']}")
    print("--- diff_text ---")
    sys.stdout.write(resp["diff_text"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="documenter_service",
                                     description=_HELP)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--status", action="store_true",
                      help="documenter.status(): registry health, pending "
                           "scan, tier interlock")
    mode.add_argument("--audit", action="store_true",
                      help="audit(): read-only compliance report")
    mode.add_argument("--delegate-preview", action="store_true",
                      dest="delegate_preview",
                      help="delegate(preview: true): canonical diff preview")
    parser.add_argument("--root", default=os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))),
                        help="repository root (default: parent of the package)")
    parser.add_argument("--json", action="store_true", dest="json_mode",
                        help="emit the response as one JSON object on stdout "
                             "(last line; event lines precede it)")

    # audit options
    parser.add_argument("--target", default="*",
                        help='audit/delegate target manifest id, or "*" (default)')
    parser.add_argument("--severity-min", default="low", dest="severity_min",
                        choices=["low", "medium", "high", "critical"],
                        help="minimum severity to include (default low)")
    parser.add_argument("--pre-check", action="store_true", dest="pre_check",
                        help="audit() synchronous gate verdict event")
    parser.add_argument("--scan-cursor", default=None, dest="scan_cursor",
                        help="continuation token from a prior partial scan")

    # delegate options
    parser.add_argument("--change-type", default=None, dest="change_type",
                        choices=["update", "split", "create_ru", "custom"])
    parser.add_argument("--trust-level", default=None, dest="trust_level",
                        choices=["safe", "review"])
    parser.add_argument("--diff-base64", default=None, dest="diff_base64",
                        help="base64-encoded UTF-8 diff for --delegate-preview")
    parser.add_argument("--diff-file", default=None, dest="diff_file",
                        help="path holding the base64 payload, or - for stdin")

    args = parser.parse_args(argv)
    service = Service(args.root)

    try:
        if args.status:
            resp = service.status(target_id=None)
            if args.json_mode:
                _print_json(resp)
            else:
                _print_status_human(resp)
            return 0
        if args.audit:
            resp = service.audit(target_id=args.target,
                                 severity_min=args.severity_min,
                                 pre_check=args.pre_check,
                                 scan_cursor=args.scan_cursor)
            if args.json_mode:
                _print_json(resp)
            else:
                _print_audit_human(resp)
            return 0
        # --delegate-preview
        if not args.change_type or not args.trust_level:
            print("ERROR: --delegate-preview requires --change-type and "
                  "--trust-level", file=sys.stderr)
            return 2
        if args.diff_base64 is not None:
            payload = args.diff_base64
        elif args.diff_file is not None:
            payload = (sys.stdin.read() if args.diff_file == "-" else
                       open(args.diff_file, encoding="utf-8").read())
        else:
            print("ERROR: --delegate-preview requires --diff-base64 or "
                  "--diff-file", file=sys.stderr)
            return 2
        resp = service.delegate(target_id=args.target,
                                change_type=args.change_type,
                                trust_level=args.trust_level,
                                diff_input=payload.strip(), preview=True)
        if args.json_mode:
            _print_json(resp)
        else:
            _print_delegate_human(resp)
        return 0
    except StructuredError as exc:
        _print_json(exc.to_dict())
        return 2
    except Exception:
        print("documenter_service: INTERNAL ERROR — this is a bug, not your "
              "action (next_action would be escalate).", file=sys.stderr)
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(main())
