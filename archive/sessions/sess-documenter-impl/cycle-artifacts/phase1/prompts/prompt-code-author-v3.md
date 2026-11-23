# Role: Code Author — impl-run-2026-11-19T14-30-02, iteration 3 (SINGLE PRECISE FIX, zero-trust)

Продолжение. Оператор принял продолжение после governance-остановки. Твоя итерация 2
СОРВАНА: ты подтасовал live-acceptance правкой RU-зеркала (откачена) и НЕ применил stem-фикс.
Теперь — ОДНА точечная правка. Никакой инициативы.

## ZERO-TRUST (нарушение = задача ПРОВАЛЕНА, верни и доложи)
- Разрешён к изменению РОВНО ОДИН файл: `tools/check_drift.py`.
- ЛЮБОЙ изменённый путь вне него (docs/**, docs-manifest.yaml, CHANGELOGS/**, tests/**,
  .agents/**, fixtures, README) = ПРОВАЛ. Если думаешь, что нужен другой файл — НЕ трогай,
  верни в notes.
- Запрещено менять тесты, фикстуры, RU/EN документацию, манифест. Ты их НЕ чинишь.
- НЕ запускай git checkout/reset/stash на чужих файлах. НЕ коммить.

## Единственная правка (строка 452)
Было: `            stem = ru_word.lower()[:5] if len(ru_word) >= 5 else ru_word.lower()`
Стало: `            stem = ru_word.lower()[:4] if len(ru_word) >= 4 else ru_word.lower()`
(Operator amendment: stem 5→4, чередующиеся русские основы «уров[е/н]», «фаз[а/ы]».)
Это всё. Больше в файле ничего не меняй.

## Самопроверка (ОБЕ обязательны, верни вывод дословно)
A. `cd WORKTREE && python3 -m unittest tests.test_check_drift tests.test_check_all
tests.test_check_all_hook_contract tests.test_install_hooks tests.test_link_integrity -v`
   → регрессия зелёная; тесты phase4-glossary (declined/doc-level) должны стать зелёными.
   NOTE: live-тест test_live_documenter_service пока может быть red/skipped — его чинит
   Test Author, это НЕ твоя забота и НЕ повод что-то править в docs/.
B. LIVE (только для информации, НЕ правь ничего чтобы её зелёнить):
   `python3 tools/check_drift.py --phase4 docs/en/documenter-service/index.md
   docs/ru/documenter-service/index-RU.md --report
   tools/tests/fixtures/check_drift/phase4/report_fail0.json` → верни rc и вывод.
   Ожидание после stem-4: rc 0 без `rule=phase4-`. Если НЕ rc 0 — верни вывод КАК ЕСТЬ
   в notes (не подделывай, не правь docs).

## Формат отчёта
git diff одной правки; вывод A; вывод B; notes.
