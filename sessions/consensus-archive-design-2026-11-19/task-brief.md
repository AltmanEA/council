# Task Brief — Full Archive Organization for the Documenter

Session: sess-archive-design-2026-11-19 (fallback mode, sequential subagent execution per operator instruction)
Mode: Subagent Fallback (fallback/index.md v0.6.0), roles activated by operator; Phase 2 executed SEQUENTIALLY (operator override of parallel launch): each role receives prior roles' reviews as input.

## Task description

The Documenter has a declarative archive concept: `docs/en/documenter-service/legacy/` with a guard file (`legacy/index.md`, status: deprecated) declaring the v0.x suite as superseded "history, not authority", readable for understanding decision history. The archive promises three properties, but only one is mechanized:

1. **Read-only for history** — declared in guard file. OK by convention.
2. **Not editable** — NOT mechanized (allowed under OP-1 "no gates" as discipline-only, but is there a cheap honest mechanism?).
3. **Not audited** — NOT mechanized and this is a live defect: `tools/check_all.py` contains zero references to `legacy`/`archive`/`skip`; the last run produced 32 findings, 28 from `legacy/` (ambiguous/unresolved cross-refs in superseded docs). The guard contract says "history, not authority" but audit applies live-document rules to the tombstone — a prose-contract divergence (AGENTS.md §1.7).

**Goal:** design a full, reusable Archive concept for the Documenter — not a one-off patch for `documenter-service/legacy/`. Decide: what an archive is in this repository, what guarantees it carries (audit exclusion, edit posture, translation duty, manifest treatment), how it is recognized mechanically by the tools, and where the boundary lies against OP-1 (no gates) and OP-2 (≤12 files / ~3,600 LOC tooling, displacement-only promotion, one operator-facing command).

## Repository facts (verified 2026-11-19)

- `tools/check_all.py`: read-only audit engine, frozen exit-code contract (0 clean / 1 findings / 2 critical), advisory only, never gates. Walks `docs/en` (+`docs/ru` for mirrors). No archive exclusion exists.
- Current audit run: 32 findings, ALL low severity; 28 in `docs/en/documenter-service/legacy/*.md`, 2 in `docs/en/scenario/index.md`, 2 in `docs/en/service-contract/error-management.md`.
- Tooling LOC: 3,459 total across `tools/*.py` — OP-2 ceiling ~3,600 is nearly consumed; any growth must be displacement.
- `gen_manifest.py` tracks legacy docs as normal entries (status: deprecated available in manifest vocabulary).
- Existing archive-like locations: `docs/en/documenter-service/legacy/` (manifest-tracked, git tombstone), `archive/sessions/<id>/` (operational, outside Documenter, per fallback/index.md §Session workspace convention), `docs/en/documenter-service/legacy/` RU mirror at `docs/ru/documenter-service/legacy/spec-v0-RU.md`.
- Guard file rules (legacy/index.md): do not execute/cite/delete; git history is recovery path; folder is "readable tombstone".
- OP-1: instant operator approval, no gating. OP-2: simplicity ceiling, displacement rule. OP-3: post-commit audit + `git revert` as error control.
- documentation-rules §2.1–2.5 define layout, manifest, changelog; §8 compliance. Status vocabulary includes `deprecated`.
- Single-commit invariant: one logical update = one atomic commit (basis of revert recovery).

## Subject list

- SUBJ-001: **Audit exclusion mechanism** — how/whether `check_all.py` excludes archived documents from the check battery (path convention? frontmatter status? manifest flag?), and what residual checks (if any) still apply to archives.
- SUBJ-002: **Edit posture of archives** — under OP-1 there are no gates; what is the honest mechanism for "not editable" (discipline + audit signal vs. hook warn vs. tool-enforced refusal in skill dispatch)?
- SUBJ-003: **Manifest and discoverability** — should archived docs stay manifest-tracked (status: deprecated) or leave the manifest; how agents discover and read archives on demand.
- SUBJ-004: **Archive as a general concept** — location/naming convention for any future archive (`legacy/` per-document? top-level `docs/archive/`? operational `archive/` reuse?), guard-file requirements, RU mirror duty, deletion policy (guard says "do not delete").
- SUBJ-005: **OP-2 budget and displacement** — cost of the chosen mechanism in tooling LOC; what gets displaced or simplified to pay for it.
- SUBJ-006: **Migration of existing legacy content** — moving/renaming current `documenter-service/legacy/` (and its RU mirror) under the chosen convention; single-commit implications.

## Constraints

- No new gates, daemons, state or config files (OP-1, OP-2).
- Tooling growth only via displacement; single operator-facing command `check_all.py` preserved.
- `check_all.py` remains read-only and advisory; exit codes informational.
- Fallback documents themselves are frozen (AGENTS.md §1.5) — do not propose changes to `fallback/`.
- Any final change must land via Documentation Worker skill with operator approve (OP-1), single atomic commit.

## Output limits

Each role: one review document per fallback/index.md §Output Structure (Summary Position, Key Findings with severity + subject refs, Recommendations, Open Questions, Status, Escalation Reason if applicable). ≤ 120 lines. Critical findings require named failure mode + subject id.
