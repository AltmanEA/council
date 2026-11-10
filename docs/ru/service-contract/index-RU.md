# Межсервисный контракт артефактов и событий

Version: 0.2.0
Status: draft
Last Modified: 2026-11-09
Abstraction: format
changelog-path: CHANGELOGS/service-contract.changes.md

---

## Область действия

Полевые схемы для артефактов, пересекающих границу сервиса, канонический событийный конверт, замораживаемые перечисления и реестр кодов ошибок. Указываются только поля, которые читает правило протокола или которые рендерит поверхность оператора; остальное остаётся авторитетным на основе текста.

Не входит в объём: полная JSON Schema для каждого артефакта, цепочка миграции схем и специфичные для провайдеров полезные нагрузки (`SUBJ-006`, отложено).

## Общие положения

- Объекты JSON в кодировке UTF-8, ключи в `snake_case`, без повторяющихся ключей.
- `schema_version`: целое число, в настоящее время `1`; обязательно для `SessionManifest` и `EventEnvelope`, наследуется встроенными артефактами.
- Метки времени: ISO 8601 UTC с `Z` (`2026-11-08T15:00:00Z`). Хэши: `sha256:<64 шестнадцатеричных символа в нижнем регистре>`.
- Неизвестные поля: производители ДОЛЖНЫ их не генерировать; потребители ДОЛЖНЫ их отклонять (`VAL.001`).
- `null` означает «явно отсутствует значение». Отсутствие обязательного поля недействительно, а не null. Обязательно для `stance`.
- Идентификаторы: `session_id` `^sess-[a-z0-9][a-z0-9-]{2,63}$`; `subject_id` `^SUBJ-[0-9]{3}$`; `escalation_id` `^esc-[a-z0-9][a-z0-9-]{2,63}$`; `event_id` `^evt-[a-z0-9][a-z0-9-]{2,63}$`; `review_id` `^rev-[a-z0-9][a-z0-9-]{2,63}$`; `audit_id` UUIDv4; `operator_id` `^op-[a-z0-9][a-z0-9-]{2,63}$`.

## Замораживаемые перечисления

Проводные значения — строчные kebab-case; строки отображения локализуются поверхностью оператора и никогда не хранятся.

| Перечисление | Значения |
|------|--------|
| `severity` | `low`, `medium`, `high`, `critical` |
| `stance` | `support`, `oppose`, `null` |
| `role_status` | `agree`, `concerns`, `blocked-in-scope`, `blocked-escalation` |
| `escalation_reason` | `information-gap`, `irresolvable-conflict`, `risk-threshold-breach` |
| `phase_id` | `1` подача, `2` индивидуальный обзор, `3` обсуждение, `4` проверка консенсуса, `5` разрешение |
| `session_mode` | `fallback`, `moderator` |

Метки глоссария сопоставляются с проводными значениями: `information gap` → `information-gap`, `irresolvable conflict` → `irresolvable-conflict`, `risk threshold breach` → `risk-threshold-breach`.

## Схемы артефактов

### Finding

| Поле | Тип | Обязательно | Правило |
|-------|------|----------|------|
| `subject_id` | string | да | Должно существовать в списке тем сессии |
| `severity` | enum | да | |
| `stance` | enum \| null | да | `null`, когда не addressed a proposed decision → «`null`, когда не addressed a proposed decision» |
| `summary` | string | да | 1–500 символов; без секретов или полного текста документа |
| `justification` | string \| null | условно | Обязательно для `critical`; указывает режим отказа или атаку и ссылается на `subject_id` |
| `recommendation` | string \| null | нет | Действие для оператора |
| `evidence_ref` | string \| null | нет | Путь к артефакту или хэш; засекреченный |

### InvalidFormat

Генерируется Layer 0 `extract_role_status()`, когда текст обзора не может быть разобран (перечисление статуса неузнаваемо, отсутствуют обязательные поля). Потребители НЕ ДОЛЖНЫ выводить статус по умолчанию; сессия переходит в `blocked-escalation` с `escalation_reason = information-gap`.

| Поле | Тип | Обязательно | Правило |
|-------|------|----------|------|
| `error_code` | string | да | Всегда `invalid-format` |
| `raw_text_hash` | string | да | `sha256` исходного текста обзора, поданного ролью |
| `parse_attempted` | boolean | да | `true` — указывает, что попытка была предпринята и завершилась неудачей |
| `role_id` | string \| null | нет | Если известно из контекста конверта; отсутствует, если сам обзор испорчен |
| `session_id` | string \| null | нет | Если известно из контекста конверта; отсутствует, если сам обзор испорчен |

### RoleReview

