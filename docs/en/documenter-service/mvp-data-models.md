# Documenter Service — MVP Data Models

id: documenter-service-mvp-data-models
Version: 0.5.0-draft
Status: draft
Abstraction: reference
references: [documenter-service-mvp-interfaces, service-contract]
allow_non_index_paths: true
changelog-path: CHANGELOGS/documenter-service-mvp-data-models.changes.md

---

## Purpose

Runtime data structures, persistence formats, and configuration schema for the Documenter Service MVP. Interface schemas are defined in `documenter-service/mvp-interfaces.md`; safety protocol and testing in `documenter-service/mvp-contract.md`.

**Threat model (operator decision, 2026-11-12):** the service never commits; every action is trivially reversible via git. `documenter/` is git-tracked, so git history is the primary audit trail. Cryptographic primitives (HMAC token signing, external key management) are excluded from MVP; the `prev_hash` chain remains as a cheap corruption-detection aid, not an anti-tamper mechanism.

---

## 1. Audit Registry

**File:** `documenter/audit_registry.jsonl` — append-only, one JSON object per line.

### Record envelope

| Field | Type | Rule |
|-------|------|------|
| record_type | enum | `audit_record` \| `token_record` \| `intent_record` \| `checkpoint_record` |
| prev_hash | string \| null | `sha256` of the previous record's canonical JSON (sorted keys, no trailing newline). `null` on first record |
| data | object | Type-specific payload below |

### audit_record

| Field | Type | Rule |
|-------|------|------|
| audit_id | string | UUIDv4 |
| issued_at | timestamp | ISO 8601 UTC `Z` |
| scope | string | `"*"` or a manifest `target_id` |
| findings | array | Finding objects, redacted per `service-contract` rules |
| scanned_ids | string[] | Documents covered by this scan |
| has_remaining | boolean | Scan paused at page ceiling |
| scan_cursor | string \| null | Token valid only while `has_remaining` is `true` |

### token_record

| Field | Type | Rule |
|-------|------|------|
| token_type | enum | `scan_cursor` \| `approval_id` |
| token_value | string | 32 random bytes, base64. Opaque to clients |
| bound_to | object | `{audit_id, target_id}` — token valid only for this pair |
| consumed | boolean | Set `true` on use; second use → `error_category: token_replay` |
| consumed_at | timestamp \| null | `null` until consumed |

**Token model.** Tokens are server-side stored, single-use, and bound to `(audit_id, target_id)`. A `scan_cursor` for target A cannot resume a scan for target B. No signature: with the registry under git and the service idle-until-invoked, server-side storage gives the same guarantee at zero key-management cost.

### intent_record (Tier 2+ writes; schema reserved in MVP)

| Field | Type | Rule |
|-------|------|------|
| target_ids | string[] | Documents in this commit set |
| staged_at | timestamp | When staging began |
| per_file_sha256 | object | `{target_id: sha256}` of each source file at staging time |
| resolved | boolean | Cleared after the final rename |

### checkpoint_record

| Field | Type | Rule |
|-------|------|------|
| segment_hash | string | `sha256` over all records being truncated |
| truncated_count | integer | Records removed |

**Retention.** Maximum 10,000 records. Truncation without a preceding `checkpoint_record` is **prohibited** — otherwise compaction silently erases the only evidence base for overrides.

**Git management.** The registry is git-tracked. The service never commits; commits are explicit operator actions. Corruption recovery path: restore the registry from any prior commit.

---

## 2. Policy File

**Authoritative schema:** `documenter-service/policy-reference.md` (§Policy File, §Field Reference). Field names, types, and defaults are defined there and are not restated here with divergent names. This section fixes only the load-time behavior the MVP runtime depends on.

**Location:** `documenter_policy.yml`, or `DOCUMENTER_POLICY_PATH`. The repository's `defaults/policy.yaml` is the framework-wide default whitelist (`planned-architecture/layer-1.md` §Zero silent defaults) and is **not** a Documenter policy file — Documenter never loads it.

```yaml
documenter_policy:
  version: "0.2.0"                   # string; only "0.2.0" recognized at MVP
  active_tier: 0                     # 0 | 1 | 2 | 3
  allowed_operations: []             # operation | pattern entries (policy-reference §Per-Operation Entries)
  audit_freshness: 30
  approval_expiry_window: 30
  rescan_batch_ceiling: 50
  max_diff_bytes: 524288             # 512 KiB
  sync_latency_budget_ms: 30000
  lock_wait_timeout: 30
  operator_approval_timeout: 300
  notification_mode: inline
  glossary_enforcement: draft
  briefing_ref: null                 # required non-null when active_tier >= 2
```

### Validation rules — fail-closed

