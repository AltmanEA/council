# Consensus Document — Telemetry in Council Distribution

Session: sess-telemetry-distribution-2026-11-22
Mode: fallback (последовательные локальные агенты; оператор = Moderator)
Date: 2026-11-22
Result: **Conditionally Resolved**
Roles (final): Architect **agree**, Reliability & Security **agree**, Human-Centric **concerns**, Operations **agree**
Rounds: 1 индивидуальный + 1 обсуждение (эскалация, поднятая в Фазе 2, снята в Фазе 3)
Predecessors: sess-tooling-separation-2026-11-22, sess-first-host-launch-2026-11-22
Operator decisions: 2026-11-22 — 6/6 открытых вопросов закрыты (см. «Уточнения оператора»)

---

## Decision

Идея оператора **принимается условно**: в v0.1.0 закладывается минимальный
**локальный, opt-in, ручной** диагностический контур; сбор метрик эффективности
и любая автоматическая отправка данных **исключаются**.

### v0.1.0 — must-have

1. **Никакого сбора по умолчанию.** `enabled: false`; сбор начинается только после
   явного действия оператора: `--enable-telemetry` при install или созданного
   оператором `.council/telemetry.yml`. Council не пишет конфиг сам.
   (SUBJ-003, SUBJ-008)
2. **Гибрид размещения.** Один тонкий скрипт-коллектор `tools/collect_telemetry.sh`
   в `core/` (покрыт существующим `copy_core "tools"`, обновляется `update.sh`);
   данные — в `.council/telemetry/diagnostics/` (JSONL, append-only) и
   `.council/telemetry/metrics/` (YAML, зарезервирован, сбор выключен), **вне
   core-manifest**, поэтому `update.sh` их не трогает. В `templates/` — ничего.
   (SUBJ-004, SUBJ-005)
3. **Жёсткий redaction со fail-closed.** Пути → `./...`; stacktrace ≤50 строк,
   hash-dedup, только `file → line → function → exception_type → message`;
   env, промпты/ответы агентов, содержимое файлов — безусловно исключены;
   ключи — regex-блок; IP → `[local]`/`[external]`. При ошибке redaction запись
   **не пишется**. (SUBJ-002)
4. **Safety valves.** `max_file_size_mb: 10`, `max_total_dir_mb: 50` на каталог,
   ротация oldest-first без демонов; при отказе — предупреждение в stderr.
   Отказ коллектора не ломает хост: try/except + silent fallback. (SUBJ-009)
5. **Отзыв согласия.** Флаговый файл `.council/opt-out-telemetry`: создание =
   прекращение сбора в следующем рабочем цикле Council. (SUBJ-003)
6. **Раскрытие до активации.** Пост-установочное сообщение в `install.sh` +
   чек-лист «Собрано / Не собрано» в `RUNBOOK.md`: Collected — версия Council/Python,
   факт и тип команды, redacted stacktrace ≤50 строк, timestamp; **не собрано** —
   исходники, промпты, ключи/env, пути хоста. Прямая фраза: данные не передаются
   наружу, экспорт — только оператор. (SUBJ-008, SUBJ-002)
7. **Ручной экспорт bundle.** Команда оператора (`tools/collect_telemetry.sh
   --bundle > bundle.tar.gz`), контракт из 5 полей: `schema_version`,
   `collector_version`, `project_name`, `generated_at`, `files[]`. Читатель
   проверяет версию: несовместимый/старый формат → warning и пропуск файлов,
   хост не ломается. (SUBJ-004, SUBJ-009)
8. **Изоляция.** Коллектор — не-git-aware (не трогает `.git/`, не регистрирует
   хуки); в `tools/README.md` явно: `check_all.py` не инициирует сбор. (SUBJ-005)

### Backlog с триггерами

