# Кросс-сервисный контракт на Артефакты и события

id: service-contract
Version: 0.3.2
Status: draft
Abstraction: format
has_translation: docs/ru/service-contract/index-RU.md
references: [service-contract-error-management]
allow_non_index_paths: true
changelog-path: CHANGELOGS/service-contract.changes.md

---

## Область применения

Схемы на уровне полей для артефактов, пересекающих границу сервиса, каноническое событие-обёртка, замороженные перечисления и реестр кодов ошибок. Указываются только те поля, которые читаются по правилам протокола или отображаются в интерфейсе оператора; для всего остального авторитетным источником остаётся текстовое описание.

Нецели: полная схема JSON Schema для каждого артефакта, цепочка миграции схем и специфичные для провайдеров полезная нагрузка (`SUBJ-006`, отложено).

## Общие соглашения

- Объекты JSON в кодировке UTF-8, ключи в `snake_case`, без повторяющихся ключей.
- `schema_version`: целое число, в настоящее время `1`; обязательно для `SessionManifest` и `EventEnvelope`, наследуется встроенными артефактами.
- Метки времени: ISO 8601 UTC с `Z` (`2026-11-08T15:00:00Z`). Хэши: `sha256:<64 lowercase hex>`.
- Неизвестные поля: производители НЕ ДОЛЖНЫ их генерировать; потребители ОБЯЗАНЫ отклонять их (`VAL.001`).
- `null` означает «явное отсутствие замечания». Отсутствие обязательного поля является недействительным, а не null. Обязательно для `stance`.
- Идентификаторы: `session_id` `^sess-[a-z0-9][a-z0-9-]{2,63}$`; `subject_id` `^SUBJ-[0-9]{3}$`; `escalation_id` `^esc-[a-z0-9][a-z0-9-]{2,63}$`; `event_id` `^evt-[a-z0-9][a-z0-9-]{2,63}$`; `review_id` `^rev-[a-z0-9][a-z0-9-]{2,63}$`; `audit_id` UUIDv4; `operator_id` `^op-[a-z0-9][a-z0-9-]{2,63}$`.

## Замороженные перечисления

Замечания wire записываются в нижнем регистре с использованием kebab-case; строки отображения локализуются на стороне интерфейса оператора и никогда не сохраняются.

| Перечисление | Замечания |
|------|--------|
| `severity` | `low`, `medium`, `high`, `critical` |
| `stance` | `support`, `oppose`, `null` |
| `role_status` | `agree`, `concerns`, `blocked-in-scope`, `blocked-escalation` |
| `escalation_reason` | `information-gap`, `irresolvable-conflict`, `risk-threshold-breach` |
| `phase_id` | `1` подача, `2` индивидуальный обзор, `3` обсуждение, `4` проверка консенсуса, `5` резолюция |
| `session_mode` | `fallback`, `moderator` |

Метки глоссария сопоставляются со значениями в схеме: `information gap` → `information-gap`, `irresolvable conflict` → `irresolvable-conflict`, `risk threshold breach` → `risk-threshold-breach`.

## Схемы артефактов

### Вывод

| Поле | Тип | Обязательно | Правило |
|-------|------|----------|------|
| `subject_id` | string | да | Должен существовать в списке объектов обсуждения сессии |
| `severity` | enum | да | |
| `stance` | enum \| null | да | `null`, если не затрагивается предлагаемое решение |
| `summary` | string | да | 1–500 символов; без секретов или полного текста документа |
| `justification` | string \| null | условно | Обязательно для `critical`; указывает на режим отказа или атаку и ссылается на `subject_id` |
| `recommendation` | string \| null | нет | Действие, ориентированное на оператора |
| `evidence_ref` | string \| null | нет | Путь к артефакту или хэш; засекречено |

### Неверный формат

Сгенерировано Layer 0 `extract_role_status()`, когда текст обзора не может быть разобран (перечисление статуса не распознано, отсутствуют обязательные поля). Потребители НЕ ДОЛЖНЫ выводить статус по умолчанию; сессия переходит в состояние `blocked-escalation` с `escalation_reason = information-gap`.

| Поле | Тип | Обязательно | Правило |
|-------|------|----------|------|
| `error_code` | string | да | Всегда `invalid-format` |
| `raw_text_hash` | string | да | `sha256` исходного текста отзыва, предоставленного ролью |
| `parse_attempted` | boolean | да | `true` — указывает, что попытка была предпринята и завершилась неудачей |
| `role_id` | string \| null | нет | Если известно из контекста конверта; отсутствует, если сам отзыв некорректен |
| `session_id` | string \| null | нет | Если известно из контекста конверта; отсутствует, если сам отзыв некорректен |

### Обзор ролей

