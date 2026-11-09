# Cross-Service Artifact & Event Contract

Version: 0.2.0
Status: draft
Last Modified: 2026-11-09
Abstraction: format
changelog-path: CHANGELOGS/service-contract.changes.md

---

## Scope

Field-level schemas for artifacts that cross a service boundary, the canonical event envelope, frozen enumerations, and the error-code registry. Only fields that a protocol rule reads or the operator surface renders are specified; prose remains authoritative for everything else.

Non-goals: full JSON Schema for every artifact, a schema migration chain, and provider-specific payloads (`SUBJ-006`, deferred).

## Common Conventions

- UTF-8 JSON objects, `snake_case` keys, no duplicate keys.
- `schema_version`: integer, currently `1`; required on `SessionManifest` and `EventEnvelope`, inherited by embedded artifacts.
- Timestamps: ISO 8601 UTC with `Z` (`2026-11-08T15:00:00Z`). Hashes: `sha256:<64 lowercase hex>`.
- Unknown fields: producers MUST NOT emit them; consumers MUST reject them (`VAL.001`).
- `null` means "explicitly no value". An absent required field is invalid, not null. Mandatory for `stance`.
- Identifiers: `session_id` `^sess-[a-z0-9][a-z0-9-]{2,63}$`; `subject_id` `^SUBJ-[0-9]{3}$`; `escalation_id` `^esc-[a-z0-9][a-z0-9-]{2,63}$`; `event_id` `^evt-[a-z0-9][a-z0-9-]{2,63}$`; `review_id` `^rev-[a-z0-9][a-z0-9-]{2,63}$`; `audit_id` UUIDv4; `operator_id` `^op-[a-z0-9][a-z0-9-]{2,63}$`.

## Frozen Enumerations

Wire values are lowercase kebab-case; display strings are localized by the operator surface and never stored.

| Enum | Values |
|------|--------|
| `severity` | `low`, `medium`, `high`, `critical` |
| `stance` | `support`, `oppose`, `null` |
| `role_status` | `agree`, `concerns`, `blocked-in-scope`, `blocked-escalation` |
| `escalation_reason` | `information-gap`, `irresolvable-conflict`, `risk-threshold-breach` |
| `phase_id` | `1` submission, `2` individual review, `3` discussion, `4` consensus check, `5` resolution |
| `session_mode` | `fallback`, `moderator` |

Glossary labels map to wire values: `information gap` → `information-gap`, `irresolvable conflict` → `irresolvable-conflict`, `risk threshold breach` → `risk-threshold-breach`.

## Artifact Schemas

### Finding

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `subject_id` | string | yes | Must exist in the session subject list |
| `severity` | enum | yes | |
| `stance` | enum \| null | yes | `null` when not addressing a proposed decision |
| `summary` | string | yes | 1–500 chars; no secrets or full document text |
| `justification` | string \| null | conditional | Required for `critical`; names a failure mode or attack and references `subject_id` |
| `recommendation` | string \| null | no | Operator-facing action |
| `evidence_ref` | string \| null | no | Artifact path or hash; redacted |

### InvalidFormat

Produced by Layer 0 `extract_role_status()` when the review text cannot be parsed (status enum unrecognizable, required fields absent). Consumers MUST NOT infer a default status; the session enters `blocked-escalation` with `escalation_reason = information-gap`.

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `error_code` | string | yes | Always `invalid-format` |
| `raw_text_hash` | string | yes | `sha256` of the original review text submitted by the role |
| `parse_attempted` | boolean | yes | `true` — indicates an attempt was made and failed |
| `role_id` | string \| null | no | If known from the envelope context; absent if the review itself is malformed |
| `session_id` | string \| null | no | If known from the envelope context; absent if the review itself is malformed |

