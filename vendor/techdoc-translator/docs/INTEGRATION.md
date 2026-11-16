# Интеграция techdoc-translator в другой проект

Документ описывает **публичный контракт** инструмента и способ подключения
его к другому проекту без публикации в каталогах и без установки зависимостей.

## 1. Что поставляется

Сборка — это один архив `techdoc-translator-<version>.tar.gz`:

```
techdoc-translator-<version>/
  techdoc_translator.py   # движок, Python 3.11+, только stdlib
  translate.sh            # точка входа: загружает .env, делает preflight
  .env.example            # шаблон конфигурации
  MANIFEST.txt            # версия, CONTRACT_VERSION, PROMPT_VERSION, git-commit, дата
  SHA256SUMS              # контрольные суммы всех файлов
  README.md               # CLI, флаги, коды выхода, схема отчёта
  LICENSE
  docs/INTEGRATION.md     # этот документ
  tests/smoke.sh          # 13 проверок без сети
  tests/test_unit.py
```

Сборка и проверка:

```bash
scripts/build_dist.sh              # → dist/techdoc-translator-<version>.tar.gz
scripts/verify_dist.sh             # checksums + MANIFEST + smoke + mock round-trip
```

## 2. Требования к платформе

| Компонент | Требование |
|---|---|
| ОС | Linux / macOS (bash); Windows — через WSL |
| Python | 3.11+ |
| Зависимости | нет (stdlib only) |
| Утилиты | `bash`, `tar`, `curl` (curl нужен для preflight и HTTP-вызовов) |
| Сеть | не нужна для локального бэкенда на той же машине; cloud — только с `--allow-cloud` |
| Бэкенд | любой OpenAI-совместимый (`.../v1`) или Ollama-совместимый endpoint |

`python3 techdoc_translator.py` работает и без `translate.sh`; обёртка добавляет
загрузку `.env` и проверку доступности сервера (exit 3 при недоступности).

## 3. Публичный API

Единственный стабильный интерфейс — **CLI**. Внутренние функции модуля не
являются API: их имена и сигнатуры могут меняться без смены `CONTRACT_VERSION`.

### 3.1. Вызов

```bash
vendor/techdoc-translator/translate.sh \
    --input-en source.md \
    --output-ru output.md \
    --glossary glossary.md \
    --report run-report.json
```

Полный список флагов и переменных окружения — в `README.md` (разделы
*Flags*, *Config reference*).

### 3.2. Коды выхода (контракт)

| Код | Значение | Реакция потребителя |
|---|---|---|
| 0 | успех | забрать `--output-ru` |
| 1 | неверные аргументы / входные данные | ошибка конфигурации вызова |
| 2 | нет конфигурации / cloud не разрешён | ошибка конфигурации |
| 3 | бэкенд недоступен | retry позже / поднять сервер |
| 4 | перевод неполный (часть строк не переведена) | выход валиден, но требует проверки |
| 5 | несовпадение `CONTRACT_VERSION` | обновить вызов или архив |
| 6 | не удалось записать отчёт | проверить путь/права |

Коды 0–6 — стабильный контракт. Ломающее изменение семантики сопровождается
сменой `CONTRACT_VERSION`.

### 3.3. Отчёт (`--report`)

JSON с полями: `ok`, `skip`, `fail`, `backend`, `model`, `prompt_version`,
`contract_version`, `source_sha256`, `output_sha256`, `exit_code`, `timestamp`,
`message`, `glossary_applied`. Схема описана в `README.md`.

### 3.4. Инвариант

**Line-parity:** число строк выхода равно числу строк входа. Если блок не
перевёлся, строки остаются как в источнике — строки не склеиваются и не
удаляются. Потребитель может полагаться на построчное сопоставление
вход/выход (например, для diff-ревью).

## 4. Подключение к проекту

Рекомендуемый вариант — **vendoring**: архив распаковывается в каталог
проекта-потребителя и коммитится в его репозиторий.

```bash
# в проекте-потребителе
mkdir -p vendor
tar -C vendor -xzf /path/to/techdoc-translator-0.1.0.tar.gz
cp vendor/techdoc-translator-0.1.0/.env.example vendor/techdoc-translator-0.1.0/.env
# отредактировать .env: TRANSLATE_API_BASE, TRANSLATE_MODEL, ключ (если cloud)
```

`.env` содержит секреты — он **не коммитится** (добавить в `.gitignore`).

Вызов из скрипта сборки документации:

```bash
#!/usr/bin/env bash
set -euo pipefail
TT="vendor/techdoc-translator-0.1.0"

"$TT/translate.sh" --input-en docs/en/guide.md \
                   --output-ru docs/ru/guide.md \
                   --report build/translate-report.json
rc=$?
case "$rc" in
    0) ;;                                        # ok
    4) echo "warning: частичный перевод, см. report.fail" >&2 ;;
    *) echo "translation failed (exit $rc)" >&2; exit "$rc" ;;
esac
```

Вызов из Python (без импорта внутренностей):

```python
import json, subprocess
from pathlib import Path

tt = Path("vendor/techdoc-translator-0.1.0")
proc = subprocess.run(
    [str(tt / "translate.sh"),
     "--input-en", "docs/en/guide.md",
     "--output-ru", "docs/ru/guide.md",
     "--report", "build/translate-report.json"],
    capture_output=True, text=True,
)
report = json.loads(Path("build/translate-report.json").read_text(encoding="utf-8"))
if proc.returncode not in (0, 4):
    raise RuntimeError(f"translation failed: {proc.returncode} {proc.stderr}")
```

Если потребителю нужен не файл, а строки — используйте отдельные временные
файлы: CLI работает только с путями.

## 5. Версионирование и обновление

- Версия архива фиксируется в имени каталога (`techdoc-translator-0.1.0/`),
  поэтому два потребителя могут держать разные версии.
- `MANIFEST.txt` фиксирует `VERSION`, `CONTRACT_VERSION`, `PROMPT_VERSION`,
  git-commit и дату сборки — это то, что нужно указать в issue при проблеме.
- Обновление = замена каталога `vendor/techdoc-translator-<old>` на новый и
  прогон `bash vendor/techdoc-translator-<new>/tests/smoke.sh`.
- `CONTRACT_VERSION` меняется только при ломающих изменениях CLI или схемы
  отчёта; `PROMPT_VERSION` — при изменениях промпта (не ломающих).
- Защита от несовпадения: `--contract-version 1.0.0` → exit 5, если архив
  собран для другого контракта. Полезно в CI потребителя.

## 6. Проверка поставки

Перед передачей архива в другой проект:

```bash
scripts/build_dist.sh
scripts/verify_dist.sh
```

`verify_dist.sh` проверяет контрольные суммы, соответствие `MANIFEST.txt`
выводу `--version`, прогоняет `tests/smoke.sh` и mock-раундтrip (exit 0 +
line-parity) на распакованном архиве. Проверка выполняется без сети и без
модели.

## 7. Ограничения

- EN→RU markdown только; обратного направления нет.
- Cloud-бэкенд вызывается только при явном `--allow-cloud`.
- Никаких провайдер-специфичных имён и endpoint'ов в коде: конфигурация —
  только через `.env` / переменные окружения.
