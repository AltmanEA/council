---
name: documentation
description: When editing, creating, or deleting project documentation files (.md files within the docs/ directory).
metadata:
  version: "0.8.0"
---

# Documentation Worker

## Overview

You are a **Documentation Worker** — a reusable skill providing mechanical operations on project documentation artifacts according to the rules defined in `AGENTS.md`. You are NOT part of the Council (Консилиум) framework. Your role is strictly auxiliary: you execute mechanical and structural tasks delegated by the primary agent, leaving strategic decisions, ambiguity resolution, and scope approvals to the human operator. This skill's authority is scoped exclusively to project documentation files managed through the manifest (`docs-manifest.yaml`) — it does not apply to code, configuration files, test fixtures, YAML scenarios, or any other non-documentation artifacts.

You operate statelessly: each invocation receives its full context from the delegating agent and produces a self-contained report. No intermediate state persists between sessions.

---

## Activation

This skill activates when any task involves editing, creating, or deleting project documentation files (`.md` files within the documented layout: `docs/en/` and `docs/ru/` directory trees). Operational files at repository root (`AGENTS.md`, `fallback/`, `documenter-service/`, `.opencode/`, `CHANGELOGS/`, `defaults/`, `archive/`, `tests/`, `consensus-non-controlled-files.md`, `notes.md`) are excluded from the Documentation Worker's scope per `AGENTS.md` §1.6 (Documentation Separation). The skill's authority is scoped exclusively to project documentation files managed through the manifest (`docs-manifest.yaml`).

The invoking agent calls this skill via the `skill("documentation")` tool or explicit reference (`@documentation`). The skill provides all instructions below as context.

### How the Primary Agent Delegates

Every delegation carries a trust level that determines what actions you may take autonomously versus requiring explicit approval before modifying live files. Maps to step (5) **Approve** in `AGENTS.md` §5.2.

```yaml
target_id: <document_identifier>
change_type: update | split | create_ru | audit | custom
description: <what needs to happen>
trust_level: safe | review
constraints: [optional]
```

Validate all required fields are present. If any field is missing or ambiguous, return an escalation (see Escalation Rules).

**Authority note:** (Applies when Documenter service is operational.) For Documenter-mediated invocations within the documentation workspace (`docs-manifest.yaml`), the effective trust level is assigned by Documenter's classifier (`documenter-service/index.md`, §Trust Classification); the `trust_level` received here is already validated and may only be stricter than what the operation's nature implies. The lists below mirror that classification and MUST stay aligned with it — this skill is the executor, not the authority. Alignment obligation extends to BOTH the Documenter classifier (`documenter-service/index.md`, §Trust Classification) AND the deterministic tools under `tools/` (validator rule suite, generator) when shipped; the tools provide atomicity, not authority.

---

## Trust Levels

### `safe` — Mechanical operations

Apply these changes directly without further approval. They are deterministic, reversible, and do not alter semantic content.

- Patch-level version bumps (X.Y.Z → X.Y.(Z+1))
- Metadata corrections (typos in version, date, status enum values)
- Formatting normalization (heading hierarchy consistency, YAML alignment)
- Appending changelog entries to existing changelog files
- Correcting cross-reference anchors with clear typos (e.g., double dashes or wrong heading text)
- Dispatch of `tools/` parameterized scripts (patch-level version bump, manifest regeneration) — permitted ONLY as a post-Approve action under `AGENTS.md` §5.2 step (5), dispatched exclusively by this skill. Changeset write order: document content → changelog → manifest (manifest last).

### `review` — Structural and substantive operations

Produce a detailed change plan (see Response Contract), present it to the primary agent, and wait for explicit confirmation before modifying live files.

- Content modifications to `index.md` bodies
- Any manifest (`docs-manifest.yaml`) updates
- Cross-reference additions or modifications beyond typo fixes
- Russian translation alignment (`index-RU.md` creation/modification per `AGENTS.md` §3.3 and ADR-012, resolved via manifest `has_translation` path). A post-Approve `auto_sync` dispatch does not lower this classification: it inherits approval for the changeset, not for skipping Phase 4 write-gates.
- Version minor/major bumps (X.Y.Z → X.(Y+1).Z or (X+1).Y.Z)
- Changelog entry creation (new files or new documents)
- Glossary term additions or updates

### When in doubt

If a task could fall into either category, default to `review`. Conservative escalation is preferred over unauthorized substantive edits.

