# Documenter Service — MVP Interfaces

id: documenter-service-mvp-interfaces
Version: 0.10.1-draft
Status: draft
Abstraction: format
references: [documenter-service-mvp-data-models]
allow_non_index_paths: true
changelog-path: CHANGELOGS/documenter-service-mvp-interfaces.changes.md

---

> **SUPERSEDED** (2026-11-19, sess-documenter-concept-revision). This document describes the abandoned Documenter design (trust tiers, policy engine, dual interlock, approval surface). It is archived for history only and is NOT normative: do not execute, implement, cite as current, or link from new documents as if active. The authoritative specification is `docs/en/documenter-service/index.md`.
## Purpose

Machine-readable interface schemas for the Documenter Service MVP. Core operations: `audit()`, `delegate(preview: true)`, `documenter.status()`. The Tier 2+ surface — write-branch `delegate(preview: false)`, `documenter.approve`, `documenter.override_gate` — is specified in `documenter-service/mvp-contract.md` §4 (operator-side workflow: `documenter-service/approval-surface.md`) and IMPLEMENTED in the build; it is gated at runtime by the policy interlock (`active_tier >= 2` + non-null `briefing_ref` + archived briefing file + authenticated operator ingress + Operator Ingress readiness sentinel, ADR-016). With the repository policy at Tier 0–1 every non-preview call fails closed with `tier_interlock`.

Data models behind these interfaces: `documenter-service/mvp-data-models.md`. Architectural intent: `documenter-service/legacy/spec-v0.md`.

**MVP scope boundary:** operates only on manifest-tracked artifacts (`docs/en/`, `docs/ru/`) and its own state (`documenter/`). Any `target_id` outside the manifest → `error_category: unknown`.

---

## 1. `audit()` — Read-only diagnostics

Read-only. Touches no write path. Scans documents against compliance rules using manifest and glossary data.

### Request

| Parameter | Type | Description |
|-----------|------|-------------|
| target_id | string | Document ID from manifest, or `"*"` for all |
| severity_min | enum | `low`\|`medium`\|`high`\|`critical`. Default `low` |
| pre_check | bool | Mid-session integrity gate flag; verdict returned synchronously to caller. Default `false` |
| scan_cursor | string\|null | Continuation token from prior partial scan. `null` = fresh full scan |

### Response

| Field | Type | Description |
|-------|------|-------------|
| audit_id | string | UUIDv4; persisted in audit registry with timestamp, scope, findings, scanned_ids, has_remaining, scan_cursor |
| report.findings | array | `{subject_id, severity, description, suggested_action}` — `description` 1–500 chars, no secrets or full document text |
| has_remaining | boolean | `true` when scan paused at `rescan_batch_ceiling`; re-invoke with returned `scan_cursor` |
| scan_cursor | string\|null | Continuation token; present only when `has_remaining` is `true` |
| coverage | object | `{scanned_count, total_count, status}`; `status` ∈ `complete`\|`partial` |

**Coverage rule.** When `coverage.status` is `partial`, the report header MUST state that a write decision cannot be made on this report. `has_remaining` alone is insufficient: an operator reading a 40-of-300-document scan must not form the impression "no findings".

### Compliance rules scanned

1. **Line count** ≤ 200 content lines per `docs/en/documentation-rules/index.md` §7.3.
2. **Changelog existence** — `changelog-path:` resolves to an existing `CHANGELOGS/<id>.changes.md`.
3. **Glossary terms** — every domain term in the body exists in `docs/en/glossary/index.md`.
4. **Cross-reference resolution** — every reference resolves to an existing heading anchor.
5. **Abstraction consistency** — declared `abstraction:` matches actual content structure.
6. **Manifest parity** — manifest-to-frontmatter parity is enforced by regenerate-and-diff against the generator (`tools/gen_manifest.py --check`); orphan detection compares on-disk `docs/en/` files against the generated manifest entries.

Rules 3 (glossary terms) and 5 (abstraction consistency) remain skill/AI-reserved judgments; rules 1, 2, 4, 6 and the naming/schema checks are deterministic (see `docs/en/documentation-rules/index.md` §8).

### Severity semantics

