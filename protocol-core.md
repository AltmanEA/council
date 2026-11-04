# Protocol Core
Version: 0.3.1
Status: draft
Last Modified: 2026-11-04
Language: en
Source: project-concept.md
Abstraction: protocol
<!-- CHANGES v0.3.1: Replaced "framework" with "Council" as canonical project name where referring to the project itself. -->
<!-- CHANGES v0.3.0: Extracted from project-concept.md (was lines 73–162). Covers role model, interaction protocol phases, and escalation logic. -->

## Role Model

Roles are assigned based on task context. The initial set includes three key roles; new ones are added as Council evolves. Each role is defined by its perspective, areas of responsibility, and prompt template.

### 1. Architect

**Perspective:** the overall system structure. The architect reasons in terms of components, their relationships, and data flows. They assess how the proposed solution fits into the architecture as a whole and whether it breaks existing integrity.

**Areas of responsibility:**
- Module and service boundaries
- Integration points between components
- Information flow through the system
- Alignment of technology choices with project goals
- Structural scalability

**Typical questions:** "Will this coupling create excessive dependency?" "What will become a bottleneck in the future?"

### 2. Reliability & Security Specialist

**Perspective:** protecting the system from failures and vulnerabilities. This role examines the task through the lens of what can go wrong, how the system will behave under extreme conditions, and what security risks the proposed approach introduces.

**Areas of responsibility:**
- Failure modes of individual components
- Recovery strategies after outages
- Vulnerabilities and attack vectors
- Regulatory compliance
- Data confidentiality assurance

**Typical questions:** "What happens if this service stops responding?" "Where could this solution leak data?"

### 3. Human-Centric Designer

**Perspective:** the human's interaction with the system. This role ensures the design accounts for the user's real capabilities, their cognitive limits, and their trust in the machine.

**Areas of responsibility:**
- End-user workflows
- Cognitive load when operating the system
- Accessibility (accessibility for people with diverse abilities)
- Calibration of user trust in AI
- Understandability and transparency of system decisions

**Typical questions:** "Will the person understand why the AI made this decision?" "Is the system overloaded with too many steps?"

### Adding a New Role

A new role is introduced by documenting:
- Role name (nominative form)
- A brief description of the perspective (one sentence)
- A list of areas of responsibility
- A prompt template for initializing an agent in this role

Adding a new role is a separate process that requires agreement within the project.

---

## Interaction Protocol

The protocol defines the sequence of actions for the discussion participants. The base version uses a simple sequential process.

### Phase 1 — Task Submission

The user formulates the task, describing:
- Scope (a module, function, or system capability)
- Context — the existing system architecture, if already defined
- Known constraints and requirements
- Explicitly stated risks or open questions that require attention

After the task is submitted, a canonical subject list is established: the components, interfaces, and decision points the task concerns, each with a stable identifier. Roles reference these identifiers in their findings; a role may propose a new subject, which is admitted to the list before the review round proceeds.

### Phase 2 — Individual Review

Each assigned role independently examines the task and produces its review. The review contains the following elements:
- A one-sentence summary position on the task
- Findings, each tagged with:
  - a severity level (low, medium, high, critical)
  - a subject reference — a stable identifier from the task's subject list
  - a stance (support / oppose) — required when the finding concerns a proposed decision on that subject, null otherwise
  - a justification — mandatory for severity=critical. It must name a concrete failure mode or attack scenario and the affected subject identifier(s). A critical finding without a format-valid justification is downgraded to high severity for protocol purposes; the original rating and text are kept in the record and reported to the operator with the resolution document.
- Recommended actions
- Open questions requiring clarification

Upon completing the review, each role declares its status: agree (no material issues found), concerns (observations exist but do not block the decision), blocked-in-scope (a fundamental issue the agent group can potentially resolve itself), or blocked-escalation (a fundamental issue matching an escalation reason: information gap, irresolvable conflict, or risk threshold breach). Only findings of severity medium or above may block.

