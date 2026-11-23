# Role: Code Author — impl-run-2026-11-19T13-00-01, iteration 1

Ты — **Code Author** в цикле реализации (Implementation Worker). Пишешь реализацию,
удовлетворяющую тестам, в разрешённых путях.

## Ответственность
Реализовать новый CLI-контракт `tools/check_all.py` и обновить `tools/hooks/pre-commit`
так, чтобы зелёными стали все 34 красных теста. Детекция правил НЕ меняется — меняется
только фильтр отчёта, exit-коды, rendering и хук.

## Рабочая директория
WORKTREE = /home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-19T13-00-01
Пиши файлы ТОЛЬКО внутри WORKTREE и ТОЛЬКО в whitelist.

## Inputs (абсолютные пути)
- `WORKTREE/.impl/target-task.md` — binding decisions 1–8 (это СПЕЦИФИКАЦИЯ, следуй точно).
- `WORKTREE/.impl/artifacts/test-files.json` — тестовые файлы и команда.
- `WORKTREE/tests/test_check_all.py`, `WORKTREE/tests/test_check_all_hook_contract.py` —
  источник истины о поведении. Прочитай КРАСНЫЕ тесты внимательно: их assertions важнее
  любых догадок.
- `WORKTREE/tools/check_all.py` — текущая реализация (правь main() и rendering; check
  battery `scan()` и все rule-функции НЕ трогай).
- `WORKTREE/tools/tests_helpers.py` — severity_rank (не менять).

## Outputs (пиши ТОЛЬКО эти файлы)
- `WORKTREE/tools/check_all.py` (существующий, разрешён задачей)
- `WORKTREE/tools/hooks/pre-commit` (существующий, разрешён задачей)
- `WORKTREE/.impl/artifacts/code-files.json`:
  ```json
  { "files": ["tools/check_all.py", "tools/hooks/pre-commit"],
    "signatures": [{"file": "tools/check_all.py", "names": ["main", "render_report", "..."]}],
    "notes": "допущения, если есть" }
  ```

## Ключевые требования (детали — в target-task.md и красных тестах)
1. В main(): после scan() применить фильтр `min_reported = --strict ? warning : args.severity`;
   `reported = [f for f in findings if rank >= rank(min_reported)]`. `--severity` принимает
   и `warning` (добавь в choices).
2. Exit: `2` если в reported есть high; `1` если reported непусто; `0` иначе.
   Внутренние ошибки/плохой `--rule` → exit 2 КАК СЕЙЧАС (stderr `ERROR:` /
   stdout-баннер `check_all: INTERNAL ERROR` — БЕЗ маркера 🚨 в выводе).
3. Rendering (не --json): reported пусто → НИЧЕГО на stdout, exit 0. Иначе:
   если есть high: сначала `🚨 critical: <n_high>`, затем `⚠ findings: <n_reported>`;
   если high нет: только `⚠ findings: <n_reported>`. Затем hint-строки, отсортированные
   по severity (high→medium→low→warning), каждая `rule=<r> severity=<s> file=<f> <desc>`.
   УБРАТЬ старые `OK — no findings ...` и `check_all: N finding(s) ... blocking ...` строки.
4. --json: по reported тем же фильтром, объекты {rule,severity,file,description}, БЕЗ
   маркерных строк.
5. Хук: обнови case-конструкцию: ветка `2)` различает критические находки (grep `🚨
   critical` в OUTPUT → warn 0 / block 1) и крах/INTERNAL ERROR (fail-closed как сейчас,
   БЕЗ вывода маркера 🚨). Ветка `1)` — блок только при belt-and-braces grep `severity=high`.
   Обнови комментарии контрактов. Пустой вывод при exit 0 — НОРМА (silent-when-clean),
   хук не должен считать его ошибкой.
6. Проверь себя: `cd WORKTREE && python3 -m unittest tests.test_check_all
   tests.test_check_all_hook_contract -v` — цель зелёные. Также прогони остальные модули
   (`tests.test_install_hooks`, `tests.test_link_integrity`) — они должны остаться зелёными;
   если чужой тест падает из-за нового поведения хука/кода, внеси минимальную синхронизацию
   в СВОИ файлы, чужие тесты не правь — отметь в notes.
7. Стиль: argparse, комментарии в духе файла. check_all.py ≤ 1300 строк.

## Запрещено
- Править tests/*.py (никогда). Если тест кажется неверным — notes.
- docs/, CHANGELOGS/, fallback/, .agents/, defaults/, sessions/, archive/.
- tools/tests_helpers.py и другие tools (read-only). Коммиты. Tier 2+ маркеры (ADR-013).

## Формат отчёта
Короткий markdown: изменённые файлы, ключевые сигнатуры, итог самопроверки (сколько
тестов зелёные), допущения.
