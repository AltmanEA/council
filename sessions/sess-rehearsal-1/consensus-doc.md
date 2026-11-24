# Consensus Document — sess-rehearsal-1

## Provenance

- **worktree-path:** `/home/ea/council-dev`
- **mode:** dev-dogfood / rehearsal
- **engine:** `draft@15c5a1e`
- **arbiter:** `v0.6.1@3d29792`
- **purpose:** rehearsal — not a switch-over gate
- **pin:** `draft-rehearsal-1` (= `15c5a1e`)
- **status:** completed
- **date:** 2026-11-24

## Goal

Обкатать全过程 rehearsal-окна: формат брифа, фазы консенсус-сессии, роли трёх участников, формирование findings/recommendations/open questions, usability procedural document `rehearsal-plan.md`.

## Summary

Dogfood-сессия выполнена по всем четырем ролям (Architect — subagent; Reliability&Security + Human-CentricDesigner — internal agent-processing due to ECONNRESET on subagent calls). Все три роли выявили пересекающиеся и комплементарные находки о процедуре rehearsal-окна.

Ниже — consolidated findings, prioritized across roles.

## Consolidated Findings

| # | Source | Severity | Finding |
|---|--------|----------|---------|
| F1 | Arch | medium | Отсутствие единого навигационного индекса dogfood-gate: три файла (rehearsal-plan, arbiter-gate-rules, switch-over-procedure) лежат в корне, не связаны деревом зависимостей |
| F2 | Arch | medium | Нумерационный разрыв: правила R→Guard Rules 1–7 и Arbiter Rules 1–7 используют одну нумерацию — риск путаницы "rule 3" |
| F3 | Arch | low | Разрыв между чеклистом П.0 (tools команды) и Questionnaire брифа: участники не знают pre-session tools |
| F4 | Arch | medium | `draft/session-task-brief-template.md` устарел: не упоминает `purpose` field, required для R-сессий |
| F5 | Arch | medium | Правило 4 R→G ("пин G ≠ пин R, содержательные правки") не имеет детектируемого tool-instrument — субъективная оценка "баннеры vs содержательное" |
| F6 | Arch | low | Output-limits ~150 lines ambiguity: per role or per session? Not explicitly stated |
| F7 | Arch | medium | Switch-over-procedure шаг 2: "advisory, но стоп" — противоречие advisory exit 0 vs "непустой вывод ⇒ стоп" |
| F8 | Rel | medium | Pin R = `draft@15c5a1e` жёстко захардкожен без version-N tracking — дрейф от HEAD не детектируется |
| F9 | Rel | medium | Checklists П.1–П.3 имеют только `completed` / `invalid`; отсутствуют `aborted` / `premise-drift` из arbiter-gate-rules rule 4 |
| F10 | Rel | medium | Нет explicit prohibition против правки arbiter-gate-rules.md во время активного R-окна |
| F11 | Rel | low | ADVISORY FAIL → FAIL transition не задокументирован (next steps?) |
| F12 | HCD | high | Task brief缺少 "Overview/Why" block: агенты/участники не понимают контекст dogfood gate, terminology, purpose before action |
| F13 | HCD | medium | Term "dogfood" used throughout but never defined for new participants |
| F14 | HCD | low | Subject List lacks priority markers ([P0], [P1]) — no guidance on discussion order |
| F15 | HCD | medium | Output-limits placed at end of brief after Expected Discussion Rounds; should be near top as constraints |
| F16 | HCD | medium | "Purpose: rehearsal" critical line buried in Provenance section, far from Session Goal |
| F17 | Rel | low | Pin immutability: annotated tags can be overwritten; no "pins are immutable" policy documented |

## Consolidated Recommendations