| # | Rule | Failure behavior |
|---|------|------------------|
| 1 | `version` recognized | Load fails; no default substitution |
| 2 | `active_tier ∈ {0,1,2,3}` | Load fails — an unreadable tier MUST NOT silently lower strictness |
| 3 | `allowed_operations` non-empty while `active_tier < 2` | Load fails (validator rule, policy-reference §Policy File) |
| 4 | No entry with `trust_level` below the static floor for its `change_type` | Load fails (authority rule); covers `type: pattern` entries too |
| 5 | `targets` are manifest IDs or empty | Load fails |
| 6 | `briefing_ref` non-null when `active_tier >= 2` | Load fails |
| 7 | Integer fields (`audit_freshness`, `approval_expiry_window`, `rescan_batch_ceiling`, `max_diff_bytes`, `sync_latency_budget_ms`, `lock_wait_timeout`, `operator_approval_timeout`, `glossary_staleness_days`) are positive integers; float fields (`temperature`, `top_p`, `frequency_penalty`) within their documented ranges (policy-reference §Field Reference); `notification_mode == inline` | Load fails |

Missing file, invalid YAML, or any rule violation → structured error to stdout; all `delegate()` calls refused. Exception: `preview: true` remains exempt — preview carries no write intent and cannot be degraded by policy state.

---

## 3. Event Channel

Documenter events are types inside the unified `EventEnvelope` (`service-contract/index.md`), not a separate contract.

| Event Type | Emitted when | Payload (redacted) |
|------------|--------------|--------------------|
| `documenter.issue` | `audit()` produces a finding | `audit_id`, `subject_id`, `severity`, `description` |
| `documenter.approval` | approve succeeds (Tier 2+) | `approval_id`, `operator_id`, `target_id`, `diff_hash`, `decision` |
| `documenter.override_gate` | override invoked (Tier 2+) | `reason`, `operator_id`, `target_id` |
| `precheck.passed` | `pre_check` audit, no blocking findings | `audit_id`, `target_id` |
| `precheck.failed` | `pre_check` audit, high/critical findings | `audit_id`, `target_id`, `blocking_severities` |
| `precheck.overridden` | `council.override_precheck` called | `reason`, `operator_id` |
| `precheck.unavailable` | surface cannot reach Documenter | emitted by Layer 2, not Documenter |
| `notice.documenter_tier2_interlock` | Tier 2+ call while interlocked | `requested_tier`, `reason` |

**MVP channel (operator-approved resolution of conflict C4).** Fallback sessions produce no `events.jsonl` and `session_id` is nullable only for corpus-wide audits, so session-scoped Documenter events have no lawful envelope before Layer 2. Resolution: the **primary MVP carrier is the audit registry plus one structured JSON line per event on stdout** — a documented channel, not an invented side-channel. Envelope serialization is deferred; when Layer 2 arrives, events are derived from registry records with `event_id` derived from `audit_id` for idempotency. An explicit `service-contract` amendment will precede any use of the envelope for session-scoped Documenter events (owner: `service-contract` maintainer).

**Redaction rule.** Event payloads MUST NOT contain secrets, full prompts, or document text. Hashes, identifiers, counts, and short summaries are allowed. `diff_text` exists only in `delegate()` responses, never in events.

---

## 4. Directory Layout

```
documenter/                    # git-tracked; service never commits
├── audit_registry.jsonl       # append-only records (§1)
├── .delegate.lock             # single operation-level advisory lock, Tier 2+ (mvp-contract §2.2.2)
├── post_mortems/<uuid>.json   # critical-finding post-mortems (Tier 2+)
└── staged/<target_id>.<hash>.tmp  # crash leftovers moved here during reconciliation (Tier 2+)
```

No file under `documenter/` is git-ignored. Staging files for atomic writes are created in the **target document's own directory** (same filesystem as the target), not under `documenter/staged/` — `rename(2)` is atomic only within one filesystem, and a cross-directory rename on the same FS is fine, but `/tmp` staging would degrade rename to copy+unlink with a partial-write window. `documenter/staged/` holds only crash leftovers moved there during reconciliation.

---

## 5. Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DOCUMENTER_POLICY_PATH` | `documenter_policy.yml` | Policy file location (schema: policy-reference §Policy File) |
| `DOCUMENTER_DATA_DIR` | `documenter/` | Operational state directory |
| `DOCUMENTER_LOG_LEVEL` | `info` | `debug` \| `info` \| `warn` \| `error`; filters service warnings on **stderr** (policy degradation, event-persistence degradation). stdout is untouched — the transport contract "last stdout line is the response" is preserved (mvp-data-models §5, fix plan p.12) |

---

## 6. Compliance Checklist (data layer)

- [ ] Registry is append-only; no record ever rewritten in place
- [ ] Every token record is bound to `(audit_id, target_id)` and consumed exactly once
- [ ] Truncation impossible without a preceding `checkpoint_record`
- [ ] Policy load is fail-closed on every validation failure
- [ ] No event payload contains document text, prompts, or secrets
- [ ] `documenter/` is git-tracked and never committed by the service

---

*Part of the Documenter MVP contract. Interfaces: `documenter-service/mvp-interfaces.md`. Stack, safety, testing: `documenter-service/mvp-contract.md`.*
