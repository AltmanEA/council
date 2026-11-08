# Operator Surface & Escalation

Version: 0.1.0
Status: draft
Last Modified: 2026-11-08
Abstraction: protocol
changelog-path: CHANGELOGS/operator-surface.changes.md

---

## Scope

Defines the single MVP transport, caller identity, operator verbs, the `pre_check` gate, escalation delivery and resume, Documenter invocation, and event delivery. Artifact fields are in `service-contract/index.md`; runtime semantics are in `execution-runtime/index.md`.

## Transport and Entry Point

MVP ships one transport: MCP over stdio. The operator surface is an adapter in Layer 2: it authenticates the caller, validates input, and calls Layer 1. It contains no protocol logic and no LLM invocation. CLI and REST remain deferred adapters over the same library functions.

## Caller Identity and Authorization

Three caller classes: `operator`, `agent`, `service`.

- AuthN: local stdio process plus `COUNCIL_OPERATOR_ID` and `COUNCIL_OPERATOR_TOKEN` from the environment. The surface verifies the token and never forwards it to Layer 1.
- AuthZ is deny-by-default. An unknown caller or missing token is `VAL.001`.
- `operator_id` is a human principal. Agent principals MUST NOT approve Documenter writes or resolve escalations at MVP.

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

## Operator Verbs

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

## `pre_check` Gate

`pre_check` is a synchronous, in-invocation integrity gate, distinct from asynchronous escalation.

- It gates transitions `2 → 3`, `3 → 4`, and `4 → 5`.
- The surface calls `documenter.audit(pre_check=true)` for the target scope and receives a verdict synchronously.
- Fail-closed: if Documenter is unavailable, returns an error, or returns a `high`/`critical` finding, the transition is blocked.
- An authenticated `council.override_precheck` may proceed despite a failure only with a recorded reason; the override is written to the manifest and the event log.
- An override never bypasses Core-role presence, consensus rules, or escalation integrity.

## Escalation Model

Escalation is stop-and-resume. The runtime writes an `EscalationRecord`, sets `phase_state = awaiting-operator`, emits `escalation.opened`, and returns. The session is durable; the operator resolves it in a later invocation.

- No blocking stdin and no background waiter.
- `timeout_at` is informational at MVP; the surface owns the clock and evaluates it on the next invocation.
- There is no automatic expiry. An elapsed deadline is surfaced as a notice, not applied as a decision.
- The fallback strategy is advisory until the operator accepts or rejects it.

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

Notices are events in the canonical envelope (`notice.*`) and appear in `council.status`.

## Documenter Integration

Documenter is a Supporting service invoked through this surface. Its `audit()` and `delegate()` are MCP tools; events and verdicts return synchronously.

- Tier 0–1 ships at MVP: read-only audit and diff preview. `documenter.delegate` validates `change_type`, `diff`, and `audit_id`, then returns a preview without writing.
- Tier 2+ is interlocked until this specification is implemented. When enabled, `documenter.delegate` returns `approval_required` with an `approval_id` and the diff hash.
- Approval MUST be out-of-band from the proposing call: `documenter.approve` runs in a separate invocation, and the approving `operator_id` MUST differ from the `actor.id` of the proposing call.
- Approval is bound to `approval_id` and the diff hash and expires after a configured window. A changed diff invalidates the approval.
- `pre_check` reuses `audit()`; Documenter never accepts invocations from Layer 0 or Layer 1.

## Event Delivery

- Events are appended to `sessions/<session_id>/events.jsonl` in the canonical envelope.
- Delivery is at-least-once; consumers deduplicate by `event_id`.
- The consumer contract is append-only: no edits, no deletes, no reordering.
- `session_id` is mandatory provenance except for corpus-wide Documenter audits.
- Manifests and events are redacted: no secrets, full prompts, or document text.
- `council.status` uses `last_event_id` to answer "what changed since last look".

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
