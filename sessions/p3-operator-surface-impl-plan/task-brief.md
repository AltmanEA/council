# Session Task Brief: Operator Surface MVP — Step-by-Step Implementation Plan

**Session:** p3-operator-surface-impl-plan
**Mode:** Fallback (protocol per `fallback/index.md` v0.6.0)
**Upstream artifact:** `roadmap.md` (session p2-operator-surface-roadmap, Conditionally Resolved 2026-11-15)

## Session Goal

Turn the Phase 1 roadmap decisions into a concrete, ordered, step-by-step implementation plan for the Operator Surface MVP, and resolve the roadmap's open questions that block implementation ordering (SUBJ-004 timeout value, SUBJ-007 tool delivery sequence, Layer 1 dependency strategy).

## Focus Areas

- Step ordering and dependencies: what can be built and tested with Layer 1 absent (Layer 1 is specification-only; only Documenter Tier 0–1 code exists)
- Vertical-slice vs horizontal-layer build order (which produces testable increments earliest)
- Test strategy per step (tests/ suite already covers documenter_service; surface needs equivalent)
- Resolution of open questions that affect ordering: SUBJ-004 (pre_check timeout constant), SUBJ-007 (tool delivery sequence), Layer 1 stub/adapter boundary
- Risk of the plan drifting into building Layer 1 disguised as Layer 2 work (scope guard)
- Where the plan hands off to the `implementation` skill (TDD subagent cycle) vs planning artifacts

## Questionnaire per Role

**Architect:**
- Q1: Is the proposed step order structurally sound? Which steps are truly independent and which hide coupling (e.g. `status` verb depends on session state, but session state is a Layer 1 concept)?
- Q2: What is the correct seam between Layer 2 and the not-yet-built Layer 1 — ports/stubs, filesystem session contract, or a minimal in-process session store? Where does the Layer 2 plan end and Layer 1 begin?
- Q3: Does the plan preserve the roadmap's decisions (HMAC-SHA256, middleware pre_check, request_id handshake) without silent re-design?

**Reliability & Security Specialist:**
- Q1: Which steps must not be skipped or reordered without a security regression (auth before any write-capable verb, error envelope before external exposure)?
- Q2: What is the attack surface at each increment while the surface is partially built (e.g. transport with no auth, verbs with no audit trail)?
- Q3: Is the crash-recovery reservation boundary respected by the plan's step 10 (intent-log metadata only, no roll-forward)?

**Human-Centric Designer:**
- Q1: Does the step order deliver an operator-usable increment early enough (identity marker, notices, status projection), or is the operator absent from the plan until the end?
- Q2: SUBJ-007 — sequential unlock vs all-visible with guidance: which produces a less confusing operator experience during rollout?
- Q3: Is the plan's definition-of-done per step verifiable by the operator (observable behavior, not internal code)?

**Operations Engineer:**
- Q1: What is the practical build/test/deploy loop for each step (pytest, MCP stdio smoke test, registration still operator-gated)?
- Q2: SUBJ-004 — fixed pre_check timeout constant at MVP: 2s, 30s, or configurable-at-boot with a fixed default? Justify with operational reasoning given Documenter runs in-process (not network).
- Q3: What observability (JSONL events, warning events, notices) must be wired per step so that partial deployments are debuggable?

## Output Limits

- Maximum findings per role: 5–7
- Maximum recommendations per role: 3–5
- Maximum open questions per role: 2–3
- Total output: ~150 lines — brevity encouraged

## Expected Discussion Rounds

- 1 round (medium task)

## Subject List

- [SUBJ-101]: Step ordering and build sequence of the implementation plan
- [SUBJ-102]: Layer 1 dependency seam — how Layer 2 verbs work before the Moderator exists (stub/port/filesystem contract)
- [SUBJ-103]: Pre_check timeout constant at MVP (roadmap SUBJ-004: 2s vs 30s vs fixed-default-configurable)
- [SUBJ-104]: Tool delivery sequence during rollout (roadmap SUBJ-007: sequential unlock vs all-visible with guidance)
- [SUBJ-105]: Test and verification strategy per step (pytest, MCP smoke, definition of done)
- [SUBJ-106]: Scope guard — plan must not silently build Layer 1 / must respect ADR-013 dual interlock and AGENTS.md write rules (docs changes go through Documentation Worker; MCP registration is operator-only)
- [SUBJ-107]: Crash-recovery reservation boundary — intent-log metadata placement in the plan without automatic roll-forward

## Additional Context / Constraints

- Current code state: `documenter_service/` Tier 0–1 is operational (CLI + MCP stdio implemented, tested). No operator-surface code exists. No Layer 1 code exists.
- The documenter MCP server is deliberately NOT registered in `.opencode/opencode.jsonc`; registration is an explicit operator decision. The plan may prepare for registration but must not assume it.
- All docs/ changes in the plan must route through the Documentation Worker skill; implementation files (package code, tests/) are outside Documenter scope.
- Actual code implementation will be executed via the `implementation` skill (TDD subagent cycle); this session produces the plan only.
- Roadmap decisions are binding inputs (see roadmap.md Key Decisions 1–8); this session may refine ordering and constants, not reverse decisions.
