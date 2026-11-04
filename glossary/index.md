# Glossary
Version: 0.3.1
Status: draft
Last Modified: 2026-11-04
<!-- Changelog: CHANGELOGS/glossary.changes.md -->

Terms and definitions for the AI-Agent Collaborative Design Framework core protocol. All definitions are in English; Russian equivalents are provided where applicable.

---

## Roles & Agents

**Role** (Роль) A perspective-driven capacity assigned to an agent within the framework, defined by its viewpoint, areas of responsibility, and a prompt template. Roles are independent evaluators; they do not represent job titles or organizational positions.

**Role Agent** (Ролевой агент) An LLM-backed agent instance initialized with a specific role's prompt and context. One instance is created per active role for each session.

**Architect** (Архитектор) The role responsible for evaluating how a design decision fits into the overall system structure — component boundaries, integration points, data flows, coupling, and structural scalability.

**Reliability & Security Specialist** (Специалист по надёжности и безопасности) The role responsible for examining failure modes, recovery strategies, vulnerabilities, attack vectors, compliance, and data confidentiality introduced or affected by a design decision.

**Human-Centric Designer** (Человекоцентричный проектировщик) The role responsible for ensuring that the design accounts for the end-user's real capabilities, cognitive load, accessibility, trust calibration, and understandability of system decisions.

---

## Session & Task

**Session** (Сессия) A discrete collaborative planning unit managed by the framework. Each session has a unique identifier, a set of assigned roles, and persists its state as files in `sessions/<id>/`. Sessions are short-lived and do not share data across discussions.

**Task** (Задача) A user-submitted item describing what needs to be designed or planned — typically a module, function, or system capability. A task includes scope, context, constraints, and explicit risks or open questions.

**Subject** (Объект обсуждения) A component, interface, or decision point identified during Phase 1 that a task concerns. Each subject is assigned a stable identifier used for cross-referencing in reviews, findings, and consensus documents.

---

## Interaction Protocol

**Phase** (Фаза) A distinct stage in the interaction protocol with clearly defined inputs, actions, and outputs. The base protocol defines five phases: Task Submission, Individual Review, Discussion Round, Consensus Check, and Resolution Formation.

**Discussion Round** (Раунд обсуждения) A single iteration of the protocol where agents receive all previously produced reviews and respond — reaffirming, adjusting, countering, or proposing compromises. Multiple rounds may occur; after a configured limit, the process advances to Consensus Check.

**Targeted Resolution Round** (Целевой раунд разрешения) An extra discussion round triggered when at least one role declares `blocked-in-scope`, focused exclusively on resolving that blocker. If the block persists, the role reclassifies it as `blocked-escalation`.

**Moderator** (Модератор) A deterministic, code-based component (not an LLM) that orchestrates the protocol by aggregating role statuses, joining findings by subject identifiers, checking consensus rules, and triggering escalation paths. It performs no interpretation of free text and holds no decision power.

**Consensus** (Консенсус) The state reached when all participating roles declare `agree` status. Consensus means the task is resolved and a Consensus Document is produced. Conditional consensus occurs when only `concerns` are present (no blocks).

**Disagreement** (Расхождение) A condition where two or more roles record opposite stances (`support` vs `oppose`) on the same subject identifier in their final-round findings. This is a structural check over machine-readable data, not a textual judgment.

---

## Findings & Severity

**Finding** (Вывод) A discrete observation produced by a role during review, tagged with severity, subject reference, optional stance, and — for critical severity only — a justification naming a concrete failure mode or attack scenario.

**Severity** (Уровень серьёзности) The seriousness level of a finding, drawn from a fixed set: `low`, `medium`, `high`, `critical`. Only medium and above can contribute to blocking a task.

**Critical Finding Justification** (Обоснование критического вывода) For severity = `critical`: a mandatory narrative that names a concrete failure mode or attack scenario and references at least one subject identifier. Format validation is performed by the Moderator; an invalid justification downgrades the finding to `high` without changing the original text.

**Stance** (Позиция) A structured field on a finding indicating whether the role supports (`support`) or opposes (`oppose`) a proposed decision on a subject. Null when the finding does not address a proposed decision.

