# Documenter Policy Reference

id: documenter-service-policy-reference
Version: 0.9.1-draft
Status: draft
Abstraction: reference
has_translation: docs/ru/documenter-service/legacy/policy-reference-RU.md
allow_non_index_paths: true
changelog-path: CHANGELOGS/documenter-policy-reference.changes.md

---

> **SUPERSEDED** (2026-11-19, sess-documenter-concept-revision). This document describes the abandoned Documenter design (trust tiers, policy engine, dual interlock, approval surface). It is archived for history only and is NOT normative: do not execute, implement, cite as current, or link from new documents as if active. The authoritative specification is `docs/en/documenter-service/index.md`.
## Purpose

Authoritative schema for the Documenter policy file: field definitions, load-time validation rules, operational tuning parameters, and the step-by-step tier authorization workflow. Protocol semantics these fields configure (trust tiers, safety protocol, interface contracts) are defined in `documenter-service/legacy/spec-v0.md`; runtime data structures (hash store, intent record, event schema) are defined in `documenter-service/configuration-guide.md`. This document defines no behavior of its own — it is the configuration surface for behavior defined elsewhere.

---

## Policy File

A YAML configuration defining which operations are permitted at each tier and compliance modes. Written and maintained by the operator. Time-based auto-proceed is not part of the model: approval is always an explicit operator action within a `delegate()` invocation, and the only auto-execution path is Tier 3 pattern-based auto-apply (see §Trust Tiers and §Approval semantics in the main spec, `documenter-service/legacy/spec-v0.md`).

**Validator rule:** Documenter MUST reject loading any policy file where `allowed_operations` is non-empty while `active_tier < 2`. This prevents misconfiguration during deployment. **Authority rule:** Policy entries may only tighten the built-in trust classification floor from the main spec (§Trust Classification): an `allowed_operations` entry may require `review` where the table permits `safe`, but a policy combination authorizing a `trust_level` below the *static floor* for its `change_type` is invalid and MUST be rejected at load time — Documenter treats it as a misconfiguration error, consistent with the validator rule above.

**Compatibility rule:** Every field in §Field Reference is optional except `version`, `active_tier`, and `allowed_operations`. A policy file written against an earlier schema version loads successfully: absent fields resolve to the defaults listed below, and no field removal or rename is implied by a schema version bump.

```yaml
documenter_policy:
  version: "0.2.0"
  active_tier: 0                  # 0 = audit-only (MVP default)
  allowed_operations: []          # inert at active_tier < 2; populate when advancing
  glossary_enforcement: draft     # draft | active — controls noise reduction
  audit_freshness: 30             # minutes; max age of audit_id accepted by delegate() pre-audit gate
  lock_wait_timeout: 30           # seconds; advisory lock acquisition wait before abort
  retry_backoff_base: 1           # seconds; exponential backoff base on hash_mismatch retry
  retry_max_attempts: 3           # count; retry attempts before escalation to operator
  operator_approval_timeout: 300  # seconds; synchronous wait for approve/reject inside delegate()
  notification_mode: inline       # inline only — no asynchronous notification channel exists
  approval_expiry_window: 30            # minutes; maximum time between Tier 2+ authorization and the first delegate() invocation under that approval
  rescan_batch_ceiling: 50        # documents per full-rescan invocation before partial-report return
  max_diff_bytes: 524288          # bytes; maximum size of a decoded diff payload (default 512 KiB)
  sync_latency_budget_ms: 30000   # milliseconds; a synchronous call exceeding this budget returns a structured timeout error instead of blocking
  glossary_staleness_days: 30     # days since last glossary modification; terms appearing ≥3 times within this window are flagged as missing
  briefing_ref: null              # path to operator briefing artifact; required when active_tier >= 2
  allow_solo_approval: false      # bool; solo (self-)approval exception per ADR-017; absent ⇒ false (fail-closed)
  min_approval_delay_seconds: 0   # int; minimum seconds between proposal and solo approval; range [60, 86400]; absent ⇒ 0
```

At Tier 0–1, `allowed_operations` must remain empty regardless of content. The operator updates this file explicitly when advancing tiers. Documenter refuses to execute any operation not listed.

