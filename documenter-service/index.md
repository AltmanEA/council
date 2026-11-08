# Documenter Service

Version: 0.14.0-draft
Status: draft
Last Modified: 2026-11-09
Abstraction: protocol
changelog-path: CHANGELOGS/documenter-service.changes.md

---

## Purpose

Documenter is a Layer 2 service maintaining documentation quality per `AGENTS.md` rules. It operates as an **on-demand utility** — all functions begin upon explicit operator invocation; no background processes or file watchers run autonomously. It provides two interfaces: `audit()` for read-only reporting and `delegate()` for write operations via the Documentation Worker skill. A four-tier trust model governs delegate() write capabilities. Interface parameter schemas are authoritative in §Interfaces; configuration fields are defined in the Policy Reference (`documenter-service/policy-reference.md`) and runtime data structures in the Configuration Guide (`documenter-service/configuration-guide.md`).

---

## Architecture Position

Documenter lives in **Layer 2 (Integration & Orchestration)** as an independent on-demand utility, alongside the other Layer 2 interface components (transport adapters, structured input validation, quick-review path, error localization — see `planned-architecture/layer-2.md`). It is not part of the Layer 1 role-agent execution path: ScenarioLoader and RoleAgentFactory belong to Layer 1 (`planned-architecture/layer-1.md`), so no peer/subordinate relationship with ScenarioLoader exists. It does NOT orchestrate Council sessions — it scans, reports, and delegates on demand. No causal dependency between Council orchestration flow and Documenter operations. Invocations are explicit RPC-style calls from the operator; no event-driven subscription or filesystem polling.

Sync mode (the `pre_check` parameter of `audit()`, see §Interfaces) is available for mid-session integrity gates. The operator is the originating actor for all invocations; the gate request is delivered through the **Layer 2 session surface** — an explicit operator command or an RPC-style request (e.g., HTTP POST received by a Layer 2 transport adapter) — and invokes Documenter downward, consistent with the downward-only dependency rule (`planned-architecture/index.md`). Documenter never accepts invocations from Layer 0 or Layer 1; sync mode preserves idle-until-invoked semantics. All modes operate identically under the hood: each invocation performs an independent full scan of the target documents.

---

## Interfaces

### audit() — Read-only diagnostics

Returns a structured report without touching any write path. Scans documents against compliance rules using information from the manifest and glossary. The table below is the authoritative parameter schema for this interface.

| Parameter | Type | Description |
|-----------|------|-------------|
| target_id | string | Document identifier from manifest, or `"*"` for all |
| severity_min | enum | Minimum severity to include: `low`, `medium`, `high`, `critical`. Default: `low` |
| pre_check | bool | Mid-session integrity gate flag, set by the Layer 2 session surface at phase boundaries. Identical scan semantics; the report is additionally returned as a synchronous gate verdict to the caller. No write path involved. Default: `false` |

| Returns | Type | Description |
|---------|------|-------------|
| audit_id | string | Unique identifier for this audit invocation (UUIDv4). Persisted in the audit registry (`documenter-service/configuration-guide.md`, §Audit Registry) with timestamp, scope, and findings. Used by `delegate()` pre-audit gate to verify freshness, scope coverage, and absence of blocking findings (see §Interfaces, delegate()). |
| report | dict | Structured findings list with severity, subject, document_id, description, suggested_action |

Severity levels (unified across all interfaces and event schema):

