# Справочник политик Документатора

Version: 0.6.0-draft
Status: draft
Last Modified: 2026-11-09
Abstraction: reference
changelog-path: CHANGELOGS/documenter-policy-reference.changes.md

---

## Purpose

Авторитетная схема для файла политики Документатора: определения полей, правила валидации во время загрузки, параметры операционной настройки и пошаговый рабочий процесс авторизации тиров. Семантика протокола, которую настраивают эти поля (тиры доверия, протокол безопасности, контракты интерфейсов), определена в `documenter-service/index.md`; структуры данных рантайма (хранилище хешей, журнал намерения, схема событий) определены в `documenter-service/configuration-guide.md`. Этот документ не определяет собственного поведения — это поверхность конфигурации для поведения, определённого в другом месте.

---

## Policy File

YAML-конфигурация, определяющая, какие операции разрешены на каждом тире и режимы соответствия (compliance). Составляется и поддерживается оператором. Автопроход по времени не является частью модели: одобрение — всегда явное действие оператора в рамках вызова `delegate()`, и единственный путь автовыполнения — автоприменение по паттерну на Tier 3 (см. §Trust Tiers и §Approval semantics в основной спецификации, `documenter-service/index.md`).

**Правило валидатора:** Документатор ДОЛЖЕН отклонить загрузку любого файла политики, где `allowed_operations` не пусто, пока `active_tier < 2`. Это предотвращает ошибку конфигурации (misconfiguration) при развёртывании. **Правило авторитета:** Записи политики могут только сужать встроенный базовый уровень доверия (built-in trust classification floor) из основной спецификации (§Trust Classification): запись `allowed_operations` может требовать `review` там, где таблица разрешает `safe`, но сочетание политики, авторизующее `trust_level` ниже *статического базового уровня* (static floor) для своего `change_type`, недействительно и ДОЛЖНО быть отклонено во время загрузки — Документатор рассматривает это как ошибку конфигурации, последовательно с правилом валидатора выше.

**Правило совместимости:** Каждое поле в §Field Reference опционально, кроме `version`, `active_tier` и `allowed_operations`. Файл политики, написанный против более ранней версии схемы, загружается успешно: отсутствующие поля разрешаются к значениям по умолчанию, и никакое удаление или переименование поля не подразумевается повышением версии схемы.

```yaml
documenter_policy:
  version: "0.2.0"
  active_tier: 0                  # 0 = audit-only (MVP default)
  allowed_operations: []          # inert at active_tier < 2; populate when advancing
  glossary_enforcement: draft     # draft | active — controls noise reduction
  audit_freshness: 30             # minutes; max age of audit_id accepted by delegate() pre-audit gate
  lock_wait_timeout: 30           # seconds; advisory lock acquisition wait before abort
  retry_backoff_base: 1           # seconds; exponential backoff base on hash_mismatch retry
  retry_max_attempts: 3           # count; retry attempts before escalation to operator
  operator_approval_timeout: 300  # seconds; synchronous wait for approve/reject inside delegate()
  notification_mode: inline       # inline only — no asynchronous notification channel exists
  approval_expiry_window: 30            # minutes; maximum time between Tier 2+ authorization and the first delegate() invocation under that approval
  rescan_batch_ceiling: 50        # documents per full-rescan invocation before partial-report return
  glossary_staleness_days: 30     # days since last glossary modification; terms appearing ≥3 times within this window are flagged as missing
  briefing_ref: null              # path to operator briefing artifact; required when active_tier >= 2
```

На Tier 0–1 `allowed_operations` должен оставаться пустым независимо от содержимого. Оператор обновляет этот файл явно при продвижении тиров. Документатор отказывается выполнять любую операцию, не указанную в списке.

**Preview exemption:** Вызовы `delegate()` без намерения записи (режим предварительного просмотра, возвращающий diff без применения изменений) не подлежат проверкам `allowed_operations` ни на одном тире. Tier 1 конкретно полагается на это исключение для формирования diff. Эти вызовы всегда возвращают вычисленный diff, но никогда не изменяют файлы. Предварительный просмотр управляется булевым параметром `preview` (§Interfaces, delegate()) — при значении `true` никакие проверки тира или enforcement вентиля не применяются; проверяется только валидность схемы обязательных полей (`target_id`, `change_type`, `diff`).

