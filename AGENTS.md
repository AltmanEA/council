# Documentation Agent Instructions (AGENTS.md)
Version: 0.3.0
Status: active
Last Modified: 2026-11-04
changelog-path: CHANGELOGS/agents.changes.md

This file defines how AI agents interact with, maintain, and evolve the project's documentation. It is not part of the framework itself — it governs the *documentation process* only. Do not confuse this file with `project-concept/index.md`, which describes Council.

---

## 1. Purpose

`AGENTS.md` serves as the operational guide for AI agents responsible for creating, editing, and maintaining all project documentation artifacts. Its goals:

- Establish clear rules for working with multi-language documentation.
- Define separation between on-disk layout and AI-consumable view.
- Assign responsibility boundaries between agent and human operator.
- Provide procedures for handling ambiguity, versioning, and glossary management.

All agents reading this file must comply with every rule defined here. Non-compliance should be reported as an open question in the consensus document.

---

## 2. Documentation Organization

### 2.1 On-Disk Layout

Documents are stored in individual folders named after their manifest identifier. The primary document is `index.md` inside that folder; a Russian translation, if present, is `index-RU.md` in the same folder. A changelog file `CHANGELOGS/<id>.changes.md` stores version history separately from content. Examples: `protocol-core/index.md`, `project-concept/index-RU.md`, `glossary/index.md`. Documents at the repository root — such as `AGENTS.md` and `docs-manifest.yaml` — serve as operational rules and the manifest index itself. New documents are created by making a new folder and an `index.md`; the manifest must be updated simultaneously.

### 2.2 AI View (Manifest)

A **manifest** file (`docs-manifest.yaml` or equivalent index) is the single source of truth. Agents MUST NOT scan the filesystem blindly. The manifest lists every document with: file path (pointing to `index.md`), title, version, status (active / draft / deprecated), abstraction level, and optionally `has_translation` to indicate a Russian variant exists. The manifest does **not** include separate entries for Russian translations — they are tracked inline via the `has_translation` field. Each document entry also omits the `language` field; English is implied by presence in the manifest. If no manifest exists yet, the agent creates one on first interaction and updates it after every add/rename/delete operation.

### 2.3 Relationship Rules

- Documents reference others by canonical identifier (filename without extension).
- Cross-references use stable anchors (headings), not line numbers.
- Creating a new document requires updating the manifest and cross-references in relevant existing documents.

### 2.4 Operational Fallback

When the code-based Moderator is not yet implemented, the file `fallback/fallback-mode.md` defines the substitute procedure using named subagents launched through this agent harness. It covers role assignment, output structure, phase sequence, and conflict aggregation rules. Refer to it whenever executing a Council session without tooling support.

---

## 2.5 Changelog Storage

Version history is stored separately from document content in `CHANGELOGS/<id>.changes.md`. Each document's header contains a single reference line pointing to its changelog file (`changelog-path: CHANGELOGS/<id>.changes.md`). Agents read the changelog on-demand when editing a document; they append new entries to the appropriate changelog file rather than embedding CHANGES blocks in document bodies.

---

## 3. Language Policy

### 3.1 Primary Language

All project documentation is authored in **technical English**. English is the authoritative version — the source of truth.

### 3.2 Russian Translations

Russian variants (`index-RU.md` inside the same folder as the English source) are provided exclusively for user convenience. They are secondary/derivative copies and **not** machine-readable sources. The manifest tracks Russian availability via the `has_translation` field — no separate manifest entry exists for a Russian file.

### 3.3 Translation Workflow

When modifying an English document: apply the change to `index.md` first → locate the corresponding `index-RU.md` in the same folder → perform a fast version check (compare section counts, heading structures, paragraph positions) → if structural mismatch detected, translate the changed portions into Russian and update the Russian file → append a brief log entry documenting the action taken (section updated, translation aligned, or verified consistent).

Translation does not apply to code, configuration, or non-document artifacts.

---

## 4. Glossary Management

### 4.1 Structure

The glossary lives in `glossary/index.md`. Each term entry includes: term name (canonical form), definition (English), Russian equivalent (if applicable), and optional category tag (e.g., `[roles]`, `[protocol]`).

### 4.2 Agent Responsibilities

Read before use (verbatim), create when a multi-used term is absent, update when meaning evolves significantly (not merely rephrased), and verify all domain terms exist before producing output (define inline or add to glossary otherwise).

### 4.3 Machine-Readable Variant

The English-only portion of `glossary/index.md` is the primary (machine-readable) version. Russian equivalents are annotations. Agents operate on English definitions exclusively.

---

## 5. Workflow

### 5.1 Responsibility Split

Document structure, formatting, content drafting, RU translation alignment, cross-references, manifest updates, and version bumping → **Agent**. Strategic/content decisions, ambiguity resolution, scope approval, and change-plan confirmation → **Human**. The Agent MUST NOT modify any document file, manifest, or changelog until after step (5) Approve is confirmed by the human operator. This rule has no exceptions — even typo fixes require explicit go-ahead after the propose step.

### 5.2 Document Processing Flow

Every task proceeds through eight steps, organized into three phases. The Agent MUST NOT modify any document file, manifest, or changelog entry until after step (5) is confirmed by the human operator. This rule has no exceptions — even typo fixes require explicit go-ahead after the propose step.

