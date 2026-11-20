# Documentation Rules
id: documentation-rules
Version: 0.2.1
Status: active
Abstraction: protocol
has_translation: docs/ru/documentation-rules/index-RU.md
changelog-path: CHANGELOGS/documentation-rules.changes.md

This document is the normative home of all documentation rules formerly held in `AGENTS.md` §§2–8. `AGENTS.md` is a thin router that points here; agents editing documentation load this file (via the Documentation Worker skill, `/.agents/skills/documentation/SKILL.md`). It is not part of the framework itself — it governs the *documentation process* only. Do not confuse it with `docs/project-concept/index.md`, which describes Council. Section numbering is preserved from the former `AGENTS.md` §§2–8 so that existing `§x.y` references remain recognizable.

---

## 2. Documentation Organization

### 2.1 On-Disk Layout

Documents are stored under the `docs/` directory in a dual-language structure: English originals live under `docs/en/<id>/`, Russian translations (when present) live under `docs/ru/<id>/`, with identical directory nesting in both trees. The primary document is `index.md` inside the English folder; a Russian translation, if present, is `index-RU.md` in the mirrored path under `docs/ru/`. A changelog file `CHANGELOGS/<id>.changes.md` stores version history separately from content (changelogs remain at repository root as operational artifacts).

Examples: `docs/en/protocol-core/index.md` (English source), `docs/ru/protocol-core/index-RU.md` (Russian translation), `docs/en/glossary/index.md`. Documents at the repository root — such as `AGENTS.md` and `docs-manifest.yaml` — serve as operational rules and the manifest index itself.

New documents are created by making a new folder under `docs/en/<id>/` and an `index.md`; the manifest must be updated simultaneously with both the English path and the RU path (if a translation exists).

Multi-document exceptions: The following pre-existing folders contain additional documents beyond `index.md`. Their non-primary file paths are recorded in the manifest explicitly and do not set a precedent for new documents: `documenter-service/*` (configuration-guide, policy-reference, remains at root as operational file), `docs/en/planned-architecture/*` (layer-0, layer-1, layer-2, decisions/index).

### 2.2 AI View (Manifest)

The **manifest** file (`docs-manifest.yaml` or equivalent index) is a **generated index**: frontmatter is the truth; the manifest is its printout. The sole writer of the manifest is the generator (`tools/gen_manifest.py`, Stage A); until Stage A lands, the Documentation Worker skill is the sole writer. Hand-editing `docs-manifest.yaml` is prohibited; fixing a wrong manifest means fixing document frontmatter and regenerating. Manifest `version` fields are derivative of document frontmatter; parity is enforced by regenerate-and-diff: regenerate and compare against the on-disk manifest. Agents MUST NOT scan the filesystem blindly. The manifest lists every document with: file path (pointing to `index.md` under `docs/en/`), title, version, status (active / draft / deprecated / archive), abstraction level, and optionally `has_translation` to indicate a Russian variant exists. The manifest does **not** include separate entries for Russian translations — they are tracked inline via the `has_translation` field, which contains the relative path from the manifest location to the Russian file (e.g., `docs/ru/glossary/index-RU.md`). Each document entry also omits the `language` field; English is implied by presence in the manifest. For content authority when documents conflict, see the Content Precedence rules in `service-contract/index.md`. The per-field provenance table for manifest fields is normative in `documenter-service/configuration-guide.md`, §Manifest Field Provenance.

### 2.3 Relationship Rules

- Documents reference others by canonical identifier (filename without extension).
- Cross-references use stable anchors (headings), not line numbers.
- Creating a new document requires updating the manifest and cross-references in relevant existing documents.

### 2.4 Operational Fallback

When the code-based Moderator is not yet implemented, the file `fallback/index.md` (operational file at repository root, frozen per `AGENTS.md` §1.5) defines the substitute procedure using named subagents launched through this agent harness. It covers role assignment, output structure, phase sequence, and conflict aggregation rules. Refer to it whenever executing a Council session without tooling support.

Session workspace files produced during fallback-mode sessions (`task-brief`, reviews, consensus docs, discussion transcripts) reside in `sessions/<id>/` and are outside the scope of Documenter; cleanup and archival are the operator's responsibility (see `fallback/index.md`, §Session workspace convention).

### 2.5 Changelog Storage

Changelog files store version history separately from document content in `CHANGELOGS/<id>.changes.md`. Each document's header contains a single reference line pointing to its changelog file (`changelog-path: CHANGELOGS/<id>.changes.md`). Agents read the changelog on-demand when editing a document; they append new entries to the appropriate changelog file rather than embedding CHANGES blocks in document bodies.

### 2.6 Archive Layout

