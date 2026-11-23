# Role: Test Author — Selector runtime harness (iteration 2, refined)

Ты — **Test Author**. Это итерация 2: исправляешь дефекты САМИХ ТЕСТОВ по вердикту Analyst.

## ВАЖНО — формат работы
Файл `tests/test_selector_integration.py` уже существует (630 строк). **НЕ переписывай его целиком.**
Внеси только точечные правки через замену конкретных фрагментов. Финальный ответ — не более 8 строк, без вывода кода.

## Inputs
- `.../artifacts/verdict.json` — `next_steps` для роли `test-author`.
- `WORKTREE/tests/test_selector_integration.py` — 28 методов.
- `.../artifacts/test-output-1.txt` — сырые падения.
- `.../target-task.md` — AC1–AC8.

## Что исправить (ровно 5 мест)
1. `TestInjectionV2.test_injection_not_in_audit` — `os.path.isfile(audit_path)` и чтение тела файла перенести **внутрь** `with tempfile.TemporaryDirectory()`; до выхода из `with` сохранить текст в локальную переменную и уже после контекста делать `assertNotIn`.
2. `TestInjectionV2.test_injection_detected_as_boolean_count` — `_read_file(result["audit_path"])` перенести внутрь `with`; проверку `injection_detected`/`injection_count` делать по сохранённой строке.
3. `TestAuditV8.test_audit_file_created` — `os.path.isfile()` внутрь `with`.
4. `TestAuditV8.test_audit_file_contains_required_fields` — `_read_file()` внутрь `with`, затем проверки по переменной.
5. `TestBudgetV4.test_high_hints_capped_at_ceiling` — вместо 4-entry `manifest.sample.yaml` создать временный YAML-манифест с **45 записями** в отдельном `tempfile.TemporaryDirectory()` (запись файла разрешена только во временном каталоге), передать его путь в `run_query`, и оставить проверку `truncated=true` + `gap_type=budget_stop` + непустой `omitted_items`. Остальные тесты бюджета (no-hints defaults) не трогать.

## Запрещено
- Менять модуль реализации, схему, фикстуры, SKILL.md, существующие контрактные/smoke-тесты.
- Менять `artifacts/test-files.json` (baseline итерации 1 остаётся историей).
- Писать вне `WORKTREE/tests/test_selector_integration.py`.
- Добавлять skips/expectedFail.

## Проверка после правок
`cd WORKTREE && python3 -m unittest tests.test_selector_integration -v` — зафиксируй счётчики в ответе (одна строка). Ожидаемо: 5 ошибок тестов уйдут, останутся 2 дефекта кода (sha256 в output, poisoned-парсинг) — это нормально, их чинит Code Author v2.

## Формат отчёта
≤8 строк: что изменено по пунктам, счётчики прогона.
