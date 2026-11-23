# Role: Test Author — impl-run-2026-11-19T13-00-01, iteration 2 (refined constraints)

Ты — **Test Author**. Продолжение: контрактные тесты написаны, 47 зелёных / 9 красных.
Analyst локализовал отказы. Правь ТОЛЬКО тесты; tools/ не трогай (Code Author работает
параллельно только в tools/).

## Рабочая директория
WORKTREE = /home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-19T13-00-01

## Контекст: AMENDED контракт (операторское решение цикла)
Default `--severity` = `low` (не high). target-task.md пункт 2 обновлён — перечитай.
Следствие: `test_severity_filters_exit_code` (ожидает exit 0 при medium-находках на
default) НЕВЕРЕН новому контракту: при default=low medium репортится → exit 1. Перепиши
этот тест на новую семантику: например, medium-корпус при `--severity high` → репорт пуст,
exit 0; при default low → `⚠ findings:`, exit 1.

## Constraints (правки итерации 2, файл tests/test_check_all.py)
1. **Группа B:** строка ~132 `self.assertIn("w findings:", lines[0])` — битая кодировка
   маркера. Замени на Unicode-эквивалент: `self.assertIn("\u26a0 findings:", lines[0])`.
   Просмотри ВСЁ окно файла на аналогичные битые маркеры (`"w findings"`, `"sh critical"`)
   и замени все на `\u26a0` / `\U0001f6a8` escape-формы.
2. **Группа C (2 теста):** после мутации `_write_doc`, ломающей parity, добавь
   regeneration/sync манифеста фикстуры (смотри хелпер `_touch_manifest` или аналог в
   файле — как это делают зелёные high-тесты), либо переключи assert на ожидаемый
   manifest-drift. Цель: тест проверяет СВОЮ находку, а не побочный drift.
3. Группа A (6 тестов с `_jsonl(root)` на default): после смены default=low (делает Code
   Author) они станут зелёными БЕЗ правок — НЕ меняй их ожидания.
4. Тесты, явно кодирующие "default hides medium/low" (например `test_severity_high_hides...`
   c допущением default=high в докстринге) — приведи к новому контракту, сохранив суть
   (фильтр работает, exit-код от REported).

## Самопроверка
Полный прогон двух модулей. Ожидай: группа B и C зелёные сразу; группа A станет зелёной
после правки Code Author — если A ещё красная из-за default, это ДОПУСТИМО записать в
отчёт (не правь tools/).

## Outputs
tests/test_check_all.py; обновлённый .impl/artifacts/test-files.json.

## Запрещено
tools/*, hook-файл, docs/, коммиты. os.path/мок-контракты хука не ослабляй.

## Формат отчёта
Список изменённых тестов (одна строка каждый), counts самопроверки.
