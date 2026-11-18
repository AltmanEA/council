# Glossary
id: glossary
Version: 0.18.0
Status: active
Abstraction: reference
has_translation: docs/ru/glossary/index-RU.md
changelog-path: CHANGELOGS/glossary.changes.md

Terms and definitions for the AI-Agent Collaborative Design Framework core protocol.
**Operator-facing terms** are protocol concepts used day-to-day.
**Tooling & services terms** are developer-facing (Documenter internals, translation pipeline).

---

## Roles & Agents

**Role** (Роль) A perspective-driven capacity assigned to an agent within the framework, defined by its viewpoint, areas of responsibility, and a prompt template. Roles are independent evaluators; they do not represent job titles or organizational positions.

**Role Agent** (Ролевой агент) An LLM-backed agent instance initialized with a specific role's prompt and context. One instance is created per active role for each session.

**Auxiliary Agent** (Вспомогательный агент) A non-role LLM-backed worker invoked by the Execution Runtime for supporting tasks. Auxiliary Agents never participate in consensus, never vote, and never advance a phase. See also: **Subagent**.

**Primary agent** (Основной агент) The orchestrating entity responsible for strategic decisions, ambiguity resolution, scope approval, and change-plan confirmation. Distinct from the human operator (who approves changes) and from subagents (which execute delegated protocol tasks). In fallback mode before the code-based Moderator exists, named subagents serve as the primary agent's operational substitute.

**Subagent** (Подагент) A named LLM-backed agent that executes delegated tasks within a session or workflow. Subagents operate under the direction of a primary agent or moderator, each assigned a specific role (e.g., Role Agent, Auxiliary Agent). They are distinct from auxiliary agents: subagents participate in structured multi-agent protocols with explicit task delegation and output aggregation.

**Architect** (Архитектор) Evaluates how a design decision fits into overall system structure — component boundaries, integration points, data flows, coupling, and structural scalability.

**Reliability & Security Specialist** (Специалист по надёжности и безопасности) Examines failure modes, recovery strategies, vulnerabilities, attack vectors, compliance, and data confidentiality introduced or affected by a design decision.

**Human-Centric Designer** (Человекоцентричный проектировщик) Ensures the design accounts for the end-user's real capabilities, cognitive load, accessibility, trust calibration, and understandability of system decisions.

**Operations Engineer** (Инженер по эксплуатации) Evaluates production-readiness and operational sustainability — deployment strategies, observability, scaling, cost estimation, and graceful degradation.

**Role Activation Tiers** (Уровни активации ролей) Classification model determining which Roles participate. **Core** (Architect + R&S Specialist + HCD, active by default) and **Extended** (Core + additional roles, activated only when justified). See also: `protocol-core/index.md`, §Role Activation Rules.

---

## Session & Task

**Session** (Сессия) A discrete collaborative planning unit with a unique identifier, assigned roles, and persisted state as files in `sessions/<id>/`. Sessions are short-lived and do not share data across discussions.

**Task** (Задача) A user-submitted item describing what needs to be designed — a module, function, or system capability. Includes scope, context, constraints, and explicit risks or open questions.

**Subject** (Объект обсуждения) A component, interface, or decision point identified during Phase 1. Each assigned a stable identifier used for cross-referencing in reviews, findings, and consensus documents.

**Scenario** (Сценарий) A declarative configuration specifying which Roles activate and how the five-phase protocol is parameterized. Produces Sessions when executed with a Task.

---

## Interaction Protocol

**Phase** (Фаза) A distinct stage in the interaction protocol with defined inputs, actions, and outputs. Five phases: Task Submission, Individual Review, Discussion Round, Consensus Check, Resolution Formation.

**Discussion Round** (Раунд обсуждения) A single iteration where agents receive all previously produced reviews and respond — reaffirming, adjusting, countering, or proposing compromises.

**Targeted Resolution Round** (Целевой раунд разрешения) An extra discussion round triggered when at least one role declares `blocked-in-scope`, focused exclusively on resolving that blocker.

