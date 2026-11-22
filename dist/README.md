# Council Distribution Packager

Scripts to build, install, and update the Council framework in downstream
projects.

## Philosophy

- **No package registry.**  Distribution is a self-contained archive + shell
  scripts — the simplest possible contract.
- **Isolated install.**  The framework installs entirely under `.council/` of
  the host project; the host root contains only mandated wiring (`AGENTS.md`,
  the `opencode.jsonc` skills entry, `.opencode/agents/selector.md`, the host
  `docs-manifest.yaml`, a managed `.gitignore` block).  No Council file lands
  inside host-owned directories and there are **no symlinks** anywhere in the
  wiring.
- **Core vs. templates.**  Core files (tools, skills, vendor, normative docs)
  are owned by the framework and updated centrally.  Template files
  (project-concept, CHANGELOGS, AGENTS.md) are owned by the host project and
  never overwritten silently.
- **Overlay-friendly.**  Existing repositories can adopt Council without
  disrupting their own file tree.
- **Pinned releases.**  A host runs a tagged snapshot of the framework; it
  updates only when the operator copies a new archive and runs `update.sh`.
  Core files are not hand-edited on hosts — fixes go through the source repo.
- **Verified channel.**  Every build emits `SHA256SUMS` next to the archive
  (same step — it cannot be forgotten); `update.sh` verifies it automatically.

**Host operators: read [RUNBOOK.md](RUNBOOK.md) before the first install.**
It covers mode choice, install, update, rollback, emergency restore,
translation `.env`, and version checks.

## Releasing (source repo side)

The pinned channel is anchored to git tags.  The first release is tagged
`v0.1.0`; every host-bound build must come from a tag:

```bash
git tag v0.1.0
bash dist/build.sh                 # VERSION taken from the tag
```

Without a tag, `build.sh` prints a warning and uses a `dev-<hash>` version.
Dev builds are for local testing only — never ship them to a host
(`update.sh` and the host will visibly show the `dev-` prefix).

Before shipping an archive after any change to `dist/*.sh`, run the smoke
test once:

```bash
bash dist/test-dry-run.sh          # exit 0 = install → update → restore → overlay OK
```

Copy BOTH `council-dist-<VERSION>.tar.gz` and `SHA256SUMS` to the host, then
on the host: `bash .council/update.sh council-dist-<VERSION>.tar.gz`.

## Build

From the Council repository root:

```bash
bash dist/build.sh [VERSION]
```

Builds also emit `SHA256SUMS` next to the archive in `dist/out/`.

Produces `dist/out/council-dist-<VERSION>.tar.gz` containing:

```
council-dist/
├── install.sh          # one-shot installer (init or overlay)
├── update.sh           # core-only updater (copied into .council/ of host)
├── RUNBOOK.md          # host-operator procedure (install/update/rollback/emergency)
├── version.txt         # release identifier
├── core-manifest.txt   # list of paths considered "core"
├── core/               # framework files (read-only reference)
│   ├── tools/
│   ├── .agents/
│   ├── vendor/
│   ├── defaults/              # translation.lock only (policy.yaml removed)
│   ├── docs/en/documentation-rules/
│   ├── docs/en/documenter-service/
│   ├── docs/en/translation-project/
│   ├── docs/en/protocol-core/
│   ├── docs/en/glossary/
│   ├── docs/en/archive/index.md   # archive guard file only
│   ├── CHANGELOGS/            # seed changelogs for shipped core docs
│   └── fallback/
└── templates/          # project-specific scaffolding
    ├── AGENTS.md.template
    ├── docs/en/project-concept/
    └── CHANGELOGS/project-concept.changes.md
```

