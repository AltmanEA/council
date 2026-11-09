# Documenter Service

Version: 0.17.0-draft
Status: draft
Last Modified: 2026-11-09
Abstraction: protocol
changelog-path: CHANGELOGS/documenter-service.changes.md

---

## Purpose

Documenter is a **Supporting service** outside the three-layer chain, maintaining documentation quality per `AGENTS.md` rules. It operates as an **on-demand utility** — all functions begin upon explicit operator invocation; no background processes or file watchers run autonomously. It provides two interfaces: `audit()` for read-only reporting and `delegate()` for write operations via the Documentation Worker skill. A four-tier trust model governs delegate() write capabilities. Interface parameter schemas are authoritative in §Interfaces; configuration fields are defined in the Policy Reference (`documenter-service/policy-reference.md`) and runtime data structures in the Configuration Guide (`documenter-service/configuration-guide.md`).

Scope boundary: Documenter operates exclusively on manifest-tracked documentation artifacts and its own operational state (`documenter/` directory). Files outside these namespaces — session workspace files (`sessions/<id>/`), archive outputs, and any other non-manifest artifacts — are explicitly excluded from Documenter's scope. The `audit()` and `delegate()` interfaces accept only `target_id` values from the manifest; any invocation referencing non-manifest files is rejected with `error_category: unknown`.

---

## Architecture Position

Documenter is a **Supporting service** outside the three-layer chain. It is invoked by the Layer 2 operator surface (an explicit MCP tool call) and, for LLM-backed writes, uses a **Layer 1 execution port** to reach the Documentation Worker. It never calls Layer 2 or Layer 0 directly, and Layer 2 never invokes an LLM on Documenter's behalf. Events and verdicts are returned synchronously to the invoking surface; Documenter keeps no event loop, no subscription, and no filesystem watcher.

It is not part of the Layer 1 role-agent path: ScenarioLoader and RoleAgentFactory belong to Layer 1 (`planned-architecture/layer-1.md`), so no peer or subordinate relationship with ScenarioLoader exists. Documenter does not orchestrate Council sessions and holds no causal dependency on the orchestration flow. Every invocation is explicit and operator-originated. **Exception:** read-only operations (`audit()`) are accessible by Operator, Agent, and Service within permitted scope per the authZ matrix (§Caller Identity and Authorization, operator-surface); write operations (`delegate()`) originate from the operator or a delegated agent. Write intent requires tier validation against the `allowed_operations` policy; preview calls (`preview: true`) bypass tier checks entirely (§Preview Exemption).

Sync mode (`pre_check`, see §Interfaces) is a mid-session integrity gate. The gate request arrives through the Layer 2 operator surface, invokes Documenter, and returns a synchronous verdict to that surface. Documenter never accepts invocations from Layer 0 or Layer 1; sync mode preserves idle-until-invoked semantics. All modes perform an independent full scan of the target documents. When Documenter is unavailable (network failure, timeout, service down), the audit invocation returns `unavailable` synchronously; the surface emits `precheck.unavailable` event and defers the transition until override via `council.override_precheck`.

---

## Interfaces

### audit() — Read-only diagnostics

Returns a structured report without touching any write path. Scans documents against compliance rules using information from the manifest and glossary. The table below is the authoritative parameter schema for this interface.

| Parameter | Type | Description |
|-----------|------|-------------|
| target_id | string | Document identifier from manifest, or `"*"` for all |
| severity_min | enum | Minimum severity to include: `low`, `medium`, `high`, `critical`. Default: `low` |
| pre_check | bool | Mid-session integrity gate flag, set by the Layer 2 operator surface at phase boundaries (see `operator-surface/index.md`, §pre_check Gate). Identical scan semantics; the report is additionally returned as a synchronous gate verdict to the caller. No write path involved. Default: `false` |
| scan_cursor | string \| null | Continuation token from a prior partial scan (when `has_remaining` was `true`). Causes `audit()` to resume scanning from the stored position. Absent or `null` means start a fresh full scan. |