| Поле | Тип | Обязательно | Правило |
|-------|------|----------|------|
| `escalation_reason` | enum \| null | нет | Обязательно при статусе = `blocked-escalation`; один из: information-gap, irresolvable-conflict, risk-threshold-breach. В остальных случаях — null. Извлекается структурно из текста обзора через Layer 0 `extract_role_status()`. |
| `review_id` | string | да | Формат идентификатора |
| `session_id` | string | да | |
| `role_id` | string | да | Должен существовать в каталоге ролей |
| `phase_id` | integer | да | `2` или `3` |
| `round` | integer | да | `0` для индивидуального обзора |
| `summary_position` | string | да | 1–2000 символов |
| `findings` | Вывод[] | да | Может быть пустым |
| `status` | enum | да | `role_status` |

В обзоре также содержатся `recommended_actions` и `open_questions` (массивы строк, которые могут быть пустыми).

### Статус роли

Сгенерировано функцией `extract_role_status()` из Layer 0; статус, заявленный в рецензии, не считается достоверным, пока не появится здесь.

| Поле | Тип | Обязательно | Правило |
|-------|------|----------|------|
| `role_id` | string | да | Должно существовать в каталоге ролей |
| `status` | enum | да | `role_status` (`agree`, `concerns`, `blocked-in-scope`, `blocked-escalation`) |
| `phase_id` | integer | да | Фаза, формирующая данный статус |
| `source_review_id` | string | да | Идентификатор проверки, из которой происходит данный статус |
| `escalation_reason` | enum \| null | условно | Обязательно при статусе = `blocked-escalation`; один из `information-gap`, `irresolvable-conflict`, `risk-threshold-breach`. Null в остальных случаях. Извлекается структурно из проверки, никогда не выводится из свободного текста. |
| `extraction` | enum | да | `parsed` или `invalid-format` |

### Вердикт консенсуса

| Поле | Тип | Обязательно | Правило |
|-------|------|----------|------|
| `session_id` | string | да | |
| `phase_id` | integer | да | `4` |
| `outcome` | enum | да | `consensus`, `conditional`, `no-consensus`, `blocked-escalation` |
| `role_statuses` | RoleStatus[] | да | По одному для каждой активной роли; без пропусков |
| `blocking_subjects` | string[] | да | Субъекты со статусом блокировки |
| `disagreement_subjects` | string[] | да | Субъекты, имеющие как `support`, так и `oppose` в финальном раунде |
| `escalation_reason` | enum \| null | условно | Обязательно, когда `outcome = blocked-escalation` |
| `computed_at` | timestamp | да | |

### ValidationResult Перевод:

`{check: subject-reference|justification-format|status-extraction, subject_id: string|null, valid: boolean, code: VAL.*|PROT.*, message: string (redacted), severity: severity|null}` — `subject_id` и `severity` необязательны; остальные обязательны.

### EscalationRecord Перевод:

| Поле | Тип | Обязательно | Правило |
|-------|------|----------|------|
| `escalation_id` | string | да | Формат идентификатора |
| `session_id` | string | да | |
| `raised_by_role` | string | да | |
| `reason` | enum | да | `escalation_reason` |
| `severity` | enum | да | |
| `blocker` | string | да | 1–2000 символов |
| `positions` | object[] | да | `{role_id, stance, summary}` для каждой стороны |
| `operator_request` | string | да | Одно конкретное решение или отсутствующий ввод |
| `fallback_strategy` | string | да | Что происходит, если оператор не отвечает |
| `timeout_at` | timestamp \| null | да | `null`, если срок не установлен |
| `resolution` | object | да | `{state: pending\|accepted\|rejected\|superseded\|expired, note, operator_id, resolved_at}` |
| `resume_phase` | integer | да | Точная фаза для возобновления |

### SessionManifest

| Поле | Тип | Обязательно | Правило |
|-------|------|----------|------|
| `schema_version` | integer | да | `1` |
| `session_id` | string | да | Формат идентификатора |
| `mode` | enum | да | `session_mode` |
| `scenario_id` | string | да | |
| `task_ref` | string | да | Относительный путь к краткому описанию задачи |
| `current_phase` | integer | да | `1`–`5` |
| `locked_roles` | string[] | нет | Явно исключенные идентификаторы ролей Core. Пусто или отсутствует, когда активны все роли Core. Каждая запись должна ссылаться на идентификатор роли определенного уровня Core. Используется только при наличии `operator_approval`. |
| `operator_approval` | boolean | нет | `true`, когда исключения ролей Core являются преднамеренными и одобрены оператором. Должно быть `false` или отсутствовать, когда `locked_roles` пусто. Если `true`, `locked_roles` НЕ ДОЛЖНО быть пустым. |
| `no_consensus_budget` | integer | да | Максимальное количество раундов обсуждения до исчерпания бюджета, после чего происходит переход 4→`awaiting-operator`. См. таблицу Outcome-to-Transition в протоколе-core для семантики. Бюджет уменьшается каждый раунд Фазы 3; нулевое значение исчерпывает его и принудительно вызывает `blocked-escalation` при следующей оценке Фазы 4. |
| `phase_state` | enum | да | `active`, `awaiting-operator`, `resolved`, `failed` |
| `active_roles` | string[] | да | Роли Core, если они не перечислены в `locked_roles` с `operator_approval: true`; см. §InvalidFormat Policy для полного правила. |
| `pending_operator_action` | string \| null | да | `null`, если действий нет |
| `configuration_source` | enum | да | `scenario_defaults`, `operator_explicit`, `mixed` |
| `role_agent_config` | object | да | Параметры для каждой роли, фактически используемые |
| `artifacts` | object | да | Пути к файлам фазы и финальным артефактам |
| `created_at` / `updated_at` | timestamp | да | |
| `manifest_hash` | string | да | Хэш канонического JSON без этого поля |
| `previous_manifest_hash` | string \| null | да | Цепочка хэшей; `null` при первой записи |
| `pre_check_override` | string \| null | нет | Причина, записанная при вызове `council.override_precheck` (действие оператора). Пусто или отсутствует, если переопределение не применялось. Логируется как событие `precheck.overridden` в журнале событий. |

