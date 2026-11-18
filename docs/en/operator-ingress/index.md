# Operator Ingress & Escalation

id: operator-ingress
Version: 1.1.0
Status: draft
Abstraction: protocol
has_translation: docs/ru/operator-ingress/index-RU.md
references: [service-contract, execution-runtime]
changelog-path: CHANGELOGS/operator-ingress.changes.md

---

> Formerly "Operator Surface" — renamed per ADR-018 (Council session sess-term-operator-surface, 2026-11-18). Tool verbs (council.*, documenter.*), event names, wire strings and environment variables are unchanged code-level identifiers; the sentinel path was later renamed documenter/.operator_ingress_ready per ADR-019; "Operator Surface" in earlier ADR text (ADR-013/015/016) denotes this same component.

## Scope

Defines the single MVP transport, caller identity, operator verbs, the `pre_check` gate, escalation delivery and resume, Documenter invocation, and event delivery. Artifact fields are in `service-contract/index.md`; runtime semantics are in `execution-runtime/index.md`.

## Transport and Entry Point

<!-- STATUS: stdio transport implemented (p3 MVP); MCP registration is an operator act (AGENTS.md §1.7); Tier 2+ dormant (ADR-013). -->

<span style="color:red;font-weight:bold">⚠ MCP UNREGISTERED — stdio ONLY</span> This section describes the transport contract; the MCP server is not registered in the workspace configuration (operator decision). Sessions run in fallback mode per `AGENTS.md` §1.7 until a Moderator adapter is available.

MVP ships one transport: MCP over stdio. Operator Ingress (formerly Operator Surface) is an adapter in Layer 2: it authenticates the caller, validates input, and calls Layer 1. It contains no protocol logic and no LLM invocation. CLI and REST remain deferred adapters over the same library functions.

## Caller Identity and Authorization

Three caller classes: `operator`, `agent`, `service`.

- AuthN: local stdio process plus `COUNCIL_OPERATOR_ID` and `COUNCIL_OPERATOR_TOKEN` from the environment. The surface verifies the token and never forwards it to Layer 1.
- AuthZ is deny-by-default. Auth failures (unknown caller, missing/invalid/revoked credential, expired token) are rejected per the AUTH.* error codes in `operator-ingress/index.md` §Caller Identity and Authorization; structural schema violations remain `VAL.001`.
- `operator_id` is a human principal. Agent principals MUST NOT approve Documenter writes or resolve escalations at MVP.
- Operator identity is defined **exclusively** in this section. The `operator_id` that resolves escalations (§Resolution Binding and Resume) and approves Documenter writes (`documenter.approve`, `documenter-service/approval-surface.md`) is the same human principal, valid cross-document. No other document may define or extend who counts as an operator.

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

| Verb | Operator | Agent | Service | Owner |
|------|----------|-------|---------|-------|
| `council.submit_task` | allow | deny | deny | `operator-surface` |
| `council.status` | allow | allow (read-only) | allow (read-only) | `operator-surface` |
| `council.list_sessions` | allow | allow (read-only) | allow (read-only) | `operator-surface` |
| `council.get_artifacts` | allow | allow (read-only) | allow (read-only) | `operator-surface` |
| `council.resolve_escalation` | allow | deny | deny | `operator-surface` |
| `council.override_precheck` | allow + reason | deny | deny | `operator-surface` |
| `documenter.audit` | allow | allow (read-only) | allow (read-only) | mvp-contract.md §4 — DORMANT (ADR-013) |
| `documenter.delegate` | allow (Tier 0–1 preview) | deny | deny | mvp-contract.md §4 — DORMANT (ADR-013) |
| `documenter.approve` | allow (Tier 2+, implemented; policy-gated) | deny | deny | mvp-contract.md §4 — DORMANT (ADR-013) |
| `documenter.override_gate` | allow + reason | deny | deny | mvp-contract.md §4 — DORMANT (ADR-013) |

This table is the single transport-level permission registry owned by this document. Contract semantics of `documenter.*` verbs are defined by their owner (`documenter-service/mvp-contract.md` §4), not here.

## Security and Threat Model (MVP)

<!-- STATUS: Describes the implemented MVP (p3 Steps 0-9, sess-operator-surface-split). -->

