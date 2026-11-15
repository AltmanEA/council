# Documenter Configuration Guide

id: documenter-service-configuration-guide
Version: 0.18.0-draft
Status: draft
Abstraction: reference
has_translation: docs/ru/documenter-service/configuration-guide-RU.md
changelog-path: CHANGELOGS/documenter-configuration-guide.changes.md

---

## Scope

This document defines runtime data structures and their integrity rules: hash store, audit registry, intent record, event schema, glossary compliance modes, and RU alignment procedure. The policy file schema, load-time validation rules, operational tuning parameters, and the tier authorization workflow live in `documenter-service/policy-reference.md` — the single source of truth for configuration. Where this guide references a policy field by name (e.g. `audit_freshness`, `rescan_batch_ceiling`), §Field Reference in the policy reference defines its type, default, and allowed values; behavior attributed to a field here is not restated there.

---

## Manifest Field Provenance

`docs-manifest.yaml` is a generated index: frontmatter is the truth, the manifest is its printout. The sole writer is `tools/gen_manifest.py` until the Stage A generator ships per plan (sess-doc-reliability-algo), after which it is the only writer.

| Manifest field | Provenance |
|----------------|------------|
| `id` | frontmatter `id` (required) |
| `path` | generator walk of `docs/en/` (actual file location) |
| `title` | frontmatter `title`, default first H1 |
| `version` | frontmatter `Version` |
| `status` | frontmatter `Status` |
| `abstraction` | frontmatter `Abstraction` |
| `has_translation` | frontmatter `has_translation` |
| `changelog-path` | frontmatter `changelog-path` |
| `references` | frontmatter `references` (author-editable exception) |
| `allow_non_index_paths` | frontmatter `allow_non_index_paths` |

Rules:

- Non-empty `references` / `allow_non_index_paths` are permitted only for registered multi-document exceptions (AGENTS.md §2.1); the validator flags others as high severity.
- Entries are sorted by `id`.
- The generated file carries a `GENERATED — DO NOT EDIT` marker.
- Historical manifest header comments are preserved by the generator as a fixed preamble constant.

---

## Hash Store

Content-hash tokens are stored externally in `documenter/hashes.json` — managed exclusively by Documenter, hidden from operator. Provides optimistic concurrency control for delegate-mode writes.

### Structure

```json
{
  "version": 1,
  "entries": {
    "path/to/file.md": {
      "last_hash": "sha256:abcdef...",
      "last_modified": "2026-11-08T10:30:00Z",
      "history": [
        {"hash": "sha256:...old", "timestamp": "2026-11-07T09:00:00Z"}
      ]
    }
  }
}
```

Two conceptual subsystems with distinct persistence and lifecycle semantics:

| Subsystem | Content | Persistence | Lifecycle |
|-----------|---------|-------------|-----------|
| **Snapshot** | `last_hash`, `last_modified` | Persists between invocations | Updated after each `audit()` or `delegate()` cycle |
| **History** | `history[]` of hash-change entries | Indefinite | Appended only; periodic GC before Tier 2+ |

The snapshot provides O(1) OCC conflict detection. The history provides audit trail and replay capability.

### Conflict Resolution

Read → compare expected hash with current content hash → apply if match → update record. On mismatch: reject with retry signal ("File changed since scan; please re-run audit() then retry"). Retry invocations MUST employ exponential backoff with jitter (base delay: `retry_backoff_base`; attempt ceiling: `retry_max_attempts` — both policy fields, see §Field Reference in `documenter-service/policy-reference.md`). Full rescan is capped by the `rescan_batch_ceiling` policy field (default 50 documents per invocation). When the ceiling is reached, the response includes `has_remaining: true` and a continuation cursor (`scan_cursor`) — pass it back to resume scanning from where the previous invocation stopped. The audit registry entry records the actual scanned document IDs (never `*` unless all documents were scanned in one invocation). A partial scan does NOT authorize delegate() for unscanned documents — the operator must complete the scan before delegation is permitted. No background execution exists. When glossary status changes, full rescan of all documents triggers hash refresh for every entry.

