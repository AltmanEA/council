# Task Brief — sess-rehearsal-1

## Provenance

- **worktree-path:** `/home/ea/council-dev`
- **mode:** dev-dogfood / rehearsal
- **engine:** `draft@15c5a1e`
- **arbiter:** `v0.6.1@3d29792`
- **purpose:** rehearsal — not a switch-over gate
- **pin:** `draft-rehearsal-1` (= `15c5a1e`)

## Session Goal

Обкатать全过程 rehearsal-окна: формат брифа, фазы консенсус-сессии, роли трёх участников (Architect, Reliability & Security, Human-Centric Designer), формирование findings/recommendations/open questions, проверка usability procedure `rehearsal-plan.md` изнутри.

## Focus Areas

- Работа с брифом: понятность структуры, достаточность инструкций.
- Фазы сессии (подготовка → обсуждение → consolidation → verdict): где возникают трения?
- Ролевые вопросы: релевантны ли шаблоны вопросов при obkatе процедуры?
- Output limits: 5–7 findings, 3–5 recommendations, 2–3 open questions per role — реально?
- Consensus-forming: насколько результат предсказуем? Как вербализуются расхождения?
- Механика записи артефактов: консенсус-документ, чеклисты, таймминги.

## Questionnaire per Role

**Architect:**
- Q1: Насколько архитектура procedural document (rehearsal-plan.md, switch-over-procedure.md) поддаётся навигации от первого прочтения?
- Q2: Где разрыв между описанием процедуры и реальной последовательностью действий агента?
- Q3: Достаточно ли чёткие границы между этапами R и G?

**Reliability & Security Specialist:**
- Q1: Какие single-point-of-failure в процессе rehearsal-окна? (одна сессия ломает окно?)
- Q2: Что произойдёт, если агент-оператор ошибётся в пине?
- Q3: Риск подмены R на G — насколько правила 1–6 предотвращают его?

**Human-Centric Designer:**
- Q1: Насколько естественно читается бриф новой сессии без предыдущего опыта?
- Q2: В каком месте оператор теряет нить? (шаблоны, термины, форматы)
- Q3: Достаточно ли мотивационного контекста ("зачем это") перед действиями?

## Output Limits

- Findings per role: 5–7
- Recommendations per role: 3–5
- Open questions per role: 2–3
- Total output: ~150 lines
- Language: русский

## Expected Discussion Rounds

2 rounds (medium complexity — rehearsal process is both the subject and the instrument).

## Subject List

- SUBJ-001: Format of task-brief in rehearsal mode (completeness vs brevity)
- SUBJ-002: Phase usability — can three roles independently produce structured output from one brief?
- SUBJ-003: Rehearsal window mechanics — 2–3 sessions, tracking, status transition
- SUBJ-004: Gate separation clarity — rules 1–6 prevent R→G substitution
- SUBJ-005: Tool integration — gen_engine.sh, check_engine_sync.py, check_forward_port.py in rehearsal flow
- SUBJ-006: Operator experience — first-run friction points

## Additional Context

- Fallback mode (no Moderator built yet): operator runs three subagents sequentially or in parallel, then consolidates.
- OP-1/OP-2/OP-3 apply (instant approval, maximum simplicity, commit audit + revert).
- This is a DOGFOOD session running on draft@15c5a1e — the participants will be testing the procedure they are documenting.
- REHEARSAL only: results feed into `arbiter-gate-rules.md` refinement, NOT into switch-over decisions.
