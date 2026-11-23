# Role: Test Author — impl-run-2026-11-19T13-00-01, iteration 1 REFINEMENT (v2)

Продолжение твоей работы (ты уже создал tests/test_check_all.py правку,
tests/test_check_all_hook_contract.py, .impl/artifacts/test-files.json).

## Дефект, который нужно исправить
`tests/test_check_all_hook_contract.py` — 14/14 PASS **против ТЕКУЩЕГО (нереализованного)
хука**. Это запрещено анти-reversed-TDD: тесты ничего не проверяют. ТЕКУЩИЙ
`tools/hooks/pre-commit` — легаси: exit 2 там означает только "internal error (crash)",
там нет ветки `🚨 critical`, нет разделения exit 2 на critical vs crash, нет обновлённого
exit-1 block-mode комментария.

## Требование
Перепиши тесты в `tests/test_check_all_hook_contract.py` так, чтобы КАЖДЫЙ из них был
КРАСНЫМ против текущего текста хука и Зелёным — против хука, обновлённого по таблице
из `WORKTREE/.impl/target-task.md` пункт 7:
- кейсы: exit 0 → exit 0; exit 1 (findings) → warn 0 / block belt-and-braces grep;
  exit 2 с `🚨 critical` в выводе → warn 0 / block 1; exit 2 с `check_all: INTERNAL ERROR`
  или без маркеров → fail-closed (warn 0 / block 1).
- Проверяй фактическое поведение ВЕТВлок case-конструкции, а не наличие исторических
  комментариев. Ориентир: assertions вида `assertIn('critical', section_text_of_rc2)` где
  section — текст между `2)` и `*)` в case; проверка что ветка `1)` block-mode больше не
  полагается только на grep как единственный критерий блокировки; проверка что в файле
  есть обработка маркера `🚨`.
- Дополнительно добавь ПОВЕДЕНЧЕСКИЙ тест (не grep): в temp git-repo создай фейковый
  `tools/check_all.py`, который печатает `🚨 critical: 1`+hint и выходит 2, запусти хук с
  block-mode flag и утверждай exit 1; без флага — exit 0. Так же фейковый чистый
  (exit 0, пустой вывод) → хук exit 0 в обеих модах (важно: пустой вывод ≠ ошибка).

## Затем
Перезапусти baseline: `python3 -m unittest tests.test_check_all tests.test_check_all_hook_contract -v`
против текущего кода. Обнови `.impl/artifacts/test-files.json` (baseline должен быть красным
ПОЛНОСТЬЮ: и test_check_all.py, и hook-контрактные тесты).

WORKTREE = /home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-19T13-00-01
Пиши только: tests/test_check_all_hook_contract.py, .impl/artifacts/test-files.json.
Отчёт: список тестов hook-контракта с их baseline-статусом (все должны быть FAIL) + общий baseline exit code.
