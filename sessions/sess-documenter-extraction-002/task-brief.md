# Session Task Brief — sess-documenter-extraction-002

Mode: Subagent Fallback v0.6.0 (`fallback/index.md`)
Date: 2026-11-17
Roster: Architect, Reliability & Security Specialist, Human-Centric Designer, Operations Engineer

## Session Goal

Независимый пересмотр: имеет ли смысл выделить Documenter Service (`documenter_service/` + его specs/state/tests) в отдельный проект/репозиторий по образцу ADR-014 (techdoc-translator) — на текущем этапе, с учётом фактов, изменившихся с момента предыдущего консенсуса.

## Context: prior consensus (must be challenged, not copied)

`sessions/sess-documenter-extraction/consensus-doc.md` (2026-11-17, conditionally resolved): **не выносить сейчас**; пересмотр по трём проверяемым триггерам (MVP-завершённость, стабилизация контракта, решение оператора). Роли прошлой сессии: все `concerns`, блоков нет.

**Эта сессия — самостоятельная ре-ревью.** Вы не связаны прошлым решением; подтвердите, скорректируйте или опровергните его аргументы своими проверками. Особое внимание — фактам, изменившимся ПОСЛЕ прошлого консенсуса (см. Additional Context).

## Verified repo facts (проверяйте сами; читать можно, писать запрещено)

- `documenter_service/` — 26 .py файлов; `adapters/` (fs_manifest.py, hash_store.py, commit_protocol.py, worker_stub.py, jsonl_registry.py, lock.py, ...), `core/` (policy.py, audit.py, write.py, trust.py, ...), `mcp_stdio.py`, `__main__.py`, `ports.py`.
- Coupling с Council: `adapters/fs_manifest.py` читает `docs-manifest.yaml`; `core/policy.py` читает `documenter_policy.yml` (дефолт — repo root, L91); path-конвенции `documenter/` state; вызов Documentation Worker skill.
- `core/policy.py` (~L360–409): surface-гейт `operator_surface_ready()` — sentinel `documenter/.operator_surface_ready`; на диске ОТСУТСТВУЕТ (fail-closed, проверено).
- `documenter_policy.yml`: `active_tier: 1`, `allowed_operations: []`, `briefing_ref: null` (проверено).
- Packaging: `pyproject.toml`/`setup.py` ОТСУТСТВУЮТ (проверено); `contract_version` в коде пакета не найден (grep пуст).
- Тесты: `tests/` — документер-специфичных файлов большинство (22× `test_documenter_*` + `test_operator_*`), фикстуры `tests/fixtures/documenter/` — мини-корпус Council.
- `documenter/` state содержит `artifacts/translation/` (provenance, git-tracked, вне manifest).
- Write authority: Documentation Worker skill — единственный исполнитель записей (AGENTS.md §2); Documenter Tier 2+ dormant за dual interlock (ADR-013 + ADR-016).

## Факты, изменившиеся ПОСЛЕ прошлого консенсуса (новые входные данные)

1. **Operator Surface реализован как код** — p3 MVP (`operator_surface/`, коммит cf4573f; ADR-015/ADR-016). Прошлая сессия рассматривала его как «код — до или после выноса» (открытый вопрос). Теперь он существует: JSON-RPC stdio verbs, pre_check gate, notices, readiness sentinel. НЕ зарегистрирован; sentinel не создан — интерлок закрыт обоими код-гейтами.
2. **Vendored distribution модель** для techdoc-translator: `vendor/techdoc-translator/` + `defaults/translation.lock` (`mode: external`, tag v0.1.0, commit pin, contract_version 1.0.0; коммит 07f8f06). Прецедент ADR-014 теперь включает consumer-side vendoring-паттерн.
3. **AGENTS.md v2.0.1** — §1.5/§1.7 выровнены с ADR-016: дуальный интерлок описан как policy-state + sentinel.

## Focus Areas