| Поле | Тип | Обязательно | Правило |
|-------|------|----------|------|
| `escalation_reason` | enum \| null | нет | Обязательно, когда статус = `blocked-escalation`; один из: information-gap, irresolvable-conflict, risk-threshold-breach. Иначе null. Структурно извлекается из текста обзора через Layer 0 `extract_role_status()`. |
| `review_id` | string | да | Формат идентификатора |
| `session_id` | string | да | |
| `role_id` | string | да | Должно существовать в каталоге ролей |
| `phase_id` | integer | да | `2` или `3` |
| `round` | integer | да | `0` для индивидуального обзора |
| `summary_position` | string | да | 1–2000 символов |
| `findings` | Finding[] | да | Может быть пустым |
| `status` | enum | да | `role_status` |

Обзор также содержит `recommended_actions` и `open_questions` (массивы строк, возможно пустые).

### RoleStatus

Генерируется Layer 0 `extract_role_status()`; объявленный обзором статус не заслуживает доверия, пока он не появится здесь.

| Поле | Тип | Обязательно | Правило |
|-------|------|----------|------|
| `role_id` | string | да | Должно существовать в каталоге ролей |
| `status` | enum | да | `role_status` (`agree`, `concerns`, `blocked-in-scope`, `blocked-escalation`) |
| `phase_id` | integer | да | Фаза, породившая этот статус |
| `source_review_id` | string | да | Идентификатор обзора, из которого получен этот статус |
| `escalation_reason` | enum \| null | условно | Обязательно, когда статус = `blocked-escalation`; один из `information-gap`, `irresolvable-conflict`, `risk-threshold-breach`. Null в остальных случаях. Извлекается структурно из обзора, никогда не выводится из свободного текста. |
| `extraction` | enum | да | `parsed` или `invalid-format` |

### ConsensusVerdict

| Поле | Тип | Обязательно | Правило |
|-------|------|----------|------|
| `session_id` | string | да | |
| `phase_id` | integer | да | `4` |
| `outcome` | enum | да | `consensus`, `conditional`, `no-consensus`, `blocked-escalation` |
| `role_statuses` | RoleStatus[] | да | По одному на активную роль; без пропусков |
| `blocking_subjects` | string[] | да | Темы с блокирующим статусом |
| `disagreement_subjects` | string[] | да | Темы, имеющие и `support` и `oppose` в последнем раунде |
| `escalation_reason` | enum \| null | условно | Обязательно, когда `outcome = blocked-escalation` |
| `computed_at` | timestamp | да | |

### ValidationResult

`{check: subject-reference|justification-format|status-extraction, subject_id: string|null, valid: boolean, code: VAL.*|PROT.*, message: string (засекречен), severity: severity|null}` — `subject_id` и `severity` необязательны; остальное обязательно.

### EscalationRecord

| Поле | Тип | Обязательно | Правило |
|-------|------|----------|------|
| `escalation_id` | string | да | Формат идентификатора |
| `session_id` | string | да | |
| `raised_by_role` | string | да | |
| `reason` | enum | да | `escalation_reason` |
| `severity` | enum | да | |
| `blocker` | string | да | 1–2000 символов |
| `positions` | object[] | да | `{role_id, stance, summary}` по сторонам |
| `operator_request` | string | да | Одно конкретное решение или недостающий ввод |
| `fallback_strategy` | string | да | Что происходит, если оператор не отвечает |
| `timeout_at` | timestamp \| null | да | `null`, когда дедлайн не установлен |
| `resolution` | object | да | `{state: pending\|accepted\|rejected\|superseded\|expired, note, operator_id, resolved_at}` |
| `resume_phase` | integer | да | Точная фаза для продолжения |

### SessionManifest

| Поле | Тип | Обязательно | Правило |
|-------|------|----------|------|
| `schema_version` | integer | да | `1` |
| `session_id` | string | да | Формат идентификатора |
| `mode` | enum | да | `session_mode` |
| `scenario_id` | string | да | |
| `task_ref` | string | да | Относительный путь к краткому заданию |
| `current_phase` | integer | да | `1`–`5` |
| `locked_roles` | string[] | нет | Явно исключённые идентификаторы ролей Core. Пусто или отсутствует, когда все роли Core активны. Каждая запись должна ссылаться на идентификатор роли определённого яруса Core. Используется только при наличии `operator_approval`. |
| `operator_approval` | boolean | нет | `true`, когда исключения ролей Core осознанны и одобрены оператором. Должно быть `false` или отсутствовать, когда `locked_roles` пусто. Если `true`, `locked_roles` НЕ ДОЛЖНО быть пустым. |
| `no_consensus_budget` | integer | да | Максимальное число раундов обсуждения перед исчерпанием бюджета, переходящее 4→`awaiting-operator`. См. таблицу переходов результатов в protocol-core §Outcome-to-Transition. Бюджет уменьшается за каждый раунд фазы 3; нулевое значение исчерпывает его и принуждает к `blocked-escalation` при следующей оценке фазы 4. |
| `phase_state` | enum | да | `active`, `awaiting-operator`, `resolved`, `failed` |
| `active_roles` | string[] | да | Роли Core, если не перечислены в `locked_roles` с `operator_approval: true`; см. §Правило InvalidFormat для полного правила. |
| `pending_operator_action` | string \| null | да | `null`, когда действий нет |
| `configuration_source` | enum | да | `scenario_defaults`, `operator_explicit`, `mixed` |
| `role_agent_config` | object | да | Параметры на роль, фактически используемые |
| `artifacts` | object | да | Пути к файлам фаз и итоговым артефактам |
| `created_at` / `updated_at` | timestamp | да | |
| `manifest_hash` | string | да | Хэш канонического JSON без этого поля |
| `previous_manifest_hash` | string \| null | да | Цепочка хэшей; `null` при первой записи |
| `pre_check_override` | string \| null | нет | Причина, записанная при вызове `council.override_precheck` (глагол оператора). Пусто или отсутствует, когда перевод не применялся. Журналируется как событие `precheck.overridden` в журнале событий. |

