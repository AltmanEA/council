# Consensus Document — sess-documenter-impl-design

Date: 2026-11-19
Mode: fallback, sequential subagents (operator instruction)
Roster: Architect, Reliability & Security, Human-Centric Designer, Operations Engineer
Inputs: task-brief.md, review-*.md, discussion-round-1.md
Result: **Conditionally resolved** (all agree; two reservations recorded)

## Decision

Produce one new project document — `docs/en/documenter-service/impl-guide.md`
(id: `documenter-service-impl-guide`, ≤200 lines) — that decomposes the
Documenter into parts and assigns each an implementation form: deterministic
script under `tools/`, AI prompt (skill prose), hybrid, or external engine.
It prescribes HOW the mechanisms of `index.md` and `SKILL.md` are implemented
and never redefines their behavior (single-source-of-truth clause;
cross-reference, do not restate).

## Component inventory and allocation matrix (agreed)

The impl-guide must contain a capability-to-step mapping table (5 rows, one
per operating-loop step: skill action → script/prompt/external label) and an
allocation matrix classifying every part:

| Part | Form | Notes |
|---|---|---|
| Documentation Worker skill (337 LOC prose) | prompt — core orchestration | explicit matrix row; maps to loop steps 1–5 |
| Manifest generation | script — gen_manifest.py (sole writer) | existing |
| Audit engine | script — check_all.py | Phase 0 rewrite pending |
| Version/changelog/manifest writer | script — bump_version.py | existing, atomic |
| Bump classification proposal | script — classify_bump.py (read-only) | existing |
| EN↔RU structural drift judge | script — check_drift.py | extended with Phase-4 write-gates |
| Translation generation | external — techdoc-translator (ADR-014, vendored, locked) | black box |
| Translation mode (a) explicit | prompt + external tool | writes post-approve |
| Translation mode (b) auto_sync | prompt + external tool + deterministic gates | writes only if all gates pass |
| Translation mode (c) drift-audit | script — check_drift.py only | read-only, report drift |
| Translation provenance | script — translation_status.py + STATUS.md | operator-facing index |
| Mechanical/semantic classification | prompt — agent judgment | labeled card line, operator may override; NO machine classifier |
| Approval grammar (`approve` / `approve: object`) | prompt — operator act | card-fixed format makes it verifiable |
| Pre-commit hook | script — hooks/pre-commit, warn-only | soak→block flip gated on Phase 0 |
| Staging for complex edits | prompt procedure + gitignored area | sessions/<id>/staging/ |

## Key decisions by subject

- **SUBJ-001 (document shape).** New file `docs/en/documenter-service/impl-guide.md`
  (entry has allow_non_index_paths: true); ≤200 lines; design-constraints-only;
  single-source clause; manifest entry + changelog via Documentation Worker
  skill after operator approve. Rejected: extension of index.md (conflates
  concept with implementation).
- **SUBJ-002 (allocation).** Binding rule applied: all deterministic checks are
  scripts; judgment items (semantic classification, glossary rule 3, abstraction
  rule 5, semantic rewrite content) stay prompt. Skill is a first-class matrix
  row. Three translation modes are three separate parts with distinct write
  authority. Phase 4 write-gates (fail==0, line parity, EN-identity, glossary)
  move from prose to deterministic code **inside check_drift.py** as rule IDs
  `phase4-fail`, `phase4-parity`, `phase4-identity`, `phase4-glossary`
  (+30–45 LOC). Standalone `translation_write_gate.py` REJECTED (13th file,
  duplicate parsing, second prose contract).
- **SUBJ-003 (OP-2 ceiling).** Current 11 files / ~3,384 LOC vs ceiling
  12 / ~3,600. Displacement: delete `tools/check_parity.py` (29 LOC; verified
  zero code references — only 4 prose mentions). Trace = one-line
  changelog-style note in tools/README.md ("displaced by check_drift.py
  phase-4 rules, date, reason"). Counting rule: executable tooling (scripts,
  helpers, test code) counts toward ceiling; fixture DATA under
  tests/fixtures/ does not (same class as README). No register table, no new
  files.
- **SUBJ-004 (check_all.py rewrite).** Phase 0, FIRST changeset, atomic:
  exit-code migration to frozen contract (0 clean / 1 findings / 2 critical)
  + rendering (silent clean; `⚠ findings: N` / `🚨 critical: N`, one-line
  hints, grouped, severity-sorted) + doc sync in the same commit (tools/README
  line 13, concept-spec implementation-status note, skill Compliance
  Checklist). No new scripts land before it. `--severity` flag semantics
  unchanged (filter only). Hook grep token contract frozen in impl-guide:
  literal `severity=high|medium|low` tokens + stable `--json` schema; ⚠/🚨
  are visual-only, not grep targets. Soak→block flip only after Phase 0.