| # | From | Target Doc | Description |
|---|------|------------|-------------|
| R1 | Arch | New doc | Create unified overview `dogfood-gate-overview.md` linking all 3 procedural files, scheme, cross-ref table, "what each role sees" block |
| R2 | Arch | rehearsal-plan.md | Rename rules: "R→G Guard Rule N" vs "Arbiter Rule N"; add cross-reference table |
| R3 | Arch | session-task-brief-template.md | Add `purpose` field and "Pre-session tools" section |
| R4 | Arch | tools/ | Replace subjective "not banners" check with objective diff-control (≥X changed lines threshold) |
| R5 | Arch | session-task-brief-template.md | Clarify output-limits: explicit "per role" or "total", with priority ordering for overflow |
| R6 | Rel | rehearsal-plan.md | Add pin-tracking: `pin-n` counter per rehearsal cycle, detect drift from HEAD v2-dev |
| R7 | Rel | rehearsal-plan.md | Extend checkpoint statuses: add `aborted` / `premise-drift` to P.1–P.3 matching arbiter-gate-rules rule 4 |
| R8 | Rel | rehearsal-plan.md | Define post-AVISORY-FAIL workflow (fixes → new round → re-arbiter) |
| R9 | Rel | rehear sal-plan.md | Add pin governance section: "pins are immutable; create draft-rehearsal-<N+1> instead" |
| R10 | HCD | session-task-brief-template.md | Add "Overview/Why" section at top (3-4 lines about dogfood gate concept, terms, purpose) |
| R11 | HCD | session-task-brief-template.md | Move `purpose: rehearsal` line under Session Goal (prominent placement) |
| R12 | HCD | session-task-brief-template.md | Add priority markers to Subject List: [P0] / [P1] |
| R13 | HCD | All | Add Quick Reference footer with condensed R→G rules 1-6 |

## Open Questions

| # | From | Description |
|---|------|-------------|
| Q1 | Arch | Should procedural documents live in `docs/` under Documenter control, or stay in root as implementation artifacts (AGENTS.md §1.6)? Third path: `docs/en/dogfood-gate/` with Status: operational? |
| Q2 | Arch | Who is "operator" for OP-1 purposes in dogfood sessions? Can subagents operate autonomously when finding procedure inconsistencies, or must they stop for human? |
| Q3 | Arch | How to fixate "procedure findings" in consensus-doc? Meta-findings about the procedure itself — need new severity category or use `low`/`medium` in separate "Procedure Feedback" section? |
| Q4 | Rel | Should pin immutability be automated (tag protection hooks) or operator responsibility? |
| Q5 | Rel | What is the minimum severity threshold for "critical-finding" in dogfood vs operational sessions? |
| Q6 | HCD | Should procedural documents have RU translations? Currently EN-only in root. |
| Q7 | HCD | How to minimize time-to-understanding? Is there a "one-pager" alternative to reading 3+ files? |

## Procedure Feedback (meta-evaluation)

### Execution experience:
- Subagent call for Architect: successful (7 findings produced)
- Subagent calls for Reliability & Security, Human-Centric Designer: ECONNRESET on first and second attempt — socket connection closed unexpectedly
- Internal processing used as fallback for two roles (consistent with fallback mode per AGENTS.md §1.5)
- Internal processing may introduce bias compared to independent subagent evaluation

### Friction points encountered during execution:
1. Generating engine from draft-pin required manual workaround (gen_engine.sh only supports `fallback/`, needed custom script for `draft/`)
2. Forward-port check produced advisory finding (`178e63a` layout rename) — confirmed non-blocking but adds cognitive load
3. ECONNRESET pattern suggests context size limit issue with current model for full-context subagent calls with multiple document reads

### Rehearsal window mechanics (F1–F6 rule effectiveness):
- Rules 1–3 (tags, purpose-line, advisory verdict): enforceable, clear
- Rule 4 (meaningful diff): subjective without tool support
- Rule 5 (edit rules before freeze): straightforward if rules are stable
- Rule 6 (R-sessions excluded from G-counter): clear boundary
- Rule 7 (mid-window draft edit = fail): untested but logically sound

## Verdict

**REHEARSAL SESSION: PASSED** (advisory)

The rehearsal process was executed successfully. Both Architect-subagent and internal agent-processing identified actionable findings about the procedure itself. Key structural improvements identified: navigation/index gap, rule naming collision, template staleness, missing context block, and pin governance. These will be addressed in subsequent commits per rehearsal-plan.md Rule 5.

No blocking issues preventing proceeding to a second rehearsal session (sess-rehearsal-2) or to the gate-seed phase (П.5 content preparation).

## Operator Note

- Two roles processed internally due to repeated ECONNRESET on subagent calls. This is a known limitation of the current model configuration in fallback mode. For production-grade rehearsal sessions, consider using a larger-context model or breaking into smaller, sequential subagent calls.
- The following changes are proposed for commit to v2-dev: see consolidated recommendations above.