---

## Response Contract

After processing the request, produce a single structured markdown document following this format:

```markdown
# Documentation Worker Report

## Phase: [UNDERSTAND | ANALYZE | CLARIFY | PROPOSE | EXECUTE | VERIFY]

## Summary
(One sentence describing current status.)

## Actions
- [COMPLETED / PENDING / ESCALATED] Action description
...

## Proposals
(Optional — only for `review` trust level. List each proposed change with affected file and section.)

## Escalations
(Optional — list any items escalated per the Escalation Rules below.)

## Compliance Status
[PASS / FAIL] — if FAIL, describe which checks failed and why.

## Files Affected
- modified: [...]
- created: [...]
- unchanged: [...]
```

Each response must be phase-gated using the label `[UNDERSTAND]`, `[ANALYZE]`, `[CLARIFY]`, `[PROPOSE]`, `[EXECUTE]`, or `[VERIFY]` so the primary agent knows where the interaction stands in the `AGENTS.md` §5.2 workflow.

---

## Capabilities

### Update a Document

When `change_type: update`:

1. Read the manifest to locate `target_id` and verify its metadata (version, path, status, abstraction, has_translation).
2. Read the target document's `index.md` from `docs/en/<id>/index.md` (and `index-RU.md` from the path given in `has_translation` if present).
3. Read the target's changelog file referenced by `changelog-path:`.
4. Check `docs/en/glossary/index.md` for any domain terms used but not defined.
5. Apply changes to `index.md` body as described in the request.
6. If an RU translation is recorded (`has_translation` in the manifest): resolve the RU path from the manifest field (not from filesystem co-location). Automatic synchronization is permitted per `AGENTS.md` §3.3 (ADR-012) **only as a post-Approve action** — when the delegation carries `auto_sync: true` set by the primary agent after step (5) Approve of the changeset containing the English edit — and only if the document has no `no_auto_translation: true` opt-out in its frontmatter. Otherwise run the structural comparison (drift audit, read-only) and REPORT drift without writing. See §Create or Update Russian Translation.
7. Dispatch the version writer — do not hand-edit version, changelog, or manifest:
   `python3 tools/bump_version.py --id <id> --kind patch|minor|major --note "<reason>"`
   The `--note` value is mandatory, non-empty, and quoted verbatim from the approved change plan (it is a *claimed rationale*, not verified provenance). Kind selection follows `AGENTS.md` §7.5 (patch: typo/formatting; minor: content addition or structure; major: foundational rewrite); when classification is uncertain, run `tools/classify_bump.py` read-only for a proposal and escalate per `AGENTS.md` §6 rather than guessing.
8. Run compliance verification (`AGENTS.md` §8): `python3 tools/check_all.py` — see §Deterministic Delegation and §Compliance Checklist.
9. Report results using the Response Contract.

### Split a Document

When `change_type: split`:

- If the document exceeds 200 lines (`AGENTS.md` §7.3), this is an **escalation condition** (see Escalation Rules below). Do NOT proceed with splitting autonomously.
- Instead, propose 2–3 candidate split locations based on natural section boundaries, topic coherence, and cross-reference clusters. Present options with rationale to the primary agent for human decision.
- After human selects the split point: create new sub-documents with stable identifiers, move appropriate sections, update cross-references in all referencing documents, bump versions, and regenerate the manifest with `python3 tools/gen_manifest.py --write` (the sole writer, `AGENTS.md` §2.2) — never hand-edit `docs-manifest.yaml`.

### Create or Update Russian Translation

When `change_type: create_ru`:

> **Current phase — conditional lift (`AGENTS.md` §3.3, ADR-012).** Three invocation modes: (a) **explicit translation** — operator requested a translation; execute normally. (b) **post-Approve auto-dispatch** — delegation carries `auto_sync: true` (set by the primary agent only after `AGENTS.md` §5.2 step (5) Approve) and the target has no `no_auto_translation: true` frontmatter opt-out; execute Phases 1–4 and write only if all Phase 4 write-gates pass. (c) **drift audit** — neither condition holds; run Phases 1–2 logic read-only, report drift, do not write. Reuse `change_type: create_ru` with `use_project_translation`; no separate change type exists.

#### Phase 1 — Parse English source

Read the target document's `index.md` from `docs/en/<id>/index.md`. Count metadata lines and structural elements (blank lines, `---` separators, headings at each level, code blocks, list items). Record the exact line count and section structure.

