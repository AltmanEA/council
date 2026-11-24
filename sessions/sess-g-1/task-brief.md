# Task Brief — sess-g-1

> `MODE: dev-dogfood/v2@ec0caa7`

## Overview / Why

Окно G (настоящий gate) — 3–5 completed-сессий на едином пине черновика, доказывающие, что черновик v2 **выполним на себе** (arbiter-gate-rules rule 5). Это первая сессия окна G. Она не является репетицией: вердикт окна будет `PASS/FAIL` (не ADVISORY).

## Provenance

- **worktree-path:** `/home/ea/council-dev`
- **mode:** dev-dogfood
- **engine:** `draft@ec0caa7`
- **arbiter:** `v0.6.1@3d29792`
- **pin:** `draft-freeze-1` (= `ec0caa7`)
- **session-number:** 1 of 3–5 in gate window G

## Task Complexity Assessment

- [x] D1: Files ≤ 3 → YES (draft/index.md, draft/session-complexity-threshold.md, session-task-brief-template.md)
- [x] D2: Lines ≤ 50 → NO (≈250 lines total)
- [x] D3: Directories ≤ 2 → YES (draft/, sessions/sess-g-1/)
- [x] D4: Roles ≤ 3 → YES (Core only)

Classification: **Moderate** → analyzer enabled by default (this session tests the analyzer contract itself).
analyzer_enabled: **auto**
Operator note: analyzer recommendation = Core only (Extended roles not required for a protocol self-review; rationale recorded in review-analyzer.md).

## Session Goal

Проверить выполнимость нового раздела `draft/index.md` §Pre-Phase 0 на самой себе: проходит ли сессия Pre-Phase 0 (анализатор + классификация сложности + артефакты) без внутренних противоречий, и однозначны ли формулировки контракта.

## Focus Areas

- Однозначен ли JSON-контракт анализатора (все поля обязательны? схема валидна?).
- Корректна ли классификация сложности (4 измерения покрывают ли реальные кейсы?).
- Fail-safe поведение: что реально происходит при невалидном JSON — описано ли однозначно?
- Meta-task exemption применим ли к этой самой сессии (рекурсия)?

## Questionnaire per Role

**Architect:**
- Q1: Противоречит ли Pre-Phase 0 существующим фазам 1–5?
- Q2: Достаточно ли декларативен контракт для машинной валидации?

**Reliability & Security Specialist:**
- Q1: Закрыт ли prompt-injection вектор через locked Core на практике?
- Q2: Fail-safe при сбое анализатора — воспроизводим ли он детерминированно?

**Human-Centric Designer:**
- Q1: Понятен ли operator manual checklist без чтения protocol-core?
- Q2: Не создаёт ли analyzer лишний когнитивный burden для простых задач?

## Output Limits
- findings: 3–5, recommendations: 2–3, open questions: 1–2, per role.
- Prioritize structural > integration > detail.

## Expected Discussion Rounds
1 (Moderate).

## Subject List
- [P0] SUBJ-001: корректность JSON-контракта анализатора
- [P0] SUBJ-002: полнота классификации сложности (4 измерения)
- [P1] SUBJ-003: fail-safe поведение анализатора
- [P1] SUBJ-004: meta-task exemption и рекурсия
- [P2] SUBJ-005: burden analyzer на простых задачах

## Additional Context / Constraints
- Пин окна G: `draft@ec0caa7` (draft-freeze-1). Правка draft/ внутри окна = FAIL окна.
- OP-1/OP-2/OP-3 apply.
- Subagents могут падать (ECONNRESET) → internal processing fallback с раскрытием в consensus.
