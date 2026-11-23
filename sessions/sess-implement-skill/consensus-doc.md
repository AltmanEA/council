# Consensus Document — sess-implement-skill
Дата: 2026-11-15
Режим: Subagent Fallback v0.6.0 | Раундов обсуждения: 1 (позиции повторялись, второй раунд не требуется)
Статус: **Conditionally resolved** (резервации вынесены оператору)

## Decision

Добавить скилл **`implementation`** («Implementation Worker») в `.agents/skills/implementation/SKILL.md`
(implementation file по AGENTS.md §1.6, вне Documenter). Скилл оркестрирует **последовательный**
TDD-цикл субагентов на локальной модели с жёсткими контрактами, изоляцией через git worktree,
детерминированной верификацией и эскалацией оператору.

## Subjects with outcomes

### SUBJ-001 — Структура и активация (agreed)
- Каталог `.agents/skills/implementation/`, имя `Implementation Worker`, фронтматтер `description`
  с триггером («реализация программного элемента проекта: новый модуль/инструмент/тестовый компонент»)
  и секцией **When NOT to call**.
- Матрица активации (Human-Centric, подтверждена Operations):
  - НЕ вызывать: правки ≤ 2 файлов / ≤ 50 строк, опечатки, логирование, конфиги, документация.
  - Умеренная: 1–3 новых файла, существующие тесты для модуля.
  - Сложная: > 3 файлов / новых модулей, либо у модуля нет существующих тестов.
- Активация только по явному запросу оператора на реализацию кода; скилл не подменяет
  Documentation Worker для любых файлов под `docs/`.

