# Task Brief — sess-g-3

> `MODE: dev-dogfood/v2@ec0caa7`

## Overview / Why

Третья сессия окна G. Проверяет §Operational Flow (Phases 1–5) и §Conflict Aggregation Rules черновика end-to-end: проводится ли полная сессия (Phase 1 → Phase 5) без потери шагов, и однозначны ли правила агрегации конфликтов.

## Provenance

- **worktree-path:** `/home/ea/council-dev`
- **mode:** dev-dogfood
- **engine:** `draft@ec0caa7`
- **arbiter:** `v0.6.1@3d29792`
- **pin:** `draft-freeze-1` (= `ec0caa7`)
- **session-number:** 3 of 3–5 in gate window G

## Task Complexity Assessment

- [x] D1: Files ≤ 3 → YES (draft/index.md, session-consolidation-prompt.md)
- [ ] D2: Lines ≤ 50 → NO (~130 lines)
- [x] D3: Directories ≤ 2 → YES
- [x] D4: Roles ≤ 3 → YES (Core)

Classification: **Moderate** → analyzer enabled → Core-only (self-review).
analyzer_enabled: **false** (meta-task exemption — analyzing the operational flow itself).
Operator note: Core-only.

## Session Goal

Провести мок-прогон Phases 1–5 на микро-задаче (выбор: должен ли consensus-doc содержать секцию `## Rehearsal mode cross-reference`?), проверяя полноту и однозначность описания фаз и Conflict Aggregation Rules.

## Focus Areas

- Phase 4 disagreement detection: «structural comparison over machine-readable fields» — реализуемо ли при markdown-артефактах fallback (нет JSON)?
- Conflict Aggregation rule 4 (convergence promotion heuristic) — слишком свободна?
- Phase 3 blocked-in-scope → resolution round — воспроизводим ли триггер?
- Полнота: все 5 фаз исполнимы без внешнего знания?

## Questionnaire per Role

**Architect:**
- Q1: Достаточно ли описания фаз для воспроизведения без protocol-core?
- Q2: Phase 4 structural comparison при markdown — есть ли machine-readable fields вообще?

**Reliability & Security:**
- Q1: Convergence promotion (rule 4) — можно ли надуть severity сговором ролей?
- Q2: blocked-in-scope триггер — можно ли использовать для DoS сессии (вечный блок)?

**Human-Centric Designer:**
- Q1: Понятен ли оператору переход Phase 4 → 5 без consolidation-prompt?
- Q2: Формат consensus-doc (7 секций) не перегружен ли для микро-задач?

## Output Limits
- findings: 3–5, recommendations: 2–3, open questions: 1–2, per role.

## Expected Discussion Rounds
1 (Moderate).

## Subject List
- [P0] SUBJ-001: полнота фаз 1–5 без внешнего знания
- [P0] SUBJ-002: Phase 4 structural comparison vs markdown артефакты
- [P1] SUBJ-003: Conflict Aggregation rule 4 (convergence promotion)
- [P1] SUBJ-004: blocked-in-scope DoS surface

## Additional Context / Constraints
- Пин окна G: `draft@ec0caa7`.
- OP-1/OP-2/OP-3 apply.
