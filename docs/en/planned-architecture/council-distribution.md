# Council Distribution System
id: council-distribution
Version: 0.1.0
Status: draft
Abstraction: protocol
changelog-path: CHANGELOGS/council-distribution.changes.md

---

## 1. Purpose

Define a zero-registry mechanism for propagating the Council framework
(documenter pipeline, consensus protocol, fallback orchestration, and
translation engine) into downstream projects.

Design constraints:
- No package registry (PyPI, npm, Docker Hub).
- Must support both new projects (`init`) and existing repositories (`overlay`).
- Core framework files must be independently updatable without touching
  project-specific content.
- Must operate in subagent-capable environments (OpenCode, Claude Code, etc.).

---

## 2. Architecture Overview

Distribution is a self-contained archive assembled from the current checkout.

```
council-dist-<VERSION>.tar.gz
├── core/              → framework files (centrally owned, updated)
├── templates/         → project scaffolding (installed once, never overwritten)
├── install.sh         → init / overlay installer
├── update.sh          → core-only updater (copied into .council/ of host)
├── version.txt        → release identifier
└── core-manifest.txt  → authoritative list of core paths
```

### 2.1 File Classification

| Category | Examples | Ownership | Updated by `update.sh` |
|----------|----------|-----------|------------------------|
| **Core** | `tools/`, `.agents/`, `vendor/`, `defaults/`, `docs/en/documentation-rules/`, `docs/en/documenter-service/`, `docs/en/protocol-core/`, `docs/en/glossary/`, `docs/en/translation-project/`, `fallback/` | Council upstream | **Yes** |
| **Templates** | `AGENTS.md`, `docs/en/project-concept/`, `docs/en/execution-runtime/`, `docs/en/operator-ingress/`, `docs/en/planned-architecture/`, `docs/en/project-reference/`, `docs/en/scenario/`, `docs/en/selector/`, `docs/en/service-contract/`, `docs/en/archive/`, `CHANGELOGS/` | Host project | **No** |

Rationale: normative rules, protocol definitions, and deterministic tooling
evolve centrally. Project identity (purpose, scenarios, architecture roadmap)
is owned by the host and must survive framework updates untouched.

---

## 3. Build Stage

Command (from Council repository root):

```bash
bash dist/build.sh [VERSION]
```

Produces `dist/out/council-dist-<VERSION>.tar.gz`.

The builder:
1. Copies core paths verbatim from the working tree.
2. Copies template paths.
3. Generates `core-manifest.txt` — a flat list of every file under `core/`,
   relative to `core/`. This manifest is the sole authority for what `update.sh`
   may overwrite.
4. Embeds `install.sh` and `update.sh`.

---

## 4. Installation

### 4.1 New Project (`init`)

```bash
tar xzf council-dist-X.Y.Z.tar.gz
cd council-dist
bash install.sh --target ../my-project \
                --mode init \
                --project-name "my-project"
```

Effects:
- `git init` if target is not already a repository.
- Core files copied into target root (destructive: overwrites any existing
  file of the same name).
- Template files copied only if absent.
- Template personalization: `{{PROJECT_NAME}}` substituted; `.template`
  extensions stripped.
- `.council/` metadata directory created with `version.lock`,
  `core-manifest.txt`, and `update.sh`.
- `tools/install-hooks.sh` executed to set `core.hooksPath`.

### 4.2 Existing Project (`overlay`)

```bash
cd my-existing-project
bash /path/to/council-dist/install.sh --target . \
                                      --mode overlay \
                                      --project-name "existing"
```

Effects:
- Core directories are **merged** into existing tree, not deleted.
  Example: if target already has `docs/README.md`, core's `docs/en/...`
  is added alongside it; existing files survive.
- Templates are installed only if absent.
- All other steps identical to `init`.

---

## 5. Update Mechanism

After installation, each host project carries a self-updater:

```bash
cd my-project
bash .council/update.sh /path/to/council-dist-X.Y.Z.tar.gz
```

Algorithm:
1. Read `.council/version.lock` and `.council/core-manifest.txt`.
2. Unpack the new archive to a temporary directory.
3. Create `.council/backup-<timestamp>/` containing every file listed in
   the old core manifest.
4. Iterate the manifest: for each path, copy from `new/core/` to host root.
   If a path no longer exists in the new distribution, delete it from host.
5. Write new `version.lock`, `core-manifest.txt`, and refresh `update.sh`.
6. Print restore instructions (`cp -R .council/backup-.../* .`).

Safety invariants:
- **Never touches templates.** `AGENTS.md`, `docs/en/project-concept/`,
  host changelogs, and all other template paths are outside updater scope.
- **Atomic by backup.** Every overwritten file exists in the timestamped
  backup directory before any write.
- **Idempotent.** Re-running the same version is a no-op (unless `--force`).

---

## 6. Dependencies & Environment

| Dependency | Check | Action on missing |
|------------|-------|-----------------|
| Python 3.11+ | `python3 --version` | Warn; do not install automatically |
| PyYAML | `python3 -c "import yaml"` | Warn with `pip install pyyaml` hint |
| Git | `command -v git` | Warn; skip hook installation |

Subagent environment: the installer does **not** register skills or invoke
MCP tools. Setup instructions for the host's AI environment are printed in
post-install messages and reside in `AGENTS.md`.

---

## 7. Translation Engine

`vendor/techdoc-translator/` is included in core and updated centrally.

**Opt-out behavior:** the installer always copies the engine. It is harmless
without configuration — no API calls are made unless the operator explicitly
creates `vendor/techdoc-translator/.env` from the provided `.env.example`.

Post-install message explicitly reminds:
```text
Translation engine is included. To enable EN→RU translation:
  cd vendor/techdoc-translator
  cp .env.example .env
  # edit .env with your API endpoint / key
```

---

## 8. Integration with Documenter

The distribution system is an **implementation file** (per `AGENTS.md` §1.6)
and operates outside Documenter scope. However, the documents it distributes
(`docs/en/...`) are manifest-tracked project documents.

When a host project edits its own `docs/en/project-concept/index.md`, the
standard Documenter workflow applies: Documentation Worker skill,
`tools/check_all.py` audit, operator `approve`, single-commit bundling.

---

## 9. Future Extensions (non-blocking)

| Extension | Trigger | Approximate effort |
|-----------|---------|------------------|
| GitHub Template Repository | Operator decision | Low: mirror `templates/` into a template repo |
| Cookiecutter variant | User demand for customization | Medium: interactive questions, filtered roles |
| Version pinning in `defaults/` | Multiple Council versions in use | Low: add `council.version` to `defaults/policy.yaml` |
| Delta-update (rsync-style) | Archive size grows | Medium: manifest + checksum based patch |

---

## 10. Acceptance Criteria

- [ ] `bash dist/build.sh` produces a valid tar.gz.
- [ ] `install.sh --mode init` creates a runnable Council project.
- [ ] `install.sh --mode overlay` merges into existing repo without deleting
      existing files.
- [ ] `update.sh` upgrades core files and leaves templates untouched.
- [ ] Backup directory is created before any overwrite.
- [ ] Missing dependencies produce warnings, not fatal errors.
- [ ] Post-install messages guide the operator through next steps.
