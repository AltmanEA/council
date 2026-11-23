# Session Task Brief — First External Host Launch

Session ID: sess-first-host-launch-2026-11-22
Mode: fallback (sequential local subagents, operator as Moderator)
Date: 2026-11-22
Predecessor: sess-tooling-separation-2026-11-22 (Conditionally Resolved)

## Session Goal

Определить конкретный, минимально достаточный список работ (definition of done),
которые необходимо завершить в source repo Council до установки фреймворка в
**первый внешний хост-проект** через `dist/` канал, с приоритизацией и разделением
на «обязательно до запуска» / «допустимо после».

## Context

Оператор подтвердил: внешние хост-проекты **планируются**. Предыдущая сессия
(sessions/sess-tooling-separation-2026-11-22/consensus-doc.md) приняла двухуровневую
модель: source repo — edit-in-place; downstream-хосты — pinned через dist/, lock-файлы
только внешним зависимостям. Из той сессии перенесены backlog-пункты, триггер
«первый внешний хост» для которых теперь наступил:

- sha256 в `build.sh` (решено: сейчас) и проверка хеша в `update.sh` (было backlog →
  триггер наступил);
- emergency hotfix-процедура для хоста (триггер был >1 хост — оценить заново);
- `check_core_drift.py` (advisory);
- semver для dist/ (триггер был >1 хост — оценить заново);
- чистка `defaults/policy.yaml` от stale v0.x ключей.

Известные дефекты канала (из ревью Reliability раунда 1):
- `dist/build.sh`: `tar czf` без генерации checksum; VERSION из `git describe` или "dev";
- `dist/update.sh`: `tar xzf` без верификации; удаляет core-файлы, отсутствующие в новой
  версии (убивает кастомизации хоста); backup в `.council/backup-<timestamp>/`;
- `dist/install.sh`: deps-check (Python 3.11+, PyYAML, git), режимы init/overlay;
  PyYAML не устанавливается автоматически;
- `.council/version.lock` упоминается в dist/README, но семантика не специфицирована;
- `defaults/policy.yaml` содержит удалённые v0.x ключи Documenter;
- vendor/techdoc-translator требует `.env` с endpoint/OpenAI-ключом — в хосте настройка
  перевода может быть не нужна;
- prose-контракты (tools/README.md, SKILL.md) не проверяются на совместимость с версией
  dist.

## Focus Areas

- Минимально достаточный DoD для первого хоста (не перестроить dist, а сделать установку
  безопасной и воспроизводимой).
- Версионирование и идентификация релиза (VERSION, version.lock, что означает "dev").
- Целостность канала: checksum на build, проверка на install/update.
- Поведение при конфликтах с файлами хоста (overlay, кастомизации, удаление файлов).
- Конфигурация периферии: .env переводчика, опциональность vendor, hooks.
- Что документировать оператору хоста (setup runbook) и как тестировать (dry-run хост).

## Questionnaire per Role

**Architect:**
- Q1: Какие компоненты dist-канала должны войти в DoD первого хоста, а какие —
  осознанно отложены, и почему?
- Q2: Где проходит граница «ядро фреймворка» vs «периферия» (vendor, hooks, defaults)
  для хоста, который может не нуждаться в переводе?

**Reliability & Security Specialist:**
- Q1: Какие дефекты канала (checksum, update-удаление файлов, version.lock) делают
  первый хост небезопасным, и каков минимальный достаточный уровень защит?
- Q2: Какой emergency-путь нужен хосту при дефекте pinned-инструмента до появления
  второго хоста?

**Human-Centric Designer:**
- Q1: Хватает ли текущих инструкций (dist/README) оператору хоста, или нужен runbook?
  Какие шаги установки наиболее подвержены ошибке?
- Q2: Как оператор хоста узнаёт, какая версия фреймворка установлена и актуальна ли она?

**Operations Engineer:**
- Q1: Как устроен тестовый прогон: dry-run установка в чистый и существующий каталог,
  откат, повторный update? Что должно быть автоматизировано до первого реального хоста?
- Q2: Как выпускать релизы dist (tag → build → archive → checksum → запись в source
  changelog) минимальным тиражом?

## Output Limits

- ≤7 находок, ≤5 рекомендаций, ≤3 открытых вопроса на роль, ~150 строк.

## Expected Discussion Rounds

1 round; при расхождении по составу DoD — уточняющий раунд модератора.

## Subject List

- `SUBJ-011`: Состав DoD первого хоста — обязательные vs отложенные работы.
- `SUBJ-012`: Версионирование и релизный цикл dist (VERSION/tag/version.lock, политика "dev").
- `SUBJ-013`: Целостность канала (checksum генерация/проверка, поведение update при
  конфликтах и удалении файлов).
- `SUBJ-014`: Конфигурация периферии хоста (vendor/.env, hooks, defaults, опциональность
  компонентов).
- `SUBJ-015`: Тестирование и запуск: dry-run хост, setup runbook, emergency hotfix-процедура.

## Additional Context / Constraints

Читать: AGENTS.md (§1.5–1.7, OP-1/2/3), sessions/sess-tooling-separation-2026-11-22/consensus-doc.md,
dist/README.md, dist/build.sh, dist/install.sh, dist/update.sh, tools/README.md,
defaults/translation.lock.

Ограничения: OP-2 (минимальный тираж, не перестраивать канал); fallback/ заморожен;
единственный оператор; хосты — проекты того же оператора; решение = список работ с
приоритетами, не реализация.