- **Ingress.** The only entry point is the local stdio JSON-RPC server. Authentication is enforced before any verb route; unauthenticated requests receive AUTH.* envelopes and no verb executes. Only the `operator` caller class may exercise governance verbs; `agent` and `service` are denied by default per the permission table above. The HMAC secret comes from `COUNCIL_OPERATOR_SECRET` (fail-closed: missing or empty aborts startup).
- **No write path.** The Tier 2+ write branch is unreachable from the surface (ADR-013 dual interlock). `documenter.delegate` is preview-only; `documenter.override_gate` records the override event without invoking the Documenter port.
- **Sentinel is not activation.** `documenter/.operator_ingress_ready` is a code consequence of a successful READY handshake; activation remains exclusively a policy-file state act (ADR-016). Sentinel presence grants nothing. With the overlay mechanism, policy readiness is determined by the overlay file's content (scope, `active_tier`, `briefing_ref`) merged into the effective policy at read-time while the sentinel remains the second interlock condition (ADR-013/ADR-016); the base policy file stays at Tier 1 baseline.
- **Volatile state.** Escalation and approval registries are in-memory; they are lost on restart. The surface reports this through the advisory `notice.fallback-deferred` notice.
- **Degradation.** When `documenter_service` is unimportable the surface still starts; `documenter.*` verbs return an honest IO.004 envelope naming `council.status` as the fallback action; the pre_check gate returns `unavailable` and submit auto-proceeds with a `precheck.unavailable` event (ADR-015).
- **Crash integrity.** The session store silently skips malformed trailing lines on cold start and ignores stale intent records; roll-forward recovery is deferred (OD-3).
- **Out of MVP scope (threats accepted):** shared-secret rotation/revocation, replay protection, and state-root tamper resistance are deferred (see §Deferred).

## Operator Verbs

<!-- STATUS: stdio Tier 0-1 MVP implemented (p3 Steps 0-9); MCP unregistered; get_artifacts deferred (KD-1); Tier 2+ dormant (ADR-013). See AGENTS.md §1.7 -->

<span style="color:red;font-weight:bold">⚠ MCP UNREGISTERED — stdio ONLY</span> Entries below are implemented behind the stdio transport at Tier 0–1; `council.get_artifacts` remains deferred (roadmap KD-1); no MCP tools are callable while the MCP server is unregistered (operator decision).

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
| `documenter.approve` | Out-of-band approval for Tier 2+ (implemented; policy-gated — see `documenter-service/approval-surface.md`) |
| `documenter.override_gate` | Override a pre-check or audit-gate failure with a recorded reason and authenticated `operator_id`; emits `documenter.override_gate` event in the canonical envelope |

**Stub-swap record.** Of the six deferred-tool envelopes drafted at implementation Step 2, five were superseded by real authenticated handlers in the MVP transport: `documenter.delegate`, `documenter.approve`, `council.resolve_escalation`, `council.override_precheck`, and `documenter.override_gate`. Their drafted CONFIG.001 texts remain the localization source for the withdrawn drafts. `council.get_artifacts` continues to serve its drafted deferred envelope.

## `pre_check` Gate

### Scope and Enforcement Point

The `pre_check` gate is an integrity check on documentation artifacts before protocol state transitions are committed. It runs in Layer 2 (operator ingress) as a synchronous call to Documenter's `audit(pre_check=true)` and returns a verdict to the caller within the same invocation.

- **Target scope:** all manifest documents relevant to the current session (identified by `target_id` from the active scenario).
- **Enforcement point:** invoked at every phase boundary transition (`2 → 3`, `3 → 4`, `4 → 5`) before committing the new phase state in Layer 1.
- **Gated transitions:** `2 → 3` (discussion start), `3 → 4` (consensus check), `4 → 5` (resolution). Transition is permitted only when the verdict is `pass`.
- **Verdict handoff to Layer 1:** the surface writes the verdict result (pass/fail/reason) into the manifest field `pre_check_override` on override or emits a `precheck.failed` event; the runtime reads this field/event at the next boundary evaluation and either proceeds or blocks accordingly.

### Verdict Logic

| Condition | Verdict | Action |
|-----------|---------|--------|
| No `high`/`critical` findings for target scope | `pass` | Proceed with transition |
| Any `high` or `critical` finding present | `fail` | Block transition; emit `precheck.failed` event |
| Documenter is unavailable (timeout, service down) | `unavailable` | Timeout-and-continue: proceed with the transition, emit `precheck.unavailable` warning event synchronously (roadmap decision 3); the action applies to timeout-induced unavailability only, not to registry-integrity `fail` |
| Documenter audit registry is absent/corrupted/unreadable | `fail` | Block transition (fail-closed per C-03) |

