# Session Task Brief — Documenter Service Development Contract

## Session Goal
Определить программные зависимости и создать технический контракт (интерфейсы, API, ошибки, конфигурация) для реализации Documenter Service на основе текущей спецификации `docs/en/documenter-service/index.md`.

## Focus Areas
- Программный стек и зависимости (язык, фреймворки, библиотеки)
- Интерфейсы audit() и delegate() — точная спецификация API
- Безопасность (trust tiers, approval flow, audit trail)
- Операционная готовность (конфигурация, логирование, мониторинг)
- Конфликт с fallback-режимом — как service расширяет capabilities

## Questionnaire per Role

**Architect:**
- Q1: Как Documenter Service интегрируется с существующей трёхслойной архитектурой (Layer 0/1/2)? Какие port/adapter границы нужны?
- Q2: Какие компоненты (manifest parser, glossary resolver, diff engine, audit registry, trust classifier) являются ядром, а какие — внешними зависимостями?
- Q3: Как спроектировать API так, чтобы он был чистым контрактом для MCP-интеграции и CLI-вызовов?

**Reliability & Security Specialist:**
- Q1: Какие уязвимости в trust tier модели и approval flow? Как предотвратить unauthorized writes?
- Q2: Как обеспечить atomicity при multi-file commits и crash recovery?
- Q3: Какие security-зависимости нужны (валидация diff, хеширование, signing)?

**Human-Centric Designer:**
- Q1: Как оператор будет взаимодействовать с audit findings и approve/reject решениями?
- Q2: Какие интерфейсы нужны для preview diff, approval workflow и audit report?
- Q3: Как сделать trust tier model понятным для оператора?

**Operations Engineer:**
- Q2: Какие зависимости нужны для конфигурации, логирования, health-check?
- Q3: Как тестировать service (unit, integration, golden fixtures)?
- Q4: Какие observable metrics нужны (audit duration, delegate latency, tier stats)?

### Output Limits
- Maximum findings per role: **5–7**
- Maximum recommendations per role: **3–5**
- Maximum open questions per role: **2–3**
- Total output: **~200 lines**

### Expected Discussion Rounds
- Medium task: **1 round**

### Subject List
- [SUBJ-001]: Software dependencies and technology stack
- [SUBJ-002]: API contract for audit() and delegate()
- [SUBJ-003]: Trust tier model and approval workflow security
- [SUBJ-004]: Configuration and operational requirements
- [SUBJ-005]: Testing strategy and quality gates
- [SUBJ-006]: Integration points with existing Council architecture

### Additional Context / Constraints
- Documenter Service — Supporting service вне трёхслойной цепочки
- MVP: Tier 0 (audit only) + Tier 1 (diff preview)
- Tier 2+ interlocked до Operator Surface specification
- Файлы вне manifest (sessions/<id>/, archive) исключены из scope
- Idle-until-invoked: никаких background processes или file watchers
- Safety Protocol: pre-change snapshot, advisory lock, temp-file + rename, multi-file commit protocol
