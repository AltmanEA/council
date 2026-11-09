# Layer 1 — Execution Runtime

Version: 0.2.1
Status: draft
Last Modified: 2026-11-09
Abstraction: protocol
changelog-path: CHANGELOGS/planned-architecture.changes.md

Source: ../index.md (planned-architecture)

---

## Purpose

Execute the Council protocol. Layer 1 combines a deterministic control plane (the Moderator) with non-deterministic execution units (Role Agents and Auxiliary Agents). It is the only layer that calls Layer 0.

## Internal Modules

| Module | Responsibility | May import |
|--------|----------------|------------|
| `orchestrator/` | Phase state machine, Moderator, consensus and escalation routing | `agents/`, `scenario/`, `persistence/`, Layer 0 |
| `agents/` | Role Agents, Auxiliary Agents, `RoleAgentFactory`, `get_model()` | `scenario/`, Layer 0 parser types |
| `scenario/` | `ScenarioLoader`, scenario validation | Layer 0 catalog types |
| `persistence/` | Session manifest, phase files, atomic writes | — |

Import rules:

- `orchestrator/` may import the other modules; `agents/` MUST NOT import `orchestrator/`.
- Only `agents/` may call `get_model()`; `orchestrator/` MUST NOT import it directly.
- Layer 1 MUST NOT import Layer 2.

## Moderator

The Moderator is the deterministic control plane inside `orchestrator/`. It aggregates role statuses, joins findings by `subject_id`, evaluates consensus through Layer 0, and routes escalation. It performs no free-text interpretation, holds no decision power, and contains no LLM call. Phase and consensus decisions are deterministic functions of validated role outputs; no model participates in control flow or safety verification.

## RoleAgentFactory

Centralized factory creating role agent instances from validated scenario config.

### Zero silent defaults policy (ADR-002)

Every parameter either specified by caller OR taken from a documented safe value visible in session manifest. No magic defaults. All applied defaults appear in session record under `"configuration_source": "scenario_defaults"` or `"configuration_source": "operator_explicit"`.

| Parameter | Default | Scope |
|-----------|---------|-------|
| temperature | 0.1 | analytical-task reviews |
| top_p | 0.9 | analytical-task reviews |
| frequency_penalty | 0.0 | neutral (explicitly set, never inferred) |

Default whitelist managed centrally in `defaults/policy.yaml`. Expansion requires PR with justification. Reviewed quarterly.

### Contract validation hook

After creation but before enqueue, verify:

- Role identifier matches known role from `protocol-core/index.md`
- Prompt template contains required sections (perspective, responsibilities, output structure reminder)
- No unauthorized instructions appended beyond role definition and scenario context

### Session manifest traceability

Each session record includes `"role_agent_config"` section listing exact parameters used for each active role, traceable back to scenario config → factory resolution → actual agent instantiation.

### No prompt modification rule

Factory injects scenario-specific context (task scope, scenario name, pre-phase results) but does NOT modify the role's base prompt template. Prompt customization scoped to emphasis/context injection only — behavioral substitution prohibited.

## Auxiliary Agents

Auxiliary Agents are non-role LLM workers invoked by the runtime for supporting tasks. The Documentation Worker used by Documenter is the first instance: Documenter calls a Layer 1 execution port, which instantiates the worker through `agents/`. Auxiliary Agents never participate in consensus, never vote, and never advance a phase.

## ScenarioLoader

Loads and validates scenario configuration files. Maps problem_type declarations to default role sets. Pre-validates that activated roles exist in the catalog before passing to RoleAgentFactory. Scenario matching is a Layer 1 concern; Layer 2 only passes the task and scenario identifier.

## Model Abstraction

Single entry point `get_model()` abstracts provider details. MVP uses one provider; swapping requires touching only this function. The entry point is owned by `agents/`; `orchestrator/` never imports it. Structured output parser converts LLM responses into validated intermediate representation before passing to Layer 0.

## Phase Control

Only `orchestrator/` advances a phase. Every transition is a deterministic function of validated artifacts. Phase states, guards, escalation routing, and session persistence mechanics are specified in the Execution Runtime & Session Lifecycle specification.

## Migration Path

If orchestration outgrows Layer 1, extract an Orchestration Core behind Layer 1's public interface (variant B). The layer boundaries and the Layer 0 rule remain unchanged.
