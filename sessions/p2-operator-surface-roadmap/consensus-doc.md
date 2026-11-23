# Consensus Document: Operator Surface MVP Roadmap

**Session:** p2-operator-surface-roadmap
**Date:** 2026-11-15
**Roles:** Architect, Reliability & Security Specialist, Human-Centric Designer, Operations Engineer
**Consensus Status:** Conditionally Resolved (all `concerns`, no `blocked-` statuses)

---

## Decision

Define a phased MVP scope for the Operator Surface with 4 priority tiers: Core tools + pre_check gate + escalation handling ship first; documenter.delegate/approve/override_gate ship in a Phase 2 delivery batch. All decisions are subject to operator review before Tier 2+ activation.

## Rationale

- **All 4 roles converge** on reducing the initial MVP tool surface from 10 to 4 core tools to minimize cognitive load, testing surface, and error taxonomy scope (Architect, HCD, Ops agree; R&S does not object).
- **All 4 roles converge** on changing pre_check from synchronous-block-on-unavailability to timeout-and-continue with visible warning (critical finding from Ops accepted by all others).
- **3 of 4 roles converge** on HMAC-SHA256 for MVP auth (Architect critical; R&S accepts with conditions; HCD and Ops do not disagree).
- **Consensus on escalation state** as in-memory volatile at MVP, with `timeout_at` advisory and no automatic expiry; `expired` state deferred (Architect, Ops agree; R&S accepts with crash-recovery caveat).
- **Consensus on `request_id` handshake** between `documenter.delegate` and `documenter.approve` (Architect, R&S agree; HCD and Ops accept).

## Subjects with Outcomes

| Subject | Status | Notes |
|---------|--------|-------|
| SUBJ-001 (MVP component set) | Agreed | 4 core tools at MVP, rest deferred |
| SUBJ-002 (Dependency sequencing) | Agreed | Auth → pre_check → verbs → escalation → documenter |
| SUBJ-003 (AuthN/AuthZ) | Conditionally Agreed | HMAC-SHA256 accepted with conditions; threat model documented; migration path reserved |
| SUBJ-004 (pre_check integration) | Agreed | Timeout-and-continue (2–30s), middleware placement, visible warning event |
| SUBJ-005 (Escalation at MVP) | Conditionally Agreed | In-memory volatile, advisory `timeout_at`, `expired` deferred, per-tool fallback semantics |
| SUBJ-006 (documenter.approve path) | Agreed | request_id handshake, actor-differentiation enforced silently, audit trail captures both IDs |
| SUBJ-007 (Operator UX) | Agreed | 4 tools, 4 items escalation presentation, identity confirmation on every response, notice hierarchy Info/Advisory/Blocking |
| SUBJ-008 (Deferred items) | Agreed | Crash recovery deferred-but-bounded (intent log); Typer/REST deferred; error taxonomy deferred to 3 classes; full taxonomy post-MVP |

## Conflicts & Disagreements

- **SUBJ-003 (Auth algorithm):** Architect proposed HMAC-SHA256 (critical); R&S insisted on RS256/ES256 (high). Resolved by compromise: HMAC-SHA256 for MVP local-stdio context with explicit threat model boundary, mandatory weak-algorithm rejection, and documented migration path to asymmetric algorithms. Not a protocol conflict — a scoping disagreement resolved by threat model constraints.

## Reservations

**Reliability & Security Specialist:**
- SUBJ-003: Shared secret must not rely on env-vars alone — mandate at least one protected storage path (process-locked file, keyring point) even at MVP.
- SUBJ-004: pre_check warning markers must be persisted (not in-memory) and surfaced on read-before-write.
- SUBJ-005: Crash recovery must include an on-disk intent log for atomic-write protocol — deferred but bounded.
- SUBJ-006: Audit trail must capture session ID on every approve call for forensic correlation.
- Escalation: "Concerns" status maintained; `risk-threshold-breach` reason for crash-recovery gap.

**Human-Centric Designer:**
- SUBJ-007: Document expected Documenter availability to evaluate whether timeout-and-continue becomes noise.
- SUBJ-007: Document how sequential tool onboarding balances guided vs. upfront visibility.
- Escalation: "Concerns" status maintained; `information-gap` reason for availability/onboarding questions.