- **SUBJ-005 (phasing / DoD).** Order: Phase 0 check_all rewrite+doc-sync →
  Phase 1 check_drift write-gate rules + check_parity deletion + README
  Contract column → Phase 2 summary-card/approve-grammar spec adopted by skill
  → Phase 3 impl-guide itself lands via the approved loop. DoD per script:
  (a) fixture dry-run under tests/fixtures/, (b) live-corpus run, (c) post
  Phase 0: one `check_all.py --strict` full-tree baseline before hook soak;
  10-commit soak precedes any block flip. DoD per prompt part: scripted
  dry-run of the loop PLUS one-off new-human-operator acceptance test (a
  different operator completes the loop using only the impl-guide + skill).
- **SUBJ-006 (Approval Card / Карточка согласования).** Operator terminology
  resolved per operator decision 2026-11-19: the deprecated term "Operator
  Surface" (glossary: do not use in new text; superseded by Operator Ingress
  per ADR-018, which is a different concept) is replaced by **Approval Card /
  Карточка согласования** for the in-chat approval artifact. No abstract
  "surface" term is introduced; no glossary entry required (process artifact,
  not a Council domain concept). Fixed card template, ≤10 lines
  (normal 6–8), fixed order and labels:
  `Files:` (max 8 per line) / `Category: create|update|delete|split|translation` /
  `Delta: +N / −M / net ±K` / `Classification: mechanical|semantic`
  (bracketed `[agent proposed: X]` only on override) / `Audit:` (absent when
  clean; else ⚠/🚨 line) / `Translation: <mode> · verified N · unverified M`
  (only when translation involved; N/M from STATUS.md at card time;
  interpretation key: M=0 → no action, M>0 → needs attention) /
  `State: final|intermediate` (staged work only). Approve grammar rules:
  (a) bare `approve` = mechanical; (b) `approve: <noun phrase>` = semantic;
  (c) boundary examples fixed (version bump + changelog = mechanical; glossary
  addition = semantic); (d) classification is always a labeled field, never
  hidden in prose.
- **SUBJ-007 (translation split).** Engine = external black box (lock file,
  contract version, fail-closed exits). Council owns: deterministic gates
  (check_drift.py after Phase-1), verification re-runs, provenance
  (runs/*.json, sidecar, STATUS.md), drift-audit mode. Agent-prose evaluation
  of `--summary-json` gate outcomes is replaced by script evaluation.
- **SUBJ-008 (single-commit invariant).** Owned once, referenced elsewhere:
  write order content → changelog → manifest enforced by bump_version.py /
  gen_manifest.py; staging in gitignored sessions/<id>/staging/; card `State:`
  field structurally prevents approving partial bundles.
- **SUBJ-009 (verification).** Prose-contract registry = new `Contract`
  column in tools/README.md tool table (canonical anchor per tool: README
  section / SKILL.md section / spec clause). Per AGENTS.md §1.7 any tool
  behavior change must update its Contract anchor in the same changeset —
  verified by audit of changeset file list, not a new tool.

## Reservations (recorded, non-blocking)

1. Reliability: fixture dry-run alone is thin regression protection for a
   1,259-LOC rewrite; mitigated by the adopted `--strict` full-tree baseline
   — operator accepts residual risk.
2. Reliability: wanted a formal displacement register; satisfied with
   README changelog-style note. If a future change lacks a clear displacement
   candidate, escalate to operator rather than silently exceed the ceiling.

## Critical findings (all with justifications; none downgraded)

- OP-2 headroom ~200 LOC (Architect) → displacement decision above.
- Prompt-evaluated write-gates (Reliability, downgraded critical→high in
  Round 2 after merge-into-check_drift resolution).
- Legacy exit-code mismatch (Reliability/Operations) → Phase 0.
- 13-file breach from standalone gate script (Operations) → rejected.
- Approve grammar / card under-specification (Human-Centric) → card template.

## Open questions (deferred, non-blocking)

1. Race safety of consecutive tool dispatches (bump_version temp+rename vs
   gen_manifest) — to be covered by a Phase-1 test fixture.
2. Exact drift-audit mode procedure (check_drift only vs Phases 1–2 read-only)
   — to be pinned in impl-guide §translation; draft proposal: check_drift.py
   only, per SKILL.md §Deterministic Delegation (no-rule-fork).

## Action items

1. Draft `docs/en/documenter-service/impl-guide.md` per this consensus
   (≤200 lines) — via Documentation Worker skill, summary card, operator approve.
2. Phase 0 changeset: check_all.py rewrite + doc sync (separate implementation
   session; the implementation skill TDD cycle).
3. Phase 1 changeset: check_drift.py phase-4 rules + check_parity.py deletion
   + README Contract column + prose-mention cleanup (AGENTS.md line, index.md
   Retained list, RU mirror).
4. Update skill card template + approve grammar after impl-guide approval.