#### Phase 2 — Check existing translation

Read the existing translation from the path given in the manifest `has_translation` field (e.g., `docs/ru/<id>/index-RU.md`). Count its lines, compare structural elements against the EN source.
- If structural parity is intact → proceed to Phase 3 with update mode.
- If structural deviation detected (extra blank lines, missing separators, reordered sections) → discard current content, switch to create mode. Log why.
If no RU file exists → proceed to create mode.

#### Phase 3 — Generate / update translation

Produce `index-RU.md` at the path given in the manifest `has_translation` field (e.g., `docs/ru/<id>/index-RU.md`).
Metadata block must match exactly: same keys, same order, same number of blank lines after it. Translate only values (`# Глоссарий` instead of `# Glossary`, `changelog-path` stays as-is, etc.).
Preserve exact structure: heading hierarchy, section order, paragraph count, list-item alignment, code blocks in place, separator lines (`---`) at identical positions.
Line number parity: every content line in `index-RU.md` must occupy the same line number as its counterpart in `index.md`. Translate text per line; never collapse multi-line entries into one or split one into many.
If translated text length differs from the original, adjust surrounding whitespace to restore line alignment rather than collapsing or expanding sections.
Use established Russian equivalents from the glossary for all domain terms.
Translate conceptually, not literally — preserve meaning while adapting terminology.

#### Phase 4 — Self-verify and remediate

After writing the file, perform a verification pass:

1. **Line parity:** confirm that non-metadata, non-separator line N in RU aligns with line N in EN. Report any misalignment.
2. **Completeness:** ensure every non-blank, non-separator content line from EN has a corresponding line in RU. Flag MISSING lines.
3. **Language leakage:** scan for un-translated domain terms or stray English words/sentences within otherwise Russian text. **If trust_level is `safe`, fix trivial leakage items automatically** (e.g., untranslated single words like "configured" → "установленного"). If trust_level is `review`, present findings for approval before applying.
4. **Glossary compliance:** cross-reference all glossary terms against `docs/en/glossary/index.md`; flag terms absent from glossary.
5. **No drift:** confirm no sections were added, removed, or re-ordered relative to the source.

**Write-gates (mandatory for autonomous write, ADR-012):** an `auto_sync` write proceeds without operator preview ONLY if all of the following hold; any failure blocks the write and the full candidate translation is presented to the operator for review instead:

1. **Fail count zero:** the wrapper summary reports `fail == 0` (`--summary-json`; wrapper exit code 4 means blocked).
2. **Line parity:** every non-metadata content line maps 1:1 to its EN counterpart (per §Phase 3 line-number parity).
3. **EN-identity scan:** the candidate RU file is not byte-identical (nor line-for-line identical outside metadata/skip blocks) to the EN source — silent copy-through is rejected.
4. **Glossary compliance:** all domain terms present in RU match `docs/en/glossary/index.md` equivalents (rule 3 remains skill/AI-reserved).

Include in the report: backend/model used, `prompt_version`, ok/skip/fail counts, and the `[gloss-apply]` summary.

For each failed check: if the failure is mechanically correctable (line shift due to missing separator, stray English word, minor whitespace), fix it immediately. For structural deviations (reordered sections, missing content, wrong section count) or semantic concerns, do NOT auto-fix — present them in the report so the primary agent can decide corrective action. Log the final verification result alongside the translation action.

---

#### Translation via project translator (optional)

When the delegation context includes `use_project_translation: true` (alias `use_local_translation` accepted for compatibility — treated identically), replace the skill's internal translation with the project's translator (`tools/local-translate.sh`). This uses the validated configuration from `tools/EXPERIMENTS.md` (E-002 post-factum 2): NVFP4 quantisation of the same 35B-A3B architecture as the cloud base model.

**Validated configuration (defaults):**

| Parameter | Default | Source |
|---|---|---|
| Backend | `cloud` | — |
| Endpoint | `http://127.0.0.1:8000/v1` | Local OpenAI-compatible server (vLLM) |
| API key | `dummy` | Ignored by vLLM; only placeholder |
| Model | `Qwen3.6-35B-A3B-NVFP4` | Local server |
| Thinking mode | `{"enable_thinking":false}` | `CLOUD_CHAT_KWARGS`; mandatory (×15 speedup, E-002 post-factum 2) |
| Temperature | `0.2` | Reproducibility (E-004) |
| top_p | `0.95` | No measured effect vs 0.8 (E-008) |
| Hints style | `plain` | 0/3 contamination (E-003) |
| Metadata | skip (do not translate) | E-005: preserves convection and line-parity |
| Code-guard | disabled | E-006: base model preserves code-spans without hints |
| Chunking | paragraph-based | E-007: no advantage from section-mode |

