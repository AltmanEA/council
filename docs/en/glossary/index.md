# Glossary
Version: 0.11.0
Status: draft
Last Modified: 2026-11-10
Abstraction: reference
changelog-path: CHANGELOGS/glossary.changes.md

Terms and definitions for the AI-Agent Collaborative Design Framework core protocol. All definitions are in English; Russian equivalents are provided where applicable.

---

## Roles & Agents

**Role** (Роль) A perspective-driven capacity assigned to an agent within the framework, defined by its viewpoint, areas of responsibility, and a prompt template. Roles are independent evaluators; they do not represent job titles or organizational positions.

**Role Agent** (Ролевой агент) An LLM-backed agent instance initialized with a specific role's prompt and context. One instance is created per active role for each session.

**Auxiliary Agent** (Вспомогательный агент) A non-role LLM-backed worker invoked by the Execution Runtime for supporting tasks — for example, the Documentation Worker behind Documenter. Auxiliary Agents never participate in consensus, never vote, and never advance a phase.

**Primary agent** (Основной агент) The orchestrating entity responsible for strategic decisions, ambiguity resolution, scope approval, and change-plan confirmation. In the documentation workflow, it directly reads files (manifest, documents, glossary, changelogs) and delegates mechanical operations to skills like Documentation Worker. During fallback mode before the code-based Moderator exists, named subagents serve as the primary agent's operational substitute.

**Subagent** (Подагент) A named LLM-backed agent that executes delegated tasks within a session or workflow. Subagents operate under the direction of a primary agent or moderator, each assigned a specific role (e.g., Role Agent, Auxiliary Agent per protocol-core). They are distinct from auxiliary agents invoked by the execution runtime: subagents participate in structured multi-agent protocols with explicit task delegation and output aggregation.

**Architect** (Архитектор) The role responsible for evaluating how a design decision fits into the overall system structure — component boundaries, integration points, data flows, coupling, and structural scalability.

**Reliability & Security Specialist** (Специалист по надёжности и безопасности) The role responsible for examining failure modes, recovery strategies, vulnerabilities, attack vectors, compliance, and data confidentiality introduced or affected by a design decision.

**Human-Centric Designer** (Человекоцентричный проектировщик) The role responsible for ensuring that the design accounts for the end-user's real capabilities, cognitive load, accessibility, trust calibration, and understandability of system decisions.

**Operations Engineer** (Инженер по эксплуатации) The role responsible for evaluating production-readiness and operational sustainability — deployment strategies, observability instrumentation, runtime scaling policies, cost estimation, incident detection, and graceful degradation patterns. Focuses on how designs behave once deployed, not on structural design decisions.

---

## Session & Task

**Session** (Сессия) A discrete collaborative planning unit managed by the framework. Each session has a unique identifier, a set of assigned roles, and persists its state as files in `sessions/<id>/`. Sessions are short-lived and do not share data across discussions.

**Task** (Задача) A user-submitted item describing what needs to be designed or planned — typically a module, function, or system capability. A task includes scope, context, constraints, and explicit risks or open questions.

**Subject** (Объект обсуждения) A component, interface, or decision point identified during Phase 1 that a task concerns. Each subject is assigned a stable identifier used for cross-referencing in reviews, findings, and consensus documents.

**Scenario** (Сценарий) A declarative configuration that specifies which Roles activate, how the base five-phase protocol is parameterized (round counts, subject criteria, pre-phase definitions), and any safety constraints for solving problems of a particular kind. A Scenario produces Sessions when executed with a Task. Scenarios configure but never redefine the protocol structure.

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

**Session working file** (Рабочий файл сессии) — A transient file created during a council session for intermediate use (e.g., discussion drafts, temporary notes). Not committed to git, not managed by Documenter. Lifecycle is tied to the session; cleanup is the operator's responsibility.

**Session artifact** (Артефакт сессии) — A persistent output from a council session (e.g., review files, consensus documents, discussion transcripts). Committed to git for audit trail. Not managed by Documenter (outside manifest scope). Visible to the operator for review but not actionable through the Documenter audit/approval flow.

---

## Resolution

**Resolution** (Резолюция) The final decision or outcome of a task processing cycle — either a fully resolved Consensus Document, a conditionally resolved document with reservations, or an escalated item forwarded to the human operator for a binding decision. In protocol terms, resolution is the conclusion of a session's collaborative planning activity.

---

## Project

**Council** The name of the AI-Agent Collaborative Design Framework project. Used as a canonical identifier and shorthand reference across all documentation (e.g., "the Council framework," "Council protocol"). Provides a stable named entity for cross-referencing without repeated use of the full title.