| Пункт | Триггер |
|-------|---------|
| Сбор метрик эффективности (SUBJ-001, SUBJ-007) | ≥2 хоста с явным opt-in + операционализация метрик; репрезентативность и этика — ответственность исследователя |
| ~~Публикационные пороги N / независимость операторов / метки `preliminary`~~ → **вне области инструмента** (SUBJ-007) | решение исследователя; Council не кодирует пороги выборки |
| Криптоподпись/целостность bundle (SUBJ-007) | по требованию исследователя (переход к публикациям) |
| Внешний push-endpoint (SUBJ-004) | решение оператора (публикация/benchmark); в v0.1.0 запрещён |
| Метрика полезности самой телеметрии — записей на проект/день (SUBJ-009) | первый месяц реальной эксплуатации |
| ~~Политика `.gitignore`~~ → решено (SUBJ-008) | создаётся `.council/telemetry/.gitignore`, host-`.gitignore` не трогается |

### Уточнения оператора (2026-11-22)

1. **Репрезентативность выборки — задача исследователя.** Council проектирует
   только инструмент сбора: в инструменте не кодируются пороги N, требование
   независимости операторов, этическая проверка и метки `preliminary`. Оговорка HCD
   по смещению выборки (SUBJ-007) вынесена за пределы области инструмента;
   остаётся только раскрытие состава данных и opt-in. Вопрос 1 закрыт как
   `out-of-scope`, а не как компромисс 2 vs N.
2. **`.gitignore`:** не менять `.gitignore` хоста (template-owned); при
   `--enable-telemetry` создать `.council/telemetry/.gitignore` и
   `.council/telemetry/README.md` с чек-листом «Собрано / Не собрано» как видимый
   индикатор наличия данных.
3. **Единственный скрипт:** `tools/collect_telemetry.sh` в core — сбор, `--bundle`
   и `--inspect` в одном файле; новый `copy_core` в `build.sh` не требуется.
   Скрипт не-git-aware; `check_all.py` не инициирует сбор.
4. **`project-slug` / `project_name`:** использовать уже существующее разрешение
   `PROJECT_NAME` в `install.sh` (`--project-name` либо `basename(target)`),
   записать значение в `.council/telemetry.yml`.
5. **Символы в stacktrace:** `function` в trace оставляем по умолчанию (иначе
   теряется ценность для отладки); в `.council/telemetry.yml` добавляется
   `redact_symbols: false` — при `true` имена заменяются хэшами для чувствительных
   проектов.
6. **`--inspect`:** тот же скрипт печатает только сводку — число записей,
   категории, размер каталога, дату последней записи, без содержимого записей.

---

## Rationale

1. **Конвергенция всех четырёх ролей:** тихий сбор неприемлем — opt-in, disclosure
   и механизм отзыва признаны обязательным условием любого сбора (HCD critical +
   Reliability critical, SUBJ-003/008).
2. **Architect critical + разворот Ops:** `update.sh` работает по core-manifest и
   удаляет пути, отсутствующие в новой версии; данные в core были бы стёрты.
   Гибрид «код в core, данные host-owned» устраняет failure mode без гейтов.
3. **Reliability critical + HCD critical:** traceback/env несут проприетарный код и
   секреты хоста; обязательны redaction и fail-closed (тихая потеря лучше утечки).
4. **Reliability high + Ops high:** неограниченный рост может заполнить диск хоста; лимиты
   10/50 МБ и oldest-first ротация — минимальная защита без демона.
5. **Наука вынесена за пределы инструмента:** метрики и подпись отложены,
   репрезентативность выборки определяет исследователь (решение оператора №1);
   OP-2 сохраняется — нет сервера, нет TLS, нет порогов выборки в коде.

## Subjects — Outcomes

