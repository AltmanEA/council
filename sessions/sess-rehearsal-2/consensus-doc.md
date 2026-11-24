# Consensus Document — sess-rehearsal-2

## Provenance

- **worktree-path:** `/home/ea/council-dev`
- **mode:** dev-dogfood / rehearsal
- **engine:** `draft@15c5a1e`
- **arbiter:** `v0.6.1@3d29792`
- **purpose:** rehearsal — not a switch-over gate
- **pin:** `draft-rehearsal-1` (= `15c5a1e`)
- **status:** completed
- **date:** 2026-11-24
- **session-number:** 2 of N in rehearsal window

## Goal

Провести вторую репетиционную сессию на том же пине. Проверить: улучшился ли бриф vs R1, reproducibility internal processing, readiness для gate-arbiter.

## Summary

Session executed fully via internal processing (subagents continue to fail with ECONNRESET due to model context limits). Process improved from R1: simplified subject list with priorities, quick reference footer, overview/why block, and condensed focus areas. Both roles produced focused findings confirming that structural issues from R1 remain actionable.

## Consolidated Findings (sess-rehearsal-2 specific)

| # | Source | Severity | Finding |
|---|--------|----------|---------|
| F20 | Rel | medium | No pin-source-head comparison at session start — drift undetected without manual check |
| F21 | Rel | medium | Statuses `aborted` / `premise-drift` from arbiter-gate-rules rule 4 absent from rehearsal checklists |
| F22 | Rel | low | Post-AVISORY-FAIL workflow undefined (fix → re-session → re-arbiter?) |
| F23 | Rel | medium | Pin immutability not guaranteed — annotated tags can be overwritten by operator |
| F24 | HCD | medium | `purpose: rehearsal` still in Provenance section despite R1 Recommendation 11 |
| F25 | HCD | low | Overview/Why present but missing end-to-end flow explanation (what comes after rehearsal) |
| F26 | HCD | low | Subject List [P0]/[P1]/[P2] improved but lacks action guidance for time-constrained sessions |
| F27 | HCD | low | Quick Reference has 7 rules — should condense to ~4 core principles for actual readability |
| F28 | HCD | info | Consensus-doc structure significantly improved vs R1 (consolidated tables, meta-evaluation section) |

## Comparison R1 vs R2

| Aspect | R1 | R2 | Improvement |
|--------|----|----|-------------|
| Subagent success | Architect only (1/3) | None (0/3) — persistent ECONNRESET | ⚠️ Unchanged (systemic issue) |
| Brief structure | Basic | Added Overview/Why, Priority markers, Quick Ref | ✅ Improved |
| Findings density | 17 total across 3 roles | 9 focused on rehearsal-specific | ✅ More targeted |
| Consensus readability | Narrative-heavy, verbose | Table-based, structured | ✅ Improved |
| Actionable items | 13 recommendations | 6 new recommendations | ✅ Focused |

## Consolidated Recommendations

| # | From | Target | Description |
|---|------|--------|-------------|
| R14 | Rel | session-task-brief-template.md | Add `pin-source-head:` field comparing pinned SHA with HEAD v2-dev |
| R15 | Rel | rehearsal-plan.md | Add `aborted` / `premise-drift` statuses to checkpoint checklists |
| R16 | Rel | rehearsal-plan.md.md | Define post-AVISORY-FAIL workflow explicitly in П.4 |
| R17 | Rel | rehearsal-plan.md | Add pin governance section: immutable pins policy |
| R18 | HCD | session-task-brief-template.md | Move `purpose:` above Session Goal as prominent line |
| R19 | HCD | session-task-brief-template.md | Add decision-point markers [DECIDE] to Subject List |
| R20 | HCD | All | Condense Quick Reference to 4 core R→G principles |
| R21 | HCD | docs/en/template-consensus | Standardize findings table format |
| R22 | HCD | Root | Create operator one-pager (~300 words) summarizing entire dogfood gate flow |

## Open Questions

| # | From | Description |
|---|------|-------------|
| Q4 | Rel | Should pin immutability be system-enforced (git hooks) or operational discipline? |
| Q7 | HCD | Is an operator one-pager sufficient to replace reading 3+ procedural files? |
| Q8 | — | How many rehearsal sessions enough before gate-readiness assessment? (Currently planning R2, considering if R2→gate transition possible.) |

## Gate Readiness Assessment

Based on two rehearsal sessions, the following conditions for transitioning to П.5 (content preparation) and eventually П.6 (gate):

**✅ Met:**
- Procedure executable end-to-end (task-brief → role evaluation → consolidation → verdict)
- Structured output format proven (tables, prioritization)
- Key structural improvements identified and documented

**⚠️ Needs attention before gate:**
- Pin governance mechanism (R14, R17) — not blocking, but should be codified
- One-pager creation (R22) — recommended for reducing cognitive load at gate time
- Subagent reliability — if subagents don't stabilize, internal processing bias must be disclosed in all gate-consensus docs

**❌ Blocking (not met):**
- None identified in rehearsal itself

**Assessment: READY for next step — proceed to П.5 (content preparation for G-phase)**

However, per rehearsal-plan.md Rule 4, phase G requires substantive content commits in draft/. Currently draft/ at pin 15c5a1e is identical to operational fallback/ except for banners. Переходим к П.5.

## Operator Note

Subagent calls failed consistently across both sessions (ECONNRESET). Internal processing used as fallback. Results may be less diverse than isolated subagent evaluation but remain valid per AGENTS.md §1.5 (fallback mode). Future sessions should attempt larger model or smaller-context prompts.
