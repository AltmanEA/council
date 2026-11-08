# Documenter Configuration Guide

Version: 0.9.0-draft
Status: draft
Last Modified: 2026-11-09
Abstraction: reference
changelog-path: CHANGELOGS/documenter-configuration-guide.changes.md

---

## Scope

This document defines runtime data structures and their integrity rules: hash store, audit registry, intent record, event schema, glossary compliance modes, and RU alignment procedure. The policy file schema, load-time validation rules, operational tuning parameters, and the tier authorization workflow live in `documenter-service/policy-reference.md` — the single source of truth for configuration. Where this guide references a policy field by name (e.g. `audit_freshness`, `rescan_batch_ceiling`), §Field Reference in the policy reference defines its type, default, and allowed values; behavior attributed to a field here is not restated there.

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

Read → compare expected hash with current content hash → apply if match → update record. On mismatch: reject with retry signal ("File changed since scan; please re-run audit() then retry"). Retry invocations MUST employ exponential backoff with jitter (base delay: `retry_backoff_base`; attempt ceiling: `retry_max_attempts` — both policy fields, see §Field Reference in `documenter-service/policy-reference.md`). Full rescan is capped by the `rescan_batch_ceiling` policy field (default 50 documents per invocation) — exceeding this threshold returns a partial report with the remaining-document count; the operator re-invokes `audit()` to process the remainder. No background execution exists. When glossary status changes, full rescan of all documents triggers hash refresh for every entry.

**Behavioral self-healing guarantee:** Hash store must be recoverable on any startup failure. The implementation MUST combine at least TWO of: atomic write (temp-file + rename), pre-write snapshot hash (CRC32c/SHA-256 alongside content), or `.bak` rotation. WAL is not required for MVP. Cold-start integrity verification checks hashes.json existence, validates structure, and scans `documenter/intent/` for leftover records per §Intent Record rules.

**Git diff as supplementary signal:** `git log` over `hashes.json` may provide historical recovery but does NOT replace CRC/checksum (corruption between commits is undetectable from log alone) nor WAL/backup (crash mid-write loses uncommitted state). Git HEAD diff should remain an **advisory only** signal — it cannot serve as primary conflict detection because refs move independently of content changes. Use direct file checksums with optimistic-lock semantics for authoritative conflict resolution.

`documenter/hashes.json` is tracked by the manifest as an operational artifact (`operational: true`).

---

## Intent Record

