# Consensus Document — sess-new-version-dev-start

**Session:** sess-new-version-dev-start
**Date:** 2026-11-23
**Mode:** Fallback (fallback/index.md), 4 roles, 1 discussion round
**Verdict:** Conditionally resolved, с двумя операторскими решениями (disagreement flags)

---

## Decision (консенсус всех ролей)

1. **SUBJ-001 — git worktree для v2.** Разработка новой версии режима консилиумов ведётся в отдельном worktree (`council-dev/`, имя с `-dev` — точнее передаёт жизненный цикл) на ветке `v2-dev`. Основной workspace (`/home/ea/council`, master) остаётся единственной операционной средой с v1. Все альтернативы (версионированный каталог в main, develop-in-place со status-флагом, отдельное пространство в том же worktree) отвергнуты: неоднозначность маршрутизации агентов + отсутствие защиты v1 от записи.

2. **SUBJ-003 — Защита v1: процедурная, честно задокументированная.** Технического bar'ьера при OP-1 нет (теги и `chmod -w` — не защита записи / ритуал; отклонено 3:1). Guard'ы: явная запись в AGENTS.md («не модифицировать fallback/ вне root»), git-tracked маркер `fallback/.frozen` («DO NOT MODIFY — see AGENTS.md §1.5»), баннеры в первых 3 строках каждого fallback-документа:
   - v1: `⚠️ РАБОЧАЯ ВЕРСИЯ v0.6.0 — ЗАМОРОЖЕНА`
   - v2: `🚧 РАЗРАБАТЫВАЕМАЯ ВЕРСИЯ — НЕ ОПЕРАЦИОННЫЙ РЕЖИМ`
   В frontmatter — поля `council-version`, `council-worktree`; в task-brief — обязательные `worktree-path`, `mode`.

3. **SUBJ-004 — Якоря и switch-over без revert.** Перед ветвлением: тег `v1-stable` на HEAD master → ветка `v2-dev` от тега → тег `v2-pre-dev` → создание worktree → запись v2-AGENTS.md. Switch-over v2→production: cherry-pick логических коммитов в master (прозрачный аудит) или branch-based возврат (`checkout master` = откат к v1); `git revert` — только для ошибок в master (на shared-репо задевает оба worktree). Незавершённые v1-сессии на момент switch: дождаться / архивировать как incomplete с archival-note.

4. **SUBJ-005 — Полный наследник.** v2-dev содержит полный набор `fallback/` (index.md + все auxiliary: task-brief-template, consolidation-prompt, koda-execution-mode), а не delta.

5. **SUBJ-002 — AGENTS.md per-worktree с правилом синхронизации** (см. решение оператора №2). Root: `MODE: fallback-v1`; v2-dev: `MODE: v2-development` с путями на v2-документы. Правило: файлы идентичны, кроме блока §1.5 — расхождение проверяется diff'ом (кастомизировать `tools/check_drift.py` или аналог). Контекстная проверка при старте сессии — лёгкий чек-лист в task brief (`pwd` = ожидаемый worktree; `git status fallback/` чист), warn+confirm, не abort (OP-1).

6. **SUBJ-006 — Аудит (OP-3).** Ветки + теги + один логический коммит на изменение; причина каждого изменения v2 — ссылка на consensus-документ сессии в сообщении коммита.

## Subjects with outcomes

- SUBJ-001: agreed (worktree)
- SUBJ-002: conditionally agreed — ждёт решения оператора №2
- SUBJ-003: conditionally agreed — процедурная защита принята как сознательный компромисс OP-1/OP-3
- SUBJ-004: agreed (процедура 5 шагов, cherry-pick switch-over)
- SUBJ-005: agreed (полный наследник)
- SUBJ-006: agreed

## Role reservations