| Returns | Type | Description |
|---------|------|-------------|
| audit_id | string | Unique identifier for this audit invocation (UUIDv4). Persisted in the audit registry (`documenter-service/configuration-guide.md`, §Audit Registry) with timestamp, scope, findings, `scanned_ids`, `has_remaining`, and `scan_cursor`. Used by `delegate()` pre-audit gate to verify freshness, scope coverage, blocking findings absence, and scan completion. |
| report | dict | Structured findings list with severity, subject, document_id, description, suggested_action |
| has_remaining | boolean | `true` when the scan was paused due to `rescan_batch_ceiling`; caller should re-invoke `audit(scan_cursor=<value>)` with the returned `scan_cursor` to continue. |
| scan_cursor | string \| null | Continuation token for resumed scans. Present only when `has_remaining` is `true`. Opaque value encoding the last processed document position. |

Severity levels (unified across all interfaces and event schema):

| Level | Descriptor | Operator effect |
|-------|-----------|-----------------|
| `low` | Cosmetic issue, no data impact | Audit trail only |
| `medium` | Potential inconsistency, low risk | Surface in report; persist event to append-only log. Write may proceed only with explicit operator approval (not automatic). |
| `high` | Confirmed issue, moderate risk | Block write by default; require explicit operator approval before proceeding. |
| `critical` | Data integrity compromise, immediate risk | Block write + mandatory post-mortem capture (§Safety Protocol #8); no auto-apply path at any tier |

### Approval semantics

Approval is an explicit operator action via the out-of-band `documenter.approve(approval_id, operator_id)` tool call (§Documenter Integration, operator-surface). Documenter does not track time-based state between invocations and does not auto-approve findings: no timer or background process exists (see §Purpose, idle-until-invoked). The only auto-execution path is Tier 3 pattern-based auto-apply, driven by the operator's prior pattern authorization — never by elapsed time.

The out-of-band approval flow: (1) at Tier 2+, `delegate()` returns `approval_required` with an `approval_id` and diff hash but performs no write; (2) the operator independently invokes `documenter.approve(approval_id, operator_id)` (MUST be a separate invocation from the proposing call); (3) the approving `operator_id` MUST differ from the actor id of the proposing call to prevent self-approval; (4) upon successful approve, the system proceeds with the write using the same diff hash for binding; (5) changed diffs invalidate pending approvals.

Approval expires after a configured window (`approval_expiry_window`, default 30 minutes per policy-reference.md §Field Reference). An expired approval must be re-obtained before the diff can be applied. A new diff hash invalidates any still-valid approval.

Legacy mappings from prior versions: `info` → `low`, `warning` → `medium`, `error` → `high`. All rendering tools SHOULD map: `critical`→red, `high`→orange, `medium`→yellow, `low`→gray.

### delegate() — Write through Documentation Worker skill

Invokes a specific operation on a document with trust-level control. Only callable after operator policy gate review. The table below is the authoritative parameter schema for this interface; the policy fields it consumes are defined in the Policy Reference (§Cross-References).

| Parameter | Type | Description |
|-----------|------|-------------|
| target_id | string | Document identifier from manifest |
| change_type | enum | One of: `update`, `split`, `create_ru`, `custom` |
| trust_level | enum | Caller's *request*, not the effective value: `safe` or `review`. Documenter derives the required floor per §Trust Classification and accepts the request only if it is equal to or stricter than that floor (`requested >= derived`); a request below the floor is rejected with `error_category: trust_mismatch`. The effective level is the requested level. |
| diff | string (base64-encoded) | Machine-readable diff for operator preview, encoded as base64 to ensure JSON-safe transport per UTF-8 JSON constraints (§Common Conventions, service-contract). Mandatory for all tiers. |
| audit_id | string | Identifier from a prior `audit()` return. Validated against `audit_freshness` policy. Omitted only when the gate is explicitly disabled in the policy file. |
| preview | boolean | When `true`, the call returns only a diff without write intent and is exempt from `allowed_operations` checks across all tiers (§Preview Exemption). When omitted or `false`, the call carries write intent and is subject to normal tier restrictions (Tier 0–1 always denies writes regardless; Tier 2+ requires explicit approval; Tier 3 may auto-apply based on patterns). |

Execution flow: `audit → compute diff → present to operator → wait for approve/reject → apply if approved → commit per Multi-file Commit Protocol (§Safety Protocol #9) → log to audit trail`. Per-file writes use the temp-file + rename syscall (see §Safety Protocol #5), guaranteeing an atomic transition from staged state to committed content for a single file. Cross-file atomicity is NOT provided by rename alone — see §Failure semantics.

**Pre-audit gate:** By default, `delegate()` requires a valid `audit_id` from a prior `audit()` invocation. Validation proceeds against the audit registry (`documenter-service/configuration-guide.md`, §Audit Registry): (1) the `audit_id` must exist; (2) its `issued_at` must fall within the `audit_freshness` window (policy field, default 30 minutes; schema: `documenter-service/policy-reference.md`, §Field Reference); (3) its `scope` must fully cover `target_id` (`*` matches any, otherwise exact match); (4) no `high` or `critical` finding may exist for `target_id` in the registry; (5) if `has_remaining` was `true` for the registered scan, the delegate is rejected until a completed rescan is performed (cursor-based continuation via `audit(scan_cursor=<value>)`). Rejection on rules (1–3) uses `error_category: audit_mismatch`; on (4) or (5) uses `error_category: blocking_finding`. Suggested action in both cases: re-run `audit()` for the target and retry. When the audit registry is absent, corrupted, or unreadable, the gate FAILS CLOSED — all write operations are denied until explicit operator override. Override requires an authenticated action via `documenter.override_gate(reason, operator_id)` which logs the incident and permits exactly one subsequent `delegate()` call without a fresh audit. Repeat overrides require Tier 2+ approval. The gate is configurable via the `audit_freshness` policy field but defaults to enforced.

**Trust Classification:** The effective trust level is assigned by Documenter, not by the caller. The caller's `trust_level` parameter may equal or tighten the derived floor but never relax it: on the scale `safe < review`, the invariant is `requested >= derived`, and the effective level is `requested`. If `requested < derived`, `delegate()` rejects the call with `error_category: trust_mismatch` before the operator approval stage. No silent upgrade occurs. When classification is uncertain, `review` applies. The policy reference (`documenter-service/policy-reference.md`) may raise the floor above the table but MUST NOT lower it (§Policy File, §Authority rule). `suggested_trust_level` in §Event Schema is the output of this same classifier.

| change_type | Static floor (policy load) | Dynamic derivation (invocation) | `safe` permitted |
|-------------|---------------------------|--------------------------------|------------------|
| `update`      | `safe`                    | `safe` if every hunk is mechanical; otherwise `review` | Yes, only for fully mechanical diff |
| `split`       | `review`                  | `review`                         | Never |
| `create_ru`   | `review`                  | `review`                         | Never (RU auto-fix banned in MVP) |
| `custom`      | `review`                  | `review`                         | Never (default when indeterminate) |

The `update` static floor is `safe` for load-time policy validation (the validator sees only `change_type`). Dynamic derivation is invocation-time: a fully mechanical diff derives `safe`, any semantic hunk derives `review`. A policy entry naming `update` + `safe` passes load-time validation; a non-mechanical diff still derives `review` and rejects a `safe` request with `trust_mismatch`.

**Failure semantics:** On interruption or failure during `delegate()` execution, the operation must follow an all-or-nothing model — no partial writes persist for a single file (guaranteed by temp-file + rename syscall). Cross-file partial commits are possible only between renames of different files; this is not prevented by rename atomicity or journaling filesystems (journaling guarantees internal filesystem consistency, not cross-file atomicity or audit log delivery). The Multi-file Commit Protocol (§Safety Protocol #9) provides crash-recoverable eventual consistency: a crash mid-sequence leaves a detectable partial state with leftover staged files and an intent record, which is reconciled by the next cold-start check (§Configuration Guide, Intent Record). Recovery without operator intervention is automatic when no external modifications occurred; otherwise, a structured error event is emitted and recovery requires explicit re-invocation. This converts silent corruption into documented limitation with an explicit mitigation path. Future versions (Phase 2+) will introduce checkpoint/resume via WAL-backed atomic state snapshots; until then, operators MUST treat each phase boundary as a commitment point.

Events emitted during delegate() use the Event Schema defined in §Configuration Guide. Every delegate() failure emits an event using §Event Schema with `error_category` (`hash_mismatch`, `trust_mismatch`, `audit_mismatch`, `blocking_finding`, `skill_failure`, `operator_timeout`, `gate_failure`, `unknown`).

---

## Trust Tiers

Four deployment tiers governing progressively greater write capability. Each tier requires explicit operator command to advance.

| Tier | Capability | Auto-execution | Diff Required | Scope |
|------|-----------|----------------|---------------|-------|
| 0 | Audit only (MVP) | None | N/A (no writes) | Read manifest + docs, produce report |
| 1 | Diff preview | None | Yes | Produce diffs, no filesystem writes |
| 2 | Confirm-per-change | No | Yes, per-item | Apply changes only after individual approve |
| 3 | Batch approve | Pattern-based | Yes, per-batch with group summaries | Approved patterns auto-apply; critical items require per-item expanded review |

Tier 0–1 ship with MVP. Tier 2+ enters production only after a documented policy file authorizing specific `change_type` + `trust_level` combinations exists. Tier 2+ is additionally interlocked at the architecture level: no Tier 2+ invocation is accepted until the Operator Surface & Escalation specification defines an authenticated, out-of-band approval channel. A policy file alone is not sufficient. Advancement to Tier 2+ requires: (a) an authored policy file per `documenter-service/policy-reference.md`, AND (b) an archived operator briefing referenced by the policy file (`briefing_ref` field). Both conditions MUST be satisfied before the first Tier 2+ invocation. See §Authorization Workflow for the step-by-step procedure. Pattern-based auto-apply at Tier 3 is the only auto-execution path in the system; it derives from the operator's prior pattern authorization, not from elapsed time (see §Approval semantics).

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

<!-- STATUS: Specification only, pre-implementation. Not executable until the Moderator is built. See AGENTS.md §1.7 for tooling separation. -->

<span style="color:red;font-weight:bold">⚠ SPECIFICATION ONLY — NOT EXECUTABLE UNTIL IMPLEMENTED</span> The following examples illustrate the interface contract; no MCP tools are currently callable. All sessions run in fallback mode per `AGENTS.md` §1.7.

The MVP invocation path is MCP stdio. Every tool requires an explicit operator call; Tier 2+ writes are disabled (see §Trust Tiers).

```
# Step 1 — Read-only audit (Tier 0) [NON-EXECUTABLE: illustration only]
documenter.audit { "target_id": "*", "severity_min": "low" }

# Step 2 — Preview a change (Tier 1, no writes) [NON-EXECUTABLE: illustration only]
documenter.delegate {
  "target_id": "<doc-id>",
  "change_type": "update",
  "trust_level": "review",
  "diff": "ZGlmIGZpbGUuYmFja3VwLmluZGV4Om1vZGlmaWVk",
  "audit_id": "<audit_id returned by Step 1>"
}
```

At Tier 1 `delegate()` returns a diff preview only; it does not write. Tier 2+ stays interlocked until the Operator Surface & Escalation specification defines an out-of-band approval channel. See §Authorization Workflow and `AGENTS.md` for documentation rules this service enforces.

---

## Safety Protocol

1. **Pre-change snapshot**: capture git status and HEAD commit before starting modifications.
2. **Advisory lock**: before any `delegate()` write, acquire an exclusive advisory lock (`flock --exclusive`) on the operation-level lock file (`documenter/.delegate.lock`) covering the entire changeset — target document, `index-RU.md`, changelog, `docs-manifest.yaml`, hash store — for single-host deployments. One operation-level lock replaces per-file locks and is deadlock-free by construction; lock ordering across files is therefore not required. If lock acquisition fails — emit error with context: "Another agent holds an advisory lock on [resource]. Lock owner: [PID/IP], acquired at [timestamp]. Wait? (yes/no) — Default: no after 30s." Distributed cross-host locking (e.g., POSIX flock on shared NFS) is out of scope for MVP; deferred to Phase 2+.
3. **Read-before-write**: immediately before writing any file, re-read it to detect concurrent modifications within the same lock scope. Abort if changed.
4. **Diff mandatory**: every write operation is preceded by machine-readable diff shown to the operator. No silent-auto changes.
5. **Atomic operation**: treat complete execution cycle as logical unit. On failure, abort remaining steps. Write operations MUST use temp-file + rename syscall pattern (write to `.tmp` path, then atomic `os.rename`) to prevent partial writes. This guarantees per-file atomicity only; multi-file changesets MUST additionally follow the Multi-file Commit Protocol (#9).
6. **No auto-commit**: modifies files but never commits them. Operator handles version control.
7. **Structured errors**: Every delegate() failure emits an event using §Event Schema with `error_category` (`hash_mismatch`, `trust_mismatch`, `audit_mismatch`, `blocking_finding`, `skill_failure`, `operator_timeout`, `gate_failure`, `unknown`). Recovery procedures reference the category in `suggested_action`.
8. **Post-mortem capture**: On critical-tier findings triggered by delegate() failure, Documenter captures full operation trace (all steps attempted, intermediate states, timestamps) for operator review.
9. **Multi-file commit protocol**: For changesets spanning multiple files (document, `index-RU.md`, changelog, manifest, hash store), enforce a two-phase commit using only file operations — no background processes or daemons.
  a. **Stage**: write all new content to `.tmp` paths in their target directories. Validate all temp files before proceeding to phase 2.
  b. **Intent record**: before the first rename, write an intent record to `documenter/intent/<tx_id>.json` (see §Configuration Guide, Intent Record) identifying every file in the changeset. This record survives crashes and enables reconstruction. Write MUST use temp-file + rename pattern (same as §5) to prevent partial intent on crash mid-write; cold-start validates intent integrity before using it. Intent record entries MUST reference only manifest-tracked file paths. Any attempt to stage a non-manifest path during a changeset causes `delegate()` to reject with `error_category: unknown` and no writes proceed.
  c. **Ordered renames**: execute renames in a fixed order — document content → `index-RU.md` → changelog → `docs-manifest.yaml` → `documenter/hashes.json`. Manifest is committed last among documents so that a crash before the manifest leaves orphaned but readable files (safe, auditable), rather than dangling cross-references (breaking).
  d. **Cleanup**: after all renames, emit audit events to the append-only audit log, update the hash store contents (the file was already renamed in 9c), then delete the intent record. The intent record MUST be the last element removed — it is the sole durable fallback for post-crash event reconstruction.
  Recovery: on cold-start, if leftover intent records exist, compare each entry's `before_hash` and `after_hash` with actual file content. Three branches: (1) if files match `after_hash` — already committed by a prior successful run, skip; (2) if files match `before_hash` — no external modification since crash, roll forward from staged `.tmp` files automatically; (3) if neither matches — external modification detected, abort and escalate to the operator with `error_category: unknown` and post-mortem trace (§8). The intent record stores structural metadata (tx_id, target_id, created_at, entries[path, before_hash, after_hash]) sufficient to reconstruct which files were changed but does NOT contain the event decisions, operator stances, or full payload of protocol events. The claim that "lost audit events are reconstructed" is incorrect at MVP — only file-change provenance is recoverable; true event reconstruction requires the append-only audit log (§Delivery Semantics, configuration-guide).

---

## Cross-References

- **`documenter-service/policy-reference.md`** — Policy file schema and field reference, operational tuning parameters, authorization workflow checklist
- **`documenter-service/configuration-guide.md`** — Hash store structure, intent record schema, event schema, glossary compliance settings, RU alignment procedure
- `protocol-core/index.md` — Protocol enforcement interface (layer boundary)
- `planned-architecture/index.md` — layer model and Supporting service placement
- `planned-architecture/layer-1.md` — execution ports and Auxiliary Agents
- `fallback/index.md` — Fallback mode operator workflow (used during pre-Moderator phase)
- `docs-manifest.yaml` — Single source of truth for document layout
- `glossary/index.md` — Canonical term definitions for compliance verification
- `.agents/skills/documentation/SKILL.md` — Documentation Worker skill (invoked by delegate())
- `AGENTS.md` — All documentation rules this service enforces

---

*Aligned with planned architecture v0.4.0, sess-documenter-consiliums, sess-services-readiness (D3), and Documenter Service v0.16.0-draft.*
