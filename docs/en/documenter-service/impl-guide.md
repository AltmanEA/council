# Documenter Implementation Guide

id: documenter-service-impl-guide
Version: 0.4.0
Status: active
Abstraction: reference
has_translation: docs/ru/documenter-service/impl-guide-RU.md
changelog-path: CHANGELOGS/documenter-service-impl-guide.changes.md
allow_non_index_paths: true
references: [documenter-service, documentation-rules]

---

## Purpose and single-source clause

This guide decomposes the Documenter into parts and prescribes **how each
part is implemented**: deterministic script under `tools/`, AI prompt (skill
prose), or external engine. Binding rule (Evolution stance, `index.md`):
everything that can be algorithmized is implemented deterministically by a
script; judgment stays with the prompt.

This document prescribes HOW the mechanisms of `docs/en/documenter-service/index.md`
(concept spec) and `.agents/skills/documentation/SKILL.md` (skill) are
implemented. It does **not** redefine their behavior. Where this guide and
those documents appear to conflict, they are authoritative for behavior and
this guide is corrected. Rules are referenced, never restated.

## Component inventory and allocation matrix

Every part is labeled: **script** (deterministic, under `tools/`), **prompt**
(skill prose / agent judgment), **external** (Translation Project engine), or
hybrid.

| Part | Form | Owner artifact |
|---|---|---|
| Documentation Worker skill — core orchestration | prompt | `.agents/skills/documentation/SKILL.md` |
| Manifest generation | script | `tools/gen_manifest.py` (sole writer) |
| Audit engine | script | `tools/check_all.py` (frozen contract, Phase 0 landed) |
| Version/changelog/manifest writer | script | `tools/bump_version.py` (atomic, ordered) |
| Bump classification proposal | script (read-only) | `tools/classify_bump.py` |
| EN↔RU structural drift judge + write-gates | script | `tools/check_drift.py` (`--phase4` gates landed, Phase 1) |
| Translation generation | external | `techdoc-translator` via `defaults/translation.lock` (ADR-014) |
| Translation mode (a) explicit | prompt + external | skill §create_ru; writes post-Approve |
| Translation mode (b) auto_sync | prompt + external + gates | skill; writes only if all gates pass |
| Translation mode (c) drift-audit | script only | `check_drift.py`, read-only report |
| Translation provenance | script | `tools/translation_status.py` + `documenter/artifacts/translation/STATUS.md` |
| Mechanical/semantic classification | prompt | agent judgment; labeled card line; operator override; no machine classifier |
| Approval grammar (`approve` / `approve: <object>`) | prompt | operator act (OP-1), card-bound |
| Pre-commit hook | script (warn-only) | `tools/hooks/pre-commit` |
| Staging for complex edits | prompt procedure + gitignored area | `sessions/<id>/staging/` |

## Capability-to-step mapping

The skill is the sole writer (AGENTS.md §2) and drives every operating-loop
step of `index.md` §Operating model:

| Loop step | Skill action | Form |
|---|---|---|
| 1 Propose + bundle | assemble changeset (staged work if complex), one commit bundle | prompt |
| 2 Advisory audit | dispatch `check_all.py`; merge verdict into card | script |
| 3 Operator review + `approve` | render Approval Card; await in-chat reply | prompt + operator |
| 4 Write | dispatch writers in order (content → changelog → manifest) | script |
| 5 Post-commit audit / revert | operator runs `check_all.py`; `git revert` | script + operator |

## Deterministic core (scripts)

- **Audit engine `check_all.py`** — frozen contract (`index.md` §Audit tool):
  exit `0` clean / `1` findings / `2` critical; findings never gate (OP-3).
  Rendering: clean is silent; otherwise `⚠ findings: N` or `🚨 critical: N`
  plus one-line fix hints, grouped and severity-sorted. `--severity` flag
  keeps filter semantics (minimum reported severity; default `low` per the
  Phase 0 operator amendment). **Token contract** (stable, grep-stable for the
  hook): literal tokens `severity=high|medium|low` in human
  output and the `--json` schema; the `⚠`/`🚨` markers are visual only, not grep
  targets.
  Shipped behavior matches this contract (Phase 0 landed).
- **Manifest** — `gen_manifest.py --write` is the sole writer; `--check`
  verifies parity. Hand-editing prohibited (documentation-rules §2.2).
- **Version writing** — `bump_version.py` owns the normative order content →
  changelog → manifest, atomic with rollback. Scripts provide atomicity, not
  authority: dispatched only by the skill post-Approve.
- **EN↔RU judge `check_drift.py`** — sole Council-side structural comparator;
  from Phase 1 also hosts the deterministic Phase-4 translation write-gates
  as rule IDs `phase4-fail` (report fail == 0), `phase4-parity` (1:1 line
  parity), `phase4-identity` (EN-copy rejection), `phase4-glossary` (glossary
  term match). Gate outcomes are evaluated in code, never re-derived from
  prose by the agent.
- **Provenance** — `translation_status.py` rebuilds sidecars + `STATUS.md`
  from run reports; the card `Translations:` line is derived from `STATUS.md`
  at card-generation time.

## Prompt parts (skill and agent judgment)

Reserved for judgment (never scripted): semantic rewrite content;
mechanical/semantic classification proposal (semantic blindness is an
accepted risk — operator naming of semantic approvals is the forcing
function); glossary compliance (documentation-rules §8 rule 3); abstraction
consistency (rule 5); orphan classification. The skill remains the sole
writer of `docs/`, `docs-manifest.yaml`, `CHANGELOGS/`.