### RoleReview

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `escalation_reason` | enum \| null | no | Required when status = `blocked-escalation`; one of: information-gap, irresolvable-conflict, risk-threshold-breach. Otherwise null. Extracted structurally from the review text via Layer 0 `extract_role_status()`. |
| `review_id` | string | yes | Identifier format |
| `session_id` | string | yes | |
| `role_id` | string | yes | Must exist in the role catalog |
| `phase_id` | integer | yes | `2` or `3` |
| `round` | integer | yes | `0` for individual review |
| `summary_position` | string | yes | 1–2000 chars |
| `findings` | Finding[] | yes | May be empty |
| `status` | enum | yes | `role_status` |

The review also carries `recommended_actions` and `open_questions` (string arrays, possibly empty).

### RoleStatus

Produced by Layer 0 `extract_role_status()`; the review's declared status is not trusted until it appears here.

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `role_id` | string | yes | Must exist in the role catalog |
| `status` | enum | yes | `role_status` (`agree`, `concerns`, `blocked-in-scope`, `blocked-escalation`) |
| `phase_id` | integer | yes | Phase producing this status |
| `source_review_id` | string | yes | Identifier of the review this status derives from |
| `escalation_reason` | enum \| null | conditional | Required when status = `blocked-escalation`; one of `information-gap`, `irresolvable-conflict`, `risk-threshold-breach`. Null otherwise. Extracted structurally from the review, never inferred from free text. |
| `extraction` | enum | yes | `parsed` or `invalid-format` |

### ConsensusVerdict

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `session_id` | string | yes | |
| `phase_id` | integer | yes | `4` |
| `outcome` | enum | yes | `consensus`, `conditional`, `no-consensus`, `blocked-escalation` |
| `role_statuses` | RoleStatus[] | yes | One per active role; no omissions |
| `blocking_subjects` | string[] | yes | Subjects with a blocking status |
| `disagreement_subjects` | string[] | yes | Subjects with both `support` and `oppose` in the final round |
| `escalation_reason` | enum \| null | conditional | Required when `outcome = blocked-escalation` |
| `computed_at` | timestamp | yes | |

### ValidationResult

`{check: subject-reference|justification-format|status-extraction, subject_id: string|null, valid: boolean, code: VAL.*|PROT.*, message: string (redacted), severity: severity|null}` — `subject_id` and `severity` optional; the rest required.

### EscalationRecord

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `escalation_id` | string | yes | Identifier format |
| `session_id` | string | yes | |
| `raised_by_role` | string | yes | |
| `reason` | enum | yes | `escalation_reason` |
| `severity` | enum | yes | |
| `blocker` | string | yes | 1–2000 chars |
| `positions` | object[] | yes | `{role_id, stance, summary}` per side |
| `operator_request` | string | yes | One concrete decision or missing input |
| `fallback_strategy` | string | yes | What happens if the operator does not answer |
| `timeout_at` | timestamp \| null | yes | `null` when no deadline is set |
| `resolution` | object | yes | `{state: pending\|accepted\|rejected\|superseded\|expired, note, operator_id, resolved_at}` |
| `resume_phase` | integer | yes | Exact phase to resume |

### SessionManifest

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `schema_version` | integer | yes | `1` |
| `session_id` | string | yes | Identifier format |
| `mode` | enum | yes | `session_mode` |
| `scenario_id` | string | yes | |
| `task_ref` | string | yes | Relative path to the task brief |
| `current_phase` | integer | yes | `1`–`5` |
| `locked_roles` | string[] | no | Explicitly excluded Core role identifiers. Empty or absent when all Core roles are active. Each entry must refer to a defined Core tier role ID. Used only when `operator_approval` is present. |
| `operator_approval` | boolean | no | `true` when Core role exclusions are deliberate and approved by the operator. Must be `false` or absent when `locked_roles` is empty. If `true`, `locked_roles` MUST not be empty. |
| `no_consensus_budget` | integer | yes | Maximum discussion rounds before budget exhaustion transitions 4→`awaiting-operator`. See protocol-core §Outcome-to-Transition table for semantics. Budget decrements per Phase 3 round; zero exhausts it and forces `blocked-escalation` on next Phase 4 evaluation. |
| `phase_state` | enum | yes | `active`, `awaiting-operator`, `resolved`, `failed` |
| `active_roles` | string[] | yes | Core roles unless listed in `locked_roles` with `operator_approval: true`; see §InvalidFormat Policy for the full rule. |
| `pending_operator_action` | string \| null | yes | `null` when none |
| `configuration_source` | enum | yes | `scenario_defaults`, `operator_explicit`, `mixed` |
| `role_agent_config` | object | yes | Per-role parameters actually used |
| `artifacts` | object | yes | Paths to phase files and final artifacts |
| `created_at` / `updated_at` | timestamp | yes | |
| `manifest_hash` | string | yes | Hash of canonical JSON without this field |
| `previous_manifest_hash` | string \| null | yes | Hash chain; `null` on first write |
| `pre_check_override` | string \| null | no | Reason recorded when `council.override_precheck` is invoked (operator verb). Empty or absent when no override was applied. Logged as a `precheck.overridden` event in the event log. |