**Documenter** (Документатор) An automated Supporting service under development that performs quality audits on project documentation and delegates write operations through the Documentation Worker skill. Provides two main interfaces: `audit()` for scanning documents and producing structured reports, and `delegate()` for applying approved changes with trust-level control and safety protocols. Unlike the Documentation Worker skill itself, Documenter adds policy enforcement, tier-based authorization, audit registries, rollback/reconciliation, and event logging. The Documenter classifier determines the effective trust level for delegated operations. Not yet implemented; the specification exists in `documenter-service/index.md`.

**Documentation Worker** A reusable skill providing mechanical and structural operations on project documentation artifacts. NOT part of the Council framework itself — it is an operational instrument provided as a skill and invoked via the skill tool by the primary agent to handle updates, splits, translations, and compliance audits under defined trust levels. Full contract and capabilities are at `/.agents/skills/documentation/SKILL.md`.

---

## Technical Concepts

**Orchestration** (Оркестрация) The coordination of protocol phases and role transitions, driven by role statuses and implemented via LangGraph's StateGraph. Transitions are deterministic; the state graph encodes which phase follows based on collected results.

**State Persistence** (Сохранение состояния) The practice of serializing each protocol phase's state as a separate JSON file in the session directory (`sessions/<id>/`). No shared state flows between sessions; tasks are short-lived.

**LLM Abstraction Layer** (Абстракция над LLM) A single entry point (`get_model()`) that abstracts away provider-specific details, enabling transparent model swapping without touching protocol or role logic. MVP uses one provider; replacement is trivial during scaling.

**Execution Runtime** (Среда исполнения) Layer 1 of the architecture: a deterministic control plane (the Moderator) plus non-deterministic execution units (Role Agents and Auxiliary Agents). It is the only layer that calls Layer 0.

**Execution Port** (Порт исполнения) The Layer 1 interface through which a Supporting service requests an LLM-backed operation. Documenter uses it to reach the Documentation Worker; the port enforces the Layer 2 → Supporting service → Layer 1 direction.

**Supporting Service** (Вспомогательный сервис) A service outside the three-layer chain that is invoked by the Layer 2 operator surface and may call Layer 1, but never calls Layer 2 or Layer 0 directly. Documenter, fallback mode, and JSON persistence are Supporting services.

**Intent Record** (Журнал намерения) A crash-recovery journal file written to `documenter/intent/` before the first rename in a multi-file commit. Records the full set of intended file transitions (`before_hash`, `after_hash`, `tmp_path`) to enable roll-forward reconciliation at cold-start. Managed exclusively by Documenter; hidden from the operator.

**Roll-forward** (Прямая докатка) Reconciliation procedure that re-applies staged renames from leftover `.tmp` files when no external modification occurred since the crash. Opposite of rollback; used by Documenter when an intent record is found at cold-start and all target files still match their `before_hash`.

**Commit Order** (Порядок коммита) The fixed sequence of renames in a multi-file commit: document content → `index-RU.md` → changelog → `docs-manifest.yaml` → `documenter/hashes.json`. Chosen so that a crash before the manifest step leaves orphaned but readable files rather than dangling cross-references.

**Trust Floor** (Базовый уровень доверия) The minimum trust level permitted for an operation. Two forms: *static floor*, computed at policy load from `change_type` and used to validate `allowed_operations`; and *derived floor* (dynamic), computed at invocation from the actual diff and used to validate the caller's request. A request below the derived floor is rejected with `trust_mismatch`.

**Mechanical Edit** (Механическое изменение) A deterministic, reversible change that does not alter semantic content. The complete enumeration is: (1) patch-level version bump in YAML headers; (2) append-only changelog entry insertion (`CHANGELOGS/<id>.changes.md`); (3) metadata corrections (Last Modified date, version numbers up by patch only); (4) typographical or grammatical corrections that do not affect technical meaning; (5) cross-reference anchor stabilization (replacing line numbers with heading anchors); (6) whitespace and indentation normalization; (7) format conversions within the same document structure (e.g., adding/removing table cells where content is preserved). Any change beyond these categories is classified as a semantic edit requiring higher trust levels. This list is normative — the authoritative source for trust classification.

**Effective Trust Level** (Фактический уровень доверия) The trust level actually applied to a `delegate()` invocation. Equal to the caller's requested level when that request is at or above the derived floor; never a silently upgraded value.

**Trust Tier** (Ступень доверия) One of four progressively broader deployment-level write-capability levels governing Documenter's `delegate()` operations: Tier 0 (audit only), Tier 1 (diff preview), Tier 2 (confirm-per-change), Tier 3 (pattern-based batch approve). Each advancement requires an explicit operator command. A tier governs what a deployment may do at all; it is distinct from trust *level* (`safe`/`review`), which scopes a single operation's autonomy (see Effective Trust Level). Defined in `documenter-service/index.md`, §Trust Tiers.

---

*Aligned with project documents v0.9.0 — expanded Mechanical Edit definition into normative seven-item enumeration (§Technical Concepts) to resolve C-04; added Primary agent and Subagent terms in Roles & Agents section to resolve T-06.*