**Preview exemption:** Calls to `delegate()` with no write intent (preview mode, returning diff without applying changes) are exempt from the `allowed_operations` check at all tiers. Tier 1 specifically relies on this exemption to produce diffs. These calls always return the computed diff but never modify files. Preview is controlled via the `preview` boolean parameter (§Interfaces, delegate()) — when set to `true`, no tier validation or gate enforcement applies; only schema validity of required fields (`target_id`, `change_type`, `diff`) is checked.

### Field Reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `version` | string | Yes | `"0.2.0"` | Policy schema version for compatibility detection |
| `active_tier` | int | Yes | `0` | Current trust tier (0–3). Must match Tier table (§Trust Tiers, main spec). |
| `allowed_operations` | array | Yes | `[]` | Operations authorized at current tier. Empty below Tier 2. May only tighten the trust floor (§Authority rule above). |
| `approval_expiry_window` | int | No | `30` | Maximum time (minutes) before an unapproved `approval_id` expires. Range: 5–1440 (5 minutes to 24 hours). Used together with the out-of-band `documenter.approve(approval_id, operator_id)` call specified in `documenter-service/mvp-contract.md` §4 (canonical approval contract). |
| `allow_solo_approval` | bool | No | `false` | Enables the solo-operator self-approval exception (`mvp-contract.md` §4, ADR-017) for the sole `op-*` identity. Absent ⇒ `false`: self-approval is denied (fail-closed), preserving the `approver ≠ proposer` norm. When `true`, solo approval additionally requires the matched operation to be `safe` (verified against the `change_type` persisted on the approval record), the acknowledgment token `CONFIRMED_SOLE_REVIEWER`, and the `min_approval_delay_seconds` window; the approve response carries a bias-warning banner. |
| `min_approval_delay_seconds` | int | No | `0` | Minimum seconds that must elapse between a proposal's `created_at` and its solo approval. Range: 60–86400. Applies only on the solo path (`allow_solo_approval: true`); out-of-range or non-integer values are rejected at policy load time. Missing or unparseable `created_at` during the delay check → `gate_failure` (fail-closed). Recommended minimum for a solo deployment: 300. |
| `audit_freshness` | int | No | `30` | Maximum age (minutes) of an `audit_id` accepted by the `delegate()` pre-audit gate. The gate additionally validates scope coverage (exact match or `*`), blocking findings, and scan completion (`has_remaining` must not be `true`) against the audit registry (`documenter-service/configuration-guide.md`, §Audit Registry). Set to `0` to disable the gate entirely (no audit required; `audit_id` will be ignored if provided). Any other value enforces the freshness window. |
| `briefing_ref` | string | No | `null` | Path to the archived operator briefing artifact documenting the scope of delegated authority. MUST be non-null when `active_tier >= 2` (§Authorization Workflow, step 4). |
| `glossary_enforcement` | enum | No | `draft` | Controls glossary compliance noise reduction (§Glossary Compliance, configuration guide). |
| `glossary_staleness_days` | int | No | `30` | Days since last glossary modification; terms appearing ≥3 times within this window are flagged as missing (§Glossary Compliance, configuration guide). |
| `lock_wait_timeout` | int | No | `30` | Seconds to wait for the operation-level advisory lock before aborting with the lock-owner error described in §Safety Protocol #2 (main spec). |
| `max_diff_bytes` | int | No | `524288` | Maximum size in bytes of a decoded `diff`/`diff_input` payload (default 512 KiB). A larger payload is rejected at ingress with a structured error before any diff processing. |
| `notification_mode` | enum | No | `inline` | Delivery mode for operator-facing prompts. `inline` is the only accepted value in MVP: prompts, diffs, and verdicts are returned inside the invocation response. Unknown values are rejected at load time. |
| `operator_approval_timeout` | int | No | `300` | Seconds the active `delegate()` invocation waits for an explicit approve/reject before emitting `error_category: operator_timeout`. Not an auto-approve window (§Approval semantics, main spec). |
| `rescan_batch_ceiling` | int | No | `50` | Documents processed per full-rescan invocation. When reached, the response includes `has_remaining: true` and a `scan_cursor` continuation token; passing it back resumes from where the previous invocation stopped. Partial scans never authorize delegates for unscanned documents — the operator must complete all batches before delegation is permitted. No background execution. |
| `retry_backoff_base` | int | No | `1` | Base delay (seconds) for the exponential backoff with jitter used by retry invocations (§Conflict Resolution, configuration guide). |
| `retry_max_attempts` | int | No | `3` | Maximum retry invocations after a `hash_mismatch` before Documenter escalates to the operator instead of retrying. |
| `temperature` | float | No | `0.1` | LLM generation randomness; higher values increase diversity (range: 0.0–2.0). Applied per role-agent inference (§Zero silent defaults, layer-1.md). |
| `top_p` | float | No | `0.9` | Nucleus sampling parameter; tokens with cumulative probability below this threshold are excluded (range: 0.0–1.0). Applied per role-agent inference (§Zero silent defaults, layer-1.md). |
| `sync_latency_budget_ms` | int | No | `30000` | Maximum duration in milliseconds for a synchronous `delegate()` call. A call exceeding this budget returns a structured timeout error rather than blocking indefinitely. |
| `frequency_penalty` | float | No | `0.0` | Reduces token repetition; positive values penalize repeated tokens (range: -2.0–2.0). Neutral default, explicitly set rather than inferred (§Zero silent defaults, layer-1.md). |

