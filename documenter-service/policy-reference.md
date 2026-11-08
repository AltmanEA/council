# Documenter Policy Reference

Version: 0.4.0-draft
Status: draft
Last Modified: 2026-11-09
Abstraction: reference
changelog-path: CHANGELOGS/documenter-policy-reference.changes.md

---

## Purpose

Authoritative schema for the Documenter policy file: field definitions, load-time validation rules, operational tuning parameters, and the step-by-step tier authorization workflow. Protocol semantics these fields configure (trust tiers, safety protocol, interface contracts) are defined in `documenter-service/index.md`; runtime data structures (hash store, intent record, event schema) are defined in `documenter-service/configuration-guide.md`. This document defines no behavior of its own — it is the configuration surface for behavior defined elsewhere.

---

## Policy File

A YAML configuration defining which operations are permitted at each tier and compliance modes. Written and maintained by the operator. Time-based auto-proceed is not part of the model: approval is always an explicit operator action within a `delegate()` invocation, and the only auto-execution path is Tier 3 pattern-based auto-apply (see §Trust Tiers and §Approval semantics in the main spec, `documenter-service/index.md`).

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
  rescan_batch_ceiling: 50        # documents per full-rescan invocation before partial-report return
  glossary_staleness_days: 30     # days since last glossary modification; terms appearing ≥3 times within this window are flagged as missing
  briefing_ref: null              # path to operator briefing artifact; required when active_tier >= 2