| Subject | Outcome |
|---------|---------|
| SUBJ-001 — целеполагание | Agreed: диагностика и наука разделены по каталогам/форматам/жизненным циклам |
| SUBJ-002 — модель данных | Conditionally agreed: redaction-таблица + fail-closed + чек-лист раскрытия |
| SUBJ-003 — согласие | Conditionally agreed: `enabled: false`, `--enable-telemetry`, отзыв-флаг; HCD сохранил concerns до факта реализации disclosure |
| SUBJ-004 — local-first/экспорт/живучесть | Agreed: гибрид, ручной bundle из 5 полей, schema-version |
| SUBJ-005 — интеграция/OP | Agreed: core-скрипт, изоляция от git-hooks, `check_all.py` не собирает |
| SUBJ-006 — диагностика fallback | Agreed: JSONL с `session_id`, категории config/tooling/protocol/agent |
| SUBJ-007 — научная валидность | Conditionally agreed: всё измеримое — backlog с триггерами ≥2 хоста + этика + подпись |
| SUBJ-008 — прозрачность | Conditionally agreed: disclosure в install + RUNBOOK; индикатор накопления данных — открытый вопрос |
| SUBJ-009 — расходы/отказ | Agreed: 10/50 МБ, oldest-first, silent fallback, версионный silent degrade |
| SUBJ-010 — граница MVP | Agreed: diagnostics в v0.1.0; metrics/architecture — backlog |

## Conflicts & Disagreements

Формального `DISAGREEMENT` в финальном раунде **нет** (нет противоположных stances
на одном SUBJ-ID). Все четыре конфликта Фазы 2 разрешены в Фазе 3:

1. SUBJ-004 размещение: Architect (`.council/`, вне manifest) ↔ Ops (`council/errors/`
   в core + `~/.council-errors/`) → **гибрид**, Ops перешёл на позицию Architect.
2. SUBJ-009/010 объём: Reliability («запрет ошибок в v0.1.0») ↔ Ops («локальные
   ошибки допустимы») → Reliability согласился при redaction + opt-in + fail-closed.
3. SUBJ-002 данные: Ops/HCD (stacktrace ≤50 строк с маскированием) ↔ Reliability
   («строки кода/env неприемлемы») → env исключён,исходный код не логируется, trace
   ограничен полями `file/line/function/exception/message`.
4. SUBJ-007 наука: Ops/HCD (≥2 хоста + этика) ↔ Reliability (нужна подпись) →
   подпись перенесена в момент перехода к публикациям.

HEURISTIC (promotion candidate): сходимость critical-находок Reliability и HCD по
«тихому сбору» зафиксирована как critical, но не повышала severity.

## Reservations

- **HCD (concerns):** требует, чтобы disclosure-чек-лист и `--enable-telemetry`
  были **реально реализованы** до первого включения сбора на хосте; без этого
  сохраняет оговорку по SUBJ-003/008. Индикатор накопления данных закрыт решением
  оператора №2 (`.council/telemetry/README.md` + `--inspect`). Оговорка по
  репрезентативности выборки вынесена за пределы инструмента (решение №1).
- **Reliability:** redaction обязан быть проверяемым кодом, а не только
  документацией; при ошибке — не писать запись. Подпись — по требованию
  исследователя (SUBJ-002/007); символы в trace — с флагом `redact_symbols` (решение №5).
- **Architect:** имя/путь скрипта зафиксированы решением оператора №3 —
  `tools/collect_telemetry.sh` (SUBJ-005).
- **Operations:** метрика «записей на проект/день» остаётся в backlog; `project-slug`
  зафиксирован решением №4 через уже существующее разрешение `PROJECT_NAME`
  в `install.sh` (SUBJ-009).

## Open Questions (дедуплицировано)

— None — Все 6 вопросов закрыты оператором 2026-11-22; решения зафиксированы
в разделе «Уточнения оператора» и в таблице ниже.

| # | Бывший вопрос | Решение оператора |
|---|---------------|-------------------|
| 1 | Порог выборки / независимость операторов / метки `preliminary` | Вне области инструмента — задача исследователя |
| 2 | `.gitignore` для `.council/telemetry/` | Локальный `.council/telemetry/.gitignore`, host-файл не трогать |
| 3 | Имя и расположение скрипта | `tools/collect_telemetry.sh`, сбор + `--bundle` + `--inspect` |
| 4 | `project-slug` | Переиспользовать `PROJECT_NAME` из `install.sh` |
| 5 | Имена функций в stacktrace | Оставить по умолчанию + флаг `redact_symbols` |
| 6 | Локальный просмотрщик | `--inspect` в том же скрипте, только сводка |

