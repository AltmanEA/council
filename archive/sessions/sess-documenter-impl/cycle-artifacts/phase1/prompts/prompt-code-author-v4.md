# Role: Code Author — impl-run-2026-11-19T14-30-02, iteration 4 (SINGLE ONE-LINE FIX, zero-trust)

Продолжение. Твоя stem-4 правка верна, но «Фаза» (длина 4) дала stem = полное слово →
«фазы» не матчится. Операторская amendment финализирована: K = min(4, len−1). Одна строка.

## ZERO-TRUST (нарушение = ПРОВАЛ)
Ровно ОДИН файл: `tools/check_drift.py`. Любой другой изменённый путь (docs/**, tests/**,
fixtures, README, манифест, CHANGELOGS) = ПРОВАЛ задачи. НЕ ослабляй live-тест и НЕ трогай
docs — ты чинишь ГЕЙТ. НЕ коммить.

## Правка (строка ~452)
Было: `            stem = ru_word.lower()[:4] if len(ru_word) >= 4 else ru_word.lower()`
Стало: `            stem = ru_word.lower()[:min(4, len(ru_word) - 1)]`
(детерминированно: min(4, len-1) ≥ 1 для слов len ≥ 2; RU-эквиваленты — слова ≥ 2 букв.)

## Самопроверка (верни вывод дословно)
A. `cd WORKTREE && python3 -m unittest tests.test_check_drift tests.test_check_all
tests.test_check_all_hook_contract tests.test_install_hooks tests.test_link_integrity -v`
   → 0 failed (skips только по окружению).
B. `python3 tools/check_drift.py --phase4 docs/en/documenter-service/index.md
docs/ru/documenter-service/index-RU.md --report
tools/tests/fixtures/check_drift/phase4/report_fail0.json; echo rc=$?`
   → ОЖИДАНИЕ: rc=0, вывод БЕЗ `rule=phase4-`. Если rc≠0 — верни вывод КАК ЕСТЬ в notes.

## Формат отчёта
Дифф (1 правка), вывод A (counts), вывод B (rc + первые строки).
