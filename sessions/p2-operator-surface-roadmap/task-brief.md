# Session Task Brief: Operator Surface MVP Roadmap

## Session Goal

Define a concrete MVP scope for the Operator Surface (Layer 2) implementation that unblocks Tier 2+ activation. Produce a phased roadmap with specific deliverables, identifying what's minimum-viable vs. deferred.

## Focus Areas

- What is the minimum set of Operator Surface functionality required to make Tier 2+ writes operational (not just specified)?
- Which existing specifications can be reused vs. need new code?
- What are the dependencies between surface components (auth → verbs → pre_check → escalation → documenter integration)?
- What is the implementation order and phase boundaries?

## Questionnaire per Role

**Architect:**
- Q1: What is the minimal component set that constitutes a "working" Operator Surface? Which components must ship at MVP vs. can be deferred?
- Q2: How does the MVP roadmap sequence dependencies — auth → verbs → pre_check → escalation → documenter.approve — to get from zero to a Tier 2+-capable surface?
- Q3: What are the critical integration points with Layer 1 (Moderator/Execution Runtime) and Supporting services (Documenter)?

**Reliability & Security Specialist:**
- Q1: What security properties must be present at MVP (authN/AuthZ, token handling) to prevent the Operator Surface from becoming an attack vector?
- Q2: What failure modes exist in the MVP scope (Documenter unavailability, token expiry, escalation timeout) and how should each be handled?
- Q3: What operational risks does rushing MVP introduce (partial auth, missing audit trail, unsafe defaults)?

**Human-Centric Designer:**
- Q1: What does the operator actually need to see and do at MVP to trust and use the system? What's the simplest viable operator workflow?
- Q2: How should escalation presentation be designed at MVP — what information must the operator see in one view?
- Q3: What cognitive load is acceptable for the MVP approval flow (operator review → approve/reject)?

**Operations Engineer:**
- Q1: What deployment considerations apply at MVP (MCP stdio only? local only? single-tenant?)?
- Q2: What observability and logging are essential at MVP (event delivery, audit trail, error localization)?
- Q3: What is the operational cost of maintaining the MVP vs. the value it delivers?

## Output Limits

- Maximum findings per role: 5–7
- Maximum recommendations per role: 3–5
- Maximum open questions per role: 2–3
- Total output: ~150 lines — brevity encouraged

## Expected Discussion Rounds

- 1 round

## Subject List

- [SUBJ-001]: Minimal MVP component set (what ships at MVP)
- [SUBJ-002]: Dependency sequencing (implementation order)
- [SUBJ-003]: Authentication/authN/AuthZ MVP scope
- [SUBJ-004]: pre_check gate integration (Layer 2 → Documenter)
- [SUBJ-005]: Escalation storage and presentation at MVP
- [SUBJ-006]: Documenter Tier 2+ out-of-band approval path
- [SUBJ-007]: Operator UX — minimal viable workflow
- [SUBJ-008]: Deferred items (what explicitly stays out of MVP)

## Additional Context / Constraints

- Current state: operator-surface/index.md is fully specified but NOT implemented — no code exists.
- Documenter Tier 2+ is dormant behind dual interlock: (a) policy file authorizing Tier 2, AND (b) Operator Surface existing as CODE (spec alone is not sufficient per ADR-013).
- MVP must ship one transport: MCP stdio. CLI (Typer) and REST are deferred.
- The roadmap should target making Tier 2+ invocation possible, not full feature parity.
- Session scope: this is a planning/roadmap session, NOT an implementation session.
