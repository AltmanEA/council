# Operator Surface & Escalation

Version: 0.1.3
Status: draft
Last Modified: 2026-11-08
Abstraction: protocol
changelog-path: CHANGELOGS/operator-surface.changes.md

---

## Scope

Defines the single MVP transport, caller identity, operator verbs, the `pre_check` gate, escalation delivery and resume, Documenter invocation, and event delivery. Artifact fields are in `service-contract/index.md`; runtime semantics are in `execution-runtime/index.md`.

## Transport and Entry Point

<!-- STATUS: Specification only, pre-implementation. Not executable until the Moderator is built. See AGENTS.md §1.7 for tooling separation. -->

<span style="color:red;font-weight:bold">⚠ SPECIFICATION ONLY — NOT EXECUTABLE UNTIL IMPLEMENTED</span> This section describes the transport contract; no MCP tools are currently callable. All sessions run in fallback mode per `AGENTS.md` §1.7.

MVP ships one transport: MCP over stdio. The operator surface is an adapter in Layer 2: it authenticates the caller, validates input, and calls Layer 1. It contains no protocol logic and no LLM invocation. CLI and REST remain deferred adapters over the same library functions.

## Caller Identity and Authorization

Three caller classes: `operator`, `agent`, `service`.

- AuthN: local stdio process plus `COUNCIL_OPERATOR_ID` and `COUNCIL_OPERATOR_TOKEN` from the environment. The surface verifies the token and never forwards it to Layer 1.
- AuthZ is deny-by-default. Auth failures (unknown caller, missing/invalid/revoked credential, expired token) are rejected per the AUTH.* error codes in `operator-surface/index.md` §Caller Identity and Authorization; structural schema violations remain `VAL.001`.
- `operator_id` is a human principal. Agent principals MUST NOT approve Documenter writes or resolve escalations at MVP.

#### Authentication (MVP)

Three caller classes are recognized:

| Class | Credential type | Scope | Verification |
|-------|----------------|-------|--------------|
| `Operator` | Session-bound signed token | Per-session, operator-identified by `op-...` prefix (format `^op-[a-z0-9][a-z0-9-]{2,63}$`) | Signature verified by shared auth module within Layer 2 |
| `Agent` | Session-scoped signed token with role claim | Bound to session_id and role_id | Signature + role membership checked on ingress |
| `Service` | HMAC-signed service account credential | Bound to service name and permitted operations | Pre-registered in policy config; HMAC verified on ingress |

Token structure: minimal JWT-like format `{alg, iss, sub, exp}`. Agent tokens include an additional `role` claim binding the principal to a specific role_id. Shared HMAC secret stored in `documenter-service/policy-reference.md` §Field Reference under `hmac_secret`, defaulting to operator-provided value at startup. Expired tokens produce `AUTH.001`. Malformed signatures produce `AUTH.002`. Unknown caller classes produce `AUTH.003`.

Error codes for auth failures:
- `AUTH.001` — Expired credential. Request the caller to obtain a fresh token.
- `AUTH.002` — Invalid signature or tampered token. Log and reject.
- `AUTH.003` — Unrecognized caller class. Verify MCP tool permissions or integration config.
- `AUTH.004` — Revoked credential (e.g., operator logout revokes all agent tokens from the session).

| Verb | Operator | Agent | Service |
|------|----------|-------|---------|
| `council.submit_task` | allow | deny | deny |
| `council.status` | allow | allow (read-only) | allow (read-only) |
| `council.list_sessions` | allow | allow (read-only) | allow (read-only) |
| `council.get_artifacts` | allow | allow (read-only) | allow (read-only) |
| `council.resolve_escalation` | allow | deny | deny |
| `council.override_precheck` | allow + reason | deny | deny |
| `documenter.audit` | allow | allow (read-only) | allow (read-only) |
| `documenter.delegate` | allow (Tier 0–1 preview) | deny | deny |
| `documenter.approve` | allow (Tier 2+, deferred) | deny | deny |
| `documenter.override_gate` | allow + reason | deny | deny |

## Operator Verbs

<!-- STATUS: Specification only — all listed tools are under development. See AGENTS.md §1.7 -->

<span style="color:red;font-weight:bold">⚠ SPECIFICATION ONLY — NOT EXECUTABLE UNTIL IMPLEMENTED</span> All entries below describe interface contracts; no MCP tools are currently callable until built.