A crash-recovery journal written to `documenter/intent/<tx_id>.json` before the first rename in a multi-file commit. Managed exclusively by Documenter, hidden from operator. Provides the "intent" half of the two-phase commit protocol (see main spec, `documenter-service/index.md`, §Safety Protocol #9).

**Schema:** `{tx_id: uuid-v4, target_id: string, created_at: ISO8601Z, entries: [{path, tmp_path, before_hash: sha256, after_hash: sha256}]}` — one entry per file in the changeset.

**Atomic write:** the intent file MUST be written via temp-file + rename (same pattern as §Safety Protocol #5 in the main spec) to prevent partial writes. Cold-start MUST validate the intent JSON structure before using it for recovery; corrupted or incomplete intent records are logged and skipped.

**Recovery rules (cold-start):** scan `documenter/intent/` on startup; for each leftover `.json`, compare actual file hash with `before_hash`/`after_hash`. Three branches: (1) if files match `after_hash` — already committed by a prior successful run, skip; (2) if files match `before_hash` — no external modification since crash, roll forward by renaming `.tmp` (per commit order in main spec); (3) if neither matches — external modification detected, abort and escalate (`error_category: unknown`).

---

## Audit Registry

Audit invocations are persisted to `documenter/audits.json` — managed exclusively by Documenter, hidden from operator. Provides the data backing the `delegate()` pre-audit gate (§Interfaces, main spec). On-demand only: no background writer; the registry is updated synchronously at the end of each `audit()` invocation.

### Structure

```json
{
  "version": 1,
  "entries": {
    "<audit_id>": {
      "issued_at": "2026-11-08T10:30:00Z",
      "scope": "*",
      "findings": [
        {"severity": "high", "target_id": "doc-a", "description": "Missing changelog"}
      ]
    }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `audit_id` | uuid-v4 | Key. Matches the `audit_id` returned by `audit()`. |
| `issued_at` | ISO8601Z | Timestamp of audit completion. Used by the gate to check `audit_freshness`. |
| `scope` | string | `*` for all documents, or a specific target_id. Used by the gate to verify that the audit covered the delegate target. |
| `findings` | array | Structured findings from `audit()`. Gate checks for `high`/`critical` entries matching `target_id`. |

### Gate Validation

When `delegate()` receives an `audit_id`, it reads the registry and validates:

1. **Existence:** `audit_id` is a key in `entries`. Absent → reject with `error_category: audit_mismatch`.
2. **Freshness:** `now - issued_at ≤ audit_freshness` (policy field). Expired → reject with `error_category: audit_mismatch`.
3. **Scope coverage:** `scope == "*" OR scope == target_id`. Mismatch → reject with `error_category: audit_mismatch`.
4. **Blocking findings:** any entry in `findings` with `severity ∈ {high, critical}` AND `target_id` matching the delegate target → reject with `error_category: blocking_finding`.

The gate is configurable via the `audit_freshness` policy field (default 30 min; set `0` to disable). When the registry file is absent or unreadable (cold-start, corruption), the gate is skipped and the call proceeds — consistent with the on-demand utility model (no background process creates the file; the first `audit()` invocation creates it).

---

## Event Schema

Structured events emitted during both audit and delegate phases for consumption by the Layer 2 session surface at phase boundaries (persisted via the append-only audit log below). See §Interfaces (main spec) for severity taxonomy mapping. `audit_id` is present on events emitted during `delegate()` calls that passed the pre-audit gate; absent on `audit()` events and on gate-rejection events.

```yaml
event_type: documenter.issue     # finding/failure events; use documenter.approval for decisions (see below)
emitted_at: ISO8601Z            # timestamp for all event types (required)
severity: low | medium | high | critical   # unified taxonomy (§Interfaces)
target_id: string               # document identifier from manifest
document_id: string             # filesystem path (relative to workspace root)
description: string             # brief human-readable description of finding
suggested_trust_level: safe | review  # output of the trust classifier (§Trust Classification, main spec); authoritative floor for delegate() requests
suggested_action: string        # brief actionable recommendation
before_hash: sha256:hex         # content hash before operation (null if no prior state)
after_hash: sha256:hex          # content hash after operation (null if no change yet)
tier: int                       # current trust tier at time of emission (0–3)
error_category: string          # see §Safety Protocol #7 (set only on failure events)
session_id: string              # originating session ID
audit_id: string                # uuid-v4 from audit() that authorized this delegate() call (null if gate disabled or audit event)
```

### Error Category Values

| Value | Meaning | Recovery Procedure |
|-------|---------|--------------------|
| `trust_mismatch` | Caller requested `trust_level` below the derived floor (§Trust Classification, main spec) | Re-invoke `delegate()` with the derived level reported in the error |
| `hash_mismatch` | Read-before-write detected concurrent modification | Re-run `audit()`, obtain fresh diff, retry `delegate()` |
| `audit_mismatch` | `audit_id` absent from the audit registry, expired per `audit_freshness`, or its `scope` does not cover `target_id` (§Audit Registry) | Re-run `audit()` for the target, obtain a fresh `audit_id`, retry `delegate()` |
| `blocking_finding` | Audit registry contains `high` or `critical` findings for the `target_id` (§Audit Registry) | Resolve the blocking findings, re-run `audit()` to obtain a clean `audit_id`, retry `delegate()` |
| `skill_failure` | Documentation Worker skill crashed or returned error | Check skill logs, verify input parameters, retry |
| `operator_timeout` | Operator did not respond to the presented diff within `operator_approval_timeout` seconds of the synchronous approval stage of the active `delegate()` invocation (policy field) | Review findings manually, re-issue command with same parameters |
| `unknown` | Unhandled exception during delegate() execution | Capture post-mortem trace (§Safety Protocol #8), escalate |

### Approval Event Schema (H12)

Approval events (`event_type: documenter.approval`) enable Tier 3 approval rate computation. Fields not listed below are inherited from the base schema (`target_id`, `document_id`, `tier`, `session_id`, `emitted_at`):

| Field | Type | Description |
|-------|------|-------------|
| `change_type` | `update` \| `split` \| `create_ru` \| `custom` | Type of the change that was reviewed |
| `requested_trust_level` | `safe` \| `review` | Caller's requested trust level |
| `effective_trust_level` | `safe` \| `review` | Trust level actually applied |
| `diff_hash` | `sha256:hex` | Hash of the diff presented to the operator |
| `decision` | `approved` \| `rejected` \| `auto_approved` | Operator or pattern decision |
| `operator_id` | string | Identity of the operator who decided, or pattern_id for `auto_approved` |
| `decided_at` | ISO8601Z | Timestamp of the decision |
| `pattern_id` | string or null | Only populated for `auto_approved` events |

Approval rate formula for Tier 3 prerequisite:

```
approval_rate = count(decision = approved) / (count(decision = approved) + count(decision = rejected))
```

`auto_approved` and `operator_timeout` events are excluded from the denominator. Tier 3 requires `approval_rate >= 0.90` AND a minimum sample size of 20 manual decisions. Pattern auto-apply is blocked if the audit registry contains `high` or `critical` findings for the target.

### Delivery Semantics

Events feed into Phase 5 artifacts during Council sessions. In on-demand mode, events are emitted synchronously and persisted to `$WORKSPACE/documenter/events/` for operator replay. Lost events are reconstructed from leftover intent records at cold-start (§Intent Record). Ordering is preserved within a `target_id` scope. During post-crash reconciliation, events are emitted before intent record deletion (§Intent Record, cleanup order).

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

*Aligned with Documenter Service v0.4.0 and sess-documenter-consiliums.*