### Per-Operation Entries

Per-operation entries in `allowed_operations` follow this structure:

```yaml
# Tier 2+ operation entry (default type — no explicit type field needed):
allowed_operations:
  - type: operation          # operation | pattern — omitted defaults to "operation"
    change_type: update      # update | split | create_ru | custom
    trust_level: safe        # safe | review — must not fall below the static floor (§Trust Classification, main spec)
    targets: []              # empty = all docs; list = specific manifest IDs
    requires_diff_preview: true  # always enforced at Tier 2+

# Tier 3 pattern entry (enables auto-apply for matching changes):
  - type: pattern
    pattern_id: "auto-bump-patch"   # unique identifier for this pattern
    pattern_description: "Deterministic patch-level version bumps in CHANGELOGS/*.changes.md and index.md metadata"
    match_criteria:
      change_type: update
      file_pattern: "CHANGELOGS/*.changes.md"  # glob-style path pattern; empty = match any file
    trust_level: safe
    requires_diff_preview: true
```

Pattern entry fields:

| Field | Type | Description |
|-------|------|-------------|
| `type` | `operation` \| `pattern` | Discriminator. Omitted defaults to `operation` (backward compatible). |
| `pattern_id` | string | Unique identifier for this pattern (kebab-case). |
| `pattern_description` | string | Human-readable description of what the pattern matches. |
| `match_criteria.change_type` | enum | Limits matching to a specific `change_type`. |
| `match_criteria.file_pattern` | string | Glob-style path pattern relative to workspace root. `*` = any chars except `/`, `**` = any chars including `/`, `?` = single char except `/`. Invalid patterns rejected at policy load time. |

## Activation Overlay

The activation overlay is an **external YAML file** loaded transparently by `load_policy()` and merged into the effective policy at read-time. The base policy file (`documenter_policy.yml`) remains the **Tier 1 baseline** and is never modified by the overlay mechanism.

### Overlay Location

The overlay path is resolved as follows:

1. **Explicit path:** `DOCUMENTER_ACTIVATION_PATH` environment variable (must be absolute and outside the workspace root).
2. **Default path:** `~/.council/documenter_activation.yml` (outside the workspace by convention).

When the explicit path is set but points to a non-existent file or a non-file, load fails with `PolicyError` (fail-closed). When the default path is absent, the overlay is considered **absent** and the base Tier 1 policy is used unchanged.

### Overlay Schema

The overlay YAML is a flat mapping. Only the following keys are permitted (strict allowlist):

