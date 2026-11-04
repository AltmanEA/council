# Protocol Core
Version: 0.4.0
Status: draft
Last Modified: 2026-11-04
Source: project-concept/index.md
Abstraction: protocol
<!-- Changelog: CHANGELOGS/protocol-core.changes.md -->

## Role Model

Roles are assigned based on task context. The initial set includes three key roles; new ones are added as Council evolves. Each role is defined by its perspective, areas of responsibility, and prompt template.

### Extending the Role Set

A new role is introduced by documenting:
- Role name (nominative form)
- A brief description of the perspective (one sentence)
- A list of areas of responsibility
- A prompt template for initializing an agent in this role
- A scope boundary statement describing interactions with existing roles (which role takes precedence on shared subjects)

Adding a new role is a separate process that requires agreement within the project. Before approval, every candidate must undergo a **responsibility matrix audit**: a scan against all existing roles demonstrating no full overlap. Any area fully covered by another role without a complementary dimension is grounds for rejection.

---

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

---

### 4. Operations Engineer

**Perspective:** production-readiness and operational sustainability. The operations engineer reasons in terms of deployment mechanics, runtime behavior, observability, cost trajectory, and the continuity of user workflows under operational stress (ensuring users can still accomplish their goals even when systems degrade). Their focus is on how designs behave once deployed — not on structural design decisions themselves, which remain with the Architect.

**Areas of responsibility:**
- Production deployment strategies (blue-green, canary, rolling)
- Observability and alerting instrumentation (metrics, logs, traces, dashboards)
- Runtime scaling policies and auto-scaling configuration
- Cost estimation and resource optimization
- Incident detection, runbook development, and graceful degradation patterns ensuring users experience reduced but functional service rather than abrupt failure during outages, provided that safety-critical integrity checks (authentication, authorization, data consistency) are preserved under all circumstances

**Typical questions:** "Can this deployment pattern recover from a single zone failure?" "How will we monitor the health of this integration in production?" "During a region outage, can a user still submit their order, even if recommendations are disabled?"

**Scope boundary:** The operations engineer works alongside all existing roles:

- **Architect** — The Architect defines structural capacity ceilings and component interaction boundaries; the operations engineer plans runtime scaling policies that operate within those structures. The Architect determines *what* should exist and *why*; the operations engineer determines *how* it operates and *at what ongoing cost*. When a subject involves both structural limits and runtime feasibility, the Architect identifies hard constraints and the operations engineer proposes workarounds within architectural bounds; unresolved conflicts are escalated to the operator.
- **Reliability & Security Specialist** — The operations engineer evaluates behavioral properties of the system in operation (deployment mechanics, scaling behavior, monitoring efficacy, cost trajectory, and operational recovery procedures). The reliability & security specialist evaluates property-violation risks (failure modes, vulnerability surfaces, data-integrity threats, compliance gaps, confidentiality breaches). Precedence follows the nature of the finding: if it classifies a data-integrity, confidentiality, compliance, or security risk, the reliability & security specialist controls; if it classifies a deployment procedure, cost, scaling threshold, or monitoring concern, the operations engineer controls. A single decision carrying material implications in both categories stands with both stances independently. If the two stances cannot be simultaneously satisfied, the matter escalates to the operator under the "irresolvable conflict" reason. Recovery playbooks are authored by the operations engineer but must incorporate the reliability & security specialist's input on failure-mode identification, data-integrity verification, and evidence preservation. If the reliability & security specialist identifies a gap in failure-mode coverage, the operations engineer must include a documented reservation rather than overriding the concern.

---

### Role Activation Rules

Not all assigned roles participate in every session. As the role set grows, universal inclusion becomes unsustainable — each additional review adds linear latency while marginal insight diminishes due to overlapping concerns.

**Activation tiers:**

| Tier | Roles active | When to use |
|------|-------------|-------------|
| Core | Architect + Reliability & Security + Human-Centric Designer | Default for every session unless a specific justification exists for exclusion |
| Extended | Core + one or more additional roles | Activate only when the task explicitly involves the relevant domain (e.g., operations-heavy systems → include Operations Engineer) |

**Rules:**
- The Core tier is always active unless explicitly overridden by the operator.
- Additional roles activate only when justified by the task's scope. Justification must be stated in Phase 1 (Task Submission).
- Maximum role count under the current sequential protocol is **five**. Beyond that, the parallel review mode (Roadmap Phase 2) must be implemented before adding more participants.
- A task that activates fewer than all Core-tier roles must include an operator-stated reason.

**Scenario-driven assignment** (see backlog/index.md) will eventually replace manual justification with declarative scenario templates. Until then, activation is operator-managed with documented rationale.

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