**Behavioral self-healing guarantee:** Hash store must be recoverable on any startup failure. The implementation MUST combine at least TWO of: atomic write (temp-file + rename), pre-write snapshot hash (CRC32c/SHA-256 alongside content), or `.bak` rotation. WAL is not required for MVP. The current implementation combines atomic write with `.bak` rotation: before every save the previous file is copied to `hashes.json.bak`, and on load a missing, unparsable, or structurally invalid `hashes.json` falls back to a valid `.bak`; when both are broken the store degrades to an empty structure (cache miss, not failure). Cold-start integrity verification checks hashes.json existence, validates structure, and scans `documenter/intent/` for leftover records per §Intent Record rules.

**Git diff as supplementary signal:** `git log` over `hashes.json` may provide historical recovery but does NOT replace CRC/checksum (corruption between commits is undetectable from log alone) nor WAL/backup (crash mid-write loses uncommitted state). Git HEAD diff should remain an **advisory only** signal — it cannot serve as primary conflict detection because refs move independently of content changes. Use direct file checksums with optimistic-lock semantics for authoritative conflict resolution.

`documenter/hashes.json` is tracked by the manifest as an operational artifact (`operational: true`). `documenter/intent/` (intent records) and `documenter/audit_registry.jsonl` (audit registry) are similarly operational — managed exclusively by Documenter, hidden from operator, and excluded from the manifest scope of `audit()` and `delegate()`.

**Cache semantics (ADR-010):** `documenter/hashes.json` is a **rebuildable cache**, not authoritative state. Documenter may rebuild it from scratch at any time (CLI flag `--rebuild-hashes`); a cache miss triggers rebuild-and-continue, not failure. Optimistic-concurrency detection therefore covers races within a single invocation window (between audit and apply) only; the git history is the primary audit trail (per `documenter-service/mvp-contract.md` §2.1 / ADR-007). Local tooling under `tools/` is NOT required to update the hash store when it mutates manifest-tracked documents.

---

## Intent Record

