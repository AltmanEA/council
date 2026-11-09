# Council Reference (Draft)
Version: 0.3.1
Status: draft
Last Modified: 2026-11-09
Abstraction: reference
changelog-path: CHANGELOGS/project-reference.changes.md

---

## Technical Implementation

**Principle:** whatever is not hard to implement in code is done in code; everything else is delegated to AI.
Code provides protocol predictability; AI provides the content of decisions.

**Stack:** Python + LangChain. LangChain provides abstractions over LLM calls, chains, agents, and memory — what is needed to orchestrate a multi-agent system.

**Architectural decisions:**

• **Orchestration** — LangGraph (LangChain's state graph). Phase by phase, transitions are driven by role statuses. A ready foundation for future parallel execution (Development Phase 2).

• **State** — JSON files in the session directory (`sessions/<id>/`). Each phase is a separate file. No extra complexity: tasks are short-lived and data does not flow between discussions.

• **LLM abstraction** — a single `get_model()` function. One provider at the start (MVP), replacement is trivial when scaling.

Protocol phases → components: Moderator (the StateGraph orchestrator), Role Agents (one instance per role with a prompt and context), Human Operator API (the escalation input entry point).

---

## Project Artifacts

The protocol revolves around three artifacts. Each has a fixed set of elements, and all protocol transitions are computed from these elements in code; the exact serialization format (file layout, field naming, schema syntax) is an implementation concern and is not specified here.

**Role review** — produced by each role in each round. Must contain: a one-sentence summary position; a list of findings, where every finding carries a severity (low / medium / high / critical), a reference to a subject from the task's subject list, an optional stance (support / oppose) when it addresses a proposed decision on that subject, and — for critical severity only — a justification naming a concrete failure mode or attack scenario; plus recommended actions, open questions, and the role's status from the fixed set (agree / concerns / blocked-in-scope / blocked-escalation), the latter paired with an escalation reason when applicable.

Three rules bind the review's elements together and are enforced mechanically: a blocking status requires at least one finding of medium severity or above; a blocked-escalation status requires a stated escalation reason; a critical finding without a format-valid justification is processed as high severity, with its original rating retained and reported to the operator.

**Consensus document** — the primary output, produced when a task resolves. Must contain: the decision taken and its rationale; the task's subjects with their outcome (agreed or conditionally agreed); the reservations of roles that raised concerns, each tied to a subject; open questions; action items raised during the discussion; references to any escalations that were resolved en route; and, for transparency, the list of critical assessments that were downgraded for lacking a valid justification, as raised by their original raters.

**Escalation record** — produced each time the system hands a problem to the operator. Must contain: the escalation type (information gap / irresolvable conflict / risk threshold breach), the raising role, severity, a description of the blocker, the conflicting parties' positions when the escalation is a conflict, the concrete request to the operator, an optional fallback strategy with its response timeout, the resolution outcome (operator decision / deferred fallback / partial continuation), and the phase from which work resumes once resolved.

Every element listed above exists because a protocol rule reads it. An element no rule depends on does not belong in the artifact; a rule that cannot be expressed through the elements means the artifact definition is incomplete.

---

## Roadmap

Council starts minimal and evolves organically.

Phase 1 — three initial roles, a sequential protocol, three escalation types.

Phase 2 — expanding the role set (for example, adding a domain expert), introducing a parallel task-review mode.

Phase 3 — implementing a weighted-voting mechanism for resolving disagreements, developing an automated tool for composing recommendations from different roles.

Phase N — full support for nested sessions, cross-session dependencies, and automated audit logs.

---

## Out of Scope (Technical Details)

- Software code generation or code analysis
- Code execution or runtime monitoring
- General-purpose chat or conversational AI
- Project management beyond the boundary of a single task

These capabilities may be built on top of Council, but they are not part of its core design.