**Moderator** (Модератор) A deterministic, code-based component (not an LLM) orchestrating the protocol by aggregating role statuses, joining findings by subject identifiers, checking consensus rules, and triggering escalation paths.

**Consensus** (Консенсус) The state reached when all participating roles declare `agree`. Means the task is resolved and a Consensus Document is produced. See also: **Disagreement**, **ConsensusVerdict**.

**Disagreement** (Расхождение) A condition where two or more roles record opposite stances (`support` vs `oppose`) on the same subject identifier in final-round findings. This is a structural check over machine-readable data, not a textual judgment. All disagreements are evaluated against escalation criteria; only those satisfying Information Gap, Irresolvable Conflict, or Risk Threshold Breach are escalable.

---

## Findings & Severity

**Finding** (Вывод) A discrete observation produced by a role during review, tagged with severity, subject reference, optional stance, and — for critical severity only — a justification naming a concrete failure mode or attack scenario.

**Severity** (Уровень серьёзности) The seriousness level of a finding, drawn from a fixed set. **low**: minor observation with no operational impact. **medium**: observable defect that can be mitigated within session. **high**: significant degradation requiring external intervention. **critical**: causes irrecoverable harm, data loss, or protocol deadlock. Only medium and above can contribute to blocking a task.

**Critical Finding Justification** (Обоснование критического вывода) For severity = `critical`: a mandatory narrative naming a concrete failure mode (security, availability, integrity, correctness, privacy) and referencing at least one subject identifier.

**Stance** (Позиция) A structured field on a finding indicating whether the role supports (`support`) or opposes (`oppose`) a proposed decision on a subject. Null when the finding does not address a proposed decision. See also: **Consensus**.

**ConsensusVerdict** (Вердикт консенсуса) A structured type produced by the Moderator at Phase 4, containing: `outcome` (`consensus`, `conditional`, `no-consensus`, or `blocked-escalation`), optional `escalation_reason`, and target `phase_state`. See also: `protocol-core/index.md`, §Outcome-to-Transition.

---

## Role Status

**Role Status** (Статус роли) A final verdict declared by a role after completing its review. Drawn from a fixed enumeration: `agree`, `concerns`, `blocked-in-scope`, `blocked-escalation`. Only the status from the last phase counts for consensus evaluation.

**Agree** (Согласие) No material issues. Contributes positively toward consensus.

**Concerns** (Замечания) Observations but none that block the decision. The task can be conditionally resolved with reservations recorded.

**Blocked In-Scope** (Заблокировано внутри домена) Identifies a fundamental issue the agent group can potentially resolve internally. Triggers a Targeted Resolution Round.

**Blocked Escalation** (Заблокировано для эскалации) Identifies a fundamental issue matching a defined escalation reason. Triggers the Escalation Protocol. See also: **Escalation**.

---

**Operator Ingress** (Точка входа оператора) The Layer 2 authenticated adapter through which the human operator reaches the Council runtime: authenticates the caller, validates input, enforces deny-by-default authorization, renders the operator status projection and escalation view, and hosts the `pre_check` gate. It contains no protocol logic and no LLM invocation. The operator — a human principal — exercises sovereign governance authority at this boundary; agent read-only verbs are an intentional design feature, not a permission leak. Despite earlier naming, it is not a network gateway and not a login screen. Formerly "Operator Surface" (renamed per ADR-018, 2026-11-18). See also: **Approval Surface**, **Escalation**.

**Operator Surface** (Поверхность оператора) *Deprecated.* Former name of **Operator Ingress**; retained only for historical reference (ADR-018). Do not use in new text.

## Escalation

**Escalation** (Эскалация) A mechanism activated when the agent group cannot reach agreement or lacks required information, routing the problem to the human operator for resolution. Escalation is a normal outcome, not a system error. See also: **Disagreement**, **Consensus**.

**Information Gap** (Информационный пробел) Agents have sufficient understanding of the task but lack specific input data needed for an informed decision. The escalation record contains an enumerated request for the missing information.