## Action Items

| # | Действие | Приоритет | Роль-источник |
|---|----------|-----------|---------------|
| 1 | В `install.sh`: `--enable-telemetry` + пост-установочный disclosure; при отсутствии флага конфиг не создаётся | до v0.1.0 | HCD, Reliability, Ops |
| 2 | `tools/collect_telemetry.sh` (сбор + `--bundle` + `--inspect`, уже в core через `copy_core "tools"`) + `.council/telemetry/.gitignore` и `README.md` только при `--enable-telemetry`; данные НЕ добавлять в core-manifest | до v0.1.0 | Architect, Ops, оператор |
| 3 | Redaction-таблица + fail-closed + `redact_symbols` в `.council/telemetry.yml` | до v0.1.0 | Reliability, оператор |
| 4 | Лимиты 10/50 МБ, oldest-first, stderr-warning, try/except silent fallback | до v0.1.0 | Reliability, Ops |
| 5 | `.council/opt-out-telemetry` + инструкция в `dist/RUNBOOK.md` | до v0.1.0 | HCD |
| 6 | Чек-лист «Собрано/Не собрано» в RUNBOOK, выводе install и `.council/telemetry/README.md` | до v0.1.0 | HCD, оператор |
| 7 | bundle `--bundle` с 5 полями + проверка `schema_version` / silent degrade | до v0.1.0 | Architect, Ops |
| 8 | Явная строка в `tools/README.md`: `check_all.py` не инициирует сбор; коллектор не-git-aware | до v0.1.0 | Architect |
| 9 | Операционализация метрик; репрезентативность/этика/подпись — по требованию исследователя | backlog (триггеры) | Ops, HCD, Reliability; оператор (out-of-scope) |

## Escalation References

- В Фазе 2 HCD заявил `blocked-escalation` / `risk-threshold-breach`: формально
  валидная critical-находка (failure mode: установка в чувствительный проект без
  disclosure → утечка при экспорте; SUBJ-003, SUBJ-008) остановила ветку.
- В Фазе 3 HCD пересмотрел статус до `concerns` после того, как все роли приняли
  opt-in, disclosure и отзыв; эскалация **разрешена внутри консилиума**, запрос
  оператору не потребовался. Финальных blocked-статусов нет.
- Условие снятия остаётся обязательным: п.1–6 Action Items должны быть реализованы
  до первого реального включения сбора на внешнем хосте.

## Downgraded Critical Findings (transparency)

- **По невалидному обоснованию не понижена ни одна critical-находка** — все три
  имели failure mode и SUBJ-ID.
- Изменены консенсусом по существу (не по формату): Architect «данные в core
  стираются» → устранено гибридом; Reliability «утечка через traceback» →
  устранено redaction + fail-closed; Reliability «shadow collection» и HCD veto →
  устранены opt-in + disclosure; HCD `blocked-escalation` → `concerns`.
- Находка HCD о смещении выборки (SUBJ-007) не понижена по формату и не
  опровергнута: решением оператора №1 она вынесена за пределы области
  инструмента (вопрос исследователя, а не Council).

## References

- Раунд 1: `review-architect-round1.md`, `review-reliability-round1.md`,
  `review-human-centric-round1.md`, `review-operations-round1.md`
- Раунд 2: `discussion-round-1.md`
- Бриф: `task-brief.md`
- Основания в репозитории: `docs/en/planned-architecture/council-distribution.md`,
  `dist/build.sh`, `dist/install.sh`, `dist/update.sh`, `dist/RUNBOOK.md`,
  `tools/install-hooks.sh`, `fallback/index.md`, AGENTS.md §1.5–1.7
