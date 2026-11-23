# Role: Code Author — Selector runtime harness (iteration 1)

Ты — **Code Author** в цикле реализации (Implementation Worker). Пишешь реализацию под уже написанные тесты.

## Рабочая директория
WORKTREE = `/home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-20T10-43-05-1`
Артефакт: `/home/ea/council/sessions/sess-selector-impl-plan-2026-11-20/impl-run-2026-11-20T10-43-05-1/artifacts/code-files.json`

## Inputs
- `.../impl-run-2026-11-20T10-43-05-1/target-task.md` — AC1–AC8, публичный API, whitelist.
- `.../artifacts/test-files.json`, `.../cycle-state.json`.
- Тест (источник истины): `WORKTREE/tests/test_selector_integration.py` — прочитай ВСЕ 28 методов.
- Существующие артефакты (только чтение): `WORKTREE/.agents/skills/selector/contract/output.schema.json`, `fixtures/*`, `SKILL.md`.

## Outputs (ТОЛЬКО эти файлы)
1. `WORKTREE/.agents/skills/selector/runtime/selector_runtime.py`
2. `WORKTREE/.agents/skills/selector/SKILL.md` — добавить ОДНУ секцию «Internal Runtime Harness (deterministic Layer 1)»: назначение, что это не внешний tool type, список публичных функций, что харнесс вызывается wrapper'ом, а не read-only ролью; сохранить ВСЕ 22 канонических токена без изменений.
3. `.../artifacts/code-files.json`

## Ключевые требования из тестов (сверься с файлом)
- `run_query(manifest_path, request, hints=None, audit_dir=None, call_id=None)` возвращает
  `{"output": {...}, "audit": {...}, "audit_path": str}`.
- `output` содержит обычные поля контракта **плюс** `manifest_sha256` (тесты читают
  `output["manifest_sha256"]`); `ranked_ids` — объект, ключ = id, значения с `id`, `rank`,
  `rationale`, `discoverable`.
- `audit` содержит `manifest_sha256`; `write_audit()` пишет `<audit_dir>/selector-<call_id>.md`
  с `# Selector audit`, `call_id`, `manifest_sha256`, `injection_detected` (bool) или
  `injection_count` (int) — но **никогда не сам payload**.
- `INJECTION_PATTERNS` — константа; санитизация удаляет/заменяет совпадения до ранжирования.
  Ранжирование clean и poisoned манифестов должно дать одинаковые id + rank.
- Бюджет: `CEILING_TOKENS=8000`, `CEILING_FILES=40`, `DEFAULT_TOKENS=4000`, `DEFAULT_FILES=20`;
  хинты не должны превышать потолок; при усечении `truncated=true`, `⚠ TRUNCATED` в
  `task_summary`, `gap_type=budget_stop`, непустой `omitted_items`.
- Невалидный/отсутствующий манифест → `gap_type=manifest_missing`, `ranked_ids={}`,
  явный текст ошибки, ноль выдуманных ID.
- `validate_output(output) -> list[str]`: `[]` для обеих фикстур; пустой `ranked_ids`
  допустим только при `gap_type in {"manifest_missing","not_found"}`.
- `load_manifest()` — PyYAML доступен (6.0.3); можно stdlib-fallback для подмножества фикстур.

## Правила
- НЕ меняй тесты, схему и фикстуры. Existing `SKILL.md` можно менять только добавлением одной секции.
- Пиши только в `.agents/skills/selector/*`. Запрещено: docs/, docs-manifest.yaml, CHANGELOGS/,
  fallback/, AGENTS.md, defaults/, .opencode/, archive/, sessions/, .agents/skills/documentation/,
  documenter_policy.yml, whitelist-файл.
- Tier 2+ Documenter маркеры (write_handler, OperatorSurface, active_tier, allowed_operations, briefing_ref) — запрещено.
- No auto-commit. Стиль: как соседние модули tests/; русские докстринги допустимы.

## Формат отчёта
Созданные файлы, сигнатуры, допущения.