### Phase 3 — Discussion Round

Agents receive the reviews of all other roles and respond. At this stage, each participant may reaffirm their position, adjust their argumentation based on colleagues' findings, raise a counterargument, or propose a compromise solution.

Multiple discussion rounds are possible — one or two are usually sufficient. After the configured round limit is reached, the process moves to the next stage.

If any role declared blocked-in-scope, one additional targeted resolution round is held, focused solely on that blocker. If the block persists after this round, the role reclassifies it as blocked-escalation. Roles may change their status during any round; only the final status counts for the consensus check.

### Phase 4 — Consensus Check

After the discussion rounds, the moderator collects the final status from each role and applies the following rule:

The moderator is a deterministic component (code, not an LLM). It aggregates statuses and joins findings on subject identifiers; it performs no interpretation of free text and holds no decision power.

All agree — every participant has declared the "agree" status. The task is considered resolved and the output document is produced.

Partial concerns — some participants reported concerns, but no one blocked the task. Recommendations are collected, and the task is considered conditionally resolved with the reservations recorded in the document.

Blocked — at least one participant's final status is blocked-escalation. The escalation protocol is triggered.

Disagreement — two or more roles recorded opposite stances (support vs oppose) on the same subject identifier in their final-round findings. This is a deterministic code join, not a textual judgment. If the structured data is insufficient to determine whether roles agree on a subject (missing subject references, ambiguous stances), the moderator raises an information-gap escalation rather than inferring agreement or conflict.

### Phase 5 — Resolution Formation

When consensus is reached, a final document is produced containing the decision taken, the rationale for the chosen approaches, a list of open questions, and a list of action items raised during the discussion. This document is written in technical English.

---

## Escalation Protocol

Escalation is a mechanism that triggers when the agent group's internal means are exhausted. It allows the system to acknowledge its own limits and hand the problem over to the human operator.

### Escalation Reasons

The system routes a task to the operator for one of the following three reasons.

**Information gap.** The agents are ready to work on the task but lack the input data needed to make an informed decision. Agents must not make assumptions merely to complete the process — an exact statement of facts is required. A typical example: the security role requests information about how confidential data is stored, but the user did not describe it in the task. In such cases, the operator receives a specific request enumerating the missing information.

**Irresolvable conflict.** Two or more roles take fundamentally different positions on a question, and the discussion does not lead to agreement. For example, the architect proposes connecting two components directly for performance, while the security specialist strictly forbids it due to an unauthorized-access threat. Both sides are well-argued and neither is willing to yield. The operator receives a summary of both positions and is asked to make the final decision.

**Risk threshold breach.** An agent identifies a risk it assesses as critical. Such a risk requires an immediate halt of the current discussion branch, even if the other agents do not consider it that severe. Here, the priority of safety and reliability is not subject to a vote.

The veto's force depends on form, not on persuasion: the escalation activates only if the critical finding carries a justification that passes format validation by the moderator (non-empty failure mode or attack scenario, naming at least one subject from the task's subject list). The moderator never judges whether the risk is real, plausible, or exaggerated — that assessment remains exclusive to the raising role and is passed to the operator verbatim. A finding that fails format validation cannot halt the branch; it is recorded, surfaced to the operator, and processed as a high-severity finding in the normal protocol flow.

### Escalation Document

Every request to the operator is accompanied by a structured record. It includes the escalation type, the name of the role that raised the escalation, the severity level (medium, high, critical), a description of the blocker, the participants' positions (in case of a conflict), a specific request to the operator, and, where applicable, a fallback course of action for the case of no response within a defined time window.

### Escalation Resolution Paths

There are three possible escalation outcomes:

- **Operator intervention.** The human provides the missing information or decides between the conflicting parties. Once a response is received, work continues.
- **Deferred fallback.** If there is no response within the allotted time, a pre-defined strategy is applied at the project's discretion.
- **Partial continuation.** The parts of the task not blocked by the escalation are executed; the remaining information is carried over into the next processing cycle.