## Политика InvalidFormat

`extract_role_status()` возвращает `RoleStatus.extraction = invalid-format`, если статус не может быть распознан однозначно. Runtime НЕ ДОЛЖЕН использовать значение по умолчанию для `agree` или `concerns`. Сессия переходит в состояние `blocked-escalation` с `escalation_reason = information-gap`; исходный текст проверки сохраняется, и Роль не учитывается как давшая Согласие. Оператор может продолжить работу после предоставления интерпретации или повторного запуска Роль.

Отсутствующая роль Core является блокирующей ошибкой протокола, а не упрощением: `blocked-escalation` с `escalation_reason = risk-threshold-breach`.

## Конверт события

Один конверт для всех сервисов. `documenter.issue` и `documenter.approval` у Документатора — это типы событий внутри этого конверта, а не отдельные контракты.

| Поле | Тип | Обязательно | Правило |
|-------|------|----------|------|
| `schema_version` | integer | да | `1` |
| `event_id` | string | да | Уникальный; ключ идемпотентности |
| `event_type` | enum | да | `session.phase-changed`, `role.review-completed`, `consensus.computed`, `escalation.opened`, `escalation.resolved`, `documenter.issue`, `documenter.approval`, `documenter.override_gate`, `notice.simplification-applied`, `notice.fallback-deferred`, `precheck.passed`, `precheck.failed`, `precheck.overridden`, `precheck.unavailable`, `notice.quick_review_disabled`, `notice.documenter_tier2_interlock` |
| `emitted_at` | timestamp | да | |
| `session_id` | string \| null | да | Обязательно для событий, специфичных для сессии; может быть пустым (`null`) только для всеобъемлющих аудитов Документатора по корпусу, которые сканируют все сессии. |
| `phase_id` | integer \| null | да | |
| `actor` | object | да | `{kind: operator\|agent\|service, id}` |
| `severity` | enum \| null | да | |
| `payload` | object | да | Специфично для типа; засекречено |
| `causation_id` / `correlation_id` | string \| null | да | Событие-причина и раунд протокола |
| `caller_class` | string \| null | нет | При наличии повторяет разрешение класса вызывающего из слоя аутентификации (`operator`, `agent` или `service`). Устанавливается входным шлюзом Уровня 2 до того, как события поступят на Уровень 1; опускается, когда аутентификация не применима к этому источнику событий (например, внутренние переходы Уровня 1). |

Актер содержит два различных поля: `actor.kind` — это класс вызывающего объекта (`operator`, `agent` или `service`); `actor.id` — это идентификатор субъекта (например, `op-...` для операторов, UUID для агентов). Конверт также неявно фиксирует результат валидации слоя аутентификации через `severity` при возникновении события, связанного с аутентификацией (см. коды ошибок AUTH.* ниже).

Правило редактирования: манифесты и события НЕ ДОЛЖНЫ содержать секреты, полные промпты или текст документа. Хэши, идентификаторы, количества и краткие резюме разрешены.

## Управление ошибками

Коды ошибок, приоритет конфигураций, версионирование схем, проверка критических **Вывод** и эталонные тестовые данные находятся в `error-management.md`.

## Перекрестные ссылки

- `error-management.md` — коды ошибок, конфигурация, процесс валидации, золотые тестовые данные
- `planned-architecture/layer-0.md` — функции, потребляющие эти схемы
- `planned-architecture/layer-1.md` — производители артефактов Роли
- `execution-runtime/index.md` — семантика Фазы и персистентности
- `operator-ingress/index.md` — рендеринг и доставка Эскалации
- `archive/documenter-service/configuration-guide.md` — полезная нагрузка событий Документатора
