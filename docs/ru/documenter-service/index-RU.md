# Сервис Документатора

<!-- CHANGES v0.1.0: Translated from English source. -->

Version: 0.18.0-draft
Status: draft
Last Modified: 2026-11-09
Abstraction: protocol
changelog-path: CHANGELOGS/documenter-service.changes.md

---

## Purpose

Документатор — это **Вспомогательный сервис** (Supporting service), находящийся вне трёхуровневой цепи, обеспечивающий качество документации в соответствии с правилами `AGENTS.md`. Он работает как **утилита по требованию** — все функции запускаются только при явном вызове оператором; фоновые процессы или мониторы файлов не работают автономно. Он предоставляет два интерфейса: `audit()` — для отчётов только на чтение и `delegate()` — для операций записи через навык Documentation Worker. Модель доверия в четыре тирa управляет возможностями записи `delegate()`. Схемы параметров интерфейсов являются авторитетными в §Interfaces; поля конфигурации определены в Справочнике политик (`documenter-service/policy-reference.md`), а структуры данных рантайма — в Руководстве по конфигурации (`documenter-service/configuration-guide.md`).

Граница области: Документатор работает исключительно с артефактами документации, отслеживаемыми в манифесте, и собственным операционным состоянием (каталог `documenter/`). Файлы за пределами этих пространств — файлы рабочего пространства сессий (`sessions/<id>/`), результаты архивирования и любые другие не-артефакты манифеста — явно исключены из области Документатора. Интерфейсы `audit()` и `delegate()` принимают только значения `target_id` из манифеста; любой вызов, ссылающийся на файлы вне манифеста, отклоняется с `error_category: unknown`.

---

## Architecture Position

Документатор — это **Вспомогательный сервис** (Supporting service) вне трёхуровневой цепи. Он вызывается поверхностью оператора Layer 2 (явный вызов MCP-инструмента) и, для записей с LLM, использует **порт исполнения Layer 1** для обращения к Documentation Worker. Он никогда не вызывает Layer 2 или Layer 0 напрямую, и Layer 2 никогда не вызывает LLM от имени Документатора. Он не является частью пути Role-Agent Layer 1: ScenarioLoader и RoleAgentFactory принадлежат Layer 1 (`planned-architecture/layer-1.md`), поэтому нет отношений «равный» или «подчинённый» с ScenarioLoader. Документатор не оркеструет сессии Консилиума и не имеет причинно-следственной зависимости от потока оркестровки. Каждый вызов явный и исходящий от оператора. **Исключение:** операции только на чтение (`audit()`) доступны для Оператора, Агента и Сервиса в пределах разрешённой области согласно матрице authZ (operator-surface, §Caller Identity and Authorization); операции записи (`delegate()`) исходят от оператора или делегированного агента. Намерение записи требует валидации тира согласно политике `allowed_operations`; вызовы предварительного просмотра (`preview: true`) полностью обходят проверки тира (§Preview Exemption).

Режим синхронизации (`pre_check`, см. §Interfaces) — это вентиль целостности середины сессии. Запрос на вентиль поступает через поверхность оператора Layer 2, вызывает Документатора и возвращает синхронный вердикт этой поверхности. Документатор никогда не принимает вызовы от Layer 0 или Layer 1; режим синхронизации сохраняет семантику «простой до вызова». Все режимы выполняют независимое полное сканирование целевых документов. Когда Документатор недоступен (сетевая ошибка, таймаут, сервис остановлен), вызов `audit()` возвращает `unavailable` синхронно; поверхность выдаёт событие `precheck.unavailable` и откладывает переход до переопределения через `council.override_precheck`.

---

## Interfaces

### audit() — Диагностика только на чтение

Возвращает структурированный отчёт, не затрагивая путь записи. Сканирует документы на соответствие правилам с использованием информации из манифеста и глоссария. Таблица ниже — авторитетная схема параметров для этого интерфейса.

| Параметр | Тип | Описание |
|-----------|------|-------------|
| target_id | string | Идентификатор документа из манифеста, или `"*"` для всех |
| severity_min | enum | Минимальная серьёзность для включения: `low`, `medium`, `high`, `critical`. По умолчанию: `low` |
| pre_check | bool | Флажок вентеля целостности середины сессии, устанавливаемый поверхностью Layer 2 на границах фаз (см. `operator-surface/index.md`, §pre_check Gate). Семантика сканирования идентичная; отчёт дополнительно возвращается как синхронный вердикт вентеля вызывающей стороне. Путь записи не задействован. По умолчанию: `false` |
| scan_cursor | string \| null | Токен продолжения от предыдущего частичного сканирования (когда `has_remaining` был `true`). Заставляет `audit()` продолжить сканирование с сохранённой позиции. Отсутствие или `null` означает начало свежего полного сканирования. |