## InvalidFormat Policy

`extract_role_status()` returns `RoleStatus.extraction = invalid-format` when the status cannot be parsed unambiguously. The runtime MUST NOT default to `agree` or `concerns`. The session enters `blocked-escalation` with `escalation_reason = information-gap`; the raw review text is preserved, and the role is not counted as agreeing. The operator may resume after supplying an interpretation or re-running the role.

A missing Core role is a blocking protocol error, not a simplification: `blocked-escalation` with `escalation_reason = risk-threshold-breach`.

## Event Envelope

One envelope for all services. Documenter's `documenter.issue` and `documenter.approval` are event types inside this envelope, not a separate contract.

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `schema_version` | integer | yes | `1` |
| `event_id` | string | yes | Unique; idempotency key |
| `event_type` | enum | yes | `session.phase-changed`, `role.review-completed`, `consensus.computed`, `escalation.opened`, `escalation.resolved`, `documenter.issue`, `documenter.approval`, `documenter.override_gate`, `notice.simplification-applied`, `notice.fallback-deferred`, `precheck.passed`, `precheck.failed`, `precheck.overridden`, `precheck.unavailable`, `notice.quick_review_disabled`, `notice.documenter_tier2_interlock` |
| `emitted_at` | timestamp | yes | |
| `session_id` | string \| null | yes | Mandatory for session-specific events; nullable (`null`) only for corpus-wide Documenter audits that scan across all sessions. |
| `phase_id` | integer \| null | yes | |
| `actor` | object | yes | `{kind: operator\|agent\|service, id}` |
| `severity` | enum \| null | yes | |
| `payload` | object | yes | Type-specific; redacted |
| `causation_id` / `correlation_id` | string \| null | yes | Cause event and protocol round |
| `caller_class` | string \| null | no | When present, echoes the auth layer's caller class resolution (`operator`, `agent`, or `service`). Set by Layer 2 ingress before events flow to Layer 1; omitted when auth is not applicable to this event source (e.g., internal Layer 1 transitions). |

Actor carries two distinct fields: `actor.kind` is the caller class (`operator`, `agent`, or `service`); `actor.id` is the principal identifier (e.g. `op-...` for operators, UUID for agents). The envelope also implicitly records the auth layer's validation result via `severity` when an auth-related event is emitted (see AUTH.* error codes below).

Redaction rule: manifests and events MUST NOT contain secrets, full prompts, or document text. Hashes, identifiers, counts, and short summaries are allowed.

## Error Management

Error codes, configuration precedence, schema versioning, critical finding validation, and golden fixtures are in `error-management/index.md`.

## Cross-References

- `error-management/index.md` — error codes, config, validation process, golden fixtures
- `planned-architecture/layer-0.md` — functions consuming these schemas
- `planned-architecture/layer-1.md` — producers of role artifacts
- `execution-runtime/index.md` — phase and persistence semantics
- `operator-surface/index.md` — rendering and escalation delivery
- `documenter-service/configuration-guide.md` — Documenter event payloads