| Tool | Purpose |
|------|---------|
| `council.submit_task` | Create a session from a task brief and scenario; returns `session_id` and initial status |
| `council.status` | Return the operator status projection: where am I, what needs me, what changed |
| `council.list_sessions` | List sessions filtered by `phase_state` or `mode` |
| `council.get_artifacts` | Retrieve phase files, consensus document, or escalation record |
| `council.resolve_escalation` | Bind an authenticated decision to an `escalation_id` |
| `council.override_precheck` | Record an authenticated `pre_check` override with a reason |
| `documenter.audit` | Run a read-only compliance scan; `pre_check=true` returns a gate verdict |
| `documenter.delegate` | Validate a change and return a diff preview; no writes at Tier 0–1 |
| `documenter.approve` | Out-of-band approval for Tier 2+ (deferred; see §Documenter Integration) |
| `documenter.override_gate` | Override a pre-check or audit-gate failure with a recorded reason and authenticated `operator_id`; emits `documenter.override_gate` event in the canonical envelope |

## `pre_check` Gate

### Scope and Enforcement Point

The `pre_check` gate is an integrity check on documentation artifacts before protocol state transitions are committed. It runs in Layer 2 (operator surface) as a synchronous call to Documenter's `audit(pre_check=true)` and returns a verdict to the caller within the same invocation.

- **Target scope:** all manifest documents relevant to the current session (identified by `target_id` from the active scenario).
- **Enforcement point:** invoked at every phase boundary transition (`2 → 3`, `3 → 4`, `4 → 5`) before committing the new phase state in Layer 1.
- **Gated transitions:** `2 → 3` (discussion start), `3 → 4` (consensus check), `4 → 5` (resolution). Transition is permitted only when the verdict is `pass`.
- **Verdict handoff to Layer 1:** the surface writes the verdict result (pass/fail/reason) into the manifest field `pre_check_override` on override or emits a `precheck.failed` event; the runtime reads this field/event at the next boundary evaluation and either proceeds or blocks accordingly.

### Verdict Logic

| Condition | Verdict | Action |
|-----------|---------|--------|
| No `high`/`critical` findings for target scope | `pass` | Proceed with transition |
| Any `high` or `critical` finding present | `fail` | Block transition; emit `precheck.failed` event |
| Documenter is unavailable (network error, timeout, service down) | `unavailable` | Block transition; emit `precheck.unavailable` event (see Override mode below) |
| Documenter audit registry is absent/corrupted/unreadable | `fail` | Block transition (fail-closed per C-03) |

### Documenter Unavailable — Override Mode

When Documenter cannot be reached (`unavailable` verdict), the moderator MVP MUST NOT block indefinitely. An authenticated `council.override_precheck(reason, operator_id)` may proceed despite the failure:

- The override records `reason` (free text explaining why the gate was bypassed).
- The override is written to the manifest via the `pre_check_override` field.
- A `precheck.overridden` event is emitted synchronously during the override invocation.
- The override permits exactly one subsequent phase transition without a fresh audit. After that transition, the next boundary requires another pass or a new override.
- An override never bypasses Core-role presence, consensus rules, or escalation integrity gates.

## Escalation Model

Escalation is stop-and-resume. The runtime writes an `EscalationRecord`, sets `phase_state = awaiting-operator`, emits `escalation.opened`, and returns. The session is durable; the operator resolves it in a later invocation or lets `timeout_at` trigger automatic application of `fallback_strategy`.

- No blocking stdin and no background waiter.
- `timeout_at` is enforced by the runtime: when current time exceeds `timeout_at`, the `fallback_strategy` from the `EscalationRecord` is applied automatically without further operator input (see `execution-runtime/index.md` §Escalation Routing).
- The surface renders `timeout_at` as a visible deadline so the operator can make an informed decision before automatic resolution.
- The fallback strategy is applied automatically at timeout; prior to that, the operator may accept or reject the request at any time.

## Escalation Presentation

The operator must see, in one view:

1. Conflicting positions side by side: role, stance, and summary per subject.
2. The concrete request: one decision or one missing input.
3. Fallback consequences: what happens if no answer is given.
4. Deadline: `timeout_at` or an explicit "no deadline".
5. Resume point: the exact `resume_phase`.
6. Evidence links: artifacts and event IDs supporting the request.

The view is a projection of `EscalationRecord`; it never paraphrases the request through an LLM.

## Escalation State Machine

| From | To | Condition |
|------|----|-----------|
| `pending` | `accepted` | Authenticated operator accepts the request or supplies the missing input |
| `pending` | `rejected` | Authenticated operator rejects the request; fallback applies |
| `pending` | `superseded` | A newer escalation replaces this one before resolution |
| `pending` | `expired` | Operator explicitly marks it expired; never automatic |
| `accepted` / `rejected` | — | Terminal; resolution is immutable once written |

