# Task Brief — Council Session: Isolated Installation Layout for Council Distribution

Session ID: sess-dist-isolated-install-2026-11-22
Mode: fallback (fallback/index.md)
Date: 2026-11-22

## Task description

**Operator goal.** The current installer (`dist/install.sh`) scatters Council framework files across the host project root: `docs/en/documentation-rules/`, `docs/en/glossary/`, `docs/en/protocol-core/`, `docs/en/documenter-service/`, `docs/en/translation-project/`, `tools/`, `CHANGELOGS/`, `fallback/`, `vendor/`, `defaults/`, `AGENTS.md`, `docs-manifest.yaml`. The operator's requirement: **the Council installation must not intersect with the host project's file tree**. The operator proposes: everything Council-owned lives under a service folder (`.council/`), host project keeps its own `docs/`, `tools/`, `CHANGELOGS/`, etc., with the minimal necessary wiring (links, AGENTS.md pointers) at the host root.

**Current state (baseline).**
- Distribution: `dist/build.sh` → `council-dist-<VERSION>.tar.gz` containing `install.sh`, `update.sh`, `core-manifest.txt`, `core/` (tools, .agents, vendor, defaults, docs/en/<5 normative docs>, CHANGELOGS seeds, fallback), `templates/` (AGENTS.md.template, docs/en/project-concept, project CHANGELOG seed).
- Install: core items are copied **flat into the host root** (overlay mode merges, never overwrites); `.council/` today holds only `version.lock`, `core-manifest.txt`, `update.sh`, optional telemetry.
- Update: `update.sh` iterates union of host `core-manifest.txt` and new archive manifest; entries absent from new release are removed; timestamped backup in `.council/backup-<timestamp>/`.
- Tools (`tools/check_all.py`, `gen_manifest.py`, `docmeta.py`) assume a single `docs/` tree and a single `docs-manifest.yaml` at repo root; they are path-coupled to `docs/en/<id>/` and frontmatter conventions (`changelog-path: CHANGELOGS/...`, `has_translation`).
- OpenCode harness constraints: `.agents/skills/` and `.opencode/agents/` are auto-discovered at project root; `AGENTS.md` is read from project root. These MUST stay discoverable.
- Prior decisions: Variant-B composition (consensus `sess-dist-content-review` 2026-11-22) — no RU mirrors, no v0.x specs; core/host ownership is expressed via `core-manifest.txt` lists, not directories.

**Design question.** How best to implement the operator's isolated-installation approach so that:
1. No Council file lands inside host-owned directories (host `docs/`, `tools/`, `CHANGELOGS/` untouched by Council);
2. Framework self-consistency holds: audit (`check_all.py`), manifest generation, translation contract, session/Documenter flows all keep working;
3. Updates/removals stay atomic and reversible (OP-3: commit audit + revert);
4. Agent discoverability is preserved (skills, AGENTS.md, selector) without heavy symlink chains;
5. Migration from the current flat layout (v0.1.0 hosts) is possible or explicitly accepted as break.

Candidate strategies (roles may propose others):
- **S1 — Full relocation:** everything Council (`tools/`, `docs/en/*` normative, `CHANGELOGS/` core seeds, `fallback/`, `vendor/`, `defaults/`, `docs-manifest.yaml` for core) moves under `.council/` (e.g. `.council/council/...`). Host root gets only `.council/`, plus minimal wiring. Tools re-pathed to two roots or run with cwd inside `.council/`.
- **S2 — Council owns a `docs/en/_council/` (or `docs/council/`) namespace:** docs stay in host `docs/` tree under a reserved subtree; tools/CHANGELOGs move to `.council/`. Compromise: doc links natural, but intersection with host `docs/` remains.
- **S3 — Dual-root with generated wiring:** Council fully under `.council/`; installer generates thin root-level stubs (`docs/council/*` index stubs or symlinks, root `AGENTS.md` includes `.council/AGENTS.md` via pointer section); tools gain a `--root`/config for core-docs root; single merged manifest lists both roots with `origin: core|host` field.
- Roles must evaluate symlink-based variants critically (git portability, ripgrep/cp semantics, Windows).

**Explicit constraints.**
- OP-2 maximum simplicity (post 2026-11-19 reconstruction): no new services, no policy engines; shell + python tools only.
- OP-1: operator approves changesets in chat; do not propose gating infrastructure.
- Prose contracts (`dist/README.md`, `RUNBOOK.md`, skill docs, `tools/README.md`) must be updated in the same changeset (AGENTS.md §1.7).
- The host project may itself be a Council-repo-like project with its own `docs/`, manifest, glossary extensions. Host glossary extension is an accepted need.
- Backward compatibility for existing v0.1.0 hosts: propose migrate-in-place, or clean-break-with-warning; argue the choice.

## Canonical subject list

- SUBJ-001: Physical layout of installed Council files (what lands under `.council/`, what must stay at root)
- SUBJ-002: Documentation roots & manifest strategy (single manifest vs dual manifest vs per-root manifest with origin field; how gen_manifest/check_all resolve two roots)
- SUBJ-003: Cross-references & frontmatter contracts (core↔host doc links, `changelog-path`, glossary extension, translation provenance)
- SUBJ-004: Update/removal/rollback mechanics under new layout (core-manifest semantics, backup, atomicity, orphan cleanup)
- SUBJ-005: Overlay collision surface (name clashes: `docs/`, `AGENTS.md`, `tools/`, `.gitignore`, hooks; init vs overlay modes)
- SUBJ-006: Agent/harness discoverability (`.agents/skills/`, `.opencode/agents/`, root `AGENTS.md` wiring; symlink vs stub vs include)
- SUBJ-007: Migration path from flat v0.1.0 layout (migrate / parallel support / clean break)
- SUBJ-008: Tooling changes required (path constants in tools/, cwd conventions, installer/updater scripts) and their test coverage (`dist/test-dry-run.sh`, tests/)

## Required output structure (per role)

Produce a single review document with sections: Summary Position; Key Findings (tag `- [severity] ... subject SUBJ-00N`, critical findings must name a concrete failure mode); Recommendations; Open Questions; Status (agree / concerns / blocked-in-scope / blocked-escalation); Escalation Reason (if blocked).

## Context to read

- `dist/README.md`, `dist/RUNBOOK.md`, `dist/install.sh`, `dist/update.sh`, `dist/build.sh`, `dist/test-dry-run.sh`
- `AGENTS.md` (§1.5–1.7, §2), `fallback/index.md`
- `tools/README.md` (skim), `tools/gen_manifest.py` and `tools/check_all.py` (path assumptions only)
- Prior consensus: `sessions/sess-dist-content-review/consensus-doc.md`

## Output limits

Each review ≤ 150 lines. Reference subjects exclusively by ID. Propose at most one alternative architecture beyond the listed S1–S3.
