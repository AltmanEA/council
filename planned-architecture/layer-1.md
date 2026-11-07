# Layer 1 — Role Agent Execution

Version: 0.1.0
Status: draft
Last Modified: 2026-11-07
Abstraction: protocol
changelog-path: CHANGELOGS/planned-architecture.changes.md

Source: ../index.md (planned-architecture)

---

## Purpose

Instantiate and execute role agents based on scenario configuration. Where non-determinism is expected and acceptable (LLM invocation).

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

## ScenarioLoader

Loads and validates scenario configuration files. Maps problem_type declarations to default role sets. Pre-validates that activated roles exist in the catalog before passing to RoleAgentFactory.

## Model Abstraction

Single entry point `get_model()` abstracts provider details. MVP uses one provider; swapping requires touching only this function. Structured output parser converts LLM responses into validated intermediate representation before passing to Layer 0.