- **Reliability (concerns):** настаивает на резолюции узла №2 до первого коммита v2; требует явной формулировки «v1 защищён политикой, не git-config»; требует merge-стратегию до первого коммита.
- **Operations (agree):** открытые вопросы — проверка незавершённых сессий перед switch; синхронизация AGENTS.md после слияния v2→master (нужна ли ветка v2-production).
- **HCD (concerns):** приемлет упрощённый вариант при отказе оператора от изоляции sessions (фильтр по `worktree-path` в task-brief); оверхед от копирования auxiliary считает оправданным.
- **Architect (agree):** предпочёл префиксные подкаталоги sessions (см. решение оператора №1); внешние глобальные пути считает нарушением OP-2 и аудируемости.

## Disagreement flags — требуется решение оператора

**Узел №1: изоляция `sessions/` (SUBJ-001/003).** Три позиции:
  - **A. Per-worktree (рекомендация модератора, позиция HCD):** каждый worktree имеет собственный `sessions/` (это естественно для worktree — разные рабочие директории). 46 существующих сессий остаются в root; в council-dev они видны как история ветки, но операционные сессии v2 пишутся в council-dev/sessions/. Нулевая миграция. Риск: агент v2 может прочитать исторические v1-сессии (артефакты, не процедуры — низкий риск; смягчается полями `mode`/`worktree-path` в task-brief).
  - **B. Префиксные подкаталоги в репо (Architect):** `sessions/v1/`, `sessions/v2-dev/` в одном корне. Явная аудируемость, но требует миграции 46 сессий и не даёт физической изоляции.
  - **C. Глобальный путь `~/.opencode/council-sessions/` (Operations):** вне git; миграция `mv` одной командой; минус — пути сессий исчезают из git-аудита (контраргумент Architect).

**Узел №2: маршрутизация AGENTS.md (SUBJ-002).** Две позиции:
  - **A. Двойная AGENTS.md + sync-правило (рекомендация модератора; Architect, Operations, HCD):** свой экземпляр в каждом worktree, различие только в §1.5, расхождение контролируется diff-инструментом. Риск Reliability (рассинхрон) смягчен проверяемым правилом.
  - **B. Единая AGENTS.md + перемещение v1 fallback → `archive/frozen/` (Reliability):** физическая недоступность v1-путей; но требует аккуратности: перемещение допустимо только в ветке v2-dev (в master v1 обязан оставаться рабочим), и оно не блокирует чтение root-файлов по абсолютному пути — то есть «физическая недоступность» частична.

## Open questions (не блокирующие)

1. Проверить наличие незавершённых сессий (без consensus-doc.md) до switch-over.
2. Синхронизация AGENTS.md после слияния v2→master: обратная разметка режима / ветка v2-production.
3. Длительность параллельного существования v1/v2 (дни vs месяцы) — влияет на нужную строгость контролов.

## Action items (после approve оператора, все — обычные git-коммиты, не Documenter-зона)

1. `git tag v1-stable` → `git branch v2-dev v1-stable` → `git tag v2-pre-dev v2-dev`.
2. Создать worktree `council-dev` (ветка v2-dev); скопировать полный `fallback/` + auxiliary.
3. Баннеры + frontmatter-поля во все fallback-документы обеих версий; `fallback/.frozen` в root.
4. AGENTS.md: §1.5 root + §1.5 v2 (MODE-маркеры), запись о worktree как НЕ операционном источнике (root), sync-правило §1.5.
5. Изоляция sessions по выбранному варианту узла №1.
6. Чек-лист контекста (3 пункта) в шаблон task brief.
7. Перенести freeze-формулировку в честную констатку: «политика, не технический контроль».

## Downgraded critical findings (transparency)

- «Теги/проза не защищают запись» (Reliability, critical) — переклассифицирован консенсусом в принятый residual risk OP-1 (документируется явно), не снят.
- «chmod -w» (Operations, из первоначальных рекомендаций) — отклонён консенсусом 3:1 как ритуал.

## Escalations

 blocked-escalation нет. Формальные disagreement-флаги по узлам №1–2 переданы оператору согласно Conflict Aggregation Rules п.2.
