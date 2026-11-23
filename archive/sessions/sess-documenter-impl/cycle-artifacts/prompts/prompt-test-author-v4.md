# Role: Test Author — impl-run-2026-11-19T13-00-01, iteration 3 (constraints only)

Продолжение. Реализация НЕ меняется (Code Author закончил). Правь ТОЛЬКО
tests/test_check_all.py. 4 красных теста — их assertions не обновлены под AMENDED
default=low. Даю точные правки по фактическим AssertionError.

## Рабочая директория
WORKTREE = /home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-19T13-00-01

## Правки (ровно эти 4 теста, строки указаны)

### 1. test_live_corpus_runs_clean_exit_code (~line 799)
Факт: live repo имеет 32 low-находки, при default=low они репортятся → rc=1.
Было: `self.assertIn(rc, (0, 2), err)`. Стало: `self.assertIn(rc, (0, 1), err)`
(0 = чистый корпус у оператора, 1 = low/medium находки, но НЕ 2 — high находок
в контролируемом корпусе быть не должно; это и есть регрессия-страж).

### 2. test_ambiguous_heading_low_not_medium (~line 521)
Суть теста — КЛАССИФИКАЦИЯ severity (low, не medium), а не exit 0. При default=low
low-находка репортится → rc=1. Перепиши assertions на проверку через --json:
запусти с `--json`, разбери записи, утверждай что для целевой мутации есть запись
с severity=="low" и НЕТ с severity=="medium" для той же находки. Добавь
assertEqual(rc, 1) (low репортится). Сохрани название/докстринг.

### 3. test_unresolved_section_reference_medium (~line 379)
Аналогично: medium-находка при default=low репортится → rc=1. Через --json утверждай
наличие записи severity=="medium" для мутации; assertEqual(rc, 1).

### 4. test_severity_filters_exit_code (~line 253)
rc_default=2 вместо 1 → побочный manifest-drift (high) от мутаций без синхронизации
манифеста, ИЛИ лишняя high-находка. ДИАГНОСТИКА: запусти тест с выводом stdout и посмотри
какие записи/маркеры. Если `🚨`/high — добавь `_touch_manifest(root)` (как в группе C
итерации 2) после каждой мутации документа, чтобы parity держалась, и оставь ожидание
rc_default==1. Если после синхронизации high остаётся — значит мутация порождает
законную high-находку: переразложи корпус так, чтобы целевая находка была medium/low
и high не было (смотри как делают соседние зелёные тесты), затем assertEqual(rc,1) для
default и assertEqual(rc,0) для --severity high (фильтр скрыл всё).

## Самопроверка
`cd WORKTREE && python3 -m unittest tests.test_check_all tests.test_check_all_hook_contract
tests.test_install_hooks -v` → цель 0 failed во всех трёх. Если test 4 не сходится после
2 попыток, оставь его и точно опиши в отчёте фактический stdout (не ломай другие тесты).

## Outputs
tests/test_check_all.py; обнови .impl/artifacts/test-files.json.

## Запрещено
tools/*, hook, docs/, коммиты; ослабление токен-контрактных и --json схемных тестов.

## Формат отчёта
4 строки (по тесту: что изменено + итог rc), финальные counts прогона.