## Approval Card (in-chat artifact of the approve act)

Fixed template, maximum 10 lines (normally 6–8), fixed order and labels;
variable-format cards are prohibited:

```
Files: <affected files, max 8 per line>
Category: <create | update | delete | split | translation>
Delta: +<N> / −<M> / net ±<K>
Classification: <mechanical | semantic> [agent proposed: <original>]
Audit: <omitted when clean; else ⚠ findings: N / 🚨 critical: N + hints>
Translations: <mode> · verified <N> · unverified <M>   # only if translation involved
State: <final | intermediate>                          # staged work only
```

- `Classification` bracket appears only on operator override (lightweight
  override log). `Audit` line is absent entirely when clean (silent-when-
  clean). `State: intermediate` warns the card binds to a not-yet-assembled
  bundle; approval binds to `final`.
- `Translations` interpretation key: `M = 0` → no action; `M > 0` → drift
  needs operator attention.
- Terminology: **Approval Card / Карточка согласования** (operator decision,
  sess-documenter-impl-design 2026-11-19). The deprecated glossary term
  "Operator Surface" is not used; not to be confused with Operator Ingress
  (Council Layer 2, ADR-018).

## Approve grammar

(a) Bare `approve` approves a mechanical change. (b) A semantic change
requires `approve: <noun phrase>` naming its object. (c) Boundary rulings:
version bump + changelog = mechanical; glossary term addition = semantic.
(d) The agent always renders classification as a labeled card field, never
buried in prose; the operator may override.

## OP-2 ceiling compliance

Ceiling: ≤12 files / ~3,100–3,600 LOC of executable tooling
(`tools/README.md` excluded). Counting rule: executable tooling (scripts,
helpers, test code) counts; fixture data under `tools/tests/fixtures/` does
not (same class as README). Displacement: any new script must name a
displacement candidate in its changeset; absent one, escalate to the
operator — never silently exceed the ceiling.

Recorded displacement: `tools/check_parity.py` (29 LOC) is displaced by the
`check_drift.py` Phase-4 rule extension (Phase 1); zero code references,
prose mentions cleaned in the same changeset. Trace: changelog-style note in
`tools/README.md` (displaced-by, date, reason), not a ledger.

## Phasing

- **Phase 0 (prerequisite, one atomic changeset):** rewrite `check_all.py` to
  the frozen exit-code contract + rendering; sync all prose contracts in the
  same commit (`tools/README.md`, `index.md` implementation-status note,
  skill Compliance Checklist). No new scripts land before this. Soak→block
  hook flip only after Phase 0 lands and passes baseline.
- **Phase 1:** add `phase4-*` gate rules to `check_drift.py`; delete
  `check_parity.py`; add the `Contract` column to the `tools/README.md` tool
  table (prose-contract registry); clean prose references.
- **Phase 2:** adopt the Approval Card template and approve grammar above in
  the skill's step-(5) procedure.
- **Phase 3:** this guide itself is adopted as normative via the approved
  changeset that creates it.

## Definition of done

Per **script** part: (a) fixture dry-run under `tools/tests/fixtures/`;
(b) at least one run against the live documentation corpus; (c) after
Phase 0: one `check_all.py --strict` full-tree baseline recorded before hook
soak starts; 10 clean-commit soak precedes any block-mode flip.
Per **prompt** part: scripted dry-run of the loop plus a one-off
new-human-operator acceptance test — a second operator completes the full
operating loop using only this guide and the skill.

## Prose-contract synchronization

Each tool's behavioral contract is registered as a `Contract` column entry in
the `tools/README.md` tool table (canonical anchor: README section, skill
section, or spec clause). Per AGENTS.md §1.7, any change to a tool's behavior
MUST update its registered contract text in the same changeset; the audit of
the changeset file list checks this, no new tool is created for it.

## Translation pipeline split

The engine is a black box (lock file, `--contract-version`, fail-closed exit
codes 0–6 per `docs/en/translation-project/`). Council owns: input preparation
(glossary, skip-patterns), deterministic verification (the four `phase4-*`
gates in `check_drift.py`), provenance artifacts, and drift-audit mode (mode
(c) runs `check_drift.py` only — no-rule-fork, documentation-rules §8). The
skill re-runs verification after generation and before any write; it never
evaluates gate outcomes by reading prose.

## Single-commit invariant and staging

Ownership is singular: bundling and the content → changelog → manifest order
are owned by `bump_version.py` / `gen_manifest.py`; staging lives in the
gitignored `sessions/<id>/staging/` area outside the `docs/` tree. The
Approval Card `State:` field is the structural guard against approving partial
bundles. Other sections reference this one, never restate it.

## References

- `docs/en/documenter-service/index.md` — concept spec (OP-1/OP-2/OP-3, loop, audit contract)
- `docs/en/documentation-rules/index.md` — audited rules (§2–§8)
- `.agents/skills/documentation/SKILL.md` — skill (sole writer; behavioral authority)
- `tools/README.md` — tool inventory and prose-contract registry
- `docs/en/translation-project/index.md` + `contract.md` — external engine contract (ADR-014)
- `sessions/sess-documenter-impl-design/consensus-doc.md` — producing consensus (implementation file, not authority)