### Field Reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `version` | string | Yes | `"0.2.0"` | Версия схемы политики для обнаружения совместимости |
| `active_tier` | int | Yes | `0` | Текущий тир доверия (0–3). Должен совпадать с таблицей Tier (§Trust Tiers, main spec). |
| `allowed_operations` | array | Yes | `[]` | Операции, авторизованные на текущем тире. Пусто ниже Tier 2. Может только сужать базовый уровень доверия (§Authority rule above). |
| `approval_expiry_window` | int | No | `30` | Максимальное время (в минутах), после которого неутверждённый `approval_id` истекает. Диапазон: 5–1440 (от 5 минут до 24 часов). Используется вместе с внеполосным вызовом `documenter.approve(approval_id, operator_id)`, описанным в operator-surface §Documenter Integration. |
| `audit_freshness` | int | No | `30` | Максимальный возраст (в минутах) `audit_id`, принимаемого вентилем предварительного аудита `delegate()`. Вентиль дополнительно проверяет покрытие области (точное совпадение или `*`), блокирующие выводы и завершение сканирования (`has_remaining` не должен быть `true`) по реестру аудита (`documenter-service/configuration-guide.md`, §Audit Registry). Установите `0`, чтобы отключить вентиль полностью (аудит не требуется; `audit_id` будет проигнорирован, если предоставлен). Любое другое значение обеспечивает соблюдение окна свежести. |
| `briefing_ref` | string | No | `null` | Путь к заархивированному артефакту брифинга оператора, документирующему объём делегированных полномочий. ДОЛЖНО быть не null при `active_tier >= 2` (§Authorization Workflow, step 4). |
| `glossary_enforcement` | enum | No | `draft` | Управляет снижением шума при соответствии глоссарию (§Glossary Compliance, configuration guide). |
| `glossary_staleness_days` | int | No | `30` | Дней с последней модификации глоссария; термины, появляющиеся ≥3 раза в этом окне, помечаются как отсутствующие (§Glossary Compliance, configuration guide). |
| `lock_wait_timeout` | int | No | `30` | Секунды ожидания рекомендательной блокировки (advisory lock) уровня операции перед прерыванием с ошибкой владельца блокировки, описанной в §Safety Protocol #2 (main spec). |
| `notification_mode` | enum | No | `inline` | Режим доставки для операторских подсказок. `inline` — единственное допустимое значение в MVP: подсказки, diff и вердикты возвращаются внутри ответа вызова. Неизвестные значения отклоняются при загрузке. |
| `operator_approval_timeout` | int | No | `300` | Секунды, которые активный вызов `delegate()` ждёт явного approve/reject перед излучением `error_category: operator_timeout`. Не является окном автоодобрения (§Approval semantics, main spec). |
| `rescan_batch_ceiling` | int | No | `50` | Документы, обрабатываемые за один полный вызов пересканирования. При достижении ответ включает `has_remaining: true` и токен продолжения `scan_cursor`; передача его обратно возобновляет сканирование с места, на котором остановился предыдущий вызов. Частичные сканирования никогда не авторизуют делегатов для несоканированных документов — оператор должен завершить все пакеты перед разрешением делегирования. Фоновое выполнение отсутствует. |
| `retry_backoff_base` | int | No | `1` | Базовая задержка (в секундах) для экспоненциального backoff с джиттером, используемого повторными вызовами (§Conflict Resolution, configuration guide). |
| `retry_max_attempts` | int | No | `3` | Максимальное число повторных вызовов после `hash_mismatch` перед тем, как Документатор эскалирует оператору вместо повторной попытки. |
| `temperature` | float | No | `0.1` | Случайность генерации LLM; более высокие значения увеличивают разнообразие (диапазон: 0.0–2.0). Применяется в рамках вывода role-agent (§Zero silent defaults, layer-1.md). |
| `top_p` | float | No | `0.9` | Параметр ядерной выборки; токены с кумулятивной вероятностью ниже этого порога исключаются (диапазон: 0.0–1.0). Применяется в рамках вывода role-agent (§Zero silent defaults, layer-1.md). |
| `frequency_penalty` | float | No | `0.0` | Снижает повторение токенов; положительные значения штрафуют повторяющиеся токены (диапазон: -2.0–2.0). Нейтральное значение по умолчанию, задаётся явно, а не выводится (§Zero silent defaults, layer-1.md). |

