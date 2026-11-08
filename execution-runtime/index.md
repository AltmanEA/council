# Execution Runtime & Session Lifecycle

Version: 0.1.0
Status: draft
Last Modified: 2026-11-08
Abstraction: protocol
changelog-path: CHANGELOGS/execution-runtime.changes.md

---

## Scope

Defines Layer 1 as the Execution Runtime: module boundaries, the deterministic control plane, the phase state machine, artifact assembly, session persistence, escalation routing, and the namespace rule between fallback and code Moderator. Artifact fields are defined in `service-contract/index.md`; operator delivery is defined in `operator-surface/index.md`.

## Layer 1 Boundaries

Layer 1 is the Execution Runtime. It contains a deterministic Moderator and non-deterministic execution units (Role Agents and Auxiliary Agents). Layer 2 is External Interfaces / Adapters; it calls Layer 1 and never calls Layer 0. The Layer 0 rule is unchanged: only Layer 1 calls Layer 0.

| Module | Responsibility | May import |
|--------|----------------|------------|
| `orchestrator/` | Phase state machine, Moderator, consensus and escalation routing | `agents/`, `scenario/`, `persistence/`, Layer 0 |
| `agents/` | Role Agents, Auxiliary Agents, `RoleAgentFactory`, `get_model()` | `scenario/`, Layer 0 parser types |
| `scenario/` | `ScenarioLoader`, scenario validation | Layer 0 catalog types |
| `persistence/` | Manifest, phase files, atomic writes, locks | — |

Import rules: `orchestrator/` may import the other modules; `agents/` MUST NOT import `orchestrator/`; only `agents/` may call `get_model()`; `orchestrator/` MUST NOT import it directly; Layer 1 MUST NOT import Layer 2.

## Deterministic Control Plane

Moderator control flow and every phase, consensus, and escalation decision are deterministic functions of validated role outputs. No LLM participates in control flow or safety verification. The Moderator may read free text only for display; it never interprets it to make a decision.

## Phase State Machine

States: `1` task submission, `2` individual review, `3` discussion, `4` consensus check, `5` resolution, plus `awaiting-operator`, `resolved`, `failed`.

| From | To | Guard |
|------|----|-------|
| 1 | 2 | Task validated; scenario loaded; all Core roles active |
| 2 | 3 | Every active role has `RoleStatus` with `extraction = parsed` |
| 2 | awaiting-operator | Any `invalid-format` status or missing Core role |
| 3 | 4 | Round limit reached, or no new `blocked-in-scope` |
| 3 | 3 | At least one `blocked-in-scope` and targeted-round budget remains |
| 4 | 5 | Outcome `consensus` or `conditional` |
| 4 | 3 | Outcome `no-consensus` and discussion budget remains |
| 4 | awaiting-operator | Outcome `blocked-escalation`, or `no-consensus` after budget |
| 5 | resolved | Final artifact persisted; manifest updated last |
| awaiting-operator | `resume_phase` | Operator resolution bound to `escalation_id` |
| any | failed | Unrecoverable IO or protocol violation |

Only `orchestrator/` advances a phase. The operator never edits phase state directly; resolution arrives through the operator surface. The `SUBJ-007` quick-review upgrade hook is reserved but not implemented at MVP.

## Role Status Handling

`extract_role_status()` is the only source of truth for consensus. An `invalid-format` extraction is a blocking protocol error: the session enters `blocked-escalation` with `information-gap`, the raw review is preserved, and the role is never counted as `agree`. A missing Core role is `blocked-escalation` with `risk-threshold-breach`. Core-role presence is checked on every path, not only before simplification.

## Artifact Assembly Order

1. Phase 2: persist one `RoleReview` per active role.
2. Phase 3: persist one `RoleReview` per active role per round.
3. Phase 4: persist `ConsensusVerdict`.
4. Phase 5: persist the consensus document or `EscalationRecord`.
5. Update `manifest.json` last.
6. Emit events only after the durable write succeeds.

A failed step aborts the remaining steps. The session remains at the last complete phase boundary.

## Escalation Routing

Escalation is stop-and-resume. The runtime writes an `EscalationRecord`, sets `phase_state = awaiting-operator`, emits `escalation.opened`, and returns control to the operator. No blocking stdin, no background waiter, and no automatic timeout enforcement at MVP: `timeout_at` is informational, and the operator surface owns the clock on the next invocation.