| Level | Descriptor | Operator effect |
|-------|-----------|-----------------|
| `low` | Cosmetic issue, no data impact | Audit trail only |
| `medium` | Potential inconsistency, low risk | Surface in report + persist event to append-only log; write may proceed only with explicit operator approval |
| `high` | Confirmed issue, moderate risk | Block write; require explicit operator approval |
| `critical` | Data integrity compromise, immediate risk | Block write + mandatory post-mortem capture (§Safety Protocol #8); no auto-apply path at any tier |

### Approval semantics

Severity governs report inclusion and write blocking only. Approval is an explicit operator action taken within the synchronous `delegate()` execution flow (see §Interfaces, delegate() execution flow). Documenter does not track time-based state between invocations and does not auto-approve findings: no timer or background process exists (see §Purpose, idle-until-invoked). The only auto-execution path is Tier 3 pattern-based auto-apply, driven by the operator's prior pattern authorization — never by elapsed time.

Legacy mappings from prior versions: `info` → `low`, `warning` → `medium`, `error` → `high`. All rendering tools SHOULD map: `critical`→red, `high`→orange, `medium`→yellow, `low`→gray.

### delegate() — Write through Documentation Worker skill

Invokes a specific operation on a document with trust-level control. Only callable after operator policy gate review. The table below is the authoritative parameter schema for this interface; the policy fields it consumes are defined in the Policy Reference (§Cross-References).

| Parameter | Type | Description |
|-----------|------|-------------|
| target_id | string | Document identifier from manifest |
| change_type | enum | One of: `update`, `split`, `create_ru`, `custom` |
| trust_level | enum | Caller's *request*, not the effective value: `safe` or `review`. Documenter derives the required floor per §Trust Classification and accepts the request only if it is equal to or stricter than that floor (`requested >= derived`); a request below the floor is rejected with `error_category: trust_mismatch`. The effective level is the requested level. |
| diff | bytes | Machine-readable diff for operator preview. Mandatory for all tiers. |
| audit_id | string | Identifier from a prior `audit()` return. Validated against `audit_freshness` policy. Omitted only when the gate is explicitly disabled in the policy file. |

Execution flow: `audit → compute diff → present to operator → wait for approve/reject → apply if approved → commit per Multi-file Commit Protocol (§Safety Protocol #9) → log to audit trail`. Per-file writes use the temp-file + rename syscall (see §Safety Protocol #5), guaranteeing an atomic transition from staged state to committed content for a single file. Cross-file atomicity is NOT provided by rename alone — see §Failure semantics.

**Pre-audit gate:** By default, `delegate()` requires a valid `audit_id` from a prior `audit()` invocation. Validation proceeds against the audit registry (`documenter-service/configuration-guide.md`, §Audit Registry): (1) the `audit_id` must exist; (2) its `issued_at` must fall within the `audit_freshness` window (policy field, default 30 minutes; schema: `documenter-service/policy-reference.md`, §Field Reference); (3) its `scope` must cover `target_id` (`*` matches any, otherwise exact match); (4) no `high` or `critical` finding may exist for `target_id` in the registry. Rejection on (1-3) uses `error_category: audit_mismatch`; on (4) uses `error_category: blocking_finding`. Suggested action in both cases: re-run `audit()` for the target and retry. When the registry is absent or unreadable (cold-start, corruption), the gate is skipped and the call proceeds. The gate is configurable via the `audit_freshness` policy field but defaults to enforced.

**Trust Classification:** The effective trust level is assigned by Documenter, not by the caller. The caller's `trust_level` parameter may equal or tighten the derived floor but never relax it: on the scale `safe < review`, the invariant is `requested >= derived`, and the effective level is `requested`. If `requested < derived`, `delegate()` rejects the call with `error_category: trust_mismatch` before the operator approval stage. No silent upgrade occurs. When classification is uncertain, `review` applies. The policy reference (`documenter-service/policy-reference.md`) may raise the floor above the table but MUST NOT lower it (§Policy File, §Authority rule). `suggested_trust_level` in §Event Schema is the output of this same classifier.

| change_type | Static floor (policy load) | Dynamic derivation (invocation) | `safe` permitted |
|-------------|---------------------------|--------------------------------|------------------|
| `update`      | `safe`                    | `safe` if every hunk is mechanical; otherwise `review` | Yes, only for fully mechanical diff |
| `split`       | `review`                  | `review`                         | Never |
| `create_ru`   | `review`                  | `review`                         | Never (RU auto-fix banned in MVP) |
| `custom`      | `review`                  | `review`                         | Never (default when indeterminate) |

The `update` static floor is `safe` for load-time policy validation (the validator sees only `change_type`). Dynamic derivation is invocation-time: a fully mechanical diff derives `safe`, any semantic hunk derives `review`. A policy entry naming `update` + `safe` passes load-time validation; a non-mechanical diff still derives `review` and rejects a `safe` request with `trust_mismatch`.

**Failure semantics:** On interruption or failure during `delegate()` execution, the operation must follow an all-or-nothing model — no partial writes persist for a single file (guaranteed by temp-file + rename syscall). Cross-file partial commits are possible only between renames of different files; this is not prevented by rename atomicity or journaling filesystems (journaling guarantees internal filesystem consistency, not cross-file atomicity or audit log delivery). The Multi-file Commit Protocol (§Safety Protocol #9) provides crash-recoverable eventual consistency: a crash mid-sequence leaves a detectable partial state with leftover staged files and an intent record, which is reconciled by the next cold-start check (§Configuration Guide, Intent Record). Recovery without operator intervention is automatic when no external modifications occurred; otherwise, a structured error event is emitted and recovery requires explicit re-invocation. This converts silent corruption into documented limitation with an explicit mitigation path. Future versions (Phase 2+) will introduce checkpoint/resume via WAL-backed atomic state snapshots; until then, operators MUST treat each phase boundary as a commitment point.

Events emitted during delegate() use the Event Schema defined in §Configuration Guide. Every delegate() failure emits an event using §Event Schema with `error_category` (`hash_mismatch`, `trust_mismatch`, `audit_mismatch`, `blocking_finding`, `skill_failure`, `operator_timeout`, `unknown`).

---

## Trust Tiers

Four deployment tiers governing progressively greater write capability. Each tier requires explicit operator command to advance.

| Tier | Capability | Auto-execution | Diff Required | Scope |
|------|-----------|----------------|---------------|-------|
| 0 | Audit only (MVP) | None | N/A (no writes) | Read manifest + docs, produce report |
| 1 | Diff preview | None | Yes | Produce diffs, no filesystem writes |
| 2 | Confirm-per-change | No | Yes, per-item | Apply changes only after individual approve |
| 3 | Batch approve | Pattern-based | Yes, per-batch with group summaries | Approved patterns auto-apply; critical items require per-item expanded review |

Tier 0–1 ship with MVP. Tier 2+ enters production only after a documented policy file authorizing specific `change_type` + `trust_level` combinations exists. Advancement to Tier 2+ requires: (a) an authored policy file per `documenter-service/policy-reference.md`, AND (b) an archived operator briefing referenced by the policy file (`briefing_ref` field). Both conditions MUST be satisfied before the first Tier 2+ invocation. See §Authorization Workflow for the step-by-step procedure. Pattern-based auto-apply at Tier 3 is the only auto-execution path in the system; it derives from the operator's prior pattern authorization, not from elapsed time (see §Approval semantics).

### Tier Selection Guidance

| Tier | Recommended Use Case | Prerequisite |
|------|---------------------|---------------|
| 0 | Initial deployment, learning system behavior | None |
| 1 | Verify accuracy without risking changes | None |
| 2 | Active maintenance, selective corrections | Policy file (`documenter-service/policy-reference.md`) authorizing Tier 2 operations |
| 3 | Large-scale cleanup, seasonal restructuring | Operational history demonstrating ≥90% approval rate at Tier 2 over 2 weeks |

### Authorization Workflow

Procedure by which the operator grants write capability. Documenter performs none of these steps on its own behalf; each is an explicit operator action, and the detailed checklist with validation failure modes is in `documenter-service/policy-reference.md`, §Authorization Workflow.

1. **Audit** — resolve `high` and `critical` findings at the current tier. Tier advancement over a non-compliant corpus automates drift, not cleanup.
2. **Author** — write the policy file: `allowed_operations` entries for the intended `change_type` + `trust_level` + `targets` combinations, plus operational tuning fields.
3. **Validate** — load the candidate file in check-only mode. Load fails on a non-empty `allowed_operations` below Tier 2, a `trust_level` below the derived floor of §Trust Classification, or an unrecognized policy value.
4. **Brief** — archive the operator briefing (delegated scope, maximum number of documents a single invocation may touch, reversal procedure) and point `briefing_ref` at it. Set `active_tier` and `briefing_ref` in the same edit so a partial edit cannot leave Tier 2+ unbriefed.
5. **Advance** — the next invocation runs at the new tier. The first `delegate()` at the new tier targets a single low-risk document; the diff is reviewed item by item regardless of tier.
6. **Evaluate** — Tier 3 requires documented evidence (≥90% approval at Tier 2 over the preceding two weeks of the event log) and explicit enumeration of approved patterns; no pattern is inferred.

Rollback is symmetric: lowering `active_tier` takes effect at the next invocation; an in-flight `delegate()` completes under the tier at which it was accepted.

---

## Quick Start

One-line getting started path for new operators:

```
# Step 1 — Read-only audit (Tier 0, no risk)
documenter audit "*" --severity-min low

# Step 2 — Review findings, understand trust tiers
documenter explain-tier --target <doc-id>

# Step 3 — Authorize write (Tier 1, diff preview only)
# Edit documenter_policy.yml: active_tier: 1

# Step 4 — Execute first delegate change
documenter delegate --target <doc-id> --diff-view
```

See §Authorization Workflow for tier advancement beyond Tier 1 and `AGENTS.md` for documentation rules this service enforces.

---

## Safety Protocol

1. **Pre-change snapshot**: capture git status and HEAD commit before starting modifications.
2. **Advisory lock**: before any `delegate()` write, acquire an exclusive advisory lock (`flock --exclusive`) on the operation-level lock file (`documenter/.delegate.lock`) covering the entire changeset — target document, `index-RU.md`, changelog, `docs-manifest.yaml`, hash store — for single-host deployments. One operation-level lock replaces per-file locks and is deadlock-free by construction; lock ordering across files is therefore not required. If lock acquisition fails — emit error with context: "Another agent holds an advisory lock on [resource]. Lock owner: [PID/IP], acquired at [timestamp]. Wait? (yes/no) — Default: no after 30s." Distributed cross-host locking (e.g., POSIX flock on shared NFS) is out of scope for MVP; deferred to Phase 2+.
3. **Read-before-write**: immediately before writing any file, re-read it to detect concurrent modifications within the same lock scope. Abort if changed.
4. **Diff mandatory**: every write operation is preceded by machine-readable diff shown to the operator. No silent-auto changes.
5. **Atomic operation**: treat complete execution cycle as logical unit. On failure, abort remaining steps. Write operations MUST use temp-file + rename syscall pattern (write to `.tmp` path, then atomic `os.rename`) to prevent partial writes. This guarantees per-file atomicity only; multi-file changesets MUST additionally follow the Multi-file Commit Protocol (#9).
6. **No auto-commit**: modifies files but never commits them. Operator handles version control.
7. **Structured errors**: Every delegate() failure emits an event using §Event Schema with `error_category` (`hash_mismatch`, `trust_mismatch`, `skill_failure`, `operator_timeout`, `unknown`). Recovery procedures reference the category in `suggested_action`.
8. **Post-mortem capture**: On critical-tier findings triggered by delegate() failure, Documenter captures full operation trace (all steps attempted, intermediate states, timestamps) for operator review.
9. **Multi-file commit protocol**: For changesets spanning multiple files (document, `index-RU.md`, changelog, manifest, hash store), enforce a two-phase commit using only file operations — no background processes or daemons.
  a. **Stage**: write all new content to `.tmp` paths in their target directories. Validate all temp files before proceeding to phase 2.
  b. **Intent record**: before the first rename, write an intent record to `documenter/intent/<tx_id>.json` (see §Configuration Guide, Intent Record) identifying every file in the changeset. This record survives crashes and enables reconstruction. Write MUST use temp-file + rename pattern (same as §5) to prevent partial intent on crash mid-write; cold-start validates intent integrity before using it.
  c. **Ordered renames**: execute renames in a fixed order — document content → `index-RU.md` → changelog → `docs-manifest.yaml` → `documenter/hashes.json`. Manifest is committed last among documents so that a crash before the manifest leaves orphaned but readable files (safe, auditable), rather than dangling cross-references (breaking).
  d. **Cleanup**: after all renames, emit audit events to the append-only audit log, update the hash store contents (the file was already renamed in 9c), then delete the intent record. The intent record MUST be the last element removed — it is the sole durable fallback for post-crash event reconstruction.
  Recovery: on cold-start, if leftover intent records exist, compare each entry's `before_hash` and `after_hash` with actual file content. Three branches: (1) if files match `after_hash` — already committed by a prior successful run, skip; (2) if files match `before_hash` — no external modification since crash, roll forward from staged `.tmp` files automatically; (3) if neither matches — external modification detected, abort and escalate to the operator with `error_category: unknown` and post-mortem trace (§8). Lost audit events are reconstructed from the intent record.

---

## Cross-References

- **`documenter-service/policy-reference.md`** — Policy file schema and field reference, operational tuning parameters, authorization workflow checklist
- **`documenter-service/configuration-guide.md`** — Hash store structure, intent record schema, event schema, glossary compliance settings, RU alignment procedure
- `protocol-core/index.md` — Protocol enforcement interface (layer boundary)
- `planned-architecture/layer-2.md` — Layer 2 component inventory (confirms Documenter's architectural position)
- `fallback/index.md` — Fallback mode operator workflow (used during pre-Moderator phase)
- `docs-manifest.yaml` — Single source of truth for document layout
- `glossary/index.md` — Canonical term definitions for compliance verification
- `.agents/skills/documentation/SKILL.md` — Documentation Worker skill (invoked by delegate())
- `AGENTS.md` — All documentation rules this service enforces

---

*Aligned with planned architecture v0.1.0, sess-documenter-consiliums, and v0.4.0 spec split.*