| Level | Descriptor | Operator effect |
|-------|-----------|-----------------|
| `low` | Cosmetic, no data impact | Audit trail only |
| `medium` | Potential inconsistency, low risk | Report + event; write only with explicit operator approval |
| `high` | Confirmed issue, moderate risk | Blocks write by default; explicit approval required |
| `critical` | Data integrity compromise | Blocks write + mandatory post-mortem; no auto-apply at any tier |

Legacy mappings: `info`→`low`, `warning`→`medium`, `error`→`high`.

---

## 2. `delegate(preview: true)` — Diff preview

Preview only. Returns a diff without write intent; exempt from `allowed_operations` checks at all tiers. **The write branch is implemented behind the dual interlock (policy state + readiness sentinel, ADR-013/ADR-016); currently unreachable.**

### Request

| Parameter | Type | Description |
|-----------|------|-------------|
| target_id | string | Document ID from manifest |
| change_type | enum | `update`\|`split`\|`create_ru`\|`custom` |
| trust_level | enum | Caller request `safe`\|`review`; accepted only when `requested >= derived` floor |
| diff_input | string | Base64-encoded UTF-8 machine-readable diff |
| preview | boolean | MUST be `true`. `false` or absent → reject `tier_interlock` |
| audit_id | string\|null | Optional; when supplied, the pre-audit gate (rules 1–5, `documenter-service/legacy/spec-v0.md` §Pre-audit gate) runs before the preview completes (`audit_mismatch`/`blocking_finding` on failure). `null` = preview exempt from the gate, as in the write-branch contract where the gate guards apply only at Tier 2+ |

### Response

| Field | Type | Description |
|-------|------|-------------|
| diff_hash | string | `sha256:<hex>` over **normalized** diff bytes; computed by Documenter |
| diff_text | string | Human-readable unified diff; rendered by Documenter |
| derived_trust_level | enum | Service-computed floor |
| derived_trust_reason | string | Textual cause, e.g. "hunk 3 changes a normative sentence → review" |
| next_action | enum | See §4 |
| findings | array | Audit findings relevant to `target_id` |
| gate | object\|absent | `{audit_id, verdict}`; present only when `audit_id` was supplied and rules 1–5 passed |

### Canonical diff

The operator approves **`diff_text` as rendered by Documenter**, not the base64 input. Documenter decodes `diff_input`, normalizes (CRLF→LF, trailing whitespace, final newline), computes `diff_hash` over the normalized bytes, and renders `diff_text`. This makes the approved object and the hash-bound object identical.

**Rendering responsibility.** Documenter returns `diff_text`; the Layer 2 operator ingress or MCP client renders it to the human. If neither does, Tier 1 "diff preview" is an unverifiable requirement — this obligation belongs in the Operator Ingress spec.

**Redaction boundary.** `diff_text` appears only in the `delegate()` **response**. It MUST NOT appear in `EventEnvelope.payload`, where document text is prohibited.

**Preview scope discipline.** `preview: true` passes the same scope resolver as a write path would, so it cannot become a reconnaissance primitive for non-manifest targets.

### Trust classification

| change_type | Static floor | Dynamic derivation | `safe` permitted |
|-------------|--------------|--------------------|------------------|
| `update` | `safe` | `safe` if every hunk mechanical, else `review` | Only for fully mechanical diff |
| `split` | `review` | `review` | Never |
| `create_ru` | `review` | `review` | Never (RU auto-fix banned in MVP) |
| `custom` | `review` | `review` | Never (default when indeterminate) |

Effective level is assigned by Documenter. On the scale `safe < review`, the invariant is `requested >= derived`; a lower request is rejected with `trust_mismatch` before any approval stage. Uncertain classification → `review`. Policy may raise the floor, never lower it.

### Write branch (Tier 2+, policy-gated)

`delegate(preview: false)` implements mvp-contract §4: guards run in order — tier authorization, registry health, `audit_id` required (gate rules 1–5), scope, `allowed_operations` match, trust invariant — then it issues a single-use `approval_id` (UUIDv4) bound to `(target_id, diff_hash, proposer_id)` and returns:

