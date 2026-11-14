"""CLI wrapper for the Documenter Service MVP — same core as the MCP path.

mvp-contract §1: "a CLI wrapper exposes the same core so MCP and CLI results
cannot diverge". This module's Service is the composition root the MCP adapter
also reuses unchanged — CLI --audit / --status / --delegate-preview and
MCP tools/call call the very core functions, no parallel logic.

Tier 2+ write branch (preview=False): --delegate-write, --approve,
--override-gate. Operator identity from environment (COUNCIL_OPERATOR_ID),
never from client-supplied parameters (operator-surface §AuthN).

Usage:
    python3 -m documenter_service --status [--json]
    python3 -m documenter_service --audit --target "*" [--severity-min low]
                                  [--pre-check] [--scan-cursor TOKEN] [--json]
    python3 -m documenter_service --delegate-preview --target <id>
                                  --change-type update --trust-level review
                                  --diff-base64 <b64> | --diff-file <path|->
                                  [--audit-id <audit_id>]
    python3 -m documenter_service --delegate-write --target <id>
                                  --change-type update --trust-level review
                                  --diff-base64 <b64> | --diff-file <path|->
                                  [--audit-id <audit_id>] [--approval-id <id>]
    python3 -m documenter_service --approve --approval-id <id> [--json]
    python3 -m documenter_service --override-gate --target <id>
                                  --diff-hash <sha256:...> --reason <text>
                                  [--audit-id <audit_id>] [--json]
    python3 -m documenter_service --mcp   # MCP stdio JSON-RPC mode

Environment (mvp-data-models §5): DOCUMENTER_POLICY_PATH (default
documenter_policy.yml), DOCUMENTER_DATA_DIR (default documenter/),
DOCUMENTER_LOG_LEVEL.

Tier 2+ ingress: COUNCIL_OPERATOR_ID (regex ^op-[a-z0-9][a-z0-9-]{2,63}$).
The operator_id is resolved from os.environ at call time for every CLI
invocation (fresh read each process) and from the MCP server's environment
on each tools/call.

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

In --mcp mode, stdout carries ONLY JSON-RPC 2.0 messages; events from the
Service's EventSink go to stderr.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback

from .adapters.diff_engine import MAX_DIFF_BYTES_DEFAULT, StdDiffEngine
from .adapters.fs_manifest import FsManifestSource
from .adapters.jsonl_registry import JsonlAuditRegistry
from .adapters.stdout_events import StdoutEventSink
from .adapters.file_events import FileEventSink
from .adapters.worker_stub import InterlockedWorkerStub
from .adapters.hash_store import HashStore
from .core.audit import audit, delegate_preview
from .core.errors import StructuredError
from .core.override import override_gate as _override_gate_core  # Tier 2+
from .core.policy import PolicyError, load_policy
from .core.status import status as status_core
from .core import write as core_write  # W2: write branch
from .core import patterns as core_patterns  # Tier 3 pattern auto-apply

__all__ = ["Service", "main", "resolve_operator_id"]

# ---------------------------------------------------------------------------
# DOCUMENTER_LOG_LEVEL — stderr warning filter (mvp-data-models §5)
# ---------------------------------------------------------------------------
#: Log level severity ranks (used for comparison against threshold).
_STDERR_LOG_RANK = {"debug": 10, "info": 20, "warn": 30, "error": 40}


def _stderr_log(msg: str, level: str = "warn", env=None) -> None:
    """Emit a service warning to stderr, filtered by DOCUMENTER_LOG_LEVEL.

    Never writes to stdout (transport contract: last stdout line is the
    response).  Unknown configured levels fall back to "info".

    IMPORTANT: This helper is for SERVICE-WARNING messages (e.g. degraded
    policy state).  Usage errors — mandatory argument missing, invalid CLI
    argument — are NOT filtered by this helper; they write directly to
    stderr via print(..., file=sys.stderr) to guarantee visibility per the
    exit-code contract (0=success, 2=structured refusal, 3=internal error).
    """
    e = env if env is not None else os.environ
    configured = str(e.get("DOCUMENTER_LOG_LEVEL", "info")).lower()
    threshold = _STDERR_LOG_RANK.get(configured, _STDERR_LOG_RANK["info"])
    if _STDERR_LOG_RANK.get(level, _STDERR_LOG_RANK["warn"]) >= threshold:
        print(msg, file=sys.stderr)

_HELP = ("Documenter Service MVP scaffold (Tier 0-1 read-only, Tier 2+ write): "
         "audit(), status(), delegate(preview: true). "
         "Tier 2+ write CLI flags: --delegate-write, --approve, "
         "--override-gate (operator from COUNCIL_OPERATOR_ID env, not CLI param). "
         "Cold-start reconcile: --reconcile (exit 0; needs_attention "
         "reported in JSON). "
         "Exit codes: 0 success; 2 structured refusal; 3 internal error. "
         "Use --mcp for MCP stdio JSON-RPC transport.")


# ---------------------------------------------------------------------------
# AuthN: resolve_operator_id
# ---------------------------------------------------------------------------
#: Regex for valid operator IDs (mvp-interfaces §5).
_OPERATOR_ID_RE = re.compile(r"^op-[a-z0-9][a-z0-9-]{2,63}$")


def resolve_operator_id(environ) -> str:
    """Resolve the authenticated operator from process environment.

    AuthN decision (mvp-contract §AuthN; operator-surface §Documenter
    Integration): operator_id NEVER comes from client-supplied parameters.
    The trusted ingress is the process environment variable COUNCIL_OPERATOR_ID,
    validated against ``^op-[a-z0-9][a-z0-9-]{2,63}$``.

    The operator_id is resolved from os.environ at call time for every CLI
    invocation (fresh read each process) and from the MCP server's
    environment on each tools/call.  Consequence: a single MCP process has
    one operator identity — the self-approval guard in core/write.approve
    forces approval from a DIFFERENT process/env (true out-of-band).

    Returns the validated operator_id string or raises StructuredError.
    """
    oid = environ.get("COUNCIL_OPERATOR_ID")
    if not oid or not _OPERATOR_ID_RE.match(oid):
        raise StructuredError(
            "unknown",
            "authenticated operator ingress missing: set COUNCIL_OPERATOR_ID "
            "(operator-surface §AuthN; expected "
            r"^op-[a-z0-9][a-z0-9-]{2,63}$)")
    return oid


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
        self._data_dir = data_dir
        self.registry = registry or JsonlAuditRegistry(data_dir)
        self.manifest = manifest or FsManifestSource(self.root)
        if events is not None:
            # Caller provided an explicit events sink (e.g. MCP path); use it.
            self.events = events
        else:
            # Default: file persistence in corpus-audit + stdout (mvp-contract
            # §1 — MVP carrier is stdout JSON; file adds durable replay).
            self.events = FileEventSink(
                os.path.join(data_dir, "corpus-audit"))
        self.engine = StdDiffEngine()
        self.worker = InterlockedWorkerStub()  # Tier 2+ stub, always locked
        self.hash_store = HashStore(data_dir, self.root)
        # -- policy cache (mvp-data-models §5; load_policy_safe called once
        #    per instance, not on every operation) ---------------------------
        self._cached_policy = None  # Policy | None
        self._cached_policy_error = None  # PolicyError | None
        self._policy_warning_emitted = False  # ensure _stderr_log fires once

    # -- policy (degradation-tolerant: audit/status never blocked by it) ----

    def load_policy_safe(self):
        """Return (policy, PolicyError|None). Callers surface the error via
        delegate()/CLI stderr — audit() and status() proceed regardless.

        Policy is loaded once per Service instance and cached; subsequent calls
        return the cached result.  On first failure a degradation warning is
        emitted to stderr exactly once (not on every invocation).
        """
        if self._cached_policy_error is not None:
            # Already failed once — emit the degradation warning once.
            if not self._policy_warning_emitted:
                self._policy_warning_emitted = True
                _stderr_log(
                    f"WARNING: policy load failed — degraded: "
                    f"{self._cached_policy_error.reason}")
            return None, self._cached_policy_error
        if self._cached_policy is not None:
            return self._cached_policy, None
        # First load.
        manifest_ids = None
        try:
            manifest_ids = {e["id"] for e in self.manifest.entries()}
        except StructuredError:
            pass  # rule 5 target validation is skipped without manifest ids
        try:
            policy = load_policy(self.root, env=self._env,
                                 manifest_ids=manifest_ids)
            self._cached_policy = policy
            return policy, None
        except PolicyError as exc:
            self._cached_policy_error = exc
            self._policy_warning_emitted = True
            _stderr_log(
                f"WARNING: policy load failed — degraded: {exc.reason}")
            return None, exc

    # -- operations -----------------------------------------------------------

    def audit(self, **kwargs) -> dict:
        if self.registry.status() == "corrupt":
            raise StructuredError(
                "gate_failure",
                "audit registry is corrupt \u2014 audit_record persistence is "
                "impossible, so audit() fails closed (restore the registry "
                "from git; mvp-data-models \u00a71). status() reports details.")
        policy, _ = self.load_policy_safe()
        ceiling = kwargs.pop(
            "rescan_batch_ceiling",
            int(policy.get("rescan_batch_ceiling")) if policy else 50)
        # sync_latency_budget_ms from policy unless caller overrides.
        budget_ms = kwargs.pop(
            "sync_latency_budget_ms",
            int(policy.get("sync_latency_budget_ms")) if policy else 30000)
        resp = audit(self.root, self.registry, self.manifest, self.events,
                      rescan_batch_ceiling=ceiling,
                      sync_latency_budget_ms=budget_ms, **kwargs)
        # Update hash store for scanned IDs (only after successful audit).
        try:
            entries_list = self.manifest.entries()
            if kwargs.get("target_id") == "*":
                scope_ids = [e["id"] for e in entries_list]
            else:
                tid = kwargs.get("target_id", "*")
                manifest_ids = {e["id"] for e in entries_list}
                scope_ids = [tid] if tid in manifest_ids else []
            if scope_ids:
                self.hash_store.update(self.manifest, scope_ids)
        except Exception:
            pass  # hash store failure is non-blocking (rebuildable cache)
        return resp

    def status(self, target_id=None) -> dict:
        policy, _ = self.load_policy_safe()
        return status_core(self.registry, policy, target_id=target_id,
                           root=self.root)

    def delegate(self, *, target_id, change_type, trust_level, diff_input,
                 preview, audit_id=None, approval_id=None,
                 sync_latency_budget_ms=None) -> dict:
        """delegate(preview: true|false) — preview and write branch.

        ``sync_latency_budget_ms`` (mvp-interfaces §5): explicit caller
        override; None means take the policy value (default 30000).

        With preview=True: existing delegate_preview flow (unchanged).
        With preview=False (write branch, Tier 2+):
          policy, policy_err = load_policy_safe()  (NEVER silently proceed on None)
          check_tier2_authorized → tier_interlock on None/low tier.
          corrupt → gate_failure.
          Then: propose_write → returns approval_required + approval_id + diff_hash.
          If approval_id is supplied (re-invocation after approve), apply_write.

        Order of refusals for preview=False:
          (a) policy load → tier_interlock (policy None-safe via
              check_tier2_authorized).
          (b) corrupt registry → gate_failure.
          Then proceed through propose_write guards (see core/write.py).

        For preview=True: behavior is byte-identical to the pre-W2 build.
        """
        if preview is True:
            # --- preview path (UNCHANGED parity) -------------------------------
            if self.registry.status() == "corrupt":
                raise StructuredError(
                    "gate_failure",
                    "audit registry is corrupt — delegate() denied (restore the "
                    "registry from git; status() reports details). The MVP has "
                    "no override path (override_gate is Tier 2+, structurally "
                    "absent).")
            # load_policy_safe emits the degradation warning exactly once per
            # instance (policy cache); do not re-emit here (would repeat per
            # call and double-log alongside the cached warning).
            policy, _ = self.load_policy_safe()
            cap = int(policy.get("max_diff_bytes")) if policy else MAX_DIFF_BYTES_DEFAULT
            freshness = (int(policy.get("audit_freshness")) if policy else 30)
            budget_ms = (sync_latency_budget_ms if sync_latency_budget_ms
                         is not None else
                         int(policy.get("sync_latency_budget_ms")) if policy
                         else 30000)
            return delegate_preview(self.root, self.manifest,
                                    target_id=target_id, change_type=change_type,
                                    trust_level=trust_level, diff_input=diff_input,
                                    preview=preview, engine=self.engine,
                                    max_diff_bytes=cap,
                                    audit_id=audit_id, registry=self.registry,
                                    audit_freshness_min=freshness,
                                    sync_latency_budget_ms=budget_ms)

        # --- write branch (preview=False) ------------------------------------
        policy, policy_err = self.load_policy_safe()
        # NEVER silently proceed on None: pass policy through;
        # check_tier2_authorized handles None → tier_interlock.

        if self.registry.status() == "corrupt":
            raise StructuredError(
                "gate_failure",
                "audit registry is corrupt — delegate() denied (restore the "
                "registry from git; status() reports details).")

        cap = int(policy.get("max_diff_bytes")) if policy else MAX_DIFF_BYTES_DEFAULT

        if approval_id:
            # Re-invocation after approve: apply the write. operator_id comes
            # from authenticated ingress ONLY (operator-surface §AuthN):
            # COUNCIL_OPERATOR_ID in the environment. The target_id is NEVER
            # a stand-in principal.
            operator_id = self._env.get("COUNCIL_OPERATOR_ID")
            if not operator_id:
                raise StructuredError(
                    "unknown",
                    "apply requires authenticated operator ingress: set "
                    "COUNCIL_OPERATOR_ID (operator-surface §AuthN); "
                    "this is a deployment defect, not operator action")
            budget_ms = (sync_latency_budget_ms if sync_latency_budget_ms
                         is not None else
                         int(policy.get("sync_latency_budget_ms"))
                         if policy else 30000)
            return self.apply(approval_id, operator_id, diff_input,
                              max_diff_bytes=cap,
                              sync_latency_budget_ms=budget_ms)

        # propose_write (full guard chain, see core/write.py)
        operator_id = self._env.get("COUNCIL_OPERATOR_ID")
        budget_ms = (sync_latency_budget_ms if sync_latency_budget_ms
                     is not None else
                     int(policy.get("sync_latency_budget_ms"))
                     if policy else 30000)
        return core_write.propose_write(
            self.root, self.manifest, self.registry, policy, self.events,
            self.engine,
            target_id=target_id, change_type=change_type,
            trust_level=trust_level, diff_input=diff_input,
            audit_id=audit_id,
            proposer_id=operator_id,
            max_diff_bytes=cap,
            sync_latency_budget_ms=budget_ms,
        )

    def approve(self, approval_id: str, operator_id: str) -> dict:
        """Approve a pending write proposal (Tier 2+).

        See core_write.approve for full step list.
        """
        policy, _ = self.load_policy_safe()
        return core_write.approve(self.registry, policy, self.events,
                                  root=self.root,
                                  approval_id=approval_id, operator_id=operator_id)

    def apply(self, approval_id: str, operator_id: str, diff_input: str,
              *, max_diff_bytes: int = 524288,
              sync_latency_budget_ms: int = 30000) -> dict:
        """Apply an approved write (Tier 2+, called after approve).

        Invokes apply_write with the same diff_input for hash verification.
        """
        policy, _ = self.load_policy_safe()
        return core_write.apply_write(
            self.root, self.manifest, self.registry, policy, self.events,
            self.engine,
            approval_id=approval_id, operator_id=operator_id,
            diff_input=diff_input,
            max_diff_bytes=max_diff_bytes,
            data_dir=self._data_dir,
            sync_latency_budget_ms=sync_latency_budget_ms,
        )

    def override_gate(self, *, target_id, diff_hash, reason, operator_id,
                      audit_id=None) -> dict:
        """Override an audit-gate failure (mvp-contract §2.2.6, §4).

        Bound to one (target_id, diff_hash); one consumption; emits event;
        unavailable for critical findings.  next_action is "rerun_audit"
        because after an override the caller must re-audit/re-propose.
        """
        policy, _ = self.load_policy_safe()
        return _override_gate_core(
            self.root, self._data_dir, self.registry, policy, self.events,
            target_id=target_id, diff_hash=diff_hash, reason=reason,
            operator_id=operator_id, audit_id=audit_id,
        )

    def reconcile(self) -> dict:
        """Cold-start reconcile of unresolved intent records.

        Delegates to core.write.reconcile; returns a structured result
        with resolutions list, needs_attention boolean, and counts.

        Returns
        -------
        dict with keys: resolutions (list), needs_attention (bool),
        counts (dict with reconciled / needs_attention).
        Exit code is always 0 on success even if needs_attention is true.
        """
        resolutions = core_write.reconcile(
            self.registry, self.manifest, self.root, self._data_dir)

        needs_attention = any(
            r.get("status") not in ("reconciled", "clean", "noop")
            for r in resolutions
        )
        reconciled_count = sum(
            1 for r in resolutions
            if r.get("status") in ("reconciled", "clean", "noop")
        )
        attention_count = len(resolutions) - reconciled_count

        return {
            "resolutions": resolutions,
            "needs_attention": needs_attention,
            "counts": {
                "reconciled": reconciled_count,
                "needs_attention": attention_count,
            },
        }

    # -- Tier 3 pattern auto-apply (mvp-contract §4 row 4) --------------------

    def pattern_auto_apply(
        self, *, pattern_id, proposals, operator_id
    ) -> dict:
        """Auto-apply a batch of proposals under a Tier 3 pattern.

        Thin wiring: load policy → delegate to core.patterns.apply_pattern_batch.
        """
        policy, _ = self.load_policy_safe()
        return core_patterns.apply_pattern_batch(
            self.root, self.manifest, self.registry, policy,
            self.events, self.engine,
            pattern_id=pattern_id,
            proposals=proposals,
            operator_id=operator_id,
        )

    def record_approval_viewed(self, *, approval_id) -> dict:
        """Mark an approval record as viewed (append-only).

        Thin wiring: delegate to core.patterns.record_viewed.
        """
        return core_patterns.record_viewed(
            self.registry, approval_id=approval_id
        )


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


def _print_delegate_write_human(resp: dict) -> None:
    """Human output for --delegate-write (preview=False write branch).

    Prints approval_id, diff_hash, and next_action.
    """
    print(f"diff_hash: {resp['diff_hash']}")
    print(f"approval_id: {resp.get('approval_id', 'N/A')}")
    print(f"derived_trust_level: {resp['derived_trust_level']}")
    print(f"derived_trust_reason: {resp['derived_trust_reason']}")
    print(f"next_action: {resp['next_action']}")
    if resp.get("approval_required"):
        print("approval_required: true — await approval before applying")


def _print_approve_human(resp: dict) -> None:
    """Human output for --approve."""
    print(f"approval_id: {resp['approval_id']}")
    print(f"decision: {resp['decision']}")
    print(f"next_action: {resp['next_action']}")


def _print_override_human(resp: dict) -> None:
    """Human output for --override-gate."""
    print(f"override_id: {resp['override_id']}")
    print(f"target_id: {resp['target_id']}")
    print(f"diff_hash: {resp['diff_hash']}")
    print(f"reason: {resp['reason']}")
    print(f"next_action: {resp['next_action']}")


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
    mode.add_argument("--delegate-write", action="store_true",
                      dest="delegate_write",
                      help="delegate(preview: false): Tier 2+ write intent "
                           "(requires --change-type, --trust-level, --diff-base64/-file, "
                           "optional --audit-id and --approval-id)")
    mode.add_argument("--approve", action="store_true",
                      help="approve: approve a pending write (requires --approval-id)")
    mode.add_argument("--override-gate", action="store_true",
                      help="override_gate: override audit-gate failure "
                           "(requires --target, --diff-hash, --reason)")
    mode.add_argument("--mcp", action="store_true",
                      help="MCP stdio JSON-RPC transport (stdout=RPC, "
                           "stderr=events)")
    mode.add_argument("--rebuild-hashes", action="store_true",
                      help="rebuild hashes.json from manifest entries "
                           "(cold-start integrity / full rescan)")
    mode.add_argument("--reconcile", action="store_true",
                      help="reconcile: cold-start resolution of leftover "
                           "intent records (exit 0; needs_attention is "
                           "reported in JSON)")
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
    parser.add_argument("--audit-id", default=None, dest="audit_id",
                        help="audit_id for pre-audit gate on delegate preview")
    parser.add_argument("--approval-id", default=None, dest="approval_id",
                        help="approval_id for --delegate-write (apply branch) "
                             "or --approve (approval decision)")
    parser.add_argument("--diff-hash", default=None, dest="diff_hash",
                        help="diff_hash for --override-gate")
    parser.add_argument("--reason", default=None, dest="reason",
                        help="reason for --override-gate")

    args = parser.parse_args(argv)
    service = Service(args.root)

    try:
        if args.mcp:
            from .mcp_stdio import serve
            svc = Service(args.root,
                          events=StdoutEventSink(sys.stderr))
            serve(svc,
                  stdin=sys.stdin, stdout=sys.stdout,
                  stderr=sys.stderr)
            return 0
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
        # --rebuild-hashes
        if args.rebuild_hashes:
            rebuilt = service.hash_store.rebuild(service.manifest)
            resp = {"rebuilt_entries": len(rebuilt.get("entries", {})),
                    "path": service.hash_store._path}
            if args.json_mode:
                _print_json(resp)
            else:
                print(f"rebuilt_entries: {resp['rebuilt_entries']}")
                print(f"path: {resp['path']}")
            return 0
        # --reconcile
        if args.reconcile:
            resp = service.reconcile()
            _print_json(resp)
            return 0
        # --approve
        if args.approve:
            if not args.approval_id:
                print("ERROR: --approve requires --approval-id",
                      file=sys.stderr)
                return 2
            operator_id = resolve_operator_id(service._env)
            resp = service.approve(args.approval_id, operator_id)
            if args.json_mode:
                _print_json(resp)
            else:
                _print_approve_human(resp)
            return 0

        # --override-gate
        if args.override_gate:
            if not all((args.target, args.diff_hash, args.reason)):
                missing = []
                if not args.target:
                    missing.append("--target")
                if not args.diff_hash:
                    missing.append("--diff-hash")
                if not args.reason:
                    missing.append("--reason")
                print(f"ERROR: --override-gate requires {', '.join(missing)}",
                      file=sys.stderr)
                return 2
            operator_id = resolve_operator_id(service._env)
            resp = service.override_gate(
                target_id=args.target,
                diff_hash=args.diff_hash,
                reason=args.reason,
                operator_id=operator_id,
                audit_id=args.audit_id,
            )
            if args.json_mode:
                _print_json(resp)
            else:
                _print_override_human(resp)
            return 0

        # --delegate-preview or --delegate-write
        if not args.change_type or not args.trust_level:
            print("ERROR: --delegate-preview/--delegate-write requires "
                  "--change-type and --trust-level", file=sys.stderr)
            return 2
        if args.diff_base64 is not None:
            payload = args.diff_base64
        elif args.diff_file is not None:
            payload = (sys.stdin.read() if args.diff_file == "-" else
                       open(args.diff_file, encoding="utf-8").read())
        else:
            print("ERROR: --delegate-preview/--delegate-write requires "
                  "--diff-base64 or --diff-file", file=sys.stderr)
            return 2
        preview = True
        if args.delegate_write:
            preview = False
        resp = service.delegate(target_id=args.target,
                                change_type=args.change_type,
                                trust_level=args.trust_level,
                                diff_input=payload.strip(), preview=preview,
                                audit_id=args.audit_id,
                                approval_id=args.approval_id)
        if args.delegate_write:
            if args.json_mode:
                _print_json(resp)
            else:
                _print_delegate_write_human(resp)
        elif args.delegate_preview:
            if args.json_mode:
                _print_json(resp)
            else:
                _print_delegate_human(resp)
        return 0

        # Fallback (should not reach here given required=True on mode)
        parser.print_help()
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
