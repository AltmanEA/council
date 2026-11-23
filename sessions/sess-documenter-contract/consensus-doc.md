# Consensus Document — Documenter Service Development Contract

Session: `sess-documenter-contract`
Date: 2026-11-12
Roles: Architect, ReliabilitySecurity, HumanCentricDesigner, OperationsEngineer
Status: Conditionally Resolved — 5 conflicts require operator decision

---

## Decision

Documenter Service MVP — **read-only surface**: `audit()`, `delegate(preview: true)`, `documenter.status` (read-only). Apply-ветка `delegate()`, approval-поток, `override_gate`, Multi-file Commit Protocol, Tier 2+ интерфейсы — **зарезервированы в контракте, но структурно отсутствуют в MVP-сборке**.

## Rationale

- **Безопасность:** `delegate()` write невозможен без авторизованного ingress (Layer 2), которого нет в MVP. Без write-ветки fail-closed гейт не может сработать, а corrupt-реестр остаётся невидимым — поэтому `documenter.status` становится обязательным индикатором деградации (везде converged, 4 роли).
- **Канонический diff:** объект одобрения — отрендеренный Documenter'ом `diff_text` + `diff_hash` над нормализованными байтами; apply-time verification (пересчёт результата Worker'а) — контрактная норма, но реализация — Tier 2 (консенсус 4 роли).
- **Токены:** `scan_cursor` и `approval_id` — случайные, серверно-хранимые, связанные с `(audit_id, target_id)`, одноразовые. HMAC отклонён — избыточен для idle-until-invoked сервиса и требует секрет-менеджмента.
- **Стек:** вынесен из контракта в ADR; контракт фиксирует только платформо-зависимые требования (atomic rename, advisory lock, отсутствие LLM-зависимостей).

## Subjects with Outcomes

| Subject | Status | Notes |
|---|---|---|
| SUBJ-001 (Stack) | Agreed | Out of contract into ADR; platform constraints retained |
| SUBJ-002 (API contract) | Conditionally Agreed | C1, C2, C4 resolved; operator decides on diff size limits |
| SUBJ-003 (Trust/Approval) | Conditionally Agreed | C3 resolved; operator decides Tier 2/3 contract presence |
| SUBJ-004 (Config/Operations) | Conditionally Agreed | C5 unresolved — operator must choose threat model |
| SUBJ-005 (Testing) | Agreed | MVP: permission matrix, canonization golden, VAL.001, corrupt-registry readiness |
| SUBJ-006 (Integration) | Agreed | MVP event channel = registry + stdout JSON; envelope deferred |

## Conflicts & Disagreements

| # | Subject | Position A | Position B |
|---|---|---|---|
| C1 | SUBJ-002 | RS: signed token + consumed-nonce journal | A/Ops/HCD: stored single-use tokens, drop HMAC |
| C2 | SUBJ-002 | Ops: apply-time verification = Tier 2 only | A/RS: apply-time recheck = contract norm (MVP spec, Tier 2 impl) |
| C3 | SUBJ-003 | Ops: Tier 2+ excluded from MVP contract entirely | A/HCD: Tier 2/3 interfaces/enums in contract, apply absent from build |
| C4 | SUBJ-006 | Ops/A: deferred envelope = documented channel | RS: deferral breaks format; needs explicit extender |
| C5 | SUBJ-004 | RS: hash-chain mandatory now | Ops: hash-chain + retention incompatible without checkpoint signer |

## Reservations

- **Architect:** Threat model for `documenter/` — единственный вопрос, от которого зависят подписи, hash-chain, внешний канал override. Runtime (OpenCode → TS?) — операторское решение. `documenter/` под git или нет — зависит от этого.
- **ReliabilitySecurity:** Модель угроз для `documenter/` (см. C5) — определяет смысл всех криптопримитивов контракта. Кто утверждает экстендер `session_id` nullable для fallback — service-contract владелец или Documenter?
- **HumanCentricDesigner:** Окончательный выбор стека (A) — влияет на тестовую инфраструктуру. Кто рендерит `diff_text` для человека (MCP-клиент vs Layer 2) — обязанность Surface spec.
- **OperationsEngineer:** Принимает ли оператор MVP как строго read-only? (C3) — от этого зависит объём контракта. Truncation с checkpoint — кто подписывает checkpoint, если подписей в MVP нет? (C5)

## Open Questions

1. **Threat model for `documenter/`:** локальный доступ на запись = компрометация или нет? («Да» → убрать криптопримитивы из контракта, вынести approval/override во внешний канал. «Нет» → ключ подписи вне каталога, hash-chain и подпись токенов нормативны.)
2. **Stack choice:** Python 3.11+ stdlib или TypeScript/Node? (OpenCode-окружение тянет TS, тогда MCP SDK и advisory lock меняются.)
3. **`documenter/` under git or not?** Affects token choice, registry recovery, and whether it falls under "files outside manifest excluded from scope."
4. **MVP volume:** strictly read-only, or do Tier 2/3 interfaces/enums stay in the contract spec?
5. **Who renders `diff_text` for the human?** Layer 2 surface or MCP client? Must be explicit obligation in the spec.
6. **Nullable `session_id` extender:** who approves — `service-contract` owner or Documenter spec?

## Action Items

| Priority | Action | Owner | Blocks |
|---|---|---|---|
| P0 | Operator decision: threat model for `documenter/` | Operator | C5, all crypto decisions |
| P0 | Operator decision: stack choice (Python vs TS) | Operator | ADR, test infrastructure |
| P0 | Operator decision: `documenter/` under git? | Operator | Token mechanism, retention |
| P1 | Write ADR for stack + threat model | Architect | Implementation start |
| P1 | Draft MVP contract spec: `audit()`, `preview`, `status` | Architect + RS | Implementation start |
| P1 | Draft Tier 2/3 spec (interfaces, approval flow, commit protocol) | RS + HCD | Tier 2+ |
| P1 | Define `next_action` enum + expanded `error_category` values | HCD | All interface responses |
| P1 | Draft policy file schema (`schema_version`, validation rules) | Ops | Config management |
| P2 | Define canonical diff normalization rules | Architect | SUBJ-002 |
| P2 | Draft retention policy + checkpoint record format | Ops | SUBJ-004 |
| P2 | Draft test plan: permission matrix, canonization golden, VAL.001 | Ops | Quality gates |

## Escalation References

— None —

## Downgraded Critical Findings

- HCD SUBJ-003 (Tier 3 habituation): downgraded from critical to high — not an MVP blocker since apply-branch absent from MVP build.
- Ops SUBJ-004 (no readiness indicator): downgraded from critical to high — fail-closed at `delegate()` is correct behavior; the real issue is unobservability, which `documenter.status` resolves.