**Irresolvable Conflict** (Неразрешимый конфликт) Two or more roles take fundamentally different positions, both well-argued, and neither yields through discussion. The operator makes the final decision between the conflicting positions.

**Risk Threshold Breach** (Превышение порога риска) An escalation reason triggered when any role assigns Severity = `critical` to a Finding that addresses a risk. Acts as a safety veto: the current discussion branch halts immediately, regardless of other agents' assessments. Safety and reliability priority is not subject to voting.

**Escalation Reason** (Причина эскалации) A categorical label explaining why an escalation was triggered, stated whenever a role declares `blocked-escalation`. Fixed set: `information gap`, `irresolvable conflict`, `risk threshold breach`.

---

## Artifacts

**Artifact** (Артефакт) A structured document produced by the framework, composed of a fixed set of elements that protocol rules depend on. Three artifacts: Role Review, Consensus Document, and Escalation record.

**Role Review** (Отзыв роли) An artifact produced by each role in each protocol round, containing a summary position, findings (severity, subject, stance, justification), recommended actions, open questions, and a role status.

**Consensus Document** (Документ консенсуса) The primary output artifact produced when a task resolves (fully or conditionally). Contains the decision, rationale, subjects with outcomes, reservations, open questions, action items, escalation references, and a transparency list of downgraded critical findings.

**Escalation record** (Запись эскалации) An artifact produced each time the system hands a problem to the operator. Contains escalation type, raising role, severity, blocker description, positions, operator request, fallback strategy with timeout, resolution outcome, and resume phase.

**Session working file** A transient file created during a council session for intermediate use (e.g., discussion drafts, temporary notes). Not committed to git, not managed by Documenter. Lifecycle is tied to the session; cleanup is the operator's responsibility.

**Session artifact** A persistent output from a council session (e.g., review files, consensus documents, discussion transcripts). Committed to git for audit trail. Not managed by Documenter (outside manifest scope). Visible to the operator for review but not actionable through the Documenter audit/approval flow.

---

## Resolution

**Resolution** (Резолюция) The final decision or outcome of a task processing cycle — either a fully resolved Consensus Document, a conditionally resolved document with reservations, or an escalated item forwarded to the human operator for a binding decision.

---

## Core Framework Concepts

**Orchestration** (Оркестрация) The coordination of protocol phases and role transitions, driven by role statuses. Transitions are deterministic; the state graph encodes which phase follows based on collected results.

**State Persistence** (Сохранение состояния) The practice of serializing each protocol phase's state as separate files in the session directory. No shared state flows between sessions.

**LLM Abstraction Layer** (Абстракция над LLM) A single entry point (`get_model()`) that abstracts away provider-specific details, enabling transparent model swapping without touching protocol or role logic.

**Execution Runtime** (Среда исполнения) Layer 1 of the architecture: a deterministic control plane (the Moderator) plus non-deterministic execution units (Role Agents and Auxiliary Agents). It is the only layer that calls Layer 0.

**Execution Port** (Порт исполнения) The Layer 1 interface for a Supporting service to request an LLM-backed operation. Enforces the Layer 2 → Supporting service → Layer 1 direction.

**Supporting Service** (Вспомогательный сервис) A service outside the three-layer chain, invoked by Layer 2, may call Layer 1, never calls Layer 2 or Layer 0.

---

## Tooling & Services

**Documenter** (Документатор) An automated Supporting service that performs quality audits on project documentation and delegates write operations through the Documentation Worker skill. Implementation status: Tier 0–1 Operational (CLI and MCP stdio implemented; MCP server not registered); Tier 2+ write branch is Dormant behind the dual interlock (ADR-013). Specification: `documenter-service/index.md`.

**Documentation Worker** A reusable skill providing mechanical and structural operations on project documentation artifacts. NOT part of the Council framework itself — it is an operational instrument invoked via the skill tool by the primary agent.

**Operational** (Операционный) Documentation-status term: the described capability exists in code and is available to the operator in the current configuration. Does not imply registered or invoked autonomously.