### Per-Operation Entries

Записи операций в `allowed_operations` следуют этой структуре:

```yaml
# Tier 2+ operation entry (default type — no explicit type field needed):
allowed_operations:
  - type: operation          # operation | pattern — omitted defaults to "operation"
    change_type: update      # update | split | create_ru | custom
    trust_level: safe        # safe | review — must not fall below the static floor (§Trust Classification, main spec)
    targets: []              # empty = all docs; list = specific manifest IDs
    requires_diff_preview: true  # always enforced at Tier 2+

# Tier 3 pattern entry (enables auto-apply for matching changes):
  - type: pattern
    pattern_id: "auto-bump-patch"   # unique identifier for this pattern
    pattern_description: "Deterministic patch-level version bumps in CHANGELOGS/*.changes.md and index.md metadata"
    match_criteria:
      change_type: update
      file_pattern: "CHANGELOGS/*.changes.md"  # glob-style path pattern; empty = match any file
    trust_level: safe
    requires_diff_preview: true
```

Поля записи паттерна:

| Field | Type | Description |
|-------|------|-------------|
| `type` | `operation` \| `pattern` | Дискриминатор. По умолчанию `operation` (если опущено), обратно совместимо. |
| `pattern_id` | string | Уникальный идентификатор этого паттерна (kebab-case). |
| `pattern_description` | string | Человекочитаемое описание того, что сопоставляет данный паттерн. |
| `match_criteria.change_type` | enum | Ограничивает совпадение конкретным `change_type`. |
| `match_criteria.file_pattern` | string | Паттерн пути в стиле glob относительно корня рабочей области. `*` — любые символы кроме `/`, `**` — любые символы включая `/`, `?` — один символ кроме `/`. Недействительные паттерны отклоняются при загрузке политики. |

---

## Operational Tuning

Какая ручка управляет каким путём отказа. Все значения — поля политики из §Field Reference; ни одно не требует изменения кода или перезапуска помимо перезагрузки политики.