| Возвращает | Тип | Описание |
|---------|------|-------------|
| audit_id | string | Уникальный идентификатор этого вызова аудита (UUIDv4). Сохраняется в реестре аудита (`documenter-service/configuration-guide.md`, §Audit Registry) с временной меткой, областью, выводами, `scanned_ids`, `has_remaining` и `scan_cursor`. Используется вентилём предварительного аудита `delegate()` для проверки свежести, покрытия области, отсутствия блокирующих выводов и завершения сканирования. |
| report | dict | Структурированный список выводов с серьёзностью, темой, идентификатором документа, описанием, рекомендуемым действием |
| has_remaining | boolean | `true`, когда сканирование было приостановлено из-за `rescan_batch_ceiling`; вызывающий должен повторно вызвать `audit(scan_cursor=<value>)` с возвращённым `scan_cursor` для продолжения. |
| scan_cursor | string \| null | Токен продолжения для возобновляемых сканирований. Присутствует только когда `has_remaining` равно `true`. Прозрачное значение, кодирующее последнюю обработанную позицию документа. |

Уровни серьёзности (едины для всех интерфейсов и схемы событий):

| Уровень | Описатель | Влияние на оператора |
|-------|-----------|-----------------|
| `low` | Косметическая проблема, нет влияния на данные | Только журнал аудита |
| `medium` | Потенциальное несоответствие, низкий риск | Отображается в отчёте; сохраняется событие в журнал только для добавления. Запись может быть выполнена только при явном одобрении оператора (не автоматически). |
| `high` | Подтверждённая проблема, умеренный риск | Блокирует запись по умолчанию; требует явного одобрения оператора перед продолжением. |
| `critical` | Нарушение целостности данных, немедленный риск | Блокирует запись + обязательный захват после-фактума (§Safety Protocol #8); нет пути автоприменения на любом тире |

### Semantics одобрения

Одобрение — это явное действие оператора через вне-вызов инструмента `documenter.approve(approval_id, operator_id)` (§Documenter Integration, operator-surface). Документатор не отслеживает состояния, основанные на времени, между вызовами и не одобрят выводы автоматически: таймера или фонового процесса не существует (см. §Purpose, idle-until-invoked). Единственный путь автовыполнения — автоприменение по паттерну Tier 3, основанное на предварительной авторизации паттернов оператором — никогда не по прошествии времени.

Вне-поток одобрения: (1) на Tier 2+, `delegate()` возвращает `approval_required` с `approval_id` и хешем diff, но не выполняет запись; (2) оператор независимо вызывает `documenter.approve(approval_id, operator_id)` (ДОЛЖЕН быть отдельным вызовом от предлагающего вызова); (3) `operator_id` одобрения ДОЛЖЕН отличаться от идентификатора актора предлагающего вызова для предотвращения самоодобрения; (4) при успешном одобрении система продолжает запись с использованием того же хеша diff для привязки; (5) изменённые diff аннулируют ожидающие одобрения.

Одобрение истекает после настроенного окна (`approval_expiry_window`, по умолчанию 30 минут per policy-reference.md §Field Reference). Истёкшее одобрение должно быть получено заново до применения diff. Новый diff-хеш аннулирует любое ещё действительное одобрение.

Устаревшие сопоставления из предыдущих версий: `info` → `low`, `warning` → `medium`, `error` → `high`. Все инструменты рендеринга ДОЛЖНЫ сопоставлять: `critical`→красный, `high`→оранжевый, `medium`→жёлтый, `low`→серый.

### delegate() — Запись через навык Documentation Worker

Вызывает определённую операцию на документе с контролем уровня доверия. Вызываем только после проверки порога политики оператора. Таблица ниже — авторитетная схема параметров для этого интерфейса; поля политики, которые он потребляет, определены в Справочнике политик (§Cross-References).

| Параметр | Тип | Описание |
|-----------|------|-------------|
| target_id | string | Идентификатор документа из манифеста |
| change_type | enum | Один из: `update`, `split`, `create_ru`, `custom` |
| trust_level | enum | *Запрос* вызывающего, не эффективное значение: `safe` или `review`. Документатор выводит требуемый пол по §Trust Classification и принимает запрос только если он равен или строже этого пола (`requested >= derived`); запрос ниже пола отклоняется с `error_category: trust_mismatch`. Эффективный уровень — запрошенный. |
| diff | string (base64-encoded) | Машинно-читаемый diff для предварительного просмотра оператора, закодированный как base64 для обеспечения JSON-безопасной передачи согласно ограничениям UTF-8 JSON (§Common Conventions, service-contract). Обязательно для всех тиров. |
| audit_id | string | Идентификатор от предыдущего возврата `audit()`. Валидируется согласно политике `audit_freshness`. Пропускается только когда вентиль явно отключён в файле политики. |
| preview | boolean | Когда `true`, вызов возвращает только diff без намерения записи и освобождается от проверок `allowed_operations` на всех тирах (§Preview Exemption). Когда опущено или `false`, вызов содержит намерение записи и подвержен обычным ограничениям тира (Tire 0–1 всегда отклоняют записи независимо; Tier 2+ требует явного одобрения; Tier 3 может автоприменять на основе паттернов). |

Поток выполнения: `audit → compute diff → present to operator → wait for approve/reject → apply if approved → commit per Multi-file Commit Protocol (§Safety Protocol #9) → log to audit trail`. Записи на файл используют операцию переименования + временного файла (см. §Safety Protocol #5), гарантируя атомарный переход от staged-состояния к committed-содержимому для одного файла. Атомарность между файлами НЕ обеспечивается переименованием в одиночку — см. §Failure semantics.

**Вентиль предварительного аудита:** По умолчанию `delegate()` требует действительный `audit_id` от предыдущего вызова `audit()`. Валидация происходит через реестр аудита (`documenter-service/configuration-guide.md`, §Audit Registry): (1) `audit_id` должен существовать; (2) его `issued_at` должен попадать в окно `audit_freshness` (поле политики, по умолчанию 30 минут; схема: `documenter-service/policy-reference.md`, §Field Reference); (3) его `scope` должен полностью покрывать `target_id` (`*` совпадает с любым, иначе точное совпадение); (4) `high` или `critical` вывод не может существовать для `target_id` в реестре; (5) если `has_remaining` было `true` для зарегистрированного сканирования, делегат отклоняется до выполнения завершённого повторного сканирования (продолжение на основе курсора через `audit(scan_cursor=<value>)`). Отклонение по правилам (1–3) использует `error_category: audit_mismatch`; на (4) или (5) использует `error_category: blocking_finding`. Предлагаемое действие в обоих случаях: заново запустите `audit()` для цели и повторите. Когда реестр аудита отсутствует, повреждён или нечитаем, вентиль FAILS CLOSED — все операции записи запрещены до явного переопределения оператора. Переопределение требует аутентифицированного действия через `documenter.override_gate(reason, operator_id)`, которое регистрирует инцидент и разрешает ровно один последующий вызов `delegate()` без свежего аудита. Повторные переопределения требуют одобрения Tier 2+. Вентиль настраивается через поле политики `audit_freshness`, но по умолчанию enforced.

**Классификация доверия:** Эффективный уровень доверия назначается Документатором, не вызывающим. Параметр `trust_level` вызывающего может совпадать с выводимым полом или сужать его, но никогда не расслабляет: на шкале `safe < review` инвариант — `requested >= derived`, и эффективный уровень — `requested`. Если `requested < derived`, `delegate()` отклоняет вызов с `error_category: trust_mismatch` до стадии одобрения оператора. Никакого тихого повышения не происходит. Когда классификация неопределённа, применяется `review`. Справочник политик (`documenter-service/policy-reference.md`) может поднять пол выше таблицы, но НЕ должен понижать его (§Policy File, §Authority rule). `suggested_trust_level` в §Event Schema — вывод того же классификатора.

| change_type | Static floor (policy load) | Dynamic derivation (invocation) | `safe` permitted |
|-------------|---------------------------|--------------------------------|------------------|
| `update`      | `safe`                    | `safe` если каждый hunk механический; иначе `review` | Да, только для полностью механического diff |
| `split`       | `review`                  | `review`                         | Нет |
| `create_ru`   | `review`                  | `review`                         | Нет (авто-фикс RU запрещён в MVP) |
| `custom`      | `review`                  | `review`                         | Нет (по умолчанию при неопределённости) |

Static floor для `update` — `safe` для валидации политики во время загрузки (валидатор видит только `change_type`). Dynamic derivation — во время вызова: полностью механический diff выводит `safe`, любой семантический hunk выводит `review`. Запись политики, называющая `update` + `safe`, проходит валидацию во время загрузки; не-механический diff всё ещё выводит `review` и отклоняет запрос `safe` с `trust_mismatch`.

**Семантика отказа:** При прерывании или отказе во время выполнения `delegate()`, операция должна следовать модели «всё или ничего» — частичные записи не сохраняются для одного файла (гарантируется операцией временного файла + переименования syscall). Частичные коммиты между файлами возможны только между переименованиями разных файлов; это не предотвращается атомарностью переименования или журналируемыми файловыми системами (журналирование гарантирует внутреннюю целостность файловой системы, не атомарность между файлами или доставку журнала аудита). Протокол мультифайлового коммита (§Safety Protocol #9) обеспечивает восстанавливаемую eventual consistency при сбое: сбой в середине последовательности оставляет обнаруживаемое частичное состояние с оставшимися staged-файлами и записью намерения, что согласуется следующей проверкой cold-start (§Configuration Guide, Intent Record). Восстановление без вмешательства оператора автоматически, когда не произошло внешних изменений; иначе излучается структурированное событие об ошибке, и восстановление требует явного повторного вызова. Это превращает тихую коррупцию в задокументированное ограничение с явным путём смягчения. Будущие версии (Phase 2+) введут checkpoint/resume через WAL-backed атомарные снимки состояний; до тех пор операторы ДОЛЖНЫ рассматривать каждую границу фазы как точку обязательств.

События, излучаемые во время `delegate()`, используют Event Schema, определённый в §Configuration Guide. Каждая ошибка `delegate()` излучает событие с использованием §Event Schema с `error_category` (`hash_mismatch`, `trust_mismatch`, `audit_mismatch`, `blocking_finding`, `skill_failure`, `operator_timeout`, `gate_failure`, `unknown`).

---

## Trust Tiers

Четыре тира развёртывания, управляющих прогрессирующе большими возможностями записи. Каждый тир требует явной команды оператора для продвижения.

| Тир | Возможность | Автовыполнение | Diff Required | Область |
|------|-----------|----------------|---------------|-------|
| 0 | Только аудит (MVP) | Нет | N/A (нет записей) | Чтение манифеста + docs, производство отчёта |
| 1 | Предварительный просмотр diff | Нет | Да | Производство diffs, нет записей на файловую систему |
| 2 | Подтвердить-на-изменение | Нет | Да, на элемент | Применяет изменения только после индивидуального approve |
| 3 | Пакетное approve | На основе паттернов | Да, на пакет с групповыми сводками | Авторизованные паттерны автоприменяются; критические элементы требуют индивидуального расширенного обзора |

Tir 0–1 поставляются с MVP. Tir 2+ входит в производство только после того, как существует задокументированный файл политики, авторизующий конкретные сочетания `change_type` + `trust_level`. Tir 2+ дополнительно заблокирован на уровне архитектуры: вызов Tir 2+ не принимается, пока спецификация Operator Surface & Escalation не определит аутентифицированный вне-поток одобрения. Сама по себе политика недостаточна. Продвижение на Tir 2+ требует: (a) авторизованный файл политики per `documenter-service/policy-reference.md`, И (b) архивированное брифинг-сообщение оператора, на которое ссылается файл политики (`briefing_ref` поле). Оба условия ДОЛЖНЫ быть выполнены перед первым вызовом Tir 2+. См. §Authorization Workflow для пошаговой процедуры. Автоприменение на основе паттернов на Tir 3 — единственный путь автовыполнения в системе; он выводится из предварительной авторизации паттернов оператором, а не от прошедшего времени (см. §Approval semantics).

### Tier Selection Guidance

| Тир | Рекомендуемый случай использования | Предпосылка |
|------|---------------------|---------------|
| 0 | Начальное развёртывание, изучение поведения системы | Нет |
| 1 | Проверка точности без риска изменений | Нет |
| 2 | Активное обслуживание, выборочные исправления | Файл политики (`documenter-service/policy-reference.md`), авторизующий операции Tir 2 |
| 3 | Крупномасштабная очистка, сезонная реструктуризация | Операционная история, демонстрирующая ≥90% rate одобрения на Tir 2 в течение 2 недель |

### Authorization Workflow

Процедура, посредством которой оператор предоставляет возможность записи. Документатор не выполняет ни один из этих шагов от своего имени; каждый — явное действие оператора, и детальный контрольный список с отказами валидации находится в `documenter-service/policy-reference.md`, §Authorization Workflow.

1. **Аудит** — разрешить выводы `high` и `critical` на текущем тире. Продвижение тира на некомплаентном корпусе автоматизирует drift, не cleanup.
2. **Author** — написать файл политики: записи `allowed_operations` для предполагаемых сочетаний `change_type` + `trust_level` + `targets`, плюс поля операционной настройки.
3. **Validate** — загрузить кандидат-файл в режиме только проверки. Загрузка fails на непустом `allowed_operations` ниже Tier 2, `trust_level` ниже выводимого пола §Trust Classification, или на неопознанном значении политики.
4. **Brief** — архивировать брифинг оператора (делегированная область, максимальное количество документов, которые один вызов может затронуть, процедура реверса) и указать `briefing_ref` на него. Установить `active_tier` и `briefing_ref` в одной записи, чтобы частичная запись не оставила Tier 2+ без брифинга.
5. **Advance** — следующий вызов работает на новом тире. Первый `delegate()` на новом тире нацелен на один низко-рисковый документ; diff проверяется на элемент независимо от тира.
6. **Evaluate** — Tier 3 требует задокументированных доказательств (≥90% approval rate на Tier 2 за предшествующие две недели журнала событий) и явного перечисления авторизованных паттернов; паттерн не выводится.

Откат симметричен: понижение `active_tier` вступает в силу при следующем вызове; ин-флоут `delegate()` завершается под тиром, при котором он был принят.

---

## Quick Start

<!-- STATUS: Specification only, pre-implementation. Not executable until the Moderator is built. See AGENTS.md §1.7 for tooling separation. -->

<span style="color:red;font-weight:bold">⚠ ТОЛЬКО СПЕЦИФИКАЦИЯ — НЕ ВЫПОЛНЯЕТСЯ ДО РЕАЛИЗАЦИИ</span> Следующие примеры иллюстрируют контракт интерфейса; никакие MCP-инструменты в настоящее время не вызываемы. Все сессии работают в fallback-режиме per `AGENTS.md` §1.7.

Путь вызова MVP — MCP stdio. Каждый инструмент требует явного вызова оператора; записи Tier 2+ отключены (см. §Trust Tiers).

```
# Step 1 — Read-only audit (Tier 0) [NON-EXECUTABLE: illustration only]
documenter.audit { "target_id": "*", "severity_min": "low" }

# Step 2 — Preview a change (Tier 1, no writes) [NON-EXECUTABLE: illustration only]
documenter.delegate {
  "target_id": "<doc-id>",
  "change_type": "update",
  "trust_level": "review",
  "diff": "ZGlmIGZpbGUuYmFja3VwLmluZGV4Om1vZGlmaWVk",
  "audit_id": "<audit_id returned by Step 1>"
}
```

На Tir 1 `delegate()` возвращает только предварительный просмотр diff; он не пишет. Tier 2+ остаётся заблокированным, пока спецификация Operator Surface & Escalation не определит вне-поток одобрения. См. §Authorization Workflow и `AGENTS.md` для правил документации, которые этот сервис enforced.

---

## Safety Protocol

1. **Pre-change snapshot**: capture git status and HEAD commit before starting modifications.
2. **Advisory lock**: before any `delegate()` write, acquire an exclusive advisory lock (`flock --exclusive`) on the operation-level lock file (`documenter/.delegate.lock`) covering the entire changeset — target document, `index-RU.md`, changelog, `docs-manifest.yaml`, hash store — for single-host deployments. One operation-level lock replaces per-file locks and is deadlock-free by construction; lock ordering across files is therefore not required. If lock acquisition fails — emit error with context: "Another agent holds an advisory lock on [resource]. Lock owner: [PID/IP], acquired at [timestamp]. Wait? (yes/no) — Default: no after 30s." Distributed cross-host locking (e.g., POSIX flock on shared NFS) is out of scope for MVP; deferred to Phase 2+.
3. **Read-before-write**: immediately before writing any file, re-read it to detect concurrent modifications within the same lock scope. Abort if changed.
4. **Diff mandatory**: every write operation is preceded by machine-readable diff shown to the operator. No silent-auto changes.
5. **Atomic operation**: treat complete execution cycle as logical unit. On failure, abort remaining steps. Write operations MUST use temp-file + rename syscall pattern (write to `.tmp` path, then atomic `os.rename`) to prevent partial writes. This guarantees per-file atomicity only; multi-file changesets MUST additionally follow the Multi-file Commit Protocol (#9).
6. **No auto-commit**: modifies files but never commits them. Operator handles version control.
7. **Structured errors**: Every delegate() failure emits an event using §Event Schema with `error_category` (`hash_mismatch`, `trust_mismatch`, `audit_mismatch`, `blocking_finding`, `skill_failure`, `operator_timeout`, `gate_failure`, `unknown`). Recovery procedures reference the category in `suggested_action`.
8. **Post-mortem capture**: On critical-tier findings triggered by delegate() failure, Documenter captures full operation trace (all steps attempted, intermediate states, timestamps) for operator review.
9. **Multi-file commit protocol**: For changesets spanning multiple files (document, `index-RU.md`, changelog, manifest, hash store), enforce a two-phase commit using only file operations — no background processes or daemons.
   a. **Stage**: write all new content to `.tmp` paths in their target directories. Validate all temp files before proceeding to phase 2.
   b. **Intent record**: before the first rename, write an intent record to `documenter/intent/<tx_id>.json` (see §Configuration Guide, Intent Record) identifying every file in the changeset. This record survives crashes and enables reconstruction. Write MUST use temp-file + rename pattern (same as §5) to prevent partial intent on crash mid-write; cold-start validates intent integrity before using it. Intent record entries MUST reference only manifest-tracked file paths. Any attempt to stage a non-manifest path during a changeset causes `delegate()` to reject with `error_category: unknown` and no writes proceed.
   c. **Ordered renames**: execute renames in a fixed order — document content → `index-RU.md` → changelog → `docs-manifest.yaml` → `documenter/hashes.json`. Manifest is committed last among documents so that a crash before the manifest leaves orphaned but readable files (safe, auditable), rather than dangling cross-references (breaking).
   d. **Cleanup**: after all renames, emit audit events to the append-only audit log, update the hash store contents (the file was already renamed in 9c), then delete the intent record. The intent record MUST be the last element removed — it is the sole durable fallback for post-crash event reconstruction.
   Recovery: on cold-start, if leftover intent records exist, compare each entry's `before_hash` and `after_hash` with actual file content. Three branches: (1) if files match `after_hash` — already committed by a prior successful run, skip; (2) if files match `before_hash` — no external modification since crash, roll forward from staged `.tmp` files automatically; (3) if neither matches — external modification detected, abort and escalate to the operator with `error_category: unknown` and post-mortem trace (§8). The intent record stores structural metadata (tx_id, target_id, created_at, entries[path, before_hash, after_hash]) sufficient to reconstruct which files were changed but does NOT contain the event decisions, operator stances, or full payload of protocol events. The claim that "lost audit events are reconstructed" is incorrect at MVP — only file-change provenance is recoverable; true event reconstruction requires the append-only audit log (§Delivery Semantics, configuration-guide).

---

## Cross-References

- **`documenter-service/policy-reference.md`** — Policy file schema and field reference, operational tuning parameters, authorization workflow checklist
- **`documenter-service/configuration-guide.md`** — Hash store structure, intent record schema, event schema, glossary compliance settings, RU alignment procedure
- `protocol-core/index.md` — Protocol enforcement interface (layer boundary)
- `planned-architecture/index.md` — layer model and Supporting service placement
- `planned-architecture/layer-1.md` — execution ports and Auxiliary Agents
- `fallback/index.md` — Fallback mode operator workflow (used during pre-Moderator phase)
- `docs-manifest.yaml` — Single source of truth for document layout
- `glossary/index.md` — Canonical term definitions for compliance verification
- `.agents/skills/documentation/SKILL.md` — Documentation Worker skill (invoked by delegate())
- `AGENTS.md` — All documentation rules this service enforces

---

*Aligned with planned architecture v0.4.0, sess-documenter-consiliums, sess-services-readiness (D3), and Documenter Service v0.16.0-draft.*