**Dormant** (Реализовано, не активировано) Documentation-status term: the described capability exists in code but is unreachable at runtime because a normative interlock blocks activation. Distinct from *structurally absent* and from *Operational*.

**Commit Order** (Порядок коммита) The fixed sequence of renames in a multi-file commit: document content → `index-RU.md` → changelog → `docs-manifest.yaml` → hash store. Chosen so a crash before the manifest step leaves orphaned but readable files.

**Hash Store** (Хранилище хэшей) The Documenter-managed persistence structure storing content-hash tokens used for optimistic concurrency control on delegate-mode writes. A rebuildable cache (ADR-010), not authoritative state.

**Rebuildable Cache** (Восстанавливаемый кэш) A derived state artifact that the owning service may discard and recompute from authoritative sources; a cache miss triggers rebuild-and-continue. Distinct from authoritative state.

**Intent Record** (Журнал намерения) A crash-recovery journal written before the first rename in a multi-file commit. Records intended file transitions to enable roll-forward reconciliation at cold-start.

**Roll-forward** (Прямая докатка) Reconciliation procedure re-applying staged renames from leftover `.tmp` files when no external modification occurred since the crash.

**Trust Floor** (Базовый уровень доверия) The minimum trust level permitted for an operation. Two forms: *static floor* (computed at policy load from `change_type`) and *derived floor* (computed at invocation from the actual diff).

**Mechanical Edit** (Механическое изменение) A deterministic, reversible change not altering semantic content. Seven enumerated categories: (1) patch-level version bump in YAML headers; (2) append-only changelog entry; (3) metadata corrections; (4) typographical corrections; (5) cross-reference anchor stabilization; (6) whitespace normalization; (7) format conversions within same document structure.

**Effective Trust Level** (Фактический уровень доверия) The trust level applied to a `delegate()` invocation. Equal to the caller's requested level when at or above the derived floor; never a silently upgraded value.

**Trust Tier** (Ступень доверия) One of four progressively broader write-capability levels: Tier 0 (audit only), Tier 1 (diff preview), Tier 2 (confirm-per-change), Tier 3 (pattern-based batch approve). Each advancement requires an explicit operator command.

**Write-Gate** (Гейт записи) A mandatory verification gate blocking automatic writing of a derived artifact until all checks pass. Used in RU translation synchronization.

**Post-Approve Auto-Dispatch** (Автозапуск после утверждения) A mechanical follow-up action runs automatically only after the human operator's approval of the parent changeset.

**Translation Opt-Out Flag** (Флаг отказа от перевода) A document frontmatter field (`no_auto_translation: true`) excluding a document from automatic Russian synchronization.

**Drift Checker** (Инструмент проверки расхождений) A deterministic tool comparing English source and Russian candidate on structural invariants only (headings, tables, code fences, list markers, inline-code spans, separators, metadata fingerprint).

**Structural Fingerprint** (Структурный отпечаток) The set of invariant structural properties used by the drift checker to verify translation candidates without semantic comparison.

**Mock Regression** (Мок-регрессия) A deterministic offline test layer where the translation model is replaced by canned responses, verifying structural invariants of the pipeline.

**Translation Project** (Проект перевода) The standalone external software project (techdoc-translator) generating EN→RU candidate translations via a CLI contract. Holds no knowledge of Council artifacts.

**Translation Project Artifact** (Артефакт проекта перевода) An operational output consumed by Council from a translation run (RU candidate, run report, provenance records). Never a project document, never listed in the manifest.

**Status Index** (Индекс статусов) A generated operational table mapping each translated document to a verification status (`verified` / `unverified` / `drift` / `error-<code>`); rebuilt from stored run reports.

**Translation Contract** (Контракт перевода) The versioned CLI interface (flags, report schema, exit codes 0–6) between Council's adapter and the Translation Project. Mismatch fails closed (ADR-014).

---

*Aligned with project documents v0.9.0 — Glossary v0.17.0: consolidated severity definitions, restructured into operator-facing / tooling sections, added cross-references, fixed formatting invariants, purged meta-evaluation content.*
