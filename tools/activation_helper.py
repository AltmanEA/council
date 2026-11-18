#!/usr/bin/env python3
"""activation_helper.py — Tier 2 activation operator helper (read-only).

Helps verify, inspect, and preview activation intent without mutating any
state.  Implements the four operator-facing subcommands described in the
Tier 2 activation overlay spec (Step 1, §7):

  verify                Verify effective activation and print diagnostics
  print-effective       Print effective policy / activation summary
  template              Print an example overlay YAML to stdout
  deactivate-hints      Print safe deactivation steps (no mutations)

Constraints:
  - Does NOT write ``documenter_policy.yml``.
  - Does NOT create files outside the workspace.
  - Does NOT create or remove the Operator Ingress sentinel.
  - No ``--apply`` that mutates activation state.

Usage::

    python3 tools/activation_helper.py verify --root .
    python3 tools/activation_helper.py print-effective --root .
    python3 tools/activation_helper.py template --scope pilot-safe-v1
    python3 tools/activation_helper.py deactivate-hints --root .

    python3 tools/activation_helper.py verify --root . --json  # machine-readable

Dependencies: stdlib + PyYAML only.  Reuses ``documenter_service.core``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Bootstrap sys.path so imports of documenter_service.core work.
# The repo root is the parent of tools/.
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import yaml  # noqa: E402  (stdlib+pyyaml only)


# ---------------------------------------------------------------------------
# Argparse setup
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="activation_helper.py",
        description="Tier 2 activation operator helper (read-only). "
                    "Verify, inspect, preview, and deactivation guidance "
                    "without mutating any state.",
    )
    parser.add_argument(
        "--root", default=os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))),
        help="Repository root path (default: parent of tools/).",
    )
    parser.add_argument(
        "--json", action="store_true", default=False,
        help="Produce JSON output on stdout (machine-readable).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -- verify -----------------------------------------------------------
    sub.add_parser("verify",
        help="Verify effective activation and print diagnostics "
             "(same checks as --verify-activation).")

    # -- print-effective --------------------------------------------------
    sub.add_parser("print-effective",
        help="Print effective policy / activation summary with expanded ops.")

    # -- template ---------------------------------------------------------
    tpl = sub.add_parser("template",
        help="Print an example overlay YAML to stdout (no file writes).")
    tpl.add_argument(
        "--scope", default="pilot-safe-v1",
        choices=["pilot-safe-v1", "docs-maint-safe",
                 "docs-content-review", "ru-sync-review"],
        help="Scope preset to use in the example (default: pilot-safe-v1).",
    )
    tpl.add_argument(
        "--briefing-ref", default=None,
        help="Example briefing_ref absolute path (default: "
             "/home/ea/.council/briefings/tier2-YYYYMMDD.md).",
    )
    tpl.add_argument(
        "--active-tier", default=2, type=int, dest="active_tier",
        help="Active tier for the example (default: 2).",
    )
    tpl_group = tpl.add_mutually_exclusive_group()
    tpl_group.add_argument(
        "--solo", action="store_true", default=False,
        help="Include solo approval fields in the example.",
    )
    tpl_group.add_argument(
        "--no-solo", action="store_true", default=True,
        help="Exclude solo approval fields (default).",
    )
    tpl.add_argument(
        "--min-delay", default=None, type=int, dest="min_delay",
        help="Example min_approval_delay_seconds (default: 300 when "
             "solo is shown).",
    )

    # -- deactivate-hints -------------------------------------------------
    sub.add_parser("deactivate-hints",
        help="Print safe deactivation steps (no file/sentinel changes).")

    return parser


# ---------------------------------------------------------------------------
# Helper: verify result builder (mirrors __main__._build_verify_activation_result)
# ---------------------------------------------------------------------------

def _build_verify_result(
    state: str,
    policy,
    policy_err,
    overlay,
    overlay_path: str | None,
    explicit: bool,
    root: str,
    overlay_load_error=None,
) -> dict:
    """Build the verify-activation response dict (read-only diagnostic)."""
    from documenter_service.core.policy import (
        operator_ingress_ready, OPERATOR_INGRESS_SENTINEL,
    )
    from documenter_service.core import scope_presets

    ok = state in ("baseline", "active")
    result: dict = {
        "mode": "verify-activation",
        "state": state,
        "ok": ok,
    }

    # Overlay info.
    result["overlay"] = {
        "present": overlay is not None or overlay_load_error is not None,
        "path": overlay_path,
        "explicit": explicit,
        "scope": None,
        "mode": None,
    }
    if overlay is not None and policy is not None:
        result["overlay"]["scope"] = getattr(
            policy, "activation_scope", None)
        result["overlay"]["mode"] = getattr(
            policy, "activation_mode", None)

    # Effective policy info.
    effective: dict = {
        "active_tier": 0,
        "allowed_operations_count": 0,
        "briefing_ref": None,
        "briefing_exists": None,
        "allow_solo_approval": False,
        "min_approval_delay_seconds": 0,
        "source": "base",
    }
    if policy is not None:
        effective["active_tier"] = policy.get("active_tier") or 0
        ops = policy.get("allowed_operations") or []
        effective["allowed_operations_count"] = len(ops)
        effective["briefing_ref"] = policy.get("briefing_ref")
        effective["allow_solo_approval"] = policy.get("allow_solo_approval")
        effective["min_approval_delay_seconds"] = (
            policy.get("min_approval_delay_seconds") or 0)
        effective["source"] = getattr(
            policy, "activation_source", "base")
        # briefing_exists
        br = policy.get("briefing_ref")
        if br and isinstance(br, str):
            br_path = br if os.path.isabs(br) else os.path.join(root, br)
            try:
                effective["briefing_exists"] = os.path.isfile(br_path)
            except Exception:
                effective["briefing_exists"] = None
        else:
            effective["briefing_exists"] = False

    result["effective"] = effective

    # Interlock readiness.
    sentinel_present = (
        operator_ingress_ready(root) if root else False
    )
    tier2_policy_ready = bool(
        policy is not None and policy.get("active_tier") >= 2
        and (policy.get("allowed_operations") or [])
        and policy.get("briefing_ref"))

    tier2_authorized = tier2_policy_ready and sentinel_present
    brief_exists = effective.get("briefing_exists")
    if tier2_policy_ready and brief_exists is False:
        tier2_authorized = False

    interlock_reasons: list[str] = []
    if not tier2_policy_ready:
        reasons: list[str] = []
        if not policy or policy.get("active_tier") < 2:
            reasons.append(
                f"active_tier={effective['active_tier']} < 2")
        if not (policy.get("allowed_operations") if policy else []):
            reasons.append("allowed_operations is empty")
        if not policy or not policy.get("briefing_ref"):
            reasons.append("briefing_ref is null")
        if reasons:
            interlock_reasons.append(
                "policy not ready: " + "; ".join(reasons))
    if not sentinel_present:
        sentinel_path = os.path.join(root, OPERATOR_INGRESS_SENTINEL)
        interlock_reasons.append(
            f"sentinel missing at {sentinel_path}")
    if effective.get("briefing_exists") is False:
        interlock_reasons.append("briefing file not found")

    reason_str = (
        "; ".join(interlock_reasons)
        if interlock_reasons
        else "all checks passed"
    )

    result["interlock"] = {
        "sentinel_present": sentinel_present,
        "tier2_policy_ready": tier2_policy_ready,
        "tier2_authorized": tier2_authorized,
        "reason": reason_str,
    }

    # Errors.
    errors: list[str] = []
    if state == "invalid":
        seen: set[str] = set()
        for err in (overlay_load_error, policy_err):
            if err and err.reason not in seen:
                errors.append(err.reason)
                seen.add(err.reason)
        if overlay is not None and policy is None and policy_err is None \
                and not overlay_load_error:
            errors.append(
                "overlay present but effective policy load failed")
    result["errors"] = errors

    # Expanded scope summary (when active with scope).
    if state == "active" and overlay is not None:
        scope_id = overlay.get("scope")
        if scope_id:
            try:
                preset_info = scope_presets.get_preset(scope_id)
                if preset_info:
                    result["scope_summary"] = _expand_scope_summary(
                        scope_id, preset_info)
            except Exception:
                pass

    return result


def _expand_scope_summary(scope_id: str, preset_info: dict) -> dict:
    """Build a concise scope summary for CLI output."""
    from documenter_service.core.scope_presets import expand

    ops_list = preset_info.get("operations", [])
    targets: list[str] = []
    for op in ops_list:
        targets.extend(op.get("targets", []))
    unique_targets = sorted(set(targets))

    return {
        "scope_id": scope_id,
        "description": preset_info.get("description", ""),
        "operation_count": len(ops_list),
        "target_count": len(unique_targets),
        "change_types": sorted(set(
            op.get("change_type", "") for op in ops_list if op.get("change_type")
        )),
        "trust_levels": sorted(set(
            op.get("trust_level", "") for op in ops_list if op.get("trust_level")
        )),
        "targets": unique_targets if len(unique_targets) <= 20 else None,
    }


def _ops_summary(policy) -> dict:
    """Build an expanded operations summary from an effective policy."""
    ops = policy.get("allowed_operations") or []
    summary_items: list[dict] = []
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            continue
        entry = {
            "index": i,
            "type": op.get("type", "operation"),
            "change_type": op.get("change_type"),
            "trust_level": op.get("trust_level"),
            "target_count": len(op.get("targets", [])),
        }
        # Include full target list for small sets (≤ 20).
        t = op.get("targets", [])
        if isinstance(t, list) and len(t) <= 20:
            entry["targets"] = sorted(t)
        else:
            entry["targets"] = f"[{len(t)} targets, omitted]"
        summary_items.append(entry)
    return {
        "count": len(summary_items),
        "operations": summary_items,
    }


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _cmd_verify(args) -> int:
    """verify — verify effective activation and print diagnostics."""
    from documenter_service.core.policy import PolicyError
    from documenter_service.core.activation import (
        load_activation_overlay, resolve_activation_path,
    )
    from documenter_service.core.policy import load_policy
    from documenter_service.core.status import status as status_core
    from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry
    from documenter_service.adapters.fs_manifest import FsManifestSource
    from documenter_service.__main__ import Service

    root = args.root
    service = Service(root)

    # 1) Resolve overlay path and explicit flag.
    overlay_path, explicit = resolve_activation_path(root, service._env)

    # 2) Attempt overlay load.
    overlay = None
    overlay_load_error = None
    try:
        overlay, loaded_path, exp = load_activation_overlay(root, service._env)
        overlay_path = loaded_path or overlay_path
        explicit = exp
    except PolicyError as exc:
        overlay_load_error = exc

    # 3) Attempt effective policy load.
    policy = None
    policy_err = None
    try:
        policy, policy_err = service.load_policy_safe()
    except Exception:
        pass

    # 4) Classify state.
    if (overlay is not None and policy is None and policy_err is not None) \
            or (overlay is None and explicit and overlay_load_error is not None):
        state = "invalid"
    elif overlay is not None and policy is not None:
        state = "active"
    else:
        state = "baseline"

    # 5) Build response dict.
    resp = _build_verify_result(
        state, policy, policy_err,
        overlay, overlay_path, explicit, root,
        overlay_load_error,
    )

    # 6) Emit output.
    if args.json:
        print(json.dumps(resp, sort_keys=True, ensure_ascii=False, indent=2))
    else:
        _print_verify_human(resp, state, policy, overlay)

    # 7) Exit code.
    return 0 if state in ("baseline", "active") else 2


def _print_verify_human(
    resp: dict, state: str, policy, overlay
) -> None:
    """Human-readable output for verify command."""
    print(f"State: {state}")

    if state == "baseline":
        print("No overlay applied; effective policy is Tier 1 baseline.")
        return

    overlay_info = resp.get("overlay", {})
    effective = resp.get("effective", {})
    interlock = resp.get("interlock", {})

    print(f"  Overlay present: {overlay_info.get('present')}")
    print(f"  Overlay path: {overlay_info.get('path') or 'N/A'}")
    print(f"  Explicit path: {overlay_info.get('explicit')}")
    print(f"  Scope: {overlay_info.get('scope') or 'N/A'}")
    print(f"  Mode: {overlay_info.get('mode') or 'N/A'}")
    print(f"  Source: {effective.get('source', 'N/A')}")
    print(f"  Effective active_tier: {effective.get('active_tier')}")
    print(f"  Allowed operations count: {effective.get('allowed_operations_count')}")
    print(f"  Briefing ref: {effective.get('briefing_ref') or 'null'}")

    solo = effective.get("allow_solo_approval")
    delay = effective.get("min_approval_delay_seconds")
    if solo is not None and delay is not None:
        print(f"  Allow solo approval: {bool(solo)}")
        print(f"  Min approval delay: {delay} seconds")

    # Readiness checklist.
    print()
    print("Interlock readiness:")

    sentinel = interlock.get("sentinel_present")
    print(f"  {'PASS' if sentinel else 'FAIL'} — sentinel present: {sentinel}")

    tier_ready = interlock.get("tier2_policy_ready")
    print(f"  {'PASS' if tier_ready else 'FAIL'} — tier2 policy ready")

    brief_exists = effective.get("briefing_exists")
    brief_str = "unknown" if brief_exists is None else str(brief_exists)
    print(f"  {'PASS' if brief_exists else 'FAIL'} — briefing exists: {brief_str}")

    authorized = interlock.get("tier2_authorized")
    print(f"  {'PASS' if authorized else 'FAIL'} — tier2 authorized")
    reason = interlock.get("reason", "")
    if reason and reason != "all checks passed":
        print(f"    Reason: {reason}")

    # Scope summary.
    summary = resp.get("scope_summary")
    if summary:
        print()
        print("Scope summary:")
        print(f"  id: {summary.get('scope_id')}")
        print(f"  description: {summary.get('description')}")
        print(f"  operation_count: {summary.get('operation_count')}")
        print(f"  target_count: {summary.get('target_count')}")
        print(f"  change_types: {summary.get('change_types', [])}")
        print(f"  trust_levels: {summary.get('trust_levels', [])}")
        targets = summary.get("targets")
        if targets:
            print("  targets:")
            for t in targets:
                print(f"    - {t}")
        else:
            print(f"  targets: ({summary.get('target_count', 0)} targets, "
                  "omitted from human output)")

    # Errors.
    errors = resp.get("errors", [])
    if errors:
        print()
        print("Errors:")
        for e in errors:
            print(f"  - {e}")


def _cmd_print_effective(args) -> int:
    """print-effective — print effective policy / activation summary."""
    from documenter_service.__main__ import Service

    root = args.root
    service = Service(root)

    policy, policy_err = service.load_policy_safe()

    if policy_err:
        if args.json:
            print(json.dumps({
                "error": policy_err.reason,
                "state": "policy_load_failed",
            }, indent=2))
        else:
            print(f"ERROR: policy load failed — {policy_err.reason}")
        return 2

    # Build output.
    activation = {
        "overlay_present": getattr(policy, "overlay_present", False),
        "overlay_path": getattr(policy, "overlay_path", None),
        "activation_scope": getattr(policy, "activation_scope", None),
        "activation_mode": getattr(policy, "activation_mode", None),
        "activation_source": getattr(policy, "activation_source", "base"),
    }
    effective_fields = {
        "active_tier": policy.get("active_tier"),
        "allowed_operations_count": len(policy.get("allowed_operations") or []),
        "briefing_ref": policy.get("briefing_ref"),
        "allow_solo_approval": policy.get("allow_solo_approval"),
        "min_approval_delay_seconds": policy.get("min_approval_delay_seconds"),
    }

    # Sentinel status.
    from documenter_service.core.policy import operator_ingress_ready
    sentinel = operator_ingress_ready(root) if root else False
    effective_fields["sentinel_present"] = sentinel

    # Expanded ops summary.
    ops_summary = _ops_summary(policy)

    # Scope summary from preset.
    scope_summary = None
    if activation.get("activation_scope"):
        from documenter_service.core import scope_presets
        preset_info = scope_presets.get_preset(
            activation["activation_scope"])
        if preset_info:
            scope_summary = _expand_scope_summary(
                activation["activation_scope"], preset_info)

    result = {
        "activation": activation,
        "effective_fields": effective_fields,
        "ops_summary": ops_summary,
        "scope_summary": scope_summary,
    }

    if args.json:
        print(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2))
    else:
        _print_effective_human(result)

    return 0


def _print_effective_human(result: dict) -> None:
    """Human-readable output for print-effective command."""
    act = result.get("activation", {})
    eff = result.get("effective_fields", {})

    print("=== Effective Policy / Activation Summary ===")
    print()

    print("Activation:")
    print(f"  overlay_present: {act.get('overlay_present')}")
    print(f"  overlay_path: {act.get('overlay_path') or 'N/A'}")
    print(f"  activation_scope: {act.get('activation_scope') or 'N/A'}")
    print(f"  activation_mode: {act.get('activation_mode') or 'N/A'}")
    print(f"  activation_source: {act.get('activation_source')}")

    print()
    print("Effective fields:")
    print(f"  active_tier: {eff.get('active_tier')}")
    print(f"  allowed_operations_count: {eff.get('allowed_operations_count')}")
    print(f"  briefing_ref: {eff.get('briefing_ref') or 'null'}")
    print(f"  allow_solo_approval: {eff.get('allow_solo_approval')}")
    print(f"  min_approval_delay_seconds: {eff.get('min_approval_delay_seconds')}")
    print(f"  sentinel_present: {eff.get('sentinel_present')}")

    # Ops summary.
    ops = result.get("ops_summary", {})
    print()
    print(f"Operations ({ops.get('count', 0)}):")
    for op in ops.get("operations", []):
        targets_str = ""
        if isinstance(op.get("targets"), list):
            targets_str = f" targets={op['targets']}"
        else:
            targets_str = f" targets=[{op.get('target_count', 0)}]"
        print(
            f"  [{op.get('index')}] "
            f"change_type={op.get('change_type')} "
            f"trust={op.get('trust_level')} "
            f"{targets_str}")

    # Scope summary.
    summary = result.get("scope_summary")
    if summary:
        print()
        print("Scope summary:")
        print(f"  id: {summary.get('scope_id')}")
        print(f"  description: {summary.get('description')}")
        print(f"  operation_count: {summary.get('operation_count')}")
        print(f"  target_count: {summary.get('target_count')}")
        targets = summary.get("targets")
        if targets:
            print("  targets:")
            for t in targets:
                print(f"    - {t}")
        else:
            print(f"  targets: ({summary.get('target_count', 0)} targets, "
                  "omitted from human output")


def _cmd_template(args) -> int:
    """template — print an example overlay YAML to stdout (no file writes)."""
    import datetime

    scope = args.scope
    briefing_ref = args.briefing_ref or (
        "/home/ea/.council/briefings/tier2-"
        + datetime.datetime.now().strftime("%Y%m%d") + ".md"
    )
    active_tier = args.active_tier
    include_solo = args.solo
    min_delay = args.min_delay

    overlay = {}

    # Required: exactly one of scope / allowed_operations.
    overlay["scope"] = scope

    overlay["active_tier"] = active_tier
    overlay["briefing_ref"] = briefing_ref

    if include_solo:
        overlay["allow_solo_approval"] = True
        if min_delay is not None:
            overlay["min_approval_delay_seconds"] = min_delay
        elif min_delay is None:
            overlay["min_approval_delay_seconds"] = 300

    # Emit YAML to stdout (comments preserved by PyYAML dumper).
    print(yaml.dump(
        overlay,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    ))

    return 0


def _cmd_deactivate_hints(args) -> int:
    """deactivate-hints — print safe deactivation steps (no mutations)."""
    root = args.root
    sentinel_path = os.path.join(root, "documenter", ".operator_ingress_ready")
    default_overlay = os.path.expanduser("~/.council/documenter_activation.yml")

    if args.json:
        hints = {
            "action": "deactivate-tier-2-activation",
            "steps": [
                {
                    "step": 1,
                    "title": "Neutralize the activation overlay file",
                    "details": (
                        f"Either remove or rename the overlay file "
                        f"{default_overlay!r}, or unset the "
                        f"DOCUMENTER_ACTIVATION_PATH environment variable. "
                        f"If using a custom path via DOCUMENTER_ACTIVATION_PATH, "
                        f"point it to a non-existent path or remove the overlay."
                    ),
                    "note": "The helper does NOT perform this action."
                },
                {
                    "step": 2,
                    "title": "Stop Operator Ingress and remove sentinel",
                    "details": (
                        f"Stop the Operator Ingress process and remove the "
                        f"readiness sentinel file at {sentinel_path!r}. "
                        f"This is required because Tier 2+ policy alone "
                        f"(without the sentinel) is insufficient for "
                        f"activation (dual interlock, ADR-013). "
                        f"The sentinel path is: "
                        f"{sentinel_path}"
                    ),
                    "note": "The helper does NOT perform this action."
                },
                {
                    "step": 3,
                    "title": "Verify Tier 1 baseline is restored",
                    "details": (
                        f"After the above steps, verify that "
                        f"the effective policy returns to Tier 1 "
                        f"baseline by running:\n\n"
                        f"  python3 -m documenter_service "
                        f"--verify-activation --root {root}\n\n"
                        f"or:\n\n"
                        f"  python3 tools/activation_helper.py "
                        f"verify --root {root}\n\n"
                        f"Expected state: baseline (active_tier=1, "
                        f"allowed_operations=empty)."
                    ),
                    "note": None
                },
            ],
            "guarantees": [
                "This helper does NOT write documenter_policy.yml.",
                "This helper does NOT create files outside the workspace.",
                "This helper does NOT create or remove the sentinel.",
                "All described actions are operator-performed steps.",
            ],
            "repo_policy": {
                "path": os.path.join(root, "documenter_policy.yml"),
                "current_tier": 1,
                "note": "documenter_policy.yml remains the Tier 1 baseline and is never rewritten by this mechanism.",
            },
        }
        print(json.dumps(hints, indent=2, ensure_ascii=False))
    else:
        print("=== Deactivation Hints ===")
        print()
        print("These steps return Tier 2+ activation to the Tier 1 baseline.")
        print("The helper does NOT perform any mutations — all steps must")
        print("be carried out by the operator.\n")

        print("Step 1: Neutralize the activation overlay file")
        print(f"  Either remove or rename:")
        print(f"    {default_overlay}")
        print(f"  Or unset the DOCUMENTER_ACTIVATION_PATH environment variable.")
        print("  (If using a custom path, point it to a non-existent file.)\n")

        print("Step 2: Stop Operator Ingress and remove sentinel")
        print(f"  Stop the Operator Ingress process and remove the readiness")
        print(f"  sentinel file at:")
        print(f"    {sentinel_path}")
        print(f"  This is required because Tier 2+ policy alone (without the")
        print(f"  sentinel) is insufficient for activation (dual interlock,")
        print(f"  ADR-013).")
        print()

        print("Step 3: Verify Tier 1 baseline is restored")
        print(f"  Run the following and confirm state: baseline")
        print(f"  active_tier: 1, allowed_operations: empty")
        print()
        print(f"  python3 -m documenter_service --verify-activation --root {root}")
        print(f"  # or:")
        print(f"  python3 tools/activation_helper.py verify --root {root}")
        print()
        print("Guarantees:")
        print("  - This helper does NOT write documenter_policy.yml.")
        print("  - This helper does NOT create files outside the workspace.")
        print("  - This helper does NOT create or remove the sentinel.")
        print("  - All described actions are operator-performed steps.")
        print()
        print("Repo policy note:")
        print(f"  {os.path.join(root, 'documenter_policy.yml')} "
              f"remains the Tier 1 baseline and is never rewritten by this mechanism.")

    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    handlers = {
        "verify": _cmd_verify,
        "print-effective": _cmd_print_effective,
        "template": _cmd_template,
        "deactivate-hints": _cmd_deactivate_hints,
    }

    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 2

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