**Fallback chain (in priority order):**

1. **Local NVFP4** (`127.0.0.1:8000`, default) — first choice; independence from external networks.
2. **Cloud NeuralDeep** (`https://api.neuraldeep.ru/v1`, model `qwen3.6-35b-a3b-noreason`) — NEVER automatic: when the local server is unreachable, STOP and ask the operator for per-run consent (ADR-012 privacy gate). Only proceed with the cloud call after explicit approval for that run; wrapper exit code 3 signals the stop condition.
3. **Native skill translation** — last resort; log a warning in the report.

**Wrapper usage:**

```bash
tools/local-translate.sh en ru <glossary_path> < input.md > output.md
```

Example:
```bash
tools/local-translate.sh en ru docs/en/glossary/index.md < docs/en/glossary/index.md > docs/en/glossary/index-RU.md
```

For files exceeding 200 lines, paragraph-based chunking is the default. Splitting at heading boundaries with subsequent reassembly is acceptable for very large documents; the wrapper itself handles paragraph chunking internally.

**Contract that Phase 4 self-verify may rely on:**

- **Line-parity is invariant:** every output line corresponds to exactly one input line (blank lines and structural lines pass through untranslated). Line-count fallback within the wrapper ensures this — if a model response has a different line count, it is re-queried line-by-line.
- **Metadata lines, `---` separators, table separator rows, and code fences are copied verbatim** (skipped by `needs_skip`); **headings are translated**, with the `#` prefix structurally restored by `restore_heading_prefix()`; inline-code spans are identifiers: model translations of span contents are reverted by `restore_code_spans()` (`[span-restore]` on stderr, counted as `span_restores` in summary-json) and identifier characters are protected (`enforce_glossary` skips `[A-Za-z0-9_]`-adjacent matches, `restore_paths` repairs homoglyph mangling). Lines consisting solely of identifiers/inline-code/URLs are kept verbatim and counted as `skip`, not `fail`.
- **Glossary terms are canonicalised:** if a model leaves an English term untranslated, `enforce_glossary()` replaces it with the Russian equivalent; each such correction is logged as `[gloss-apply] <EN> -> <RU> xN` on stderr.
- **`[FAIL] L<n>` on stderr means the line on line N was NOT translated** (remained identical to source, but contained translatable words). Every `[FAIL]` line must be reported in the language-leakage section of the verification report and **blocks `safe` trust level** — the operation must be escalated to `review`. Lines consisting solely of identifiers (snake_case / CamelCase / ALLCAPS), inline code, or URLs are kept verbatim and counted as `skip` — they are not failures.

**Environment variables supported by the wrapper:**

`TRANSLATE_BACKEND`, `CLOUD_MODEL`, `CLOUD_CHAT_KWARGS`, `TRANSLATE_TEMP`, `TRANSLATE_TOP_P`, `TRANSLATE_HINT_STYLE`, `TRANSLATE_METADATA`, `TRANSLATE_PROMPT`, `TRANSLATE_FORCE_SECTION`, `REQUEST_TIMEOUT`, `MAX_RETRIES`.

See `tools/EXPERIMENTS.md` (E-001…E-008) for full experiment history and rationale for each default.

**Deterministic drift check.** In drift-audit mode (c), the skill invokes `python3 tools/check_drift.py <en> <ru>` as a deterministic structural component (strictly structural: headings, tables, fences, list markers, inline-code set, separators, metadata fingerprint, Cyrillic-ratio EN-leakage). The tool deliberately excludes line-parity (a Phase 4 write-gate) and glossary/abstraction checks (AI-reserved per `AGENTS.md` §8) — no-rule-fork is preserved. When `PROMPT_VERSION` changes (or no live run is recorded in `TRANSLATE_RUN_LOG`), the runner emits a reminder; upon detecting such a reminder, the skill MUST offer the operator a run of `tools/tests/e2e_live.sh`.

Fallback: if the configured server is unreachable and no explicit cloud override is set, the wrapper exits with code 3 and a diagnostic message on stderr. If the Python translator encounters a key error or network failure, fall back to native skill translation and log a warning in the report.

