# Planned Architecture

Version: 0.3.0
Status: draft
Last Modified: 2026-11-08
Abstraction: conceptual
changelog-path: CHANGELOGS/planned-architecture.changes.md

---

## Overview

Council uses three core layers plus supporting services. Dependencies point downward only: no layer imports from a layer above it, and supporting services have a restricted call surface. The Moderator is not a separate layer — it is the deterministic control plane inside Layer 1.

```
Layer 2 ─ External Interfaces / Adapters
          MCP stdio transport · input validation · error localization · operator surface
              │ invoke
              ▼
Layer 1 ─ Execution Runtime
          deterministic Moderator · Role Agents · Auxiliary Agents · ScenarioLoader · persistence
              │
              ▼
Layer 0 ─ Protocol Enforcement
          deterministic consensus · validation rules

Supporting services (outside the layer chain)
          Documenter · fallback mode · JSON persistence
```

## Layer Summary

| Layer | Name | Responsibility | Determinism |
|-------|------|----------------|-------------|
| 2 | External Interfaces / Adapters | Transport, ingress validation, error localization, operator surface | Adapters only; no LLM |
| 1 | Execution Runtime | Phase orchestration, agent instantiation, scenario loading, session persistence | Mixed: deterministic Moderator, non-deterministic agents |
| 0 | Protocol Enforcement | Consensus evaluation, subject validation, status extraction, justification format | Fully deterministic; no LLM |

## Dependency Rules

- Layer 2 may call Layer 1. It MUST NOT call Layer 0 directly.
- Layer 1 may call Layer 0. Layer 0 calls nothing above it.
- Layer 1 MUST NOT import Layer 2. Layer 0 MUST NOT import Layer 1 or Layer 2.
- Layer 2 MUST NOT invoke an LLM directly. LLM access is confined to Layer 1 agents through `get_model()`.
- The Moderator is deterministic and lives in Layer 1 (`orchestrator/`). No LLM participates in control flow or safety verification.

## Supporting Services

Supporting services sit outside the layer chain. They may call Layer 1 and MUST NOT call Layer 2 or Layer 0 directly.

| Service | Role | Call surface |
|---------|------|--------------|
| Documenter | Documentation audit and delegated writes | Invoked by the Layer 2 operator surface; LLM-backed writes use a Layer 1 execution port |
| Fallback mode | Manual protocol execution by named subagents | Operator-driven; replaces the code Moderator; shares only the artifact format |
| JSON persistence | Session state store (`sessions/<id>/`) | Used by Layer 1 `persistence/`; local-only, not committed |

## Migration Path

If orchestration outgrows Layer 1, extract an Orchestration Core behind Layer 1's public interface. The layer boundaries and the Layer 0 rule remain unchanged.

## Enhancements

All six functional enhancements from Architecture B are integrated; none require changes to the layer boundaries. Deferred items — ScenarioLoader catalog, schema migration chain, quick-review classifier, Typer CLI, checkpoint/resume, distributed locking — are listed in the consensus document that produced this revision and will be tracked in the service specifications.

See: `layer-0.md`, `layer-1.md`, `layer-2.md`, `decisions/index.md`.
