# Documentation Agent Instructions (AGENTS.md)
Version: 0.1.1
Status: active
Last Modified: 2026-11-04
Language: en
<!-- CHANGES v0.3.1: Replaced "the collaborative design framework" with "Council" as project name reference. -->
<!-- CHANGES v0.1.1: Added §2.4 Operational Fallback referencing fallback-mode.md for subagent-based Council sessions. -->

This file defines how AI agents interact with, maintain, and evolve the project's documentation. It is not part of the framework itself — it governs the *documentation process* only. Do not confuse this file with `PROJECT-CONCEPT.md`, which describes Council.

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

Documents are stored as individual Markdown files at the repository root or within subdirectories. Examples: `PROJECT-CONCEPT.md`, `GLOSSARY.md`. New documents are created as needed; content structure follows domain context.

### 2.2 AI View (Manifest)

A **manifest** file (`docs-manifest.yaml` or equivalent index) is the single source of truth. Agents MUST NOT scan the filesystem blindly. The manifest lists every document with: file path, title, version, last modified date, language variant, and status (active / draft / deprecated). If no manifest exists yet, the agent creates one on first interaction and updates it after every add/rename/delete operation.

### 2.3 Relationship Rules

- Documents reference others by canonical identifier (filename without extension).
- Cross-references use stable anchors (headings), not line numbers.
- Creating a new document requires updating the manifest and cross-references in relevant existing documents.

### 2.4 Operational Fallback

When the code-based Moderator is not yet implemented, the file `fallback-mode.md` defines the substitute procedure using named subagents launched through this agent harness. It covers role assignment, output structure, phase sequence, and conflict aggregation rules. Refer to it whenever executing a Council session without tooling support.

---

## 3. Language Policy

### 3.1 Primary Language

All project documentation is authored in **technical English**. English is the authoritative version — the source of truth.

### 3.2 Russian Translations

Russian variants (`<original>-RU.md`) are provided exclusively for user convenience. They are secondary/derivative copies and **not** machine-readable sources.

### 3.3 Translation Workflow

When modifying an English document: apply the change to English first → locate the corresponding `-RU.md` file → perform a fast version check (compare section counts, heading structures, paragraph positions) → if structural mismatch detected, translate the changed portions into Russian and update the Russian file → append a brief log entry documenting the action taken (section updated, translation aligned, or verified consistent).

Translation does not apply to code, configuration, or non-document artifacts.

---

## 4. Glossary Management

### 4.1 Structure

The glossary lives in `GLOSSARY.md`. Each term entry includes: term name (canonical form), definition (English), Russian equivalent (if applicable), and optional category tag (e.g., `[roles]`, `[protocol]`).

### 4.2 Agent Responsibilities

Read before use (verbatim), create when a multi-used term is absent, update when meaning evolves significantly (not merely rephrased), and verify all domain terms exist before producing output (define inline or add to glossary otherwise).

### 4.3 Machine-Readable Variant

The English-only portion of `GLOSSARY.md` is the primary (machine-readable) version. Russian equivalents are annotations. Agents operate on English definitions exclusively.

---

## 5. Workflow

### 5.1 Responsibility Split

Draft creation, formatting, structuring, boilerplate generation, structural reorganization, and fast EN↔RU version checks → **Agent**. Strategic/content decisions, scope approval, role/capability definition, and ambiguity resolution → **Human**.

### 5.2 Document Processing Flow

Every task proceeds through seven steps: (1) **Understand** — read manifest, identify targets and related materials, read existing content. (2) **Analyze** — determine what to create/modify/delete, check glossary for undefined terms. (3) **Draft** — produce English content consistently with existing documents. (4) **Flag Ambiguity** — halt and present options to human (see Section 6). (5) **Approve** — wait for confirmation if flagged, proceed directly if not. (6) **Finalize** — write final version, update manifest and cross-references, handle Russian translation (§3.3). (7) **Log** — record a one-line changelog summary at the top of affected documents.

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

Use kebab-case (`protocol-core.md`). Russian translations append `-RU` (`protocol-core-RU.md`). Draft files carry `.draft` suffix temporarily during review — remove it upon approval.

### 7.2 Metadata Headers

Each document begins with a YAML-style comment block:

```
# Title
Version: X.Y.Z
Status: active | draft | deprecated
Last Modified: <date>
Language: en | ru
Source: <english-filename>    # Russian files only
Synced: <date>                 # Russian files only
Abstraction: conceptual | protocol | format | reference   # during drafting
```

### 7.3 Line Count Limit

Each document must not exceed **200 lines** of content (excluding metadata headers and changelog entries). When a draft exceeds this threshold, the agent MUST halt and present options to the human operator: (1) **Split** — divide into logical sub-documents with stable identifiers and cross-references; (2) **Condense** — remove detail from lower-priority sections while preserving core substance. The agent MUST NOT silently truncate, omit, or skip content. The manifest must reflect the resulting file layout once resolved.

### 7.4 Consistent Abstraction Level

Mixing broad concepts with concrete formats/signatures within one document is prohibited. Abstraction levels: **Conceptual** (principles, goals, rationale), **Protocol** (procedures, phases, decision logic), **Format** (field definitions, schemas, signatures), **Reference** (glossaries, checklists, config examples). Multi-level drafts require splitting by level (§7.3). Promote `Abstraction:` field to permanent once approved.

### 7.5 Versioning

Bump patch (X.Y.**Z**) for typos/formatting, minor (X.**Y**.Z) for content additions or structural changes, major (**X**.Y.Z) for foundational rewrites. Document version history in the changelog header when substantive changes occur.

### 7.6 Changelog

Append a changelog entry at the top of affected documents for every substantive edit: `<!-- CHANGES v0.3.0: Added threat model section to escalation workflow, updated role status enumeration. -->`

---

## 8. Compliance Verification

At the end of any session that modifies documentation files, perform a final compliance check: manifest up-to-date, Russian checks performed per §3.3, all terms exist in the glossary, all cross-references resolve, changelog entries appended. Fix failures before considering the session complete.