Superseded documents that must remain readable for decision history live under `docs/en/archive/<id>/` (Russian mirrors under `docs/ru/archive/<id>/`), with `Status: archive` in their frontmatter. The archive root carries a guard file (`docs/en/archive/index.md`) stating that archived content is history only, never authority, and must not be deleted. Archived documents stay manifest-tracked and follow the naming conventions of §7.1; they are exempt from content-compliance audit (the audit engine filters the archive path prefix — see `documenter-service/index.md`, §Archive and §Audit tool) and from scheduled translation duty: a stale RU mirror inside an archive is expected, not a defect. Moving a live document into the archive is a semantic change surfaced on the Approval Card's `Archive:` line.

---

## 3. Language Policy

### 3.1 Primary Language

All project documentation is authored in **technical English**. English is the authoritative version — the source of truth.

### 3.2 Russian Translations

Russian variants live under `docs/ru/<id>/index-RU.md` (mirroring the English structure under `docs/en/`). They are provided exclusively for user convenience. They are secondary/derivative copies and **not** machine-readable sources. The manifest tracks Russian availability via the `has_translation` field, which contains the full relative path from the manifest location to the Russian file (e.g., `docs/ru/glossary/index-RU.md`). No separate manifest entry exists for a Russian file.

### 3.3 Translation Workflow

When modifying an English document: apply the change to `docs/en/<id>/index.md` first → look up the corresponding RU path from the manifest `has_translation` field → perform a fast version check (compare section counts, heading structures, paragraph positions) → if structural mismatch detected, translate the changed portions into Russian and update the Russian file at `docs/ru/<id>/index-RU.md` → append a brief log entry documenting the action taken (section updated, translation aligned, or verified consistent).

Translation does not apply to code, configuration, or non-document artifacts.

**Current phase exception — RU synchronization conditionally lifted (ADR-012).** Automatic Russian synchronization is permitted only as a **post-Approve action**: after step (5) Approve of §5.2 confirms a changeset covering the English edit, the Documentation Worker may translate and write `index-RU.md` at the manifest `has_translation` path automatically, provided every Phase 4 write-gate passes (translation completeness, line parity, EN-identity scan, glossary compliance). Any gate failure blocks the write and escalates to operator review of the full translation. A document may opt out via `no_auto_translation: true` in its frontmatter; opted-out documents fall back to report-only drift audit. When the local translation backend is unavailable, cloud fallback requires the operator's per-run explicit consent (ADR-012). This rule replaces the previous full suspension of 2026-11-12.

---

## 4. Glossary Management

### 4.1 Structure

The glossary lives in `docs/en/glossary/index.md`. Each term entry includes: term name (canonical form), definition (English), Russian equivalent (if applicable), and optional category tag (e.g., `[roles]`, `[protocol]`).

### 4.2 Agent Responsibilities

Read before use (verbatim), create when a multi-used term is absent, update when meaning evolves significantly (not merely rephrased), and verify all domain terms exist before producing output (define inline or add to glossary otherwise).

### 4.3 Machine-Readable Variant

The English-only portion of `docs/glossary/index.md` is the primary (machine-readable) version. Russian equivalents are annotations. Agents operate on English definitions exclusively.

---

## 5. Workflow

### 5.1 Responsibility Split

Document structure, formatting, content drafting, manifest updates, cross-references, and version bumping → **Documentation Worker skill** (/.agents/skills/documentation/SKILL.md). Russian translation alignment → Documentation Worker per its skill definition. Strategic decisions, ambiguity resolution, scope approval, and change-plan confirmation → **Primary agent**. All mechanical write operations go through the skill; reading files (manifest, documents, glossary, changelogs) is done directly by the primary agent. The Agent MUST NOT modify any document file, manifest, or changelog until after step (5) Approve is confirmed by the human operator. This rule has no exceptions — even typo fixes require explicit go-ahead after the propose step. All mechanical operations use the Documentation Worker skill; no other automation tools are operational at this stage. Parameterized write-scripts under `tools/` (when shipped) are dispatched exclusively by the Documentation Worker skill and only after step (5) Approve; scripts provide atomicity, not authority. Changeset write order is document content → changelog → manifest (manifest last).

### 5.2 Document Processing Flow

Every task proceeds through three phases controlled by the primary agent. Detailed steps are handled by the Documentation Worker skill per its Work Request Contract (/.agents/skills/documentation/SKILL.md).

**Phase 1 — Understand:** The primary agent reads manifest, target documents, related docs, and glossary. The skill executes UNDERSTAND/ANALYZE report.
**Phase 2 — Align:** The primary agent clarifies ambiguities with the human (see §6), proposes changes based on the skill's PROPOSE output, waits for explicit approval at step (5).
**Phase 3 — Execute:** The primary agent delegates execution to the skill (trust level determined by change scope). The skill runs EXECUTE/VERIFY, produces diff + compliance report. Primary agent reviews results, then REPORTs to human.

### 5.3 Concurrent Work