| Field | Type | Description |
|-------|------|-------------|
| approval_required | boolean | `true` — no file written at proposal time |
| approval_id | string | UUIDv4; apply requires out-of-band `documenter.approve` |
| diff_hash | string | `sha256:<hex>` over normalized diff bytes |
| derived_trust_level / reason | enum/string | As preview response |
| expires_in_min | integer | `approval_expiry_window` from policy |
| next_action | enum | `await_approval` |

Re-invocation with `approval_id` (after approval) applies the write under the mvp-contract §2.2 sequence and returns `{applied: true, target_id, diff_hash, approval_id, next_action: write_applied}`; the approval is consumed on apply. Changed `diff_input` → `approval_invalidated`; stale/expired → `approval_expired`; replay → `token_replay`; lock timeout → `lock_conflict`; hash mismatch → `hash_mismatch`.

`documenter.approve(approval_id, operator_id, acknowledge?)` — separate invocation; `operator_id` comes from authenticated ingress only (never a client parameter); approver ≠ proposer (sole exception ADR-017: a solo self-approval is permitted only when `acknowledge` equals `CONFIRMED_SOLE_REVIEWER`, the matched operation is `safe`, and `min_approval_delay_seconds` has elapsed — see `documenter-service/mvp-contract.md` §4); single-use; expiry per policy. `acknowledge` is supplied as the CLI `--acknowledge` flag or the MCP `acknowledge` argument and is inert on non-solo approvals. `documenter.override_gate(reason, operator_id, target_id, diff_hash, audit_id?)` — bound to one `(target_id, diff_hash)`, one-shot within the window, emits `documenter.override_gate`, returns `next_action: rerun_audit`; unavailable for `critical` findings (`blocking_finding` + `resolve_finding`).

---

## 3. `documenter.status()` — Operational status

Read-only. Single answer to "why is the gate rejecting right now?". Under `idle-until-invoked` there is no background probe, so this call is the only channel through which registry degradation becomes observable.

### Request

| Parameter | Type | Description |
|-----------|------|-------------|
| target_id | string\|null | Filter to one document; `null` = whole corpus |

### Response

| Field | Type | Description |
|-------|------|-------------|
| active_tier | integer | `0`\|`1`\|`2`\|`3` |
| registry.status | enum | `healthy`\|`degraded`\|`corrupt` |
| registry.last_audit | object | `{audit_id, issued_at, fresh}`; `fresh` = within `audit_freshness` |
| registry.staged_files | array | `{target_id, staged_at}` — leftovers from an interrupted write |
| registry.override_counter | integer | Override calls in the current session (counters habituation) |
| scan_status | object | `{has_pending_scan, pending_scan_cursor, blocking_operator}` |
| tier_interlock | object | `{tier_2_plus_locked, reason}` |
| `activation` | object | Activation overlay diagnostics (see below). Reflects the runtime-merged effective policy (base + overlay) — overlay merge is transparent to callers. |

| Sub-field | Type | Description |
|-----------|------|-------------|
| `overlay_present` | bool | Whether an activation overlay was loaded at read-time |
| `overlay_path` | str or null | Resolved overlay file path (absolute, outside workspace root) |
| `scope` | str or null | Selected scope preset ID (e.g. `pilot-safe-v1`) |
| `mode` | str or null | `"scope"` (preset-based) or `"override"` (advanced `allowed_operations`), null when absent |
| `source` | str | `"base"` (no overlay), `"overlay"` (overlay active), or `"none"` (no policy loaded) |
| `briefing_ref` | str or null | Effective briefing reference path |
| `allowed_operations_count` | int | Number of effective allowed operations after scope expansion |
| `sentinel_present` | bool or null | Operator Ingress sentinel (`documenter/.operator_ingress_ready`) status |
| `briefing_exists` | bool or null | Whether the effective `briefing_ref` file exists |

**Registry health.** `healthy` — readable, `prev_hash` chain consistent. `degraded` — chain break, or size exceeds retention without checkpoint. `corrupt` — missing, truncated, or unparsable. On `corrupt`, `delegate()` returns `gate_failure`.

**Pending scan visibility.** An unclosed `audit("*")` blocks every write under pre-audit rule 5, which is a cheap denial of service. `status` MUST name the blocking operator and how to release it; releasing another operator's scan is an operator-only action.

### CLI `--verify-activation`

