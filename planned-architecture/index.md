# Planned Architecture

Version: 0.2.0
Status: draft
Last Modified: 2026-11-09
Abstraction: conceptual
changelog-path: CHANGELOGS/planned-architecture.changes.md

---

## Overview

Council platform uses a multi-layered architecture with three concentric layers plus supporting mechanisms. Each layer imports only from layers below it. No layer may import from layers above it.

```
Layer 2 ─ Integration & Orchestration (MCP, CLI, scenario matching, error localization)
Layer 1 ─ Role Agent Execution (RoleAgentFactory, ScenarioLoader, model abstraction)
Layer 0 ─ Protocol Enforcement (deterministic consensus, validation rules)
Supporting ─ Fallback subagent path + JSON filesystem persistence
```

All six functional enhancements from Architecture B are integrated. None require architectural changes to layer boundaries.

See: `layer-0.md`, `layer-1.md`, `layer-2.md`, `decisions/index.md`.