```

At Tier 0–1, `allowed_operations` must remain empty regardless of content. The operator updates this file explicitly when advancing tiers. Documenter refuses to execute any operation not listed.

### Field Reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `version` | string | Yes | `"0.2.0"` | Policy schema version for compatibility detection |
| `active_tier` | int | Yes | `0` | Current trust tier (0–3). Must match Tier table (§Trust Tiers, main spec). |
| `allowed_operations` | array | Yes | `[]` | Operations authorized at current tier. Empty below Tier 2. May only tighten the trust floor (§Authority rule above). |
| `glossary_enforcement` | enum | No | `draft` | Controls glossary compliance noise reduction (§Glossary Compliance, configuration guide). |
| `audit_freshness` | int | No | `30` | Maximum age (minutes) of an `audit_id` accepted by the `delegate()` pre-audit gate. The gate additionally validates scope coverage and blocking findings against the audit registry (`documenter-service/configuration-guide.md`, §Audit Registry). Set `0` to disable the gate. |
| `lock_wait_timeout` | int | No | `30` | Seconds to wait for the operation-level advisory lock before aborting with the lock-owner error described in §Safety Protocol #2 (main spec). |
| `retry_backoff_base` | int | No | `1` | Base delay (seconds) for the exponential backoff with jitter used by retry invocations (§Conflict Resolution, configuration guide). |
| `retry_max_attempts` | int | No | `3` | Maximum retry invocations after a `hash_mismatch` before Documenter escalates to the operator instead of retrying. |
| `operator_approval_timeout` | int | No | `300` | Seconds the active `delegate()` invocation waits for an explicit approve/reject before emitting `error_category: operator_timeout`. Not an auto-approve window (§Approval semantics, main spec). |
| `notification_mode` | enum | No | `inline` | Delivery mode for operator-facing prompts. `inline` is the only accepted value in MVP: prompts, diffs, and verdicts are returned inside the invocation response. Unknown values are rejected at load time. |
| `rescan_batch_ceiling` | int | No | `50` | Documents processed per full-rescan invocation before the response returns a partial report with remaining-document count; the operator re-invokes `audit()` to process the remainder. No background execution. |
| `glossary_staleness_days` | int | No | `30` | Days since last glossary modification; terms appearing ≥3 times within this window are flagged as missing (§Glossary Compliance, configuration guide). |
| `briefing_ref` | string | No | `null` | Path to the archived operator briefing artifact documenting the scope of delegated authority. MUST be non-null when `active_tier >= 2` (§Authorization Workflow, step 4). |

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

---

## Operational Tuning

Which knob governs which failure path. All values are policy fields from §Field Reference; none require a code change or a restart beyond policy reload.

| Failure or Pressure | Field | On Exhaustion |
|---------------------|-------|---------------|
| Concurrent `delegate()` from another agent | `lock_wait_timeout` | Abort before any write; error names lock owner PID/IP and acquisition timestamp (§Safety Protocol #2) |
| File changed between scan and write | `retry_backoff_base` + `retry_max_attempts` | Escalate to operator; re-run `audit()` for a fresh `audit_id` |
| Operator absent while diff is presented | `operator_approval_timeout` | Emit `error_category: operator_timeout`; nothing is written, staged `.tmp` files are discarded |
| Expectation of out-of-band alerts | `notification_mode` | Not applicable — no asynchronous channel exists; see §Notification Semantics |
| Full rescan exceeds document count | `rescan_batch_ceiling` | Partial report returned with remaining count; operator re-invokes `audit()` |
| Stale or invalid `audit_id` presented to `delegate()` | `audit_freshness` | Reject with `error_category: audit_mismatch` (registry absent/expired/scope mismatch) or `error_category: blocking_finding` (high/critical findings present) and a re-run-`audit()` action |

### Notification Semantics

Documenter has no notification subsystem: no timer, no daemon, no push channel, no background poller (see §Purpose and §Approval semantics, main spec). Every operator-visible signal — audit report, diff preview, lock-conflict prompt, approval request — is produced inside the synchronous response of the invocation that generated it, and is additionally persisted to the append-only event log (§Event Schema, configuration guide) for later replay. `notification_mode` exists to make this explicit and to reserve the field namespace: introducing an asynchronous channel would be a model change to the main spec, not a policy edit, and requires a new `notification_mode` value plus a defined delivery contract.

---

## Authorization Workflow

Procedure for advancing write capability. Each step is a discrete operator action; Documenter never performs a step on its own behalf. Steps 1–3 precede the first Tier 2+ invocation; the main spec §Trust Tiers states both the policy file and the briefing as mandatory preconditions.

1. **Audit at current tier.** Run `audit("*")` and resolve findings at `high` and `critical`. Tier 2+ on a non-compliant corpus automates drift, not cleanup.
2. **Draft the policy file.** Author `documenter_policy.yml` per §Policy File: set the intended `change_type` + `trust_level` + `targets` combinations in `allowed_operations`, and set operational knobs per §Operational Tuning.
3. **Validate offline.** Load the candidate file in check-only mode. Load fails on: `allowed_operations` non-empty below Tier 2 (validator rule), a `trust_level` below the derived floor for its `change_type` (authority rule), or an unrecognized `notification_mode` value.
4. **Record the briefing.** Write and archive the operator briefing — which documents and `change_type` values are delegated, the maximum number of documents a single invocation may touch, and the reversal procedure — then set `briefing_ref` to its path. This artifact is the human-readable counterpart of `allowed_operations`.
5. **Advance the tier.** Set `active_tier` in the same edit as `briefing_ref`, so a partial edit cannot leave Tier 2+ without a briefing reference.
6. **First write at the new tier.** Invoke `delegate()` on a single low-risk target with a fresh `audit_id`. Review the diff item by item regardless of tier; Tier 2 grants capability, not reduced scrutiny.
7. **Evaluate for Tier 3.** Advance only on documented evidence: ≥90% approval rate at Tier 2 across the preceding two weeks of the event log (§Tier Selection Guidance, main spec), computable from `decision` fields in the event log (§Event Schema, configuration guide). Approved patterns are then enumerated explicitly in `allowed_operations` using `type: pattern` entries with `pattern_id`, `pattern_description`, and `match_criteria` (§Per-Operation Entries); Tier 3 never infers a pattern the operator did not authorize.

**Rollback:** set `active_tier` to a lower value. The change takes effect at the next invocation; an in-flight `delegate()` completes under the tier at which it was accepted, holding the operation-level lock to §Safety Protocol #2.

---

## Cross-References

- **§Documenter Service (index.md)** — Main specification: interface contracts, trust tiers, safety protocol, trust classification floor
- **§Configuration Guide** — Hash store, intent record schema, event schema, glossary compliance, RU alignment
- `AGENTS.md` — All documentation rules this service enforces
- `glossary/index.md` — Canonical term definitions for compliance verification

---

*Defines the configuration surface for Documenter Service v0.11.0; extracted from Configuration Guide v0.5.0.*