- Переносимость контракта Documenter (что именно является «контрактом»: CLI exit codes? MCP tools? порты?) и его зрелость.
- Прочность dual interlock при внешнем размещении кода (policy-файл, sentinel, регистрация MCP, env `COUNCIL_OPERATOR_ID`).
- Стоимость: второй репозиторий, CI, release-цикл, prose-contract synchronization, одиночный оператор.
- Тесты/фикстуры/state: что переносимо без Council-контекста.
- Отличие топологии от ADR-014 (stateless one-way CLI vs bidirectional service с write-path).
- НОВЫЙ: меняет ли наличие Operator Surface как кода баланс аргументов (в обе стороны)?

## Questionnaire per Role

**Architect:**
- Q1: Есть ли сейчас versioned contract boundary, или вынос законсервирует draft-состояние? Что конкретно должно существожать до любого выноса?
- Q2: Куда должны «переехать» Council-специфичные порты (ManifestSource, policy path, skill binding) — and is that refactor cheap or deep?

**Reliability & Security Specialist:**
- Q1: Какие конкретные fail-closed гарантии (interlock, gate, hashes, intent) ослабевают при кросс-репо размещении? Назовите attack/failure mode.
- Q2: Кто является approver при внешнем коде (operator_surface как код теперь есть) — меняется ли threat model?

**Human-Centric Designer:**
- Q1: Где оператор фактически теряет время/понимание при текущем in-tree размещении? Есть ли подтверждённая боль или гипотетическая?
- Q2: Становится ли ментальная модель «кто что пишет» сложнее или проще при выносе?

**Operations Engineer:**
- Q1: Оцените операционную стоимость второго репо для одного оператора (CI, релизы, lock, sync prose-contracts) против стоимости integration-адаптера in-tree.
- Q2: Тесты и фикстуры: доля переносимых; что нужно сделать до переносимости (пороги)?

## Output Limits

- Максимум находок на роль: 5–7; рекомендаций: 3–5; открытых вопросов: 2–3; ~150 строк всего.

## Expected Discussion Rounds

1 раунд дискуссии (сложная задача, но с прецедентом-консенсусом).

## Subject List (каноническая)

- `SUBJ-001`: Решение о выносе Documenter Service (сейчас / позже по триггерам / никогда)
- `SUBJ-002`: Контракт и версионирование (contract_version, схемы, packaging, транспорт CLI/MCP/порт)
- `SUBJ-003`: Write authority и audit-контур (Documentation Worker skill, `documenter/` state, hashes/intent/registry)
- `SUBJ-004`: Dual interlock (ADR-013/ADR-016): policy-state, sentinel, регистрация MCP, env COUNCIL_OPERATOR_ID — прочность при выносе
- `SUBJ-005`: Спецификации, тесты, фикстуры и state — переносимость без Council-контекста
- `SUBJ-006`: Трансферируемость паттерна ADR-014 (techdoc-translator: stateless CLI, lock/vendoring) к Documenter
- `SUBJ-007` (новая): Наличие Operator Surface как кода (p3 MVP) — влияние на предпосылки и баланс решения

## Additional Context / Constraints

- Проект: этап Specification→MVP (ADR-011). Единственный оператор. Tier 2+ dormancy — намеренный safety-дефолт, а не технический долг.
- Известный precedent-риск: prose-contract divergence (sess-translate-automation 2026-11-14).
- Документированной операционной боли от in-tree размещения нет; HCD проверяет это с вопросом к оператору (Open Question допустим).
- Разрешено предлагать новые subjects (адмитируются модератором перед раундом дискуссии).

## Mode constraints for all roles

Read-only: вы НЕ изменяете файлы. Проверяйте фактуру по репозиторию; находки без subject-ссылки маркируйте `[NO-SUBJ]`. Критические находки обязаны называть конкретный failure mode + subject.

**Execution constraint (operator, 2026-11-17):** субагенты локальной модели НЕ запускать параллельно — строго последовательно, один за другим (касается всех последующих фаз и раундов).
