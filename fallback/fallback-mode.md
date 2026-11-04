# Subagent Fallback Mode
Version: 0.2.0
Status: draft
Last Modified: 2026-11-04
Abstraction: reference
changelog-path: CHANGELOGS/fallback-mode.changes.md

---

## Overview

This document defines how to run the Council interaction protocol using named subagents when the Moderator (code-based orchestrator) is not yet implemented. It is a manual approximation of the same protocol defined in `../protocol-core/index.md`; all artifacts and role status semantics remain identical. Use this mode until a dedicated tool layer replaces it.

### Fixed Roles

The following three roles constitute the initial set:

| Role | Perspective | Responsibility |
|------|-------------|----------------|
| **Architect** | System structure, component boundaries, data flows | Architecture, coupling, scalability, integration points |
| **Reliability & Security Specialist** | Failure modes, vulnerabilities, recovery strategies | Resilience, attack vectors, compliance, data confidentiality |
| **Human-Centric Designer** | User experience, cognitive load, trust calibration | Accessibility, understandability, real-user capabilities |

Additional roles are added per §7.5 (version bump minor) and documented in `../protocol-core/index.md` (§1.x).

### Output Structure

Each subagent produces a single structured document containing:

```markdown
# <Role Name> Review

## Summary Position
(One sentence: overall stance on the task.)

## Key Findings
- [severity] Finding text referencing subject `<subject-id>` where applicable.
- ...

## Recommendations
- Actionable suggestion derived from findings.
- ...

## Open Questions
- Clarification needed on topic X.
- ...

## Status
agree / concerns / blocked-in-scope / blocked-escalation

## Escalation Reason
(if status == blocked-escalation) information-gap / irresolvable-conflict / risk-threshold-breach
```

Critical findings must include a justification naming a concrete failure mode or attack scenario plus affected subject identifier(s). Missing or invalid justification causes automatic downgrade to high severity for protocol purposes.

---

## Operational Flow

### Phase 1 — Task Submission

The operator (human) provides:

1. **Task description:** scope, context, constraints, explicit risks, open questions.
2. **Subject list:** identifiers for components, interfaces, and decision points the task concerns (e.g., `SUBJ-001: notification transport selection`).

Roles reference these identifiers exclusively in their findings. A role may propose adding a subject; the operator admits it before the review round begins.

### Phase 2 — Individual Review

Launch three subagents, one per role, in parallel. Each receives:

- Its role identity (prompt identifying perspective and responsibilities).
- The full task description.
- The canonical subject list.
- Required output structure (from the previous section).

All three subagents work independently. No communication between them during this phase. Collect and store each result.

### Phase 3 — Discussion Round

Present every role's individual review back to each role as input. Instruct each subagent to examine the others' findings and respond: reaffirm, adjust arguments, counter, or propose compromise. Launch the three subagents again, in parallel. Collect results.

For simple tasks: zero or one discussion round is sufficient. For complex tasks: allow up to two rounds. The operator decides when to advance based on whether new positions are being introduced or prior ones simply repeated.

If any role declared `blocked-in-scope` in the previous round: hold one additional targeted resolution round. Only the blocking role and optionally one ally participate. If the block persists after the round, the role reclassifies it as `blocked-escalation`.

### Phase 4 — Consensus Check

The operator (acting as fallback Moderator) collects final statuses from all roles:

- **All agree → Resolved.** Proceed to Phase 5.
- **Some concerns, no blocks → Conditionally resolved.** Record reservations, proceed to Phase 5.
- **Any `blocked-escalation` → Escalation.** Trigger the Escalation Protocol.
- **Opposing stances on the same subject → Disagreement.** If structured data alone cannot determine agreement, escalate as information gap.

Disagreement detection: compare stances (`support` vs `oppose`) on identical subject identifiers across final-round findings. This is a structural comparison over machine-readable fields, not a textual judgment.

### Phase 5 — Resolution Formation

Produce a Consensus Document containing:

- Decision taken and rationale.
- Subjects with outcomes (agreed / conditionally agreed).
- Role reservations tied to subjects.
- Open questions.
- Action items.
- References to escalations (if any resolved en route).
- List of critical findings downgraded for invalid justification (transparency).

---

## Conflict Aggregation Rules

When the operator evaluates multiple role reviews, apply the following merge logic:

1. **Duplicate findings.** If two or more roles raise identical observations on the same subject, record the highest severity among them. Note which other roles converged on the same finding.
2. **Conflicting recommendations.** When two roles recommend opposite actions on the same subject with equal severity, flag as disagreement and require operator decision.
3. **Non-conflicting overlap.** Different roles citing different aspects of the same problem: record all as independent findings, no conflict.
4. **Severity escalation via convergence.** If one role raises medium and another independently raises medium on the same aspect, the combined weight may justify promoting to high. This is a heuristic, not a protocol rule.

---

## Operator Tooling

The following auxiliary documents live in the same directory and are referenced from the relevant phases. They are **not** part of the main documentation scheme — only cross-referenced here.

### Task Brief (`session-task-brief-template.md`)

Fill out before launching subagents. Defines session goal, focus areas, questionnaires, output limits, and constraints. Pass as context to all three subagents in Phase 2.

See also: `../protocol-core/index.md` §1.x (task submission requirements).

### Consolidation Prompt (`session-consolidation-prompt.md`)

Step-by-step instructions for the operator acting as Moderator during the Phase 4 → Phase 5 transition. Covers matrix normalization, deduplication, conflict identification, consensus determination, and Consensus Document drafting under 300 lines.

See also: `../protocol-core/index.md` §4–5 (consensus check and resolution formation).

### Session workspace convention

All per-session artifacts created by or for the operator go into `sessions/<session-id>/`:

- `task-brief.md` — filled-out task brief
- `review-<role>.md` — each role's final review output
- `consensus-doc.md` — the produced Consensus Document
- Optional: `discussion-round-N.md` — transcript of round N

The workspace directory is isolated from the root project directory. When a session produces approved changes to core documents (`../protocol-core/index.md`, etc.), those changes are applied manually after operator review, never automatically.

---

## Compliance Notes

This fallback mode implements the same five-phase interaction protocol as `../protocol-core/index.md` with operator-in-the-loop substitution for the code-based Moderator. All terminology inherits from `../glossary/index.md`. Role prompts are derived from the role definitions in `../protocol-core/index.md` (§1).

*Aligned with project documents v0.3.1.*