Agents working on different documents must coordinate through the manifest. No two agents modify the same file concurrently unless explicitly agreed upon. The Documentation Worker skill handles all concurrent-write protection (TOCTOU detection) per its safety protocol (/.agents/skills/documentation/SKILL.md).

### 5.4 Subagent Delegation Budget

Before launching a subagent, the primary agent MUST estimate the task's expected size (rough token budget). If the estimate exceeds 40,000 tokens, the primary agent MUST consider splitting the work into smaller subtasks and delegate each separately rather than launching one oversized run. The estimate is recorded in the delegation brief. This keeps subagent outputs reviewable and prevents context exhaustion mid-task.

**Concurrency limit.** The number of subagents the primary agent may run concurrently depends on the subagent model configured in `.opencode/opencode.jsonc` (see the comment block there for switching): local model — at most **1** concurrent subagent (queue sequentially); cloud model — at most **2**. The limit is behavioral (executed by the primary agent); the config carries no mechanical cap. Subtasks must be sequenced to respect it.

---

## 6. Ambiguity Handling

An ambiguity exists whenever more than one reasonable approach exists with no prior guidance — including conflicting term usage across documents, unstructured decisions, domain questions requiring factual input beyond pattern-matching, or changes affecting other documents. Describe clearly, propose 2–3 options with consequences and a recommendation, wait for human selection. If the human does not respond and work blocks progress, record unresolved items as open questions rather than guessing.

---

## 7. File Conventions

### 7.1 Naming and Layout

Use kebab-case for folder names under `docs/en/` and `docs/ru/`; primary document is `index.md`; Russian translation is `index-RU.md` in the mirrored path under `docs/ru/`. Draft files carry `.draft` suffix temporarily. Changelog files use format `CHANGELOGS/<id>.changes.md`.

### 7.2 Metadata & Format Conventions

Metadata headers follow YAML-style format; English is implied by presence in the manifest, no `Language` field. Required frontmatter fields: `id`, `Version`, `Status`, `Abstraction`, `changelog-path`; optional: `has_translation`, `references`, `allow_non_index_paths`. The `Last Modified` field is removed from authored document headers (derived from git at display time when needed). Documents reference others by canonical identifier (filename without extension). Cross-references use stable anchors (headings), not line numbers. Creating a new document requires updating the manifest and cross-references in relevant existing documents.

### 7.3 Document Size Limits

Each document must not exceed **200 lines** of content (excluding metadata and changelog entries). When exceeded, halt and present `Split` (divide into sub-documents with stable identifiers and cross-references) or `Condense` (remove detail from lower-priority sections) options to the human operator. Escalation for oversized documents is handled by the Documentation Worker skill (/.agents/skills/documentation/SKILL.md).

### 7.4 Abstraction Levels

Mixing broad concepts with concrete formats/signatures within one document is prohibited. Abstraction levels: `Conceptual` (principles, goals, rationale), `Protocol` (procedures, phases, decision logic), `Format` (field definitions, schemas, signatures), `Reference` (glossaries, checklists, config examples). Multi-level drafts require splitting by level. Promote `Abstraction:` field to permanent once approved.

### 7.5 Versioning Convention

Bump patch (X.Y.**Z**) for typos/formatting, minor (X.**Y**.Z) for content additions or structural changes, major (**X**.Y.Z) for foundational rewrites.

### 7.6 Changelog Storage

Document version history in the changelog file using format `<!-- CHANGES vX.Y.Z: description of change. -->`. Changelog entries live separately from document bodies — each document references its changelog via `changelog-path:` in metadata.

---

## 8. Compliance Verification

At the end of any session that modifies documentation files, perform a final compliance check: manifest up-to-date, Russian alignment checked per §3.3, all terms exist in glossary, all cross-references resolve, changelog entries appended. While the §3.3 suspension is in effect, Russian alignment is report-only: record drift when an RU file exists, but do not update it. The Documentation Worker skill runs these checks automatically per its compliance checklist (/.agents/skills/documentation/SKILL.md); the primary agent reviews the result before reporting completion. Run `tools/check_all` (deterministic rule suite) as part of the end-of-session compliance check. The audit rules "glossary terms" and "abstraction consistency" (`mvp-interfaces.md` rules 3 and 5) remain skill/AI-reserved; the tool MUST NOT claim to implement "audit rules 1–6".

---

## Cross-References

- `AGENTS.md` — thin router: agent context, write-rule pointer, project stage, documentation/tooling separation guards
- `docs-manifest.yaml` — generated index, single source of truth for document layout
- `docs/en/glossary/index.md` — canonical term definitions
- `.agents/skills/documentation/SKILL.md` — Documentation Worker skill (sole write executor)
- `fallback/index.md` — fallback-mode operator workflow
- `service-contract/index.md` — Content Precedence rules