Resume requires an authenticated resolution bound to `escalation_id` and `operator_id`. On resume, the runtime applies the decision, sets `current_phase = resume_phase`, records the resolution in the escalation record and event log, and continues. A rejected or superseded escalation follows its `fallback_strategy`.

## Session Directory Contract

```
sessions/<session_id>/
  manifest.json      # SessionManifest (service-contract)
  task.md            # operator-authored task brief
  phase-1.json       # one file per phase, overwritten atomically
  phase-2.json
  phase-3.json
  phase-4.json
  phase-5.json
  events.jsonl       # append-only event log
  .lock              # single-writer lock
```

Each phase file is `{schema_version, phase_id, status: complete|partial, artifacts: string[], updated_at}`. Phase files hold session-local review text; `manifest.json` and `events.jsonl` hold only redacted summaries, hashes, and identifiers. Runtime state is local-only and MUST NOT be committed to git; only configuration and schemas are versioned.

## Session Manifest

`manifest.json` follows `SessionManifest` in `service-contract/index.md`. Additional lifecycle rules:

- `manifest_hash` is `sha256` of canonical JSON (sorted keys, no whitespace) with `manifest_hash` omitted.
- `previous_manifest_hash` links each write to the prior manifest; the first write uses `null`.
- `role_agent_config` records the exact parameters used per role, satisfying ADR-002 provenance.
- `pending_operator_action` is the operator-facing projection of an open escalation.

## Persistence Mechanics

- Writes use temp file → `fsync` → atomic `rename`.
- A single-writer advisory lock (`flock` exclusive) on `.lock` covers the whole session; acquisition timeout is 30 seconds.
- Manifest writes are serialized and hash-chained. A broken chain is `IO.002`.
- Readers may inspect a session without the lock; they MUST tolerate a missing last phase file and fall back to the previous complete boundary.

## Crash Semantics

MVP provides resume at phase boundaries, not mid-phase checkpoint (ADR-004 deferred).

1. On startup, validate the manifest hash chain.
2. Find the highest contiguous phase file with `status: complete`.
3. Discard leftover `.tmp` files.
4. Resume at that phase boundary; re-run the incomplete phase.
5. If the manifest is invalid, mark the session `failed`; the operator must start a new session.

Re-running a phase invokes the LLM again and may produce different findings. The event log records the new attempt; the prior complete artifacts remain the evidence of record until the re-run commits.

## Namespace Rule

`mode: fallback | moderator` is mandatory in the manifest.

- A code Moderator MUST NOT resume a `fallback` session.
- Fallback tooling MUST NOT resume a `moderator` session.
- Both modes share the session directory layout, the artifact schemas, and the consensus document format.
- There is no converter between modes; a session stays in the mode in which it started.
- The operator may read both modes through the same status projection.

## Supporting Service Rule (D3)

Documenter, fallback mode, and JSON persistence are Supporting services outside the layer chain. Documenter is invoked by the Layer 2 operator surface and uses a Layer 1 execution port for LLM-backed writes (Documentation Worker). Supporting services never call Layer 2 or Layer 0 directly. Layer 2 contains no direct LLM invocation.

## Operator Status Projection

The runtime exposes a read-only projection answering three questions:

| Question | Fields |
|----------|--------|
| Where am I? | `session_id`, `mode`, `current_phase`, `phase_state` |
| What needs me? | `pending_operator_action`, open `escalation_id`, `resume_phase` |
| What changed since last look? | `last_event_id`, `changed_since_last_view`, `artifacts` |

A hash chain proves integrity, not comprehensibility. This projection is mandatory and is rendered by the operator surface.

## Migration Path

If orchestration outgrows Layer 1, extract an Orchestration Core behind Layer 1's public interface (variant B). The layer boundaries, the Layer 0 rule, and the session contract remain unchanged.

## Cross-References

- `service-contract/index.md` — artifact and event schemas
- `operator-surface/index.md` — transport, identity, escalation delivery
- `planned-architecture/layer-1.md` — architecture summary
- `planned-architecture/layer-0.md` — deterministic protocol functions
- `fallback/index.md` — manual fallback procedure
