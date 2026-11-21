# Council Distribution Packager

Scripts to build, install, and update the Council framework in downstream
projects.

## Philosophy

- **No package registry.**  Distribution is a self-contained archive + shell
  scripts — the simplest possible contract.
- **Core vs. templates.**  Core files (tools, skills, vendor, normative docs)
  are owned by the framework and updated centrally.  Template files
  (project-concept, CHANGELOGS, AGENTS.md) are owned by the host project and
  never overwritten silently.
- **Overlay-friendly.**  Existing repositories can adopt Council without
  disrupting their own file tree.

## Build

From the Council repository root:

```bash
bash dist/build.sh [VERSION]
```

Produces `dist/out/council-dist-<VERSION>.tar.gz` containing:

```
council-dist/
├── install.sh          # one-shot installer (init or overlay)
├── update.sh           # core-only updater (copied into .council/ of host)
├── version.txt         # release identifier
├── core-manifest.txt   # list of paths considered "core"
├── core/               # framework files (read-only reference)
│   ├── tools/
│   ├── .agents/
│   ├── vendor/
│   ├── defaults/
│   ├── docs/en/documentation-rules/
│   ├── docs/en/documenter-service/
│   ├── docs/en/translation-project/
│   ├── docs/en/protocol-core/
│   ├── docs/en/glossary/
│   └── fallback/
└── templates/          # project-specific scaffolding
    ├── AGENTS.md.template
    ├── docs/en/project-concept/
    ├── docs/en/execution-runtime/
    ├── docs/en/operator-ingress/
    ├── docs/en/planned-architecture/
    ├── docs/en/project-reference/
    ├── docs/en/scenario/
    ├── docs/en/selector/
    ├── docs/en/service-contract/
    ├── docs/en/archive/
    └── CHANGELOGS/
```

## Install into a new project

```bash
tar xzf council-dist-1.0.0.tar.gz
cd council-dist
bash install.sh --target ../my-project --mode init --project-name "my-project"
```

## Overlay onto an existing project

```bash
cd my-existing-project
bash /path/to/council-dist/install.sh --target . --mode overlay --project-name "my-existing-project"
```

## Update core framework later

```bash
cd my-project
bash .council/update.sh /path/to/council-dist-1.1.0.tar.gz
```

`update.sh` only overwrites files listed in `.council/core-manifest.txt`;
project-specific templates are never touched.  A timestamped backup is made in
`.council/backup-<timestamp>/` before any overwrite.

## What gets installed

| Component | Source | Updated by `update.sh` | Purpose |
|-----------|--------|------------------------|---------|
| `tools/` | `core/` | **Yes** | Deterministic audit, manifest, translation verification |
| `.agents/skills/documentation/SKILL.md` | `core/` | **Yes** | OpenCode / subagent skill contract |
| `vendor/techdoc-translator/` | `core/` | **Yes** | EN→RU translation engine (vendored) |
| `defaults/` | `core/` | **Yes** | Policy and translation lock defaults |
| `docs/en/documentation-rules/` | `core/` | **Yes** | Normative documentation rules |
| `docs/en/documenter-service/` | `core/` | **Yes** | Documenter specification & impl guide |
| `docs/en/translation-project/` | `core/` | **Yes** | Translation consumer contract |
| `docs/en/protocol-core/` | `core/` | **Yes** | Council consensus protocol (roles, phases, escalation) |
| `docs/en/glossary/` | `core/` | **Yes** | Framework glossary (host project may extend) |
| `fallback/` | `core/` | **Yes** | Fallback-mode procedure for subagent environments |
| `AGENTS.md` | `templates/` | **No** | Host-project agent instructions (derived from template) |
| `docs/en/project-concept/` | `templates/` | **No** | Host project description & principles |
| `docs/en/execution-runtime/` | `templates/` | **No** | Execution environment spec |
| `docs/en/operator-ingress/` | `templates/` | **No** | Operator interface spec |
| `docs/en/planned-architecture/` | `templates/` | **No** | Architecture roadmap |
| `docs/en/project-reference/` | `templates/` | **No** | Project reference docs |
| `docs/en/scenario/` | `templates/` | **No** | Scenarios |
| `docs/en/selector/` | `templates/` | **No** | Selector spec |
| `docs/en/service-contract/` | `templates/` | **No** | Service contracts |
| `docs/en/archive/` | `templates/` | **No** | Archive directory |
| `CHANGELOGS/` | `templates/` | **No** | Per-document changelogs |

## Subagent environments

The installer detects whether the host project already runs in an environment
with subagent support (OpenCode, Claude Code, etc.).  The `AGENTS.md` template
includes a section instructing the operator how to register the
`documentation` skill and how to run fallback-mode Council sessions.  No
external MCP tools are invoked by the installer — setup is manual per the
`AGENTS.md` instructions.

## Dependencies

- **Python 3.11+** (enforced by installer; warn if missing)
- **PyYAML** (`pip install pyyaml` — checked by installer, never installed
  automatically to respect host project isolation)
- **Git** (for hook installation)
- For translation: OpenAI-compatible endpoint or local Ollama; configured in
  `vendor/techdoc-translator/.env` (`.env.example` is provided; installer
  prints a reminder)