---

## Role Status

**Role Status** (Статус роли) A final verdict declared by a role after completing its review. Drawn from a fixed enumeration: `agree`, `concerns`, `blocked-in-scope`, `blocked-escalation`. Only the status from the last phase counts for consensus evaluation.

**Agree** (Согласие) The role reports no material issues with the task. Contributes positively toward consensus.

**Concerns** (Замечания) The role has observations but none that block the decision. The task can be conditionally resolved with reservations recorded.

**Blocked In-Scope** (Заблокировано внутри домена) The role identifies a fundamental issue it believes the agent group can potentially resolve internally. Triggers a Targeted Resolution Round.

**Blocked Escalation** (Заблокировано для эскалации) The role identifies a fundamental issue matching a defined escalation reason (`information gap`, `irresolvable conflict`, or `risk threshold breach`). Triggers the Escalation Protocol.

---

## Escalation

**Escalation** (Эскалация) A mechanism activated when the agent group cannot reach agreement or lacks required information, routing the problem to the human operator for resolution. Escalation is a normal outcome, not a system error.

**Information Gap** (Информационный пробел) An escalation reason indicating that agents have sufficient understanding of the task but lack specific input data needed to make an informed decision. The escalation record contains an enumerated request for the missing information.

**Irresolvable Conflict** (Неразрешимый конфликт) An escalation reason where two or more roles take fundamentally different positions, both well-argued, and neither yields through discussion. The operator is asked to make the final decision between the conflicting positions.

**Risk Threshold Breach** (Превышение порога риска) An escalation reason triggered when any role identifies a risk it assesses as critical. This acts as a safety veto: the current discussion branch halts immediately, regardless of other agents' assessments. Safety and reliability priority is not subject to voting.

**Escalation Reason** (Причина эскалации) A categorical label explaining why an escalation was triggered. Must be stated whenever a role declares `blocked-escalation`. The set is fixed: `information gap`, `irresolvable conflict`, `risk threshold breach`.

---

## Artifacts

**Artifact** (Артефакт) A structured document produced by the framework, composed of a fixed set of elements that protocol rules depend on. There are three artifacts: Role Review, Consensus Document, and Escalation record.

**Role Review** (Отзыв роли) An artifact produced by each role in each protocol round, containing a summary position, findings (with severity, subject, stance, justification), recommended actions, open questions, and a role status.

**Consensus Document** (Документ консенсуса) The primary output artifact produced when a task resolves (either fully or conditionally). Contains the decision, rationale, subjects with outcomes, reservations, open questions, action items, escalation references, and a transparency list of downgraded critical findings.

**Escalation record** (Запись эскалации) An artifact produced each time the system hands a problem to the operator. Contains escalation type, raising role, severity, blocker description, positions, operator request, fallback strategy with timeout, resolution outcome, and resume phase.

---

## Resolution

**Resolution** (Резолюция) The final decision or outcome of a task processing cycle — either a fully resolved Consensus Document, a conditionally resolved document with reservations, or an escalated item forwarded to the human operator for a binding decision. In protocol terms, resolution is the conclusion of a session's collaborative planning activity.

---

## Project

**Council** The name of the AI-Agent Collaborative Design Framework project. Used as a canonical identifier and shorthand reference across all documentation (e.g., "the Council framework," "Council protocol"). Provides a stable named entity for cross-referencing without repeated use of the full title.

---

## Technical Concepts

**Orchestration** (Оркестрация) The coordination of protocol phases and role transitions, driven by role statuses and implemented via LangGraph's StateGraph. Transitions are deterministic; the state graph encodes which phase follows based on collected results.

**State Persistence** (Сохранение состояния) The practice of serializing each protocol phase's state as a separate JSON file in the session directory (`sessions/<id>/`). No shared state flows between sessions; tasks are short-lived.

**LLM Abstraction Layer** (Абстракция над LLM) A single entry point (`get_model()`) that abstracts away provider-specific details, enabling transparent model swapping without touching protocol or role logic. MVP uses one provider; replacement is trivial during scaling.

---

*Aligned with project documents v0.4.0 — split: project-concept/index.md, protocol-core/index.md, project-reference/index.md.*