A dedicated CLI command (`python3 -m documenter_service --verify-activation`) that reports activation state and interlock readiness (read-only, no writes). Supports `--json` for machine-readable output and `--root` for workspace root specification.

**States:**

| State | Exit Code | Meaning |
|-------|-----------|---------|
| `baseline` | 0 | No overlay applied; effective policy is base Tier 1 |
| `active` | 0 | Overlay present and effective policy loaded valid; interlock sub-checks reported (sentinel/briefing readiness) |
| `invalid` | 2 | Overlay present but invalid (fail-closed) or base policy invalid; structured error emitted |

**Output fields (JSON mode):** `state`, `ok`, `overlay` (present/path/explicit/scope/mode), `effective` (active_tier/allowed_operations_count/briefing_ref/briefing_exists/allow_solo_approval/min_approval_delay_seconds/source), `interlock` (sentinel_present/tier2_policy_ready/tier2_authorized/reason), `errors`. For `active` state, also reports expanded scope summary (id, type, trust, target count, targets list). Human-readable mode prints labeled diagnostics with PASS/FAIL readiness checklist.

See `documenter-service/configuration-guide.md` §Activation Overlay for runtime diagnostics and `tools/activation_helper.py verify` as an alternative helper command.

---

## 4. `next_action` Enum

Closed enum in every response, so the operator always knows the next step:

| Value | Meaning | Returned when |
|-------|---------|---------------|
| `preview_only` | Preview; no write will occur | MVP `delegate(preview: true)` |
| `write_applied` | Write applied and approval consumed | Tier 2+ apply under §2.2 |
| `await_approval` | Write pending operator approval | Tier 2+ `delegate()` accepted |
| `rerun_audit` | Audit ID stale, missing, or out of scope | `audit_mismatch` |
| `resolve_finding` | High/critical finding blocks write | `blocking_finding` |
| `rescan_to_completion` | Partial scan; resume with `scan_cursor` | `has_remaining: true` |
| `preview_denied` | Tier interlock; run with `preview: true` | `tier_interlock` |
| `escalate` | Unknown error — this is a bug, not your action | `unknown` |

### Error categories

`audit_mismatch`, `blocking_finding`, `tier_interlock`, `approval_expired`, `approval_invalidated`, `hash_mismatch`, `trust_mismatch`, `token_replay`, `lock_conflict`, `gate_failure`, `unknown`.

Canonical names: `audit_mismatch` covers a missing, stale, or out-of-scope `audit_id` (pre-audit rules 1–3); `blocking_finding` covers high/critical findings and an incomplete scan (`has_remaining: true`, rule 5). These match `service-contract/error-management.md` §Error Code Registry (Documenter mapping) and the pre-audit gate in `documenter-service/legacy/spec-v0.md` §Pre-audit gate; earlier drafts that split these into `audit_missing` / `audit_stale` / `audit_scope_insufficient` / `finding_high` / `finding_critical` / `rescan_incomplete` are superseded.

`error_category` is not part of the frozen `service-contract` enumeration set, so this expansion is legal. `unknown` is reserved for genuine defects; a Tier 2+ call hitting `unknown` (as it would today) is a contract bug, since `tier_interlock` exists.

---

## 5. Common Constraints

- UTF-8 JSON, `snake_case` keys, no duplicate keys. `audit_id` is UUIDv4; `operator_id` matches `^op-[a-z0-9][a-z0-9-]{2,63}$`; hashes are `sha256:<64 lowercase hex>`; timestamps ISO 8601 UTC with `Z`.
- **VAL.001:** producers MUST NOT emit unknown fields; consumers MUST reject them.
- All limits come from the policy file: `max_diff_bytes` (default 512 KiB), `rescan_batch_ceiling` (default 50 documents), `sync_latency_budget_ms` (default 30000). A synchronous call that cannot finish inside the budget returns a structured timeout error rather than blocking indefinitely.
- Transport: MCP stdio in MVP; a CLI wrapper exposes the same core so MCP and CLI results cannot diverge.

---

*Part of the Documenter MVP contract. Data models: `documenter-service/mvp-data-models.md`. Stack, safety, testing: `documenter-service/mvp-contract.md`.*