A crash-recovery journal written to `documenter/intent/<tx_id>.json` before the first rename in a multi-file commit. Managed exclusively by Documenter, hidden from operator. Provides the "intent" half of the two-phase commit protocol (see main spec, `documenter-service/index.md`, §Safety Protocol #9).

**Schema:** `{tx_id: uuid-v4, target_id: string, created_at: ISO8601Z, entries: [{path, tmp_path, before_hash: sha256, after_hash: sha256}]}` — one entry per file in the changeset.

**Atomic write:** the intent file MUST be written via temp-file + rename (same pattern as §Safety Protocol #5 in the main spec) to prevent partial writes. Cold-start MUST validate the intent JSON structure before using it for recovery; corrupted or incomplete intent records are logged and skipped.

**Recovery rules (cold-start):** scan `documenter/intent/` on startup; for each leftover `.json`, compare actual file hash with `before_hash`/`after_hash`. Three branches: (1) if files match `after_hash` — already committed by a prior successful run, skip; (2) if files match `before_hash` — no external modification since crash, roll forward by renaming `.tmp` (per commit order in main spec); (3) if neither matches — external modification detected, abort and escalate (`error_category: unknown`).

---

## Audit Registry

Audit invocations are persisted to `documenter/audit_registry.jsonl` — an **append-only JSONL log** (one envelope per line, `documenter-service/mvp-data-models.md` §Audit Registry), managed exclusively by Documenter, hidden from operator. Provides the data backing the `delegate()` pre-audit gate (§Interfaces, main spec). On-demand only: no background writer; the registry is updated synchronously at the end of each `audit()` invocation. Concurrent appends are serialized by a dedicated advisory lock file `documenter/.registry.lock` (`fcntl.flock(LOCK_EX)`, separate from `.delegate.lock` so a lock holder that appends cannot self-deadlock).

### Structure

Each line is an envelope `{record_type, prev_hash, data}` (mvp-data-models §Audit Registry); audit invocations are `audit_record` envelopes. Within one logical (possibly paginated) scan, `scanned_ids` and `findings` are cumulative per record, so a resumed batch reports honest coverage:

```json
{
  "record_type": "audit_record",
  "prev_hash": "<sha256-hex-of-previous-line>",
  "data": {
    "audit_id": "<uuid-v4>",
    "issued_at": "2026-11-08T10:30:00Z",
    "scope": "*",
    "findings": [
      {"subject_id": "doc-a", "severity": "high", "description": "Missing changelog", "suggested_action": "…"}
    ],
    "scanned_ids": ["doc-a", "doc-b"],
    "has_remaining": false,
    "scan_cursor": null
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `audit_id` | uuid-v4 | Key. Matches the `audit_id` returned by `audit()`. |
| `issued_at` | ISO8601Z | Timestamp of audit completion. Used by the gate to check `audit_freshness`. |
| `scope` | string | `*` only when ALL documents were scanned in a single invocation; otherwise equals the single `target_id` passed to `audit()` (e.g., `audit(target_id="doc-a")`). When partial scans are used (`has_remaining: true`), scope may still equal the `target_id` but delegation is blocked by rule 5 in §Gate Validation. Full coverage is verified via `scanned_ids`, not scope alone. |
| `findings` | array | Structured findings from `audit()`: `{subject_id, severity, description, suggested_action}` (mvp-data-models §Audit Registry; `subject_id` is the manifest id, or a repository-relative path for corpus-level findings). Gate checks for `high`/`critical` entries whose `subject_id` matches the delegate target. |
| `scanned_ids` | array[string] | List of document IDs actually scanned during this invocation. Populated on every audit — never empty unless the scan covered zero documents. |
| `has_remaining` | boolean | `true` when the scan was paused due to `rescan_batch_ceiling`; indicates incomplete coverage. False or absent means all documents were scanned. |
| `scan_cursor` | string \| null | Continuation token for resumed scans. Present only when `has_remaining` is `true`. Opaque value encoding the last processed document position. |

### Gate Validation

When `delegate()` receives an `audit_id`, it reads the registry and validates:

1. **Existence:** a `audit_record` with this `audit_id` exists in the append-only log (latest record per `audit_id` governs). Absent → reject with `error_category: audit_mismatch`.
2. **Freshness:** `now - issued_at ≤ audit_freshness` (policy field). Expired → reject with `error_category: audit_mismatch`.
3. **Scope coverage:** `scope == "*" OR scope == target_id`. Mismatch → reject with `error_category: audit_mismatch`. For full-corpora scans (`target_id: "*"`), completeness is additionally verified via `scanned_ids` — the delegate target must appear in the list; if `has_remaining` is `true`, some documents are unscanned and any delegate is blocked by rule 5 below.
4. **Blocking findings:** any entry in `findings` with `severity ∈ {high, critical}` AND `target_id` matching the delegate target → reject with `error_category: blocking_finding`.
5. **Scan completion:** if `has_remaining` was `true` for the registered scan, the delegate is rejected until a completed rescan is performed (cursor-based continuation via `audit(scan_cursor=<value>)`). Rejection uses `error_category: blocking_finding`.

**Pre-audit gate:** By default, `delegate()` requires a valid `audit_id` from a prior `audit()` invocation. Validation proceeds against the audit registry (§ above): (1) the `audit_id` must exist; (2) its `issued_at` must fall within the `audit_freshness` window (policy field, default 30 minutes; schema: `documenter-service/policy-reference.md`, §Field Reference); (3) its `scope` must fully cover `target_id` (`*` matches any, otherwise exact match); (4) no `high` or `critical` finding may exist for `target_id` in the registry; (5) if `has_remaining` was `true` for the registered scan, the delegate is rejected until a completed rescan is performed (cursor-based continuation via `audit(scan_cursor=<value>)`). Rejection on rules (1–3) uses `error_category: audit_mismatch`; on (4) or rule (5) uses `error_category: blocking_finding`.

**Preview exemption:** Calls to `delegate()` with `change_type=update` and no write intent (preview mode, returning diff without applying changes) are exempt from `allowed_operations` checks across all tiers. These calls always return the computed diff but never modify files.

**Cold-start failure mode:** If the audit registry is absent, corrupted, or unreadable, the gate FAILS CLOSED — all write operations are denied until explicit operator override. Override requires an authenticated action via `documenter.override_gate(reason, operator_id)` which logs the incident and permits exactly one subsequent `delegate()` call without a fresh audit. Repeat overrides require Tier 2+ approval.

---

## Event Schema

Documenter events are emitted inside the canonical [EventEnvelope](../../service-contract/index.md#event-envelope) defined in the Cross-Service Artifact & Event Contract. The envelope carries routing metadata (`schema_version`, `event_id`, `event_type`, `emitted_at`, `session_id`, `phase_id`, `actor`, `severity`, `causation_id`/`correlation_id`); the Documenter-specific data lives in the `payload` object below.

### Issue Payload Schema

Emitted when `audit()` or `delegate()` finds issues. `event_type: documenter.issue`.

**MVP-emitted payload (authoritative subset).** The MVP emitter closes the payload to exactly `{audit_id, subject_id, severity, description}` (mvp-data-models §3 Event Channel; `adapters/stdout_events.py` `EVENT_SCHEMAS`), where `subject_id` is the manifest id, or a repository-relative path for corpus-level findings (manifest drift, orphan). Emission is validated against this closed key set before any side effect; any other key is rejected. The wider table below describes the target envelope for later layers (and is the source the `service-contract` amendment will adopt); it is NOT emitted by the MVP build.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `target_id` | string | yes | Document identifier from manifest |
| `document_id` | string | yes | Filesystem path (relative to workspace root) |
| `description` | string | yes | Brief human-readable description of finding |
| `suggested_trust_level` | `safe` \| `review` | yes | Output of the trust classifier; authoritative floor for delegate() requests |
| `suggested_action` | string | yes | Brief actionable recommendation |
| `before_hash` | sha256:hex \| null | no | Content hash before operation (null if no prior state) |
| `after_hash` | sha256:hex \| null | no | Content hash after operation (null if no change yet) |
| `tier` | int | yes | Current trust tier at time of emission (0–3) |
| `error_category` | string \| null | no | Set only on failure events (see §Error Category Values below) |
| `audit_id` | uuid-v4 \| null | conditional | Present on `delegate()` events that passed the pre-audit gate (UUID of the audit invocation that authorized this call); absent on `audit()` events and on gate-rejection events. Null on events where delegate was invoked without audit (gate explicitly disabled in policy). |

**Envelope-level fields:** `event_id` (unique; idempotency key), `event_type` (`documenter.issue`), `emitted_at` (ISO 8601Z, required), `actor` (`{kind: operator\|agent\|service, id}`), `severity` (`low` | `medium` | `high` | `critical` — unified taxonomy), `session_id` (`string\|null`; mandatory when auditing a specific session; nullable for corpus-wide documenter compliance scans), `phase_id` (integer \| null; present when event correlates to a specific protocol phase, otherwise null).

### Approval Payload Schema

Emitted by Tier 3 approval rate computation or by an explicit `documenter.approve()` invocation. `event_type: documenter.approval`. Fields not listed below replace the corresponding issue-payload fields within the same envelope.

**MVP-emitted payload (authoritative subset).** The MVP emitter closes the
payload to exactly `{approval_id, operator_id, target_id, diff_hash, decision}`
(mvp-data-models §3 Event Channel; `adapters/stdout_events.py` `EVENT_SCHEMAS`).
Emission is validated against this closed key set; any other key is rejected.
`decision` is `approved` on both MVP emit paths (explicit approval and apply of
an approved write). The wider table below describes the target envelope for
later layers (Tier 3 auto-approve, reject, decision timestamps); it is NOT
emitted by the MVP build.

| Field | Type | Description |
|-------|------|-------------|
| `change_type` | `update` \| `split` \| `create_ru` \| `custom` | Type of the change that was reviewed |
| `requested_trust_level` | `safe` \| `review` | Caller's requested trust level |
| `effective_trust_level` | `safe` \| `review` | Trust level actually applied |
| `diff_hash` | `sha256:hex` | Hash of the diff presented to the operator (bound to `approval_id`) |
| `approval_id` | uuid-v4 \| null | The `approval_id` returned by `delegate()` when `approval_required` is true; present on out-of-band approvals, null for Tier 3 auto-approve events |
| `decision` | `approved` \| `rejected` \| `auto_approved` | Out-of-band operator approve/reject or Tier 3 pattern decision |
| `operator_id` | string | Identity of the operator who approved/rejected; MUST differ from the proposing actor.id (out-of-band). For `auto_approved`, contains `pattern:<pattern_id>` instead of a real operator ID. |
| `decided_at` | ISO8601Z | Timestamp of the approve/reject action via `documenter.approve()` |
| `pattern_id` | string \| null | Only populated for `auto_approved` events |

Approval rate formula for Tier 3 prerequisite:

```
approval_rate = count(decision = approved) / (count(decision = approved) + count(decision = rejected))
```

`auto_approved` and `operator_timeout` events are excluded from the denominator. Tier 3 requires `approval_rate >= 0.90` AND a minimum sample size of 20 manual decisions. Pattern auto-apply is blocked if the audit registry contains `high` or `critical` findings for the target.

### Error Category Values

| Value | Meaning | Recovery Procedure |
|-------|---------|--------------------|
| `trust_mismatch` | Caller requested `trust_level` below the derived floor (§Trust Classification, main spec) | Re-invoke `delegate()` with the derived level reported in the error |
| `hash_mismatch` | Read-before-write detected concurrent modification | Re-run `audit()`, obtain fresh diff, retry `delegate()` |
| `audit_mismatch` | `audit_id` absent from the audit registry, expired per `audit_freshness`, its `scope` does not cover `target_id`, or its scan is incomplete (`has_remaining: true`) (§Audit Registry) | Re-run `audit()` for the target with a `scan_cursor` if a partial scan exists, obtain a fresh `audit_id`, retry `delegate()` |
| `blocking_finding` | Audit registry contains `high` or `critical` findings for the `target_id`, or the scan is incomplete (`has_remaining: true`) — delegate cannot authorize for unscanned documents (§Audit Registry) | Resolve the blocking findings, re-run `audit()` to obtain a clean `audit_id`, retry `delegate()` |
| `skill_failure` | Documentation Worker skill crashed or returned error | Check skill logs, verify input parameters, retry |
| `operator_timeout` | Operator did not respond to the presented diff within `operator_approval_timeout` seconds of the synchronous approval stage of the active `delegate()` invocation (policy field) | Review findings manually, re-issue command with same parameters |
| `gate_failure` | Audit registry is absent, corrupted, or unreadable on cold-start — FAIL-CLOSED behavior blocks the delegate. Requires authenticated override via `documenter.override_gate(reason, operator_id)` before any write can proceed. Repeat overrides require Tier 2+ approval. | Perform operator override, then retry `delegate()` |
| `unknown` | Unhandled exception during delegate() execution | Capture post-mortem trace (§Safety Protocol #8), escalate |

### Delivery Semantics

Events feed into Phase 5 artifacts during Council sessions. In on-demand mode, events are emitted synchronously and persisted via `$WORKSPACE/documenter/events/` for operator replay. Lost events are reconstructed from leftover intent records at cold-start (§Intent Record). Ordering is preserved within a `target_id` scope. During post-crash reconciliation, events are emitted before intent record deletion (§Intent Record, cleanup order). **Single storage location**: all event data corpus-wide lives under `sessions/<session_id>/events.jsonl` (canonical envelope); corpus-wide Documenter audits use `documenter/corpus-audit/events.jsonl`. No other event path exists. Consumers deduplicate by `event_id`; the contract is append-only.

---

## Glossary Compliance

Controlled by `glossary_enforcement` (policy: `draft` or `active`). Staleness guard: flag missing only if term appears ≥3 times AND glossary last modified > `glossary_staleness_days` ago (default 30).

---

## Russian Translation Alignment

Auto-fix banned in all tiers during MVP. When enabled (Tier 3+): invokes `change_type: create_ru` with line parity per AGENTS.md §3.3.

---

## Cross-References

- **§Documenter Service (index.md)** — Main specification: purpose, interfaces, trust tiers, safety protocol (including Multi-file Commit Protocol #9)
- **§Documenter Policy Reference** (`documenter-service/policy-reference.md`) — Policy file schema, field reference, operational tuning, authorization workflow
- `AGENTS.md` — All documentation rules this service enforces
- `glossary/index.md` — Canonical term definitions for compliance verification
- `.agents/skills/documentation/SKILL.md` — Documentation Worker skill (invoked by delegate())

---

*Aligned with Documenter Service v0.16.0-draft and sess-documenter-consiliums.*