| Key | Type | Description |
|-----|------|-------------|
| `active_tier` | int (not bool) | Override effective tier (normally 2) |
| `scope` | str | Scope preset ID (see below) |
| `allowed_operations` | list | Advanced override — manual operation list (XOR with `scope`) |
| `scope_targets` | list[str] | Narrowing subset for a scope (only with `scope`) |
| `briefing_ref` | str or null | Absolute path outside workspace root |
| `allow_solo_approval` | bool | Solo-operator exception (default: false) |
| `min_approval_delay_seconds` | int in [60, 86400] | Solo delay window |

Unknown keys cause `PolicyError` (fail-closed).

### Scope Presets

Four scope presets map a short identifier to a deterministic set of allowed operations:

| Preset ID | Change Type | Trust Level | Target Count | Description |
|-----------|-------------|-------------|--------------|-------------|
| `pilot-safe-v1` | `update` | `safe` | 2 | Minimal safe pilot: mechanical updates to 2 operational docs |
| `docs-maint-safe` | `update` | `safe` | 24 | Mechanical maintenance (metadata) across full doc corpus |
| `docs-content-review` | `update` | `review` | 24 | Content/normative updates across full doc corpus |
| `ru-sync-review` | `create_ru` | `review` | 18 | RU translation create/sync for docs with translations |

When a scope preset is selected, `scope_targets` may narrow the target set to a **non-empty subset** of the preset's targets (narrowing-only; widening is rejected).

### XOR Rule

The overlay must specify **exactly one** of `scope` or `allowed_operations`. Specifying both, or neither, causes `PolicyError`.

### Containment Rules

- An explicit overlay path must be absolute and outside the workspace root.
- `briefing_ref` (if present and non-null) must be an absolute path outside the workspace root.
- Containment uses `realpath` to resist symlink escape.

### Example Overlay

```yaml
# Example: pilot-safe-v1 activation
active_tier: 2
scope: pilot-safe-v1
briefing_ref: /home/user/.council/briefings/tier2-pilot-safe-v1.md
allow_solo_approval: false
```

### Activation / Deactivation Procedure

1. **Activate:** place a valid overlay file (or set `DOCUMENTER_ACTIVATION_PATH`), verify with `python3 -m documenter_service --verify-activation --root .` (state `active`) or `python3 tools/activation_helper.py verify`.
2. **Deactivate:** remove or neutralize the overlay file, stop Operator Ingress, and remove the readiness sentinel; verify with `--verify-activation` (state `baseline`).

---

## Operational Tuning

Which knob governs which failure path. All values are policy fields from §Field Reference; none require a code change or a restart beyond policy reload.