Every transition records `operator_id`, `resolved_at`, and an optional note. A resolution without a matching `escalation_id` is `VAL.003`.

## Resolution Binding and Resume

`council.resolve_escalation` requires `{session_id, escalation_id, decision, note, operator_id}`. The surface verifies that the caller is an operator and that the escalation is `pending`.

- The decision is bound to `escalation_id`; it cannot be applied to another escalation or session.
- `resume_phase` defaults to the record's value. An explicit override requires a reason and is recorded.
- `resume_context` carries `{phase_id, subject_ids, artifacts, operator_note}` for partial continuation; absent fields mean "resume with existing artifacts".
- On success, the runtime applies the decision, updates the record, emits `escalation.resolved`, and continues from `resume_phase`.

## Notices

The surface MUST show operator-visible notices when any of the following occurs:

- A simplification was applied to the protocol parameters.
- A fallback was deferred or is advisory only.
- The quick-review path is disabled and the full path is forced.
- Documenter Tier 2+ is interlocked.
- A `pre_check` override was recorded.

Notices map to the following event types in the canonical envelope: `notice.simplification-applied`, `notice.fallback-deferred`, `notice.quick_review_disabled`, `notice.documenter_tier2_interlock`. Pre-check events use `precheck.passed`, `precheck.failed`, `precheck.overridden`, and `precheck.unavailable`. All appear in `council.status` and are persisted as append-only events. The complete notice-to-event mapping:

| Notice Condition | Event Type |
|------------------|------------|
| Simplification applied to protocol parameters | `notice.simplification-applied` |
| Fallback deferred or advisory only | `notice.fallback-deferred` |
| Quick-review path disabled, full path forced | `notice.quick_review_disabled` |
| Documenter Tier 2+ interlocked | `notice.documenter_tier2_interlock` |
| `pre_check` override recorded | `precheck.overridden` |

## Documenter Integration

<!-- STATUS: Specification only, pre-implementation. Not executable until the Moderator is built. See AGENTS.md §1.7 -->

<span style="color:red;font-weight:bold">⚠ SPECIFICATION ONLY — NOT EXECUTABLE UNTIL IMPLEMENTED</span> All `documenter.*` tools are specification-only; no MCP calls are currently callable. The operator surface integrates with the Documenter service per its contract.

Documenter is a Supporting service invoked through this surface. Its `audit()` and `delegate()` are MCP tools; events and verdicts return synchronously.

- Tier 0–1 ships at MVP: read-only audit and diff preview. `documenter.delegate` validates `change_type`, `diff`, and `audit_id`, then returns a preview without writing.
- Tier 2+ is interlocked until this specification is implemented. When enabled, `documenter.delegate` returns `approval_required` with an `approval_id` and the diff hash; no write proceeds until approval.
- Approval is **out-of-band**: the operator invokes `documenter.approve(approval_id, operator_id)` as a separate MCP tool call from the proposing `delegate()` invocation. The approving `operator_id` MUST differ from the `actor.id` of the proposing call to prevent self-approval.
- `approval_id` is a UUID-v4 returned by `delegate()`. It binds the specific diff hash; changed diffs invalidate pending approvals. The approval expires after `approval_expiry_window` minutes (default 30) — see policy-reference.md §Field Reference for the field definition.
- `documenter.approve` emits a `documenter.approval` event in the canonical envelope with `decision: approved` or `rejected`.

## Event Delivery

Events are appended to `sessions/<session_id>/events.jsonl` in the canonical envelope. This is the **single storage location** for all event data corpus-wide. The rule for `session_id = null` (corpus-wide Documenter audits) is: when `session_id` is `null`, events are appended to `documenter/corpus-audit/events.jsonl`. No other location is valid. Both paths follow the same at-least-once delivery semantics; consumers deduplicate by `event_id`.

## Error Handling

Errors use the registry in `service-contract/index.md` and are localized by the Layer 2 lookup table. Responses contain a code, a localized message, and an operator action. Stack traces, raw provider payloads, and secrets are never returned to the operator.

## Deferred

Typer CLI, REST transport, parallel mode, distributed locking, automatic escalation expiry, and mid-phase checkpoint/resume (ADR-004). Tier 2+ writes stay blocked until the out-of-band approval path is implemented and tested.

## Cross-References

- `service-contract/index.md` — artifact, event, and error schemas
- `execution-runtime/index.md` — phase machine, persistence, escalation routing
- `documenter-service/index.md` — Documenter interfaces and trust tiers
- `planned-architecture/layer-2.md` — adapter responsibilities
- `fallback/index.md` — manual fallback workflow