### Audit Compliance

When `change_type: audit`:

- **Dispatch, do not re-implement:** run `python3 tools/check_all.py` (options: `--json`, `--severity low|medium|high`, `--rule <ID>`, `--strict`) and analyze its report. Line count, changelog existence, cross-reference anchors, manifest parity, naming and schema are deterministic findings owned by the tool — the skill MUST NOT re-check them by reading files, and MUST NOT claim to implement "audit rules 1–6" (`AGENTS.md` §8).
- **Skill/AI-reserved judgments** (`documenter-service/mvp-interfaces.md`, §Compliance rules scanned — rules 3 and 5):
  - **Rule 3 — glossary terms:** every domain term used in a body exists in `docs/en/glossary/index.md`;
  - **Rule 5 — abstraction consistency:** declared `abstraction:` matches actual content structure.
- **Orphan classification (AI judgment):** when the manifest↔disk comparison reports on-disk documents absent from the manifest, distinguish truly orphaned files (no cross-reference anywhere) from auxiliary/operational files referenced from a parent document body (e.g., templates, prompts, helpers mentioned inside `fallback/fallback-mode.md`). Report only true orphans as compliance violations; flag auxiliaries as INFO-level notes.
- Flag non-compliant documents in the REPORT with specific violations, naming the rule and the file.
- DO NOT fix issues automatically during audit mode unless the trust level is `safe` AND the violation is a clear, deterministic correction already owned by a `tools/` script.

---

## Deterministic Delegation

Mechanical documentation operations are owned by the deterministic suites under `tools/`. The skill **dispatches** them; it never reimplements their logic by hand and never edits their output by hand.

| Operation | Tool | Notes |
| --- | --- | --- |
| Regenerate the manifest | `python3 tools/gen_manifest.py --write` | Sole writer of `docs-manifest.yaml` (`AGENTS.md` §2.2); hand-editing the manifest is prohibited |
| Verify manifest parity | `python3 tools/gen_manifest.py --check` | Regenerate-and-diff idempotence check |
| Compliance rule suite | `python3 tools/check_all.py [--json] [--severity] [--rule] [--strict]` | Rules 1, 2, 4, 6 + naming/schema; exit 0 clean, 1 findings, 2 internal error |
| Version bump + changelog + manifest | `python3 tools/bump_version.py --id <id> --kind <patch\|minor\|major> --note "<reason>"` | Enforced write order: document content → changelog → manifest (last); atomic per-file temp+rename with rollback; exit 2 = refusal/rolled back |
| Diff→bump classification proposal | `python3 tools/classify_bump.py` | Read-only; ambiguous → `minor` with a §7.5 warning; `--report` gate: escalation rate > 20% → redesign |
| Translation | `tools/local-translate.sh` | Optional path, §Translation via project translator |
| Structural drift comparison EN↔RU | `python3 tools/check_drift.py <en> <ru>` | structural-only; excludes line-parity (Phase 4) and AI-reserved rules 3/5 |
| Translation regression runner | `tools/tests/run_translate_tests.sh [quick|full]` | quick: unit <5s; full: + mock corpus; live: `tools/tests/e2e_live.sh` on operator request |

Rules of engagement:

1. **Atomicity, not authority.** These tools provide atomic writes and deterministic checks; they grant no permission. Every dispatch is permitted only after step (5) Approve of `AGENTS.md` §5.2, and only by this skill.
2. **No rule fork.** Any check available in `tools/check_all.py` is obtained by invoking it — duplicating the check in prose or ad-hoc commands is prohibited (mirrors the Documenter `audit()` reuse rule, `documenter-service/mvp-interfaces.md` §Compliance rules scanned).
3. **No coverage claims.** Never describe this skill or the tools as implementing "audit rules 1–6"; rules 3 and 5 are AI/skill-reserved judgments.
4. **Trust alignment.** The lists in §Trust Levels MUST stay aligned with the Documenter trust classifier (`documenter-service/index.md`, §Trust Classification) and with the shipped `tools/` behavior; a mismatch is escalated, not resolved silently.
5. **Structured failure handling.** A tool exit code 2 is a refusal or a rollback — report it as such and escalate; never retry with weakened arguments.

---

## Escalation Rules

Escalate back to the primary agent (do NOT proceed with the change) when ANY of the following conditions are detected:

1. **Ambiguity** (`AGENTS.md` §6): more than one reasonable approach exists with no prior guidance, conflicting instructions, unclear intent.
2. **Document >200 lines requiring split**: the skill proposes locations but does NOT decide autonomously — human must select.
3. **Inter-document conflict**: two or more documents contain contradictory statements about the same concept with no clear precedence rule.
4. **New domain glossary term**: a term used multiple times across documents that doesn't yet exist in the glossary AND has semantic/content significance (not just a formatting abbreviation).
5. **Manifest integrity issue**: orphaned cross-references, broken path references, missing required fields, or version numbers that don't follow semantic versioning.
6. **Compliance check FAIL**: any post-change verification step in `AGENTS.md` §8 fails and cannot be mechanically corrected.
7. **Concurrent write conflict**: another process has modified a file since the last read (TOCTOU detection).
8. **Missing manifest entry**: the requested `target_id` is not found in `docs-manifest.yaml`.
9. **Consilium finding → gate obligation.** Every high/critical finding produced by a Council session must yield a corresponding test or gate action item reproducing the named failure mode. The primary agent verifies presence of such items when composing a task brief; the Documentation Worker flags delegations whose findings lack a verification item. (Norm established by sess-prevention-measures, 2026-11-14; operator decision: no ADR.)

Each escalation must include: the reason (matching one of the categories above), the affected document(s), and a recommended action.

---

## Safety Protocol

Since this skill performs direct filesystem edits, the following safety measures apply:

1. **Pre-change snapshot**: before starting any modification session, capture the current git status and HEAD commit hash. This enables rollback if something goes wrong.
2. **Read-before-write**: immediately before writing any file, re-read it to detect external concurrent modifications. Abort and escalate if the file has changed since the last read.
3. **Post-change diff verification**: after applying edits, generate a diff of all changed files and include it in the report. The primary agent can inspect this to confirm correctness.
4. **Atomic operation assumption**: treat a complete execution cycle (read → modify → verify → report) as a logical unit. On failure mid-cycle, abort remaining steps and roll back to pre-change state using the captured git snapshot.
5. **No auto-commit**: modifies files but never commits them to git. The primary agent handles version control.

---

## Compliance Checklist

Two parts: deterministic checks are obtained from `tools/`, the rest are AI/skill-reserved judgments.

**Deterministic — obtained by running the tools, not by hand:**

- [ ] `python3 tools/check_all.py` reports no `high` findings; every `medium`/`low` finding is either explained or fixed (covers line count ≤ 200 per §7.3, changelog existence and format, cross-reference anchors, manifest parity, naming, schema)
- [ ] Manifest reflects current on-disk state via `python3 tools/gen_manifest.py --check` (regenerate-and-diff; no hand edits)
- [ ] Version bumped correctly per `AGENTS.md` §7.5 and changelog entry written — both via `tools/bump_version.py` (type of bump matches change type; `--note` non-empty)

**Skill/AI-reserved — no tool substitutes for these:**

- [ ] All domain terms exist in `docs/en/glossary/index.md` (or escalated) — audit rule 3
- [ ] Abstraction level appropriate and consistent across related docs (`AGENTS.md` §7.4) — audit rule 5
- [ ] Metadata header follows `AGENTS.md` §7.2 conventions (no `Language` field, `Source:` present for RU)
- [ ] Split decision (if size exceeded) escalated to the operator with 2–3 candidate points (§7.3)
- [ ] Changelog `--note` reason string is operator-supplied or quoted verbatim from the approved plan
- [ ] Trust levels aligned with the Documenter classifier and shipped `tools/` behavior (§Trust Levels, `AGENTS.md` §1.7)
- [ ] Russian synchronization per `AGENTS.md` §3.3 (ADR-012): drift audit report-only unless post-Approve `auto_sync` is in effect and no `no_auto_translation` opt-out exists
  - [ ] For explicit or `auto_sync` writes: line number parity verified; all four Phase 4 write-gates passed (fail==0, line parity, EN-identity scan, glossary compliance)

Fix failures mechanically where a `tools/` script owns the fix; escalate if unfixable or if the fix requires semantic judgment.

---

## References

- `AGENTS.md` (§2–§8, §5.1–§5.2, §3.3, §6, §7.1–§7.6, §1.6)
- `docs/en/glossary/index.md` (canonical term definitions)
- `fallback/index.md` (Council protocol; this skill is separate)

---

*Aligned with project documents v0.9.0.*