> Variant-B composition (consensus `sess-dist-content-review`, 2026-11-22):
> `docs/ru/` mirrors are not shipped; `has_translation` frontmatter lines and
> concrete `docs/ru/...` path tokens are stripped from the staged copies at
> build time (council's own tree is untouched). Superseded v0.x specs
> (execution-runtime, operator-ingress, planned-architecture, scenario,
> service-contract, selector, project-reference) and the council CHANGELOGS
> bulk no longer ship to hosts.

> Layout note (`sess-dist-isolated-install-2026-11-22`): the archive's `core/`
> keeps the plain source-repo layout, while `core-manifest.txt` entries carry
> the `.council/` destination prefix (e.g.
> `.council/docs/en/glossary/index.md`). The installer strips the prefix to
> locate the source file in `core/` and creates the destination under the
> host's `.council/`.

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

`update.sh` iterates the **union** of the host's `.council/core-manifest.txt`
and the new archive's manifest: entries present in the new archive are
updated; entries listed in the host manifest but absent from the new release
are **removed** (`[removed]`, with a restore path shown).  Project-specific
templates are never touched.  A timestamped backup is made in
`.council/backup-<timestamp>/` before any overwrite or removal.

## What gets installed

All framework files install under `.council/` (isolated layout, per consensus
`sess-dist-isolated-install-2026-11-22`); only the last four rows touch the host
root, and they are the mandated wiring.

| Component | Source | Updated by `update.sh` | Purpose |
|-----------|--------|------------------------|---------|
| `.council/tools/` | `core/tools/` | **Yes** | Deterministic audit, manifest, translation verification |
| `.council/skills/` | `core/.agents/skills/` | **Yes** | Skill contracts (registered in `opencode.jsonc`; re-mapped from `.council/.agents/skills` at install and after every update) |
| `vendor/techdoc-translator/` under `.council/` | `core/` | **Yes** | EN→RU translation engine (vendored); developer `.env` is excluded |
| `.council/docs-manifest.yaml` | generated at install | **No** | Core manifest, generated by `.council/tools/gen_manifest.py --root .council --write` |
| `.council/defaults/translation.lock` | `core/` | **Yes** | Translation engine pin (policy.yaml is no longer shipped) |
| `.council/docs/en/documentation-rules/` | `core/` | **Yes** | Normative documentation rules |
| `.council/docs/en/documenter-service/` | `core/` | **Yes** | Documenter specification & impl guide |
| `.council/docs/en/translation-project/` | `core/` | **Yes** | Translation consumer contract |
| `.council/docs/en/protocol-core/` | `core/` | **Yes** | Council consensus protocol (roles, phases, escalation) |
| `.council/docs/en/glossary/` | `core/` | **Yes** | Framework glossary (host project may extend via its own docs) |
| `.council/docs/en/archive/index.md` | `core/` | **Yes** | Archive guard file (history-only convention marker) |
| `.council/CHANGELOGS/` (seeds) | `core/` | **Yes** | Seed changelogs referenced by shipped core docs' frontmatter |
| `.council/fallback/` | `core/` | **Yes** | Fallback-mode procedure for subagent environments |
| `.opencode/agents/selector.md` | `core/` | **Yes** (root) | Model-neutral selector subagent; host keeps its own model/provider config |
| `AGENTS.md` | `templates/` | **No** (root) | Host-project agent instructions (derived from template) |
| `docs-manifest.yaml` (root) | generated at install | **No** | Host manifest, generated by `.council/tools/gen_manifest.py --root <target> --write` if absent; existing host manifest is kept |
| `docs/en/project-concept/` (root) | `templates/` | **No** | Host project description & principles |
| `CHANGELOGS/project-concept.changes.md` (root) | `templates/` | **No** | Seed changelog for the project-concept doc |

Host-root wiring beyond the templates above: the installer creates or merges
`opencode.jsonc` with `"skills": ["./.council/skills"]` (a host config without a
`skills` key is never rewritten — the installer warns instead) and appends an
idempotent managed block to `.gitignore` (`.council/backup-*/`,
`.council/**/__pycache__/`, `.council/telemetry/**/*.jsonl`,
`**/techdoc-translator/.env`).  Git hooks are installed automatically:
`core.hooksPath` points at `.council/tools/hooks`, and that hook resolves
`check_all.py` relative to itself.

## Subagent environments

Skills under `.council/skills/` are discovered through an explicit
`opencode.jsonc` entry (`"skills": ["./.council/skills"]`) written by the
installer — OpenCode does **not** auto-discover `.council/.agents/skills`, and
symlinks are not used.  The shipped `.opencode/agents/selector.md` registers the
selector subagent at its harness-fixed location without overriding the host's
model/provider configuration — the source repo's `.opencode/opencode.jsonc` is
deliberately not shipped.  The `AGENTS.md` template also explains how to run
fallback-mode Council sessions, including the Koda CLI profile in
`.council/fallback/koda-execution-mode.md`.  No external MCP tools are invoked
by the installer — setup is manual per the `AGENTS.md` instructions.

A fresh install generates BOTH manifests: the core manifest
(`.council/docs-manifest.yaml`) and, if absent, the host manifest
(`docs-manifest.yaml` at root), so `.council/tools/check_all.py --root .
--core-root .council` is clean and manifest-first doc reads work immediately.
On overlay, existing manifests are never overwritten.

The vendored translator's `.env` is never shipped: the host copies
`.env.example` itself (see RUNBOOK §7).  This avoids leaking the build machine's
endpoint/model defaults.

## Dependencies

- **Python 3.11+** (enforced by installer; warn if missing)
- **PyYAML** (`pip install pyyaml` — checked by installer, never installed
  automatically to respect host project isolation; required to generate
  `docs-manifest.yaml` and to run the core tools)
- **Git** (for hook installation)
- For translation: OpenAI-compatible endpoint or local Ollama; configured in
  `.council/vendor/techdoc-translator/.env` (`.env.example` is provided;
  installer prints a reminder)