## Правило InvalidFormat

`extract_role_status()` возвращает `RoleStatus.extraction = invalid-format`, когда статус не может быть разобран неоднозначно. Время выполнения НЕ ДОЛЖНО использовать статус по умолчанию `agree` или `concerns`. Сессия переходит в `blocked-escalation` с `escalation_reason = information-gap`; исходный текст обзора сохраняется, и роль не засчитывается как согласившаяся. Оператор может продолжить после предоставления интерпретации или повторного запуска роли.

Отсутствующая роль Core — это блокирующая ошибка протокола, а не упрощение: `blocked-escalation` с `escalation_reason = risk-threshold-breach`.

## Событийный конверт

Один конверт для всех сервисов. `documenter.issue` и `documenter.approval` Documenter'а — это типы событий внутри этого конверта, а не отдельный контракт.

| Поле | Тип | Обязательно | Правило |
|-------|------|----------|------|
| `schema_version` | integer | да | `1` |
| `event_id` | string | да | Уникально; ключ идемпотентности |
| `event_type` | enum | да | `session.phase-changed`, `role.review-completed`, `consensus.computed`, `escalation.opened`, `escalation.resolved`, `documenter.issue`, `documenter.approval`, `documenter.override_gate`, `notice.simplification-applied`, `notice.fallback-deferred`, `precheck.passed`, `precheck.failed`, `precheck.overridden`, `precheck.unavailable`, `notice.quick_review_disabled`, `notice.documenter_tier2_interlock` |
| `emitted_at` | timestamp | да | |
| `session_id` | string \| null | да | Обязательно для событий, специфичных для сессии; допускает `null` только для общекорпусных проверок Documenter, сканирующих все сессии. |
| `phase_id` | integer \| null | да | |
| `actor` | object | да | `{kind: operator\|agent\|service, id}` |
| `severity` | enum \| null | да | |
| `payload` | object | да | Специфично для типа; засекреченный |
| `causation_id` / `correlation_id` | string \| null | да | Событие-причина и раунд протокола |
| `caller_class` | string \| null | нет | При наличии — повторяет разрешение класса вызывающего из уровня аутентификации (`operator`, `agent` или `service`). Устанавливается Layer 2 ingress перед потоком событий в Layer 1; отсутствует, когда аутентификация не применима к источнику этого события (например, внутренние переходы Layer 1). |

У актора два различных поля: `actor.kind` — класс вызывающего (`operator`, `agent` или `service`); `actor.id` — идентификатор субъекта (например, `op-...` для операторов, UUID для агентов). Конверт также неявно записывает результат валидации уровня аутентификации через `severity`, когда генерируется связанное с аутентификацией событие (см. коды ошибок AUTH.* ниже).

Правила засекречивания: манифесты и события НЕ ДОЛЖНЫ содержать секретов, полных приглашений или текста документа. Хэши, идентификаторы, подсчёты и краткие резюме разрешены.

## Управление ошибками

Коды ошибок, приоритет конфигурации, версионирование схем, валидация критических находок и золотые контрольные примеры находятся в `error-management/index.md`.

## Перекрёстные ссылки

- `error-management/index.md` — коды ошибок, конфигурация, процесс валидации, золотые контрольные примеры
- `planned-architecture/layer-0.md` — функции, потребляющие эти схемы
- `planned-architecture/layer-1.md` — источники ролевых артефактов
- `execution-runtime/index.md` — семантика фаз и сохранённости
- `operator-surface/index.md` — рендеринг и доставка эскалаций
- `documenter-service/configuration-guide.md` — полезные нагрузки событий Documenter'а