**Phase 1 — Understand:** (1) **Understand** — read the manifest to locate the target document(s), identify related documents, read existing content of all affected files (`index.md` for English, `index-RU.md` if present). (2) **Analyze** — determine what needs to be created/modified/deleted; check `glossary/index.md` for undefined domain terms.

**Phase 2 — Align:** (3) **Clarify** — enumerate all ambiguities found during Understand/Analyze and present them to the user as questions with options (see §6 Resolution Procedure). Wait for answers. If no ambiguities exist, skip to step (4) anyway — the proposal itself serves as confirmation of scope. (4) **Propose** — produce a concrete change plan listing: every file that will be modified, which sections/headings within each file will change, whether RU translation needs updating (§3.3), whether new changelog entries are needed, and whether manifest cross-references or the manifest itself must be updated. Present this plan to the user for review. (5) **Approve** — wait for explicit user confirmation ("go" / approve / proceed). DO NOT write any changes until this step yields positive confirmation.

**Phase 3 — Execute:** (6) **Modify** — apply the approved plan sequentially: edit each `index.md`, update matching `index-RU.md` if applicable (§3.3), append changelog entries to `CHANGELOGS/<id>.changes.md`, bump version per §7.5, update manifest, update cross-references. (7) **Verify** — run final compliance check (§8): manifest up-to-date, Russian alignment checked, all terms exist in glossary, all cross-references resolve, changelog entries appended. Fix failures before proceeding. (8) **Report** — inform the user of completed changes, summarizing modified files, new versions, and changelog references.

### 5.3 Concurrent Work

Agents working on different documents must coordinate through the manifest. No two agents modify the same file concurrently unless explicitly agreed upon.

---

## 6. Ambiguity Handling

### 6.1 Trigger Conditions

An ambiguity exists whenever more than one reasonable approach exists with no prior guidance — including conflicting term usage across documents, unstructured decisions (heading levels, ordering), domain questions requiring factual input beyond pattern-matching, or additions/deletions affecting other documents.

### 6.2 Resolution Procedure

Describe the ambiguity clearly, propose 2–3 concrete options with consequences and a recommendation, wait for human selection. The agent MUST NOT default to its own preference without explicit instruction.

### 6.3 Escalation Within Documentation

If the human fails to respond within the session context and pending work blocks progress, record the unresolved item as an open question in the nearest consensus document rather than guessing.

---

## 7. File Conventions

### 7.1 Naming

Use kebab-case for folder names (`protocol-core/`). The primary document inside is `index.md`. Russian translation: `index-RU.md` in the same folder. Draft files carry `.draft` suffix temporarily during review — remove it upon approval. Changelog files use format `CHANGELOGS/<id>.changes.md`.

### 7.2 Metadata Headers

Each document begins with a YAML-style comment block:

```
# Title
Version: X.Y.Z
Status: active | draft | deprecated
Last Modified: <date>
Source: <english-path>          # Russian files only — path to index.md
changelog-path: CHANGELOGS/<id>.changes.md
Abstraction: conceptual | protocol | format | reference   # during drafting
```

The `Language` field has been removed from metadata. English is implied by presence in the manifest; Russian files do not carry a language tag — they have a `Source:` field pointing to their English parent.

### 7.3 Line Count Limit

Each document must not exceed **200 lines** of content (excluding metadata headers and changelog entries). When a draft exceeds this threshold, the agent MUST halt and present options to the human operator: (1) **Split** — divide into logical sub-documents with stable identifiers and cross-references; (2) **Condense** — remove detail from lower-priority sections while preserving core substance. The agent MUST NOT silently truncate, omit, or skip content. The manifest must reflect the resulting file layout once resolved.

### 7.4 Consistent Abstraction Level

Mixing broad concepts with concrete formats/signatures within one document is prohibited. Abstraction levels: **Conceptual** (principles, goals, rationale), **Protocol** (procedures, phases, decision logic), **Format** (field definitions, schemas, signatures), **Reference** (glossaries, checklists, config examples). Multi-level drafts require splitting by level (§7.3). Promote `Abstraction:` field to permanent once approved.

### 7.5 Versioning

Bump patch (X.Y.**Z**) for typos/formatting, minor (X.**Y**.Z) for content additions or structural changes, major (**X**.Y.Z) for foundational rewrites. Document version history in the changelog file (`CHANGELOGS/<id>.changes.md`) when substantive changes occur — entries are appended as `<!-- CHANGES v0.3.0: ... -->` lines.

### 7.6 Changelog Storage

Changelog entries live in `CHANGELOGS/<id>.changes.md`, not inside document bodies. When making an edit, the agent appends a new entry at the top of the relevant changelog file using the format: `<!-- CHANGES vX.Y.Z: description of change. -->`. The document body only contains a single reference line: `changelog-path: CHANGELOGS/<id>.changes.md`. During document reads, agents may optionally load the changelog by resolving this reference path.

---

## 8. Compliance Verification

At the end of any session that modifies documentation files, perform a final compliance check: manifest up-to-date, Russian checks performed per §3.3, all terms exist in the glossary, all cross-references resolve, changelog entries appended. Fix failures before considering the session complete.