The gate timeout is a boot-time constant: default 5 seconds, overridable once at startup via the `PRE_CHECK_TIMEOUT` environment variable; it is immutable for the process lifetime. Exceeding the timeout produces the `unavailable` verdict. A `precheck.running` event is emitted when the gate starts, so observers can distinguish an in-progress check from a stalled surface. (Operator Ingress MVP plan p3, ADR-015.)

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
- Activation overlay state changed — see below for `notice.activation_active` and `notice.activation_invalid`.

Notices map to the following event types in the canonical envelope: `notice.simplification-applied`, `notice.fallback-deferred`, `notice.quick_review_disabled`, `notice.documenter_tier2_interlock`, `notice.activation_active`, `notice.activation_invalid`. Pre-check events use `precheck.passed`, `precheck.failed`, `precheck.overridden`, and `precheck.unavailable`. All appear in `council.status` and are persisted as append-only events. The complete notice-to-event mapping:

| Notice Condition | Event Type |
|------------------|------------|
| Simplification applied to protocol parameters | `notice.simplification-applied` |
| Fallback deferred or advisory only | `notice.fallback-deferred` |
| Quick-review path disabled, full path forced | `notice.quick_review_disabled` |
| Documenter Tier 2+ interlocked | `notice.documenter_tier2_interlock` |
| `pre_check` override recorded | `precheck.overridden` |
| Activation overlay present, valid, and effective (state `active`) | `notice.activation_active` |
| Activation overlay present but invalid, fail-closed (state `invalid`) | `notice.activation_invalid` |

## Documenter Integration

<!-- STATUS: approval-lifecycle moved to `documenter-service/approval-surface.md` (Phase 2, sess-operator-surface-split); canonical contract mvp-contract.md §4. See AGENTS.md §1.7 -->

<span style="color:red;font-weight:bold">⚠ DORMANT (ADR-013) — MCP UNREGISTERED</span> The operator-side Tier 2+ approval and gate-override workflow is specified in `documenter-service/approval-surface.md`; the canonical approval contract and `documenter.*` event schemas are in `documenter-service/mvp-contract.md` §4. The Tier 2+ write branch is implemented and dormant behind the ADR-013 dual interlock.

## Event Delivery

Events are appended to `sessions/<session_id>/events.jsonl` in the canonical envelope. This is the **single storage location** for all event data corpus-wide. The rule for `session_id = null` (corpus-wide Documenter audits) is: when `session_id` is `null`, events are appended to `documenter/corpus-audit/events.jsonl`. No other location is valid. Both paths follow the same at-least-once delivery semantics; consumers deduplicate by `event_id`.

## Error Handling

Errors use the registry in `service-contract/index.md` and are localized by the Layer 2 lookup table. Responses contain a code, a localized message, and an operator action. Stack traces, raw provider payloads, and secrets are never returned to the operator.

## Deferred

Deferred items (A10, p2 roadmap; source: p3 impl-plan out-of-scope list): crash-recovery roll-forward (OD-3); full error taxonomy; Typer CLI and REST transport; parallel mode and distributed locking; automatic escalation expiry; mid-phase checkpoint/resume (ADR-004); shared-secret rotation and revocation (roadmap SUBJ-003); Agent and Service caller classes; real Layer 1 / Moderator adapters; `council.get_artifacts` (the sole remaining deferred surface tool, roadmap KD-1). Tier 2+ writes are not deferred but **gated**: the write branch is implemented and dormant behind the ADR-013 dual interlock, activatable by the operator out-of-session only.

## Cross-References

- `service-contract/index.md` — artifact, event, and error schemas
- `execution-runtime/index.md` — phase machine, persistence, escalation routing
- `documenter-service/index.md` — Documenter interfaces and trust tiers
- `documenter-service/approval-surface.md` — operator-side Tier 2+ approval and override workflow
- `documenter-service/mvp-contract.md` §4 — canonical Tier 2+ approval contract and `documenter.*` event schemas
- `planned-architecture/layer-2.md` — adapter responsibilities
- `fallback/index.md` — manual fallback workflow
