# Task Brief — sess-g-2

> `MODE: dev-dogfood/v2@ec0caa7`

## Overview / Why

Окно G — доказательство выполнимости черновика v2 на себе. G-2 валидирует §Task Complexity Threshold (`draft/session-complexity-threshold.md`) эмпирически: прогоняет 4-измеренческий классификатор на реальных исторических сессиях и проверяет, не даёт ли он абсурдных классификаций.

## Provenance

- **worktree-path:** `/home/ea/council-dev`
- **mode:** dev-dogfood
- **engine:** `draft@ec0caa7`
- **arbiter:** `v0.6.1@3d29792`
- **pin:** `draft-freeze-1` (= `ec0caa7`)
- **session-number:** 2 of 3–5 in gate window G

## Task Complexity Assessment

- [x] D1: Files ≤ 3 → YES (threshold.md, sess-branch-version-strategy brief, sess-council-role-selection brief)
- [ ] D2: Lines ≤ 50 → NO (~200 lines)
- [x] D3: Directories ≤ 2 → YES (draft/, sessions/)
- [x] D4: Roles ≤ 3 → YES (Core)

Classification: **Moderate**

analyzer_enabled: **false**
Operator note: META-TASK EXEMPTION applies (validating the analyzer/classifier procedure itself → recursive dependency per §Meta-task Exemption). Core-only roster.

## Session Goal

Эмпирически проверить классификатор сложности: прогнать его на 3–4 реальных исторических сессиях (sess-branch-version-strategy, sess-council-role-selection, sess-new-version-dev-start, sess-rehearsal-1/2) и зафиксировать, корректны ли классификации и не возникают ли спорные кейсы.

## Focus Areas

- Покрывают ли 4 измерения (D1–D4) реальные кейсы? Какие сессии классифицируются неверно?
- Правило классификации (all-Simple / any-Moderate / any-Complex-or-2moderate) — даёт ли оно разумные результаты?
- Meta-task exemption применим ли корректно к этой и к G-1 сессиям?
- Edge cases: сессия с 1 огромным файлом; сессия со многими мелкими; meta-задача.

## Questionnaire per Role

**Architect:**
- Q1: Достаточно ли измерений D1–D4 для разделения Simple/Moderate/Complex?
- Q2: Не пропущено ли измерение (например, число SUBJ-предметов)?

**Reliability & Security:**
- Q1: Можно ли манипулировать классификацией, раздув task-brief (D2) намеренно?
- Q2: Meta-task exemption — можно ли им злоупотребить, чтобы всегда отключать анализатор?

**Human-Centric Designer:**
- Q1: Прогоняется ли checklist вручную за разумное время (≤2 мин)?
- Q2: Понятны ли пороги D2 (50/200) без примеров?

## Output Limits
- findings: 3–5, recommendations: 2–3, open questions: 1–2, per role.

## Expected Discussion Rounds
1 (Moderate).

## Subject List
- [P0] SUBJ-001: эмпирическая корректность D1–D4 на исторических кейсах
- [P0] SUBJ-002: edge cases классификатора
- [P1] SUBJ-003: манипулируемость классификации
- [P1] SUBJ-004: meta-task exemption abuse surface

## Additional Context / Constraints
- Пин окна G: `draft@ec0caa7`. Правка draft/ внутри окна = FAIL окна.
- Исторические брифы: `sessions/sess-branch-version-strategy/`, `sessions/sess-council-role-selection/`, `sessions/sess-rehearsal-1/`.
- OP-1/OP-2/OP-3 apply.
