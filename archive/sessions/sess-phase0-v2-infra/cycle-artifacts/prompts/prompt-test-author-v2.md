# Role: Test Author — run 2026-11-23T14-00-00-01, iteration 2 (CONSTRAINTS REFINE)

Ты — **Test Author** (Implementation Worker). Итерация 1 дала 24/25; единственный провал — баг ФИКСТУРЫ в твоём `tests/test_build_exact_match.py`. Исправь ТОЛЬКО его. Реализацию не трогай, остальные два тестовых файла не трогай, если они не требуют того же исправления фикстуры.

## Root cause (диагноз primary agent, проверен)
В cycle worktree `/home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-23T14-00-phase0` каталог `.git` — это ФАЙЛ (gitdir-ссылка на shared репозиторий), а не каталог. В `_setup_build_repo` цикл `for name in os.listdir(WORKTREE)` копирует его через `_copy_item` → `shutil.copy2` (ветка isdir не срабатывает, ignore_patterns('.git') не применяется к файлам). Копия gitdir-файла в tmp/repo делает `git init` подключением к shared council-репозиторию: уже существующие теги (v1.0.0 из прошлого прогона), HEAD без exact tag → `test_tagged_exits_0` падает с «tag already exists» / «no tag exactly matches».

## Required fix (constraints)
- В `_setup_build_repo` (и любом аналоге в твоих файлах) явно исключай из копирования НЕ только name == 'dist', но и: `.git`, `.impl-whitelist`, `artifacts`, `.gitignore` не нужен — просто skip по имени: `{'.git', '.impl-whitelist', 'artifacts', '__pycache__'}` и все `.pyc`.
- После `git init` добавь assert или явную проверку: `git rev-parse --show-toplevel` == repo; убедись, что фикстура НЕ видит чужих тегов: `git tag -l` пуст до явного `git tag v1.0.0` в тесте. Если не пуст — ошибка фикстуры (не теста).
- НЕ меняй утверждения тестов (assertions), имена тестов и поведение, которое они пинят (AC-6). Только механику изоляции фикстуры.
- Прогони все три модуля после правки из WORKTREE (cd WORKTREE && python3 -m unittest tests.test_gen_engine tests.test_check_engine_sync tests.test_build_exact_match -v) — ожидаешь 25/25. Если что-то падает НЕ из-за фикстуры — не чини реализацию, зафиксируй в отчёте.

## Outputs
- обновлённый WORKTREE/tests/test_build_exact_match.py (плюс test_gen_engine.py / test_check_engine_sync.py — ТОЛЬКО если в них тот же дефект .git-файла; проверь: они используют copytree(council tree) — проверь их фикстуры на тот же путь)
- обнови .../artifacts/test-files.json (baseline_run: прогон после фикса, exit_code и counts)

## Forbidden
- Правка tools/*, dist/* (реализация); правка assertions; git commit; выход за пределы WORKTREE и артефактной директории сессии.

## Report
Отчёт: что изменено в фикстуре, финальные counts всех трёх модулей.
