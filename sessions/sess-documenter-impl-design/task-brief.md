# Session Task Brief — sess-documenter-impl-design

Date: 2026-11-19
Mode: fallback (subagents one at a time, per operator instruction)

## Task

The Documenter concept (`docs/en/documenter-service/index.md`, v1.2.0-draft) is
settled: three principles (OP-1 instant approval, OP-2 maximum simplicity,
OP-3 commit audit + revert), the operating loop, the audit contract, accepted
risks, surviving tooling. The next artifact is an **implementation document**
that decomposes the Documenter into concrete parts and prescribes how each
part is implemented: **deterministic script under `tools/`** or **AI prompt
(skill prose)**, with the binding rule: *everything that can be algorithmized
is done deterministically by script*.

The session must produce a consensus on the structure and content decisions of
that implementation document so the orchestrating agent can draft it for
operator approval.

## Session Goal

Agree on the component decomposition of the Documenter, the deterministic-vs-prompt
allocation matrix, OP-2 ceiling strategy, phasing, and the shape of the
implementation document itself.

## Normative inputs (roles MUST read)

- `docs/en/documenter-service/index.md` — the concept spec (v1.2.0-draft)
- `docs/en/documentation-rules/index.md` — audited rules (§2–§8)
- `.agents/skills/documentation/SKILL.md` — Documentation Worker skill (sole writer)
- `tools/README.md` — current tool inventory and statuses
- `AGENTS.md` §1.5–§1.7 — stage, separation, tooling separation
- `fallback/index.md` — this procedure

## Ground facts (operator-verified)

- Current `tools/` code: 11 files, ~3,384 LOC total (incl. shell helpers).
  OP-2 ceiling: at most 12 files / ~3,100–3,600 LOC. Headroom is nearly zero;
  any new script must **displace** existing code.
- `check_all.py` (1,259 LOC) still uses legacy exit codes (0/1-high/2-error);
  migration to the frozen contract (0 clean / 1 findings / 2 critical) is a
  pending rewrite, plus rendering (`⚠ findings: N`, one-line hints, grouped,
  severity-sorted).
- Translation engine is external (`techdoc-translator`, ADR-014, vendored,
  pinned by `defaults/translation.lock`); Council keeps verification gates,
  provenance artifacts, `check_drift.py`, `translation_status.py`.
- The document will live under `docs/en/documenter-service/` (the entry has
  `allow_non_index_paths: true`), as a new project document with changelog.

## Focus Areas

- Completeness: does the part-list cover every mechanism named in the spec
  (operating loop steps, audit battery, recovery, skill as sole writer,
  translation split, hook, staging for complex edits)?
- The deterministic-vs-prompt boundary: any item that is fully specified by
  inputs and rules must be a script; judgment stays prompt.
- OP-2 ceiling strategy: displacement plan, what may be deleted/merged, what
  new scripts (if any) are justified.
- Phasing and acceptance criteria: what "implemented" means per part, how
  each deterministic part is verified (tests), how each prompt part is
  specified (prompt contract).
- Document shape: sections, level of detail, where it sits in the manifest.

## Subject List

- `SUBJ-001`: Structure of the implementation document (sections, audience,
  relationship to the concept spec; new document vs extension of index.md).
- `SUBJ-002`: Component inventory and the script-vs-prompt allocation matrix
  (every part classified: script / prompt / hybrid / external).
- `SUBJ-003`: OP-2 ceiling compliance strategy (displacement, budget
  accounting, what gets deleted or merged to make room).
- `SUBJ-004`: `check_all.py` rewrite scope: exit-code contract, rendering,
  check battery vs the spec table, legacy-code migration.
- `SUBJ-005`: Phasing/prioritization of implementation work and definition of
  done per part.
- `SUBJ-006`: Approval Card (Карточка согласования): card format,
  mechanical/semantic classification proposal, `approve` grammar, audit
  rendering the operator sees.
- `SUBJ-007`: Translation pipeline split: external engine vs Council-side
  gates/provenance; what stays prompt-only per documentation-rules §8.
- `SUBJ-008`: Skill bundling and single-commit invariant: staging area,
  write order (content → changelog → manifest), atomicity ownership.
- `SUBJ-009`: Verification strategy: tests for deterministic parts, prompt
  contracts for judgment parts, prose-contract synchronization duty.

## Questionnaire per Role

**Architect:**
- Is the part-list complete against the spec? What boundary is mis-drawn?
- Where does the implementation document risk duplicating (and thus drifting
  from) the concept spec or SKILL.md? How is single-source-of-truth preserved?

**Reliability & Security Specialist:**
- Which allocation decisions create silent failure modes (a prompt doing what
  a script should, drift between prose contract and code)?
- Does the plan weaken OP-3 recovery (revert viability) or the sole-writer rule?

**Human-Centric Designer:**
- Can a new operator (or new agent) act on the implementation document
  without asking the original authors? Is the summary card and approval
  grammar specified precisely enough?
- Does the document itself obey OP-2 (is it over-engineered)?

**Operations Engineer:**
- Is the phasing realistic given the OP-2 ceiling and the check_all rewrite
  debt? What is the operational order of work, and what breaks while parts
  are half-migrated?
- How is "implemented" demonstrated per part (tests, dry-runs, soak)?

## Output Limits

- Maximum findings per role: 7
- Maximum recommendations per role: 5
- Maximum open questions per role: 3
- Total output: ~150 lines

## Expected Discussion Rounds

Medium task: **1 round** (sequential, one subagent at a time).

## Additional Context / Constraints

- All documentation writes go through the Documentation Worker skill after
  operator `approve` — the council output is a consensus + a draft proposal,
  never a direct write.
- Do not reintroduce deleted v0 machinery (tiers, gates, policy files).
- The fallback documents themselves are frozen; this task does not touch them.
