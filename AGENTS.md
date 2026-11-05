# Documentation Agent Instructions (AGENTS.md)
Version: 0.6.0
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

When the code-based Moderator is not yet implemented, the file `fallback/index.md` defines the substitute procedure using named subagents launched through this agent harness. It covers role assignment, output structure, phase sequence, and conflict aggregation rules. Refer to it whenever executing a Council session without tooling support.

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

Document structure, formatting, content drafting, manifest updates, cross-references, and version bumping → **Documentation Worker skill** (/.agents/skills/documentation/SKILL.md). Russian translation alignment → Documentation Worker per its skill definition. Strategic decisions, ambiguity resolution, scope approval, and change-plan confirmation → **Primary agent**. All mechanical write operations go through the skill; reading files (manifest, documents, glossary, changelogs) is done directly by the primary agent. The Agent MUST NOT modify any document file, manifest, or changelog until after step (5) Approve is confirmed by the human operator. This rule has no exceptions — even typo fixes require explicit go-ahead after the propose step.

### 5.2 Document Processing Flow

Every task proceeds through three phases controlled by the primary agent. Detailed steps are handled by the Documentation Worker skill per its Work Request Contract (/.agents/skills/documentation/SKILL.md).

**Phase 1 — Understand:** The primary agent reads manifest, target documents, related docs, and glossary. The skill executes UNDERSTAND/ANALYZE report.
**Phase 2 — Align:** The primary agent clarifies ambiguities with the human (see §6), proposes changes based on the skill's PROPOSE output, waits for explicit approval at step (5).
**Phase 3 — Execute:** The primary agent delegates execution to the skill (trust level determined by change scope). The skill runs EXECUTE/VERIFY, produces diff + compliance report. Primary agent reviews results, then REPORTs to human.

### 5.3 Concurrent Work

Agents working on different documents must coordinate through the manifest. No two agents modify the same file concurrently unless explicitly agreed upon. The Documentation Worker skill handles all concurrent-write protection (TOCTOU detection) per its safety protocol (/.agents/skills/documentation/SKILL.md).

---

## 6. Ambiguity Handling

An ambiguity exists whenever more than one reasonable approach exists with no prior guidance — including conflicting term usage across documents, unstructured decisions, domain questions requiring factual input beyond pattern-matching, or changes affecting other documents. Describe clearly, propose 2–3 options with consequences and a recommendation, wait for human selection. If the human does not respond and work blocks progress, record unresolved items as open questions rather than guessing.

---

## 7. File Conventions

Use kebab-case for folder names; primary document is `index.md`; Russian translation is `index-RU.md` in the same folder. Draft files carry `.draft` suffix temporarily. Metadata headers follow YAML-style format; English is implied by presence in the manifest, no `Language` field. Changelog files use format `CHANGELOGS/<id>.changes.md`.

Each document must not exceed **200 lines** of content (excluding metadata and changelog entries). When exceeded, halt and present **Split** (divide into sub-documents with stable identifiers and cross-references) or **Condense** (remove detail from lower-priority sections) options to the human operator. Escalation for oversized documents is handled by the Documentation Worker skill (/.agents/skills/documentation/SKILL.md).

Mixing broad concepts with concrete formats/signatures within one document is prohibited. Abstraction levels: **Conceptual** (principles, goals, rationale), **Protocol** (procedures, phases, decision logic), **Format** (field definitions, schemas, signatures), **Reference** (glossaries, checklists, config examples). Multi-level drafts require splitting by level. Promote `Abstraction:` field to permanent once approved.

Bump patch (X.Y.**Z**) for typos/formatting, minor (X.**Y**.Z) for content additions or structural changes, major (**X**.Y.Z) for foundational rewrites. Document version history in the changelog file using format `<!-- CHANGES vX.Y.Z: description of change. -->`. Changelog entries live separately from document bodies — each document references its changelog via `changelog-path:` in metadata.

---

## 8. Compliance Verification

At the end of any session that modifies documentation files, perform a final compliance check: manifest up-to-date, Russian alignment checked per §3.3 (including line parity, completeness, language leakage, glossary compliance, no drift when RU file exists), all terms exist in glossary, all cross-references resolve, changelog entries appended. The Documentation Worker skill runs these checks automatically per its compliance checklist (/.agents/skills/documentation/SKILL.md); the primary agent reviews the result before reporting completion.