| Failure or Pressure | Field | On Exhaustion |
|---------------------|-------|---------------|
| Concurrent `delegate()` from another agent | `lock_wait_timeout` | Abort before any write; error names lock owner PID/IP and acquisition timestamp (§Safety Protocol #2) |
| File changed between scan and write | `retry_backoff_base` + `retry_max_attempts` | Escalate to operator; re-run `audit()` for a fresh `audit_id` |
| Operator absent while diff is presented | `operator_approval_timeout` | Emit `error_category: operator_timeout`; nothing is written, staged `.tmp` files are discarded |
| Expectation of out-of-band alerts | `notification_mode` | Not applicable — no asynchronous channel exists; see §Notification Semantics |
| Full rescan exceeds document count | `rescan_batch_ceiling` | Response includes `has_remaining: true` and `scan_cursor`; operator re-invokes `audit(scan_cursor=<value>)` to resume from where previous invocation stopped |
| Stale, invalid, or incomplete `audit_id` presented to `delegate()` | `audit_freshness` | Reject with `error_category: audit_mismatch` (registry absent/expired/scope mismatch) or `error_category: blocking_finding` (high/critical findings present or scan incomplete, `has_remaining: true`) and a re-run-`audit()` action. If registry is absent/unreadable, FAILS CLOSED — all writes denied until authenticated override via `documenter.override_gate(reason, operator_id)` |

### Notification Semantics

Documenter has no notification subsystem: no timer, no daemon, no push channel, no background poller (see §Purpose and §Approval semantics, main spec). Every operator-visible signal — audit report, diff preview, lock-conflict prompt, approval request — is produced inside the synchronous response of the invocation that generated it, and is additionally persisted to the append-only event log (§Event Schema, configuration guide) for later replay. `notification_mode` exists to make this explicit and to reserve the field namespace: introducing an asynchronous channel would be a model change to the main spec, not a policy edit, and requires a new `notification_mode` value plus a defined delivery contract.

---

## Authorization Workflow

Procedure for advancing write capability. Each step is a discrete operator action; Documenter never performs a step on its own behalf. Steps 1–3 precede the first Tier 2+ invocation; the main spec §Trust Tiers states both the policy file and the briefing as mandatory preconditions. The operator-side out-of-band approval and override mechanics once activated are specified in `documenter-service/approval-surface.md` (canonical contract: `mvp-contract.md` §4).

1. **Audit at current tier.** Run `audit("*")` and resolve findings at `high` and `critical`. Tier 2+ on a non-compliant corpus automates drift, not cleanup.
2. **Draft the policy file.** Author `documenter_policy.yml` per §Policy File: set the intended `change_type` + `trust_level` + `targets` combinations in `allowed_operations`, and set operational knobs per §Operational Tuning.
3. **Validate offline.** Load the candidate file in check-only mode. Load fails on: `allowed_operations` non-empty below Tier 2 (validator rule), a `trust_level` below the derived floor for its `change_type` (authority rule), or an unrecognized `notification_mode` value.
4. **Record the briefing.** Write and archive the operator briefing — which documents and `change_type` values are delegated, the maximum number of documents a single invocation may touch, and the reversal procedure — then set `briefing_ref` to its path. This artifact is the human-readable counterpart of `allowed_operations`.
5. **Advance the tier.** Set `active_tier` in the same edit as `briefing_ref`, so a partial edit cannot leave Tier 2+ without a briefing reference. Alternatively, place a valid activation overlay (see §Activation Overlay) that supplies `active_tier: 2`, a scope or `allowed_operations`, and `briefing_ref`; the base policy file remains the Tier 1 baseline when overlay activation is used.
6. **Solo authorization (ADR-017 only).** If — and only if — the deployment has a single operator, additionally set `allow_solo_approval: true` and `min_approval_delay_seconds` (≥300 recommended) in the same edit as step 5, and record the solo scope in the briefing. The briefing must state: the experiment is risk-accepted and bounded; solo approval applies only to `safe`-trust matched operations; each solo approval requires the typed acknowledgment token `CONFIRMED_SOLE_REVIEWER` and the delay window; every solo approval returns a bias-warning banner; scope widens only after 5 consecutive clean write cycles (one change_type or one document per expansion); a mandatory operator review occurs within 30 days of activation. Without `allow_solo_approval: true` the system keeps the strict `approver ≠ proposer` norm.
7. **First write at the new tier.** Invoke `delegate()` on a single low-risk target with a fresh `audit_id`. Review the diff item by item regardless of tier; Tier 2 grants capability, not reduced scrutiny.
8. **Evaluate for Tier 3.** Advance only on documented evidence: ≥90% approval rate at Tier 2 across the preceding two weeks of the event log (§Tier Selection Guidance, main spec), computable from `decision` fields in the event log (§Event Schema, configuration guide). Approved patterns are then enumerated explicitly in `allowed_operations` using `type: pattern` entries with `pattern_id`, `pattern_description`, and `match_criteria` (§Per-Operation Entries); Tier 3 never infers a pattern the operator did not authorize.

**Rollback:** set `active_tier` to a lower value. The change takes effect at the next invocation; an in-flight `delegate()` completes under the tier at which it was accepted, holding the operation-level lock to §Safety Protocol #2.

---

## Cross-References

- **§Documenter Service (index.md)** — Main specification: interface contracts, trust tiers, safety protocol, trust classification floor
- **§Configuration Guide** — Hash store, intent record schema, event schema, glossary compliance, RU alignment
- `docs/en/documentation-rules/index.md` — All documentation rules this service enforces
- `glossary/index.md` — Canonical term definitions for compliance verification

---

*Defines the configuration surface for Documenter Service v0.9.0-draft; extracted from Configuration Guide.*
