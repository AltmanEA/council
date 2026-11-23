# Task Brief — sess-documenter-concept-revision

Session: sess-documenter-concept-revision
Date: 2026-11-19
Mode: Subagent Fallback (fallback/index.md v0.6.0), sequential role launch per operator decision.

## Goal

Переформулировать базовые концепции Документатора (Documenter Service) заново. Текущая разработка зашла в тупик; проектирование начинается с чистого листа на трёх новых операторских принципах. Результат консилиума будет записан в документацию Documenter (папка documenter: `docs/en/documenter-service/`) через Documentation Worker skill после утверждения изменений оператором.

## Operator Principles (нормативные входные ограничения)

- **OP-1. Instant operator approval.** Один оператор может утверждать любые правки в документации в любой момент, без ожидания каких-либо gating-механизмов (никаких policy-gate, interlock, readiness-sentinel, out-of-band approval queues, блокирующих pre_check).
- **OP-2. Maximum simplicity.** Система должна быть максимально простой. Каждый сохраняемый механизм должен оправдать своё существование; по умолчанию всё, что не является строго необходимым, удаляется.
- **OP-3. Commit-audit as primary error control.** Основное средство контроля ошибок — аудит git-коммита (после факта) и откат (revert) при необходимости. Превентивные блокирующие проверки де-приоритизируются в пользу постфактум-контроля.

## Context (текущее состояние, от которого уходим)

Текущая конструкция Документатора (см. `docs/en/documenter-service/index.md` v0.24.0-draft, `mvp-contract.md`, `policy-reference.md`, `approval-surface.md`, AGENTS.md §1.5, §1.7):
- Trust tiers (Tier 0–1 operational, Tier 2+ dormant за «dual interlock»);
- Dual interlock: `documenter_policy.yml` (`active_tier: 1`, null `briefing_ref`) + sentinel `documenter/.operator_ingress_ready`; активация Tier 2+ — только оператором out-of-session;
- Operator Ingress (JSON-RPC stdio, pre_check gate, notices, sentinel) — код есть, не зарегистрирован;
- Approval Surface (out-of-band approval Tier 2+);
- Audit registry, token model, policy schema;
- Многослойные контракты: mvp-contract / mvp-interfaces / mvp-data-models / configuration-guide / policy-reference / approval-surface.

Именно эта многослойность и gating-механика признаны тупиком. Консилиум должен определить, что из этого survives под новыми принципами, а что удаляется.

## Constraints

- Фолбэк-режим: консенсус-документ в markdown (`sessions/<id>/...`), без SessionManifest/JSON.
- Итоговые изменения в `docs/`, манифест, `CHANGELOGS/` — только через Documentation Worker skill после Approve оператора (§2 AGENTS.md). КонсилиумProduces только консенсус-документ и предложение changeset.
- Английский authoritative; RU — derivative.
- Терминология — по глоссарию (`docs/en/glossary/index.md`).

## Subject List

- **SUBJ-001: Модель утверждения правок.** Оператор утверждает любые правки мгновенно (OP-1). Что заменяет/вытесняет прежние gating-механизмы (tiers, interlock, policy gate, approval surface, pre_check)? Каков минимальный протокол «утвердил → записано»?
- **SUBJ-002: Границы простоты (что удаляем).** Какой минимальный набор компонентов Documenter остаётся под OP-2? Что удаляем: trust tiers, policy engine, audit registry, token model, Operator Ingress как сервис, approval surface? Что обязана делать система вместо них?
- **SUBJ-003: Модель контроля ошибок.** Аудит коммита + откат как первичный контроль (OP-3). Что означает «аудит коммита» практически: кто/когда/против чего проверяет уже сделанный коммит? Что делает «откат при необходимости» надёжным (кто детектирует необходимость, кто исполняет revert)? Какие минимальные превентивные проверки допустимы как исключение?
- **SUBJ-004: Судьба существующих артефактов документации и кода.** Как соотносятся новые концепции с существующими документами documenter-service (index, mvp-contract, mvp-interfaces, mvp-data-models, policy-reference, approval-surface, configuration-guide) и пакетом кода `documenter_service/`? Переписываем, архивируем, помечаем superseded?
- **SUBJ-005: Размещение и структура новой концептуальной документации.** Куда и в какой структуре кладём переформулированные концепции («папка documenter»)? Одна документ-основа концепций + ссылки, или иной layout? Взаимосвязь с Documentation Worker skill и tools/.

## Output limits

Each role: one structured document per fallback/index.md §Output Structure, ≤ ~120 lines. Findings must reference SUBJ-xxx identifiers.

## Role roster (sequential launch per operator instruction)

1. Architect
2. Reliability & Security Specialist
3. Human-Centric Designer
4. Operations Engineer

## Discussion

Phase 3: один раунд дискуссии (operator decides advance when positions repeat).
