# Consensus Document — Operator Surface MVP Implementation Plan

**Session:** p3-operator-surface-impl-plan
**Mode:** Fallback (fallback/index.md v0.6.0)
**Date:** 2026-11-15
**Roles:** Architect · Reliability & Security Specialist · Human-Centric Designer · Operations Engineer
**Consensus:** Conditionally Resolved (statuses: Arch concerns, R&S agree, HCD agree, Ops concerns; no `blocked-` statuses)
**Inputs:** roadmap.md (p2), plan-draft-v1, round-1 reviews, discussion round 1

---

## Decision

Adopt the revised 10-step implementation plan (`plan-draft-v2.md`) as the ordered build sequence for the Operator Surface MVP. Round 1 produced six binding refinements to the draft; one structural divergence (session-store backing) is referred to the operator.

## Resolutions (subjects with outcomes)

### Agreed (all roles converged)

1. **C3 closed — pre_check gap is phantom.** MVP verbs (`submit_task`, `status`, `list_sessions`, `audit`) perform no phase-boundary transitions; `pre_check` wraps transitions owned by the unbuilt Layer 1. Residual risk (`submit_task` accepts an un-audited brief) accepted as MVP scope; mitigated by `documenter.audit` availability. **Addition (R&S, accepted):** Step 4 ships a pre_check passthrough skeleton returning `pass`, wired for real in Step 6 — middleware is integrated into already-wired verbs, never retrofitted.
2. **D-c / C1 closed — intent log co-developed with Step 4** in the same TDD cycle (R&S constraint: same commit as the verb's write, not "around the same time"). No gap window; scan/roll-forward stays deferred (roadmap decision 7 boundary intact).
3. **D-b closed — pre_check timeout: 5s default**, `PRE_CHECK_TIMEOUT` env var read once at boot, immutable at runtime (wording contradiction resolved). Within roadmap range 2–30s. Mitigations: `precheck.running` event at gate start; verdict event at completion. Architect's 10s compromise noted and superseded by Ops' margin analysis (2.5x for manifest-scale audits; false-`unavailable` preferable to silent hang).
4. **`unavailable` semantics fixed (R&S rec 4):** middleware auto-proceeds with a `precheck.unavailable` warning event (timeout-and-continue per roadmap decision 3); override verbs are for verdict-fail only; Step 9 verbs formalize operator-acknowledged override. DoD assertion required.
5. **C7 closed — notices merged into Step 4.** First `council.status` response carries identity marker, session status, and the 5-type notice set (Info/Advisory/Blocking) — complete operator-observable vertical slice at the first operator-visible step.
6. **C2 closed — honest error text pattern fixed:** `code` + human `message` + `action` naming at least one currently-available tool; plan terms ("Phase 2") banned from operator text. All 6 deferred-tool envelopes drafted at Step 2 and tested against stubs.
7. **C6 closed — stub discipline is programmatic:** architecture test `tests/test_architecture.py` asserts (a) no Layer-1 module imports, (b) cross-layer calls only via `ports.py`, (c) no writes to `phase_state`/`mode`/`consensus` in verb handlers, (d) no direct attribute access on session objects. Stores annotated `# STUB: replaced by real Layer 1 at Phase 3`; test classes named `TestMvp*AsStub`.
8. **Smoke tests without registration:** stdio subprocess spawn of `python3 -m operator_surface` over JSON-RPC (exercises the real transport contract; no workspace MCP registration needed).
9. **Verb emission discipline (Ops residual):** Step 9 integration test stubs `EventSink.write()` and asserts every verb smoke test emits at least one `verb.*` or `precheck.*` event.

### Disagreement — operator decision required

**D-a: MVP session store backing.**
- **Architect + Ops: volatile in-memory.** Consistent with roadmap decision 4 (volatile escalation state); disk persistence risks the stub drifting into a de-facto data layer; crash = session loss is bounded and communicated via an Advisory notice.
- **R&S: disk-backed (JSONL/flat files) — firm.** Operator expects `status`/`list_sessions` to be stable across process restarts (common in dev); real Layer 1 is filesystem-based, so same-medium swap avoids migration risk; file-based CRUD without protocol logic is still a legitimate stub.
- **HCD (implicit, via notice design):** operator expectation management required either way; notice text adapts to the outcome.
- **Moderator's recommendation to the operator:** **disk-backed**, because the sessions/<id>/ filesystem convention already exists in the runtime contract, persistence ≠ protocol logic (the architecture test c(i)(c) still forbids drift), and it closes R&S's crash-loss and swap-migration concerns at negligible cost. Ops's mitigation (volatile + notice) is the fallback if the operator prefers strict roadmap-consistency. HCD notice text branches: disk-backed → `notice.layer1_stub_active: "temporary adapter; sessions are stored in a provisional format"`; volatile → "…sessions do not persist across restarts".

## Reservations (carried)

| Role | Reservation | Tied subject |
|------|-------------|--------------|
| Architect | `submit_task` accepts un-audited briefs at MVP (scope gap, not defect) | SUBJ-101 |
| Ops | 5s timeout unverified against manifest scale until Step 9 benchmark; env var is the relief valve | SUBJ-103 |

## Critical findings downgraded (transparency)

- Architect round-1 [critical] on pre_check ordering — downgraded to design note; premise misread (no MVP phase transitions). Moderator annotation, confirmed in round 2.
- Ops round-1 [high] on event/verb ordering — annotation: Step 3 already preceded Step 4 in v1; residual absorbed as emission-discipline test.

## Operator decisions (RESOLVED 2026-11-15 — operator confirmed moderator recommendations)

1. **OD-1 / D-a: ACCEPTED — disk-backed session store** (JSONL under `sessions/<id>/`, path convention and record schema pinned in Step 0 `Layer1Port`). HCD notice text branch fixed: `notice.layer1_stub_active: "temporary adapter; sessions are stored in a provisional format"`.
2. **OD-2: ACCEPTED — 5s default timeout**, `PRE_CHECK_TIMEOUT` read once at boot, immutable at runtime. Finalizes roadmap open question SUBJ-004.
3. **OD-3: ACCEPTED — crash-recovery boundary** (intent metadata only, no roll-forward). Note: this accepts the *plan's* boundary; explicit acceptance for **Tier 2+ activation** remains a separate act at activation time (roadmap condition preserved).

## Implementation handoff

Execution of each step goes through the `implementation` skill (TDD cycle). Docs artifacts produced en route (threat model note, ADR for D-a, deferred-items doc) go through the Documentation Worker skill. MCP registration remains an operator-only act (AGENTS.md §1.7).

## References

`task-brief.md`, `plan-draft-v1.md`, `plan-draft-v2.md`, `review-*-r1.md` (4), `discussion-round-1-*.md` (4 + moderator notes)
