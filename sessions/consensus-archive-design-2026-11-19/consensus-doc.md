# Consensus Document — Full Archive Organization for the Documenter

Session: sess-archive-design-2026-11-19 (fallback mode, sequential execution per operator instruction)
Mode: Subagent Fallback v0.6.0, 4 roles (Architect, Reliability & Security, Human-Centric Designer, Operations Engineer), 1 discussion round + peer confirmation round.
Moderator: operator-substituted (fallback).

## Decision

The Documenter adopts a first-class **Archive** concept: `docs/en/archive/<id>/` (+ mirrored `docs/ru/archive/<id>/`), recognized by a dual-layer mechanism, excluded from the audit battery by path prefix, tracked in the manifest via a genuine frontmatter field, and guarded by a root guard file. The existing `docs/en/documenter-service/legacy/` migrates to `docs/en/archive/documenter-service/` in one atomic commit.

## Rationale

The current `legacy/` guard file promises three properties (read-only-for-history, not editable, not audited) but mechanizes only the first; `check_all.py` has no archive awareness and floods the audit with 28 low findings from superseded documents — a prose-contract divergence per AGENTS.md §1.7. The design closes the gap at minimum cost consistent with OP-1 (no gates), OP-2 (no new tools/config/state, headroom verified), OP-3 (revert as error control).

## Subjects with outcomes

| Subject | Outcome | Decision |
|---------|---------|----------|
| SUBJ-001 Audit exclusion | agreed | Path-prefix skip in `tools/check_all.py`: a single `_ARCHIVE_SKIP` prefix constant (`docs/en/archive/`, `docs/ru/archive/`) filters files before every check pass (~20 LOC). Applies to all current and future battery members. No info line in audit output — the frozen `clean is silent` rendering contract is untouched. |
| SUBJ-002 Edit posture | agreed | No gates (OP-1). Deterrent = Documentation Worker skill: manifest-aware check before any write to an archive path (~10–25 LOC of skill contract prose), surfaced on the Approval Card via `Archive: <N files entering/archived>` line. Residual smuggling risk accepted under OP-3 (card catches it at approve time; revert recovers). |
| SUBJ-003 Manifest & discovery | agreed | Archived docs stay manifest-tracked. Recognition is dual-layer: `Status: archive` frontmatter field (manifest truth per §2.2; `gen_manifest.py` prints it, ~5 LOC) + path-prefix skip in the audit (enforcement net). No consistency checker between the two layers (OP-2; drift caught informally). |
| SUBJ-004 General convention | agreed | New top-level convention `docs/en/archive/<id>/` + RU mirrors at `docs/ru/archive/<id>/`; a root guard file `docs/en/archive/index.md` states the convention (history only, not authority, not to be deleted). Per-document `legacy/` folders are superseded by this convention. Status vocabulary gains `archive` (distinct from `deprecated`). |
| SUBJ-005 OP-2 budget | agreed | Executable tooling verified at 3,459 LOC (Ops' 3,693 included README.md 105 + sync_translator.sh 129, excluded by spec's 'executable tooling only'). Feature cost ~50 LOC → 3,509 < 3,600 ceiling. **No displacement required.** |
| SUBJ-006 Migration | agreed (conditionally) | Move `docs/en/documenter-service/legacy/` → `docs/en/archive/documenter-service/`, RU mirror likewise, root guard file, cross-reference fixes corpus-wide, status changes, manifest regen — all in ONE atomic commit (single-commit invariant). Intermediates allowed only in gitignored `sessions/` area per §Complex edits. |

## Role reservations (tied to subjects)

- **Reliability (SUBJ-001/002):** archive-smuggling is the accepted critical residual — any file placed under `archive/` becomes audit-blind. Mitigations are the Approval Card `Archive:` line at the approve moment and `git revert`; both are judgment-based, not gating, per OP-1.
- **Reliability (SUBJ-001):** future battery members (controlled-file deletion, translation staleness) MUST inherit the `_ARCHIVE_SKIP` filter — record in the spec's check table footnote at implementation.
- **HCD (SUBJ-002):** the skill must be genuinely manifest-aware before the warning is trustworthy; today it is not. The card line replaces a conditional line to stay within the 10-line budget.
- **Operations (SUBJ-001):** transparency deliberately routed away from `check_all.py` output to preserve the frozen rendering contract (spec ~lines 29/44/55, hook consumption); pre-commit hook is not installed and cannot carry archive enforcement.
- **Operations (SUBJ-006):** migration surface ~10 status files, 4 RU mirrors, 8 changelog paths (6 share the root `documenter-service.changes.md`, unchanged), corpus-wide cross-ref fixes; grep corpus first, fix atomically.

## Open questions

1. Should `Status: archive` also stop translation-staleness expectations for existing RU mirrors (spec table currently implies RU duty for all documents)? Deferred to implementation session.
2. Should `deprecated` remain usable for non-archived docs, or converge on `archive` only for superseded material? Editorial, implementation session.

## Action items (each via Documentation Worker skill, operator approve, single commit per logical update)

1. **Spec amendment** — `docs/en/documenter-service/index.md`: add Archive section (convention, dual-layer recognition, skip contract, card line, accepted smuggling risk; note future checks inherit skip). (+ RU mirror alignment)
2. **Rule amendment** — `docs/en/documentation-rules/index.md` §2: archive layout convention + `Status: archive` vocabulary. (+ RU mirror)
3. **Tooling** — `tools/check_all.py`: `_ARCHIVE_SKIP`; `tools/gen_manifest.py`: print `Status: archive`; tests for both.
4. **Skill** — `.agents/skills/documentation/SKILL.md`: archive-aware write check + Approval Card `Archive:` line (card-contract tests updated in same changeset).
5. **Migration** — move `documenter-service/legacy/` → `archive/documenter-service/` (+RU), create `docs/en/archive/index.md` guard, fix cross-refs (incl. AGENTS.md — operational file, operator edit), regenerate manifest.

Order: 1–2 (norms) → 3–4 (mechanics) → 5 (migration). Items 3–5 depend on norms landing first.

## Critical findings downgraded for invalid justification

None.

## Escalations

None. Final statuses: all four roles `agree`. **Resolved.**
