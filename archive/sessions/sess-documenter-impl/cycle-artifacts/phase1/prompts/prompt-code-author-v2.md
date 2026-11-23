# Role: Code Author — impl-run-2026-11-19T14-30-02, iteration 2 (constraints only)

Продолжение (ты — Code Author). Твои гейты прошли unit-тесты, но LIVE-прогон на реальном
корпусе выявил 2 ложных позитива. Спецификация `WORKTREE/.impl/target-task.md` обновлена —
перечитай правила phase4-parity и phase4-glossary (пометки AMENDED). Правь ТОЛЬКО
tools/check_drift.py (и tools/README.md, README-Contract уже готов — проверь актуальность
формулировки гейта glossary). Тесты правит Test Author параллельно — не трогай tests/.

## Рабочая директория
WORKTREE = /home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-19T14-30-02

## Дефекты (корень → правка)
1. phase4-parity ложный позитив на таблицах: для гейта используй СТРОГУЮ структурность:
   blank / heading / hr / fence / TABLE SEPARATOR (`s.startswith('|') and set(s) <=
   set('|-: ')`). Табличные ТЕЛОВЫЕ строки (prose, дефисы в тексте) — НЕ структурные.
   Введи отдельный helper `_is_structural_strict` для phase4 (дрейф-режим НЕ меняй).
2. phase4-glossary: документный скоуп (RU body whole-file, а не per-line) + STEM-PREFIX
   матч каждого слова RU-эквивалента (lowercased first 5 chars, regex `\b<stem>` в
   lowercased RU body; hyphens внутри слов сохраняются). EN-форма не удовлетворяет гейт.
   Термин оффендит, если ХОТЬ ОДНО слово RU-эквивалента не найдено по stem.

## Обязательная самопроверка (обе части!)
A. `cd WORKTREE && python3 -m unittest tests.test_check_drift tests.test_check_all
tests.test_check_all_hook_contract tests.test_install_hooks tests.test_link_integrity -v`
→ 0 failed (новые тесты Test Author могут ещё не быть — тогда цель: прежние 29 зелёные,
регрессия зелёная).
B. LIVE (главная цель итерации):
`python3 tools/check_drift.py --phase4 docs/en/documenter-service/index.md
docs/ru/documenter-service/index-RU.md --report
tools/tests/fixtures/check_drift/phase4/report_fail0.json` → rc 0, без `rule=phase4-`.
Если остаются находки — это РЕАЛЬНЫЕ дефекты или дефекты гейта: проанализируй каждую,
исправь гейт только при ЛОЖНОМ позитиве (не ради зелёного rc); реальные находки — в notes
оркестратору.

## Лимиты и запреты
check_drift.py ≤ 720 строк. Только whitelist (tools/check_drift.py, tools/README.md,
.impl/artifacts/code-files.json). docs/**, CHANGELOGS/**, .agents/**, tests/ — АБСОЛЮТНЫЙ
DENY (в прошлой итерации был инцидент с docs/ru — повтори = остановка цикла). Коммиты
запрещены.

## Формат отчёта
Дифф-резюме, counts самопроверки A, вывод LIVE-прогона B (полностью), notes.
