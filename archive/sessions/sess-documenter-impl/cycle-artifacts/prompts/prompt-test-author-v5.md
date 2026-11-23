# Role: Test Author — impl-run-2026-11-19T13-00-01, iteration 4 (AMENDED: link-integrity contract)

Продолжение. Реализация check_all.py финальная и зелёная (75/75 в worktree). При мерже в
основное дерево обнаружилась регрессия: `tests/test_link_integrity.py` вызывает
`check_all.main` напрямую и кодирует СТАРЫЕ blocking-семантики exit-кодов. Этот файл теперь
в whitelist. Правь ТОЛЬКО его.

## Рабочая директория
WORKTREE = /home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-19T13-00-01

## Новый контракт exit-кодов (напоминание)
По REPorted-находкам после --severity-фильтра (default=low):
- 0 = нет reported находок; 1 = есть, none high; 2 = ≥1 high (critical) ИЛИ internal error.
Docs→manifest находки — HIGH → rc=2 (было rc=1).

## Падения, которые нужно починить (в worktree прогони для воспроизведения)
`cd WORKTREE && python3 -m unittest tests.test_link_integrity -v`:
1. test_missing_file_reference_blocks: ожидает rc=1, docs→manifest high → теперь rc=2.
   Правка: assertEqual(rc, 2) (high = critical). Если в тесте проверяется ещё и вывод —
   убедись что маркер `🚨 critical` допустим.
2. test_ru_reference_requires_registration: rc=1 → 2 (аналогично).
3. test_unregistered_existing_file_blocks: rc=1 → 2.
4. test_unparsable_manifest_skips_docs_side: rc=1 → (проверь факт; если docs-side пропущен
   и high-находка manifest всё равно репортится → 2; если находка medium → 1; определи по
   --json). Поставь верный rc.
5. test_full_scan_baseline_unchanged (live corpus): ожидает rc=0; live repo имеет 32 low →
   при default=low rc=1. Как в test_check_all: поменяй ожидание на assertIn(rc, (0,1)) —
   high в контролируемом корпусе быть не должно (регрессия-страж). НЕ маскируй через
   --severity high.

## Дисциплина
- Меняй ТОЛЬКО exit-code ассерты под новый контракт; СЕМАНТИКУ детекции (какие правила
  срабатывают, severity-класс) НЕ меняй. Тест обязан по-прежнему доказывать, что
  docs→manifest разрыв ДЕТЕКТИТСЯ (теперь как critical/high).
- Проверь остальные ассерты файла: rc=0 остаются rc=0 (те, где находок нет), rc=1 остаются
  rc=1 (где находки low/medium). Не переводи всё в 2.

## Самопроверка
`cd WORKTREE && python3 -m unittest tests.test_link_integrity tests.test_check_all
tests.test_check_all_hook_contract tests.test_install_hooks -v` → цель 0 failed во всех.

## Outputs
tests/test_link_integrity.py; обнови .impl/artifacts/test-files.json (добавь файл).

## Запрещено
tools/*, docs/, коммиты, ослабление проверок детекции.

## Формат отчёта
Список изменённых тестов + итоговые rc, финальные counts прогона.