### SUBJ-002 — Пайплайн и роли (agreed)
Строго **последовательный** pipeline (локальная модель = 1 параллельный субагент; параллельность
отклонена Architect'ом по аргументу Operations). 4 роли, каждая — subagent `general` на локальной модели:

| # | Роль | Inputs | Outputs |
|---|------|--------|---------|
| 1 | **Test Author** | target-task.md, cycle-state.json | новые `tests/test_*.py`, `artifacts/test-files.json` |
| 2 | **Code Author** | target-task.md, test-files.json | код в целевом scope, `artifacts/code-files.json` |
| 3 | **Test Runner** | tests/, (реализация — нет; см. анти-reversed-TDD) | `artifacts/test-output-{n}.txt`, `test-results.json` (exit code, counts) |
| 4 | **Analyst** | test-results.json, test-output, diff | `artifacts/verdict.json` (pass, progress, reasons, next_steps, critical_blocker) |

- **Анти-reversed-TDD** (Reliability): тесты фазы 1 запускаются против существующего кода
  ДО написания реализации (красные тесты фиксируются как baseline ожиданий).
- Все межфазные контракты — **JSON** (не free-text, не YAML — Solution Architect: парсится даже слабой моделью).
- Каждая фаза обновляет `cycle-state.json` (checkpoint).

### SUBJ-003 — Внешний цикл основного агента (agreed)
- Состояние: `cycle-state.json` — `run_id`, `iteration`, `phase`, `status`, `fail_count`,
  `progress`, `last_exit_code`, пути артефактов, снимки промтов.
- **Двухуровневый Analyst** (Operations, подтверждено Reliability): Level 0 — скрипт
  (`python3 -m unittest` exit code, pass-count динамика, grep сигнатур); Level 1 — LLM-анализ
  только при Level 0 fail. Финальный accept — human-in-the-loop.
- Детерминированный `progress` (Operations): pass-count растёт → `improving`; diff не меняется →
  `stalled`; не улучшается ≥2 итерации → `regressing`.
- Политка уточнения промтов (Architect): `improving` — обновлять только constraints; `stalled` — пересматривать context; `critical_blocker` — немедленная эскалация.
- **Досрочное согласие оператора**: файл `operator-approve` в workspace цикла → статус
  `operator-approved`, цикл останавливается, результат принимается.
- **Checkpoint recovery**: при перезапуске незавершённый `run_id` продолжается с текущей фазы.

### SUBJ-004 — Остановка и эскалация (agreed)
- Эскалация при любом из: (a) 3 прогона без `improving` (stalled/regressing), (b) `critical_blocker`,
  (c) hard timeout 20 мин (Operations/Reliability; предупреждение оператору при >10 мин),
  (d) governance-stop `BLOCKED_GOVERNANCE`.
- `improving`-прогон не увеличивает `fail_count`.
- **Эскалационный пакет** (Human-Centric + Reliability, единый `escalation-payload.md`):
  вердикты всех прогонов; diff целевого кода; вывод Test Runner (последние 3 прогона);
  все промты цикла; гипотезы Analyst; checksum целевых файлов; причина остановки
  `TIMEOUT | GOVERNANCE | MAX_ITERATIONS`.

### SUBJ-005 — Governance (agreed, резервация R-1)
- **Path-gate** (Operations, скрипт `path-gate.sh`): каждый изменённый path проверяется
  против blacklist до применения; нарушение → мгновенная остановка `BLOCKED_GOVERNANCE`.
- Безусловный deny: `docs/`, `fallback/`, `AGENTS.md`, `CHANGELOGS/`, `defaults/`, `.opencode/`,
  `documenter_policy.yml`, `archive/`, `.agents/skills/documentation/`.
- Разрешено: **новые** файлы в целевом scope (`tools/`, `documenter-service/` Tier 0–1, `tests/test_*.py`);
  **существующие** файлы — только явно перечисленные в задаче; существующие `test_*.py` read-only
  по умолчанию (разрешение конфликта Reliability ↔ фаза 1).
- ADR-011/013: статический grep Code Author-выхода на Tier 2+ паттерны (write-хуки, registry-операции,
  Operator Surface) → immediate fail + эскалация. Запрет на изменение `documenter_policy.yml` и
  регистрацию MCP сохраняется в тексте скилла.
- **Резервация R-1 (решение оператора):** окончательный whitelist допустимых target-областей
  утверждается оператором в task brief каждой конкретной задачи (пре-гейт до запуска цикла).

### SUBJ-006 — Артефакты и окружение (agreed, резервация R-2)
- **Изоляция: git worktree на цикл** (`tools.opencode.worktree_create("impl-run-<run-id>")`,
  консенсус Operations+Architect; Reliability принимает для MVP): субагенты работают только в
  cwd worktree; merge — только через diff-review основным агентом после `pass`;
  `worktree_remove()` при завершении. Merge в репозиторий делает основной агент, только
  whitelisted-файлы, после верификации diff.
- Тестовый фреймворк: **unittest** (факт проверен); команды генерируются детекцией
  `tests/test_*.py` → `python3 -m unittest tests.<module> -v`; без `discover`.
- Артефакты цикла: `sessions/<session-id>/impl-run-<run-id>/artifacts/`; после завершения —
  архивация в `archive/sessions/<session-id>/cycle-artifacts/`, в итоговой сводке — 1 резюме.
  `__pycache__` и временные файлы — автоочистка в cleanup-фазе.
- **Резервация R-2 (решение оператора):** подтверждение политики хранения (архив vs удаление) —
  принято по умолчанию «архивировать», оператор может отклонить.

## Role reservations
- Reliability: переход на обязательный git worktree (вместе с auto-rollback) зафиксирован как
  post-MVP требование; для MVP accept diff-review.
- Operations: реальная стоимость цикла — оценка 20–30 мин на задачу (12+ запусков локальной модели).
- Architect: governance pre-gate не может быть полностью статическим — опирается на R-1.

## Open questions (для оператора)
1. R-1: подтвердить whitelist target-областей по умолчанию (`tools/`, `documenter-service/` Tier 0–1, новые `tests/`).
2. R-2: подтвердить архивацию артефактов цикла по умолчанию.
3. Имя скилла принято `implementation` — подтвердить.

## Action items
1. Написать `.agents/skills/implementation/SKILL.md` по консенсусу (после approve оператора).
2. Приложить вспомогательные шаблоны: контракты JSON (cycle-state, verdict), `path-gate.sh`, тексты промтов 4 ролей.
3. После написания — dry-run на пилотной задаче из scope ADR-011.

## Escalations resolved en route
- Конфликт «запрет tests/ vs Test Author» — разрешён раундом обсуждения (whitelist new-vs-existing).
- Критический finding Reliability (полный запрет) понижен роли: согласован new-only.

## Critical findings downgraded
- Reliability R1 «полный запрет tests/» — переквалифицирован в «read-only для существующих» (обоснование пересмотрено в Round 2, прозрачность).