| Сбой или нагрузка | Field | При исчерпании |
|---------------------|-------|---------------|
| Одновременный `delegate()` от другого агента | `lock_wait_timeout` | Прервать до любой записи; ошибка называет PID/IP владельца блокировки и метку времени захвата (§Safety Protocol #2) |
| Файл изменён между сканированием и записью | `retry_backoff_base` + `retry_max_attempts` | Эскалировать оператору; заново запустить `audit()` для получения свежего `audit_id` |
| Оператор отсутствует, пока diff показан | `operator_approval_timeout` | Излучить `error_category: operator_timeout`; ничего не записано, staged `.tmp` файлы отброшены |
| Ожидание внеполосных оповещений | `notification_mode` | Не применимо — асинхронного канала не существует; см. §Notification Semantics |
| Полный рескан превышает число документов | `rescan_batch_ceiling` | Ответ включает `has_remaining: true` и `scan_cursor`; оператор повторно вызывает `audit(scan_cursor=<value>)` для возобновления с места, где остановился предыдущий вызов |
| Устаревший, недействительный или неполный `audit_id` предоставлен `delegate()` | `audit_freshness` | Отклонить с `error_category: audit_mismatch` (реестр отсутствует/истёк/несоответствие области) или `error_category: blocking_finding` (присутствуют выводы high/critical или сканирование неполное, `has_remaining: true`) и действием re-run-`audit()`. Если реестр отсутствует/нечитаем, ЗАКРЫВАЕТСЯ ОТКАЗОМ — все записи запрещены до аутентифицированного переопределения через `documenter.override_gate(reason, operator_id)` |

### Notification Semantics

У Документатора нет подсистемы оповещений: нет таймера, демона, канала push-уведомлений и фонового опросника (см. §Purpose и §Approval semantics, main spec). Каждый видимый оператору сигнал — отчёт аудита, предварительный просмотр diff, подсказка конфликта блокировки, запрос одобрения — производится внутри синхронного ответа вызова, который его сгенерировал, и дополнительно сохраняется в журнал событий только для добавления (§Event Schema, configuration guide) для последующего воспроизведения. `notification_mode` существует, чтобы сделать это явным и зарезервировать пространство имён полей: введение асинхронного канала было бы изменением модели в основной спецификации, а не правкой политики, и потребовало бы нового значения `notification_mode` плюс определённый контракт доставки.

---

## Authorization Workflow

Процедура продвижения возможности записи. Каждый шаг — дискретное действие оператора; Документатор никогда не выполняет шаг от своего имени. Шаги 1–3 предшествуют первому вызову Tier 2+; основная спецификация §Trust Tiers указывает и файл политики, и брифинг как обязательные предварительные условия.

1. **Аудит на текущем тире.** Выполнить `audit("*")` и устранить выводы `high` и `critical`. Tier 2+ на некомплаентном корпусе автоматизирует дрейф, а не уборку.
2. **Черновик файла политики.** Составить `documenter_policy.yml` per §Policy File: установить предполагаемые сочетания `change_type` + `trust_level` + `targets` в `allowed_operations` и настроить операционные ручки per §Operational Tuning.
3. **Валидация офлайн.** Загрузить файл-кандидат в режиме только проверки. Загрузка падает на: `allowed_operations` не пусто ниже Tier 2 (правило валидатора), `trust_level` ниже выводимого базового уровня для своего `change_type` (правило авторитета) или нераспознанное значение `notification_mode`.
4. **Записать брифинг.** Составить и заархивировать брифинг оператора — какие документы и значения `change_type` делегированы, максимальное число документов, которые может затронуть один вызов, и процедура отката — затем установить `briefing_ref` на его путь. Этот артефакт — читаемый человеком аналог `allowed_operations`.
5. **Продвинуть тир.** Установить `active_tier` в той же правке, что и `briefing_ref`, чтобы частичная правка не оставила Tier 2+ без ссылки на брифинг.
6. **Первая запись на новом тире.** Вызвать `delegate()` на одном низко-рисковом объекте со свежим `audit_id`. Просмотреть diff поэлементно независимо от тира; Tier 2 даёт возможность, а не сниженную тщательность.
7. **Оценка для Tier 3.** Продвигаться только на основе задокументированных свидетельств: доля одобрения ≥90% на Tier 2 за предшествующие две недели журнала событий (§Tier Selection Guidance, main spec), вычисляемая из полей `decision` в журнале событий (§Event Schema, configuration guide). Затем авторизованные паттерны явно перечисляются в `allowed_operations` с использованием записей `type: pattern` с `pattern_id`, `pattern_description` и `match_criteria` (§Per-Operation Entries); Tier 3 никогда не выводит паттерн, который оператор не авторизовал.

**Откат:** установить `active_tier` на меньшее значение. Изменение вступает в силу при следующем вызове; выполняющийся `delegate()` завершается под тиром, на котором был принят, удерживая блокировку уровня операции согласно §Safety Protocol #2.

---

## Cross-References

- **§Documenter Service (index.md)** — Основная спецификация: контракты интерфейсов, тиры доверия, протокол безопасности, базовый уровень классификации доверия
- **§Configuration Guide** — Хранилище хешей, схема журнала намерения, схема событий, соответствие глоссарию, выравнивание RU
- `AGENTS.md` — Все правила документации, которые обеспечивает этот сервис
- `glossary/index.md` — Канонические определения терминов для проверки соответствия

---

*Определяет поверхность конфигурации для Documenter Service v0.5.0-draft; извлечено из Configuration Guide.*