**Operations Engineer:**
- SUBJ-004: pre_check must be in middleware, not embedded in `submit_task`, to cover all verbs.
- SUBJ-005: Per-tool fallback semantics must be configurable at boot.
- Escalation: "Concerns" status maintained; `information-gap` reason for retry frequency / middleware scope questions.

**Architect:**
- None (status: `agree`).

## Open Questions

1. **SUBJ-003:** Shared secret lifecycle (rotation, revocation, distribution) — not defined at MVP, deferred to Phase 2.
2. **SUBJ-004:** Pre_check timeout value — Architect proposed 2s, Ops proposed 30s. Must be fixed constant at MVP.
3. **SUBJ-005:** Expected Documenter availability profile — affects whether timeout-and-continue becomes noise.
4. **SUBJ-007:** Tool delivery sequence: sequential unlock vs. all-visible with guidance?
5. **SUBJ-008:** Error taxonomy: which 3 classes to include at MVP (CONFIG., IO., VAL. all roles agree)?

## Action Items

| # | Action | Priority | Roles Involved |
|---|--------|----------|----------------|
| A1 | Draft MVP scope document with 4 core tools: `submit_task`, `status`, `list_sessions`, `audit` | P0 | All |
| A2 | Specify authN: HMAC-SHA256 with threat model, weak-algo rejection, protected secret storage | P0 | Architect, R&S |
| A3 | Define pre_check: middleware placement, timeout value, warning event format | P0 | Ops, Architect |
| A4 | Define EscalationRecord schema for MVP: 4 fields (conflicting_positions, concrete_request, fallback_consequences, evidence_links), volatile state, advisory timeout | P0 | Architect, HCD, Ops, R&S |
| A5 | Define delegate→approve request_id handshake | P0 | Architect, R&S |
| A6 | Define per-tool fallback semantics configuration | P1 | Ops, Architect |
| A7 | Draft on-disk intent log spec for crash-recovery boundary | P1 | R&S, Ops |
| A8 | Document operator-visible identity confirmation pattern | P1 | HCD |
| A9 | Classify 5 notice types into Info/Advisory/Blocking hierarchy | P1 | HCD |
| A10 | Document deferred items list (crash recovery, Typer/REST, error taxonomy, automatic expiry) | P2 | All |

## Escalation References

- R&S: `risk-threshold-breach` — crash recovery gap requires explicit operator acceptance before Tier 2+ activation.
- HCD: `information-gap` — Documenter availability profile unknown; tool delivery sequence model TBD.
- Ops: `information-gap` — Documenter availability frequency; middleware scope for pre_check.
- Architect: `agree` — no escalation.

## Downgraded Critical Findings

- None. All critical findings from R1 were addressed and resolved (none downgraded for invalid justification).

---

## Consilium Recommendations — MVP Roadmap (Phase Sequence)

**Phase 1 (Core, must-have):**
1. Transport layer: MCP stdio adapter (existing spec)
2. AuthN: HMAC-SHA256 with shared secret, env delivery, protected storage, weak-algo rejection
3. 4 core verbs: `submit_task`, `status`, `list_sessions`, `documenter.audit`
4. pre_check gate (middleware, timeout-and-continue, visible warning)
5. Error envelope + CONFIG./IO./VAL. localization table
6. Event delivery (JSONL, canonical envelope)
7. Operator identity confirmation on every response
8. Notice hierarchy (Info / Advisory / Blocking)

**Phase 2 (Documenter write path):**
9. `documenter.delegate` — Tier 0–1 preview with request_id
10. `documenter.approve` — out-of-band approval with request_id, actor differentiation
11. `documenter.override_gate` — audit gate override with reason
12. Escalation verbs: `resolve_escalation`, `override_precheck`
13. Full EscalationRecord schema with all 6 fields (MVP deferred fields now included)
14. Per-tool fallback semantics

**Phase 3 (Deferred):**
15. Crash recovery via on-disk intent log + cold-start recovery scan
16. Full error taxonomy (VAL., PROT., MODEL., IO., CONFIG., AUTH.)
17. Typer CLI, REST transport
18. Automatic escalation expiry
19. Shared secret lifecycle (rotation, revocation)
20. Agent and Service caller classes (MVP: Operator-only)
