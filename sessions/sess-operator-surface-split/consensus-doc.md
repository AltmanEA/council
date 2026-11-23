# Consensus Document — sess-operator-surface-split

Session: sess-operator-surface-split
Mode: fallback (fallback/index.md v0.6.0), operator as Moderator
Date: 2026-11-17
Roster: Architect, Reliability & Security Specialist, Human-Centric Designer, Operations Engineer
Input: task-brief.md, review-<role>.md (round 1 + discussion round 2)

---

## Decision

**Разделение спецификации `docs/en/operator-surface/index.md` признано целесообразным, но выполняется как двухфазный процесс. Немедленное физическое разделение — ОТКЛОНЕНО всеми четырьмя ролями.**

**Phase 1 (немедленно, по решению оператора): canonical-source fix без нового файла.**
1. Canonical authority для out-of-band approval-контракта (approval_id, diff-hash binding, approver ≠ proposer, single-use, expiry, changed-diff invalidation) — `docs/en/documenter-service/mvp-contract.md` §4. При любом несогласовании описания approval-поведения **mvp-contract wins** (зафиксировать в cross-references обеих сторон).
2. Из `operator-surface/index.md` §Documenter Integration удалить дублирующую детализацию approval-механики, заменить ссылочной формулировкой (пропозиция Security):
   > `documenter.approve` and related Tier 2+ approval mechanics are specified in `documenter-service/mvp-contract.md` §4; this section provides only the operator-surface rendering and delivery semantics.
3. В `mvp-contract.md` §4 добавить пометку: event schema раздела — canonical для событий `documenter.approval`, `documenter.override_gate`.
4. В verbs-таблицу `operator-surface/index.md` (строки 51–62) добавить колонку `owner` (`council.*` → operator-surface; `documenter.*` → mvp-contract §4) и атрибут `DORMANT (ADR-013)` для `documenter.*` строк. Таблица остаётся ЕДИНЫМ transport/permission-реестром, не расщепляется.
5. В `operator-surface/index.md` §Caller Identity добавить охранную формулировку (Security/HCD):
   > operator identity is defined exclusively in this section, valid cross-document for escalation and approval.
6. Обновить кодовые prose-ссылки на `§Documenter Integration` (реальный impact-инвентарь Ops: `patterns.py` l.21/545, `write.py` l.379/436, `status.py` l.32 — 3 места) на canonical-путь — в том же changeset.

**Phase 2 (deferred, НЕ в этой сессии): физический вынос approval-lifecycle** в `docs/en/documenter-service/approval-surface.md` — только после того, как Operator Surface существует как код (триггерный критерий — open question, см. ниже), при условиях:
- AuthN/AuthZ остаётся ИСКЛЮЧИТЕЛЬНО в `operator-surface/index.md`; новый документ содержит header-guard: «AuthN/AuthZ boundary is exclusively defined in operator-surface/index.md §Caller Identity and Authorization… any apparent conflict is resolved in favor of operator-surface/index.md».
- DORMANT-баннер (не SPECIFICATION ONLY) — семантика «реализовано, но interlocked».
- verbs-таблица остаётся в operator-surface; строки `documenter.*` — minimal entry + ссылка.
- Новые артефакты: регистрация в манифесте, RU-перевод, обновление кросс-ссылок (`layer-2.md`, `policy-reference.md`, `decisions/index.md`, `mvp-interfaces.md`) — один atomic changeset.

**Обе фазы — только через Documentation Worker skill после Approve оператора (AGENTS.md §2).**

## Subjects with outcomes

| Subject | Outcome |
|---------|---------|
| SUBJ-001 (факт разделения) | conditionally agreed — разделение корректно архитектурно (dual audience / dual lifecycle), исполнение deferred (Phase 2) |
| SUBJ-002 (целостность AuthN) | agreed — AuthN неперемещаем; охранная формулировка в §Caller Identity + header-guard при Phase 2; self-approval vector закрыт единым определением operator_id |
| SUBJ-003 (дублирование approval-контракта) | agreed — дефект, подтверждённый (прецедент sess-prevention-measures); устраняется в Phase 1 независимо от SUBJ-001; canonical = mvp-contract §4 |
| SUBJ-004 (pre_check) | agreed — остаётся в operator-surface целиком (включая verdict-таблицу — неперевариваемый фрагмент; ADR-015 нормативно привязан к пути); `approval-surface.md` pre_check не касается |
| SUBJ-005 (prose-contract sync) | agreed — реальные кодовые зависимости: 3 места (не 8+; AuthN-ссылки не трогаются); синхронизация обязательна в том же changeset |
| SUBJ-006 (стоимость сопровождения) | conditionally agreed — стоимость Phase 1 пренебрежима; Phase 2 cost реален, но управляем; reservations см. ниже |
| SUBJ-007 (альтернатива «не делить») | rejected as final state — «никогда не делить» не поддержано (3 из 4 ролей за отложенный split); принята как содержание Phase 1 |

## Normative rules adopted (для включения в changeset Phase 1)

1. **Canonical rule:** `documenter-service/mvp-contract.md` §4 wins over `operator-surface/index.md` при несогласовании описания Tier 2+ approval-поведения (включая event schema `documenter.*` событий).
2. **Tier 2+ Activation Gate Norm** (пропозиция Security, адоптирована):
   > Tier 2+ activation is gated exclusively by code-level checks — policy file state (`active_tier`, `briefing_ref`, `allowed_operations`) and Operator Surface sentinel (`documenter/.operator_surface_ready`). No prose document may independently impose, extend, or contradict activation conditions. Documents may describe the gate but cannot create one.
3. **Event ownership rule:** события определены там, где генерируются — `precheck.*` и `notice.documenter_tier2_interlock` → operator-surface (surface рендерит); `documenter.approval`, `documenter.override_gate` → mvp-contract (сервис эмитит).

## Role reservations (tied to subjects)

- **Operations Engineer (SUBJ-001/006):** Phase 2 запускать не раньше, чем появляется CI-check ссылочной целостности docs↔код (standalone pre-merge guard, расширение `tools/check_all.py`; pytest для этого непригоден — проверяет чистые функции). Без guard stale cross-reference остаётся critical-риском. Status concerns сохранён.
- **Security (SUBJ-001/002):** guard language — перенаправление, а не устранение semantic drift (вектор: читатель fallback-сессии экстраполирует «agent may initiate documenter.audit» на approve). Поэтому Phase 2 только когда trust boundary = функция (Operator Surface как код), а не текст.
- **HCD (SUBJ-006):** двухбаннерная нагрузка допустима только при семантическом разделении DORMANT ≠ SPECIFICATION ONLY; иначе возвращаемся к одному документу.
- **Architect (SUBJ-001):** отказ от immediate split — из-за риска partial split (разделён документ, не устранено дублирование); Phase 1 обязан выполняться первым и полностью, Phase 2 без Phase 1 запрещён.

## Operator decisions

- **O-1 (RESOLVED 2026-11-17, оператор принял вариант C в форме конъюнкции):** Триггер Phase 2 = **все** условия:
  (i) Step 9 DoD п3-плана (`sessions/p3-operator-surface-impl-plan/plan-draft-v2.md`) выполнен — integration hardening + registration kit, включая реализацию создания sentinel `documenter/.operator_surface_ready` в коде, покрытую тестами (`tests/test_documenter_surface_sentinel.py` и преемники);
  (ii) CI link-integrity check docs↔код в pipeline (warn-only допустим по рекомендации Security; усиление режима — отдельное решение, см. O-3);
  (iii) оператор подтвердил O-2 (placement) и O-4 (RU).
  Уточнения, принятые вместе с формулировкой:
  - Термин «post-Moderator-Alpha» из обсуждений ролей переопределён: опорные вехи — шаги p3-плана **Operator Surface** (пакет `operator_surface`), а не Moderator (компоненты разные).
  - Смена документа (Phase 2) НЕ привязывается к акту активации Tier 2+ (policy/briefing/sentinel/`COUNCIL_OPERATOR_ID`) — отдельный акт по прецеденту OD-3 и Activation Gate Norm; Phase 2 — перемещение прозы, не включение записи.
  - Фактическая MCP-регистрация поверхности (решение оператора, AGENTS.md §1.7) НЕ является частью триггера (риск смешения политического акта и зрелости кода).
- **O-2 (RESOLVED 2026-11-17, вариант A):** Placement Phase 2-документа — `docs/en/documenter-service/approval-surface.md`. Обоснование (консенсус ролей 4/4 + нормы консилиума): canonical-соседство с `mvp-contract.md` §4 и `policy-reference.md`; аудитория — разработчик/оператор Документатора (trust model, §1.6 separation); соответствие event ownership rule (контракт там, где генерируются события). Обязательное следствие: перекрёстные ссылки в обоих направлениях между `operator-surface/index.md` и `approval-surface.md` (guard-формулировки AuthN + canonical-ссылки). Альтернатива B (`operator-surface/approval-surface.md`) отклонена: semantic mismatch — контракт поведения Документатора в папке surface противоречил бы принятой границе Council-ingress vs Documenter-trust.
- **O-3 (RESOLVED 2026-11-17, гибридный режим CI link-integrity check):**
  - **hard fail** — unresolved **docs→manifest** ссылки (ссылка документа на несуществующий/незарегистрированный в `docs-manifest.yaml` путь). Область полного контроля Documentation Worker/манифеста; прецедент — ADR-003 (падающий CI для prose-инварианта).
  - **warn-only** — **code→docs** ссылки (комментарии `documenter_service/`, будущего `operator_surface/`): штатное рассогласование при работе implementation-скила в worktree не должно блокировать легитимные changesets; отдельный `--strict` режим для чистовых pre-merge прогонов.
  - Реализация: standalone step (расширение `tools/check_all.py`, exit code 0/1), не pytest. Ограничение стоимости: ≤2 человеко-дней (критерий Ops; иначе check сам становится блокирующим должником триггера O-1(ii)).
  - Честная граница (Security): check ловит broken link, не semantic drift; он defense-in-depth, а не primary guard.
- **O-4 (RESOLVED 2026-11-17, вариант A):** RU-перевод `approval-surface.md` — **сразу при Phase 2**, через автоматическую синхронизацию ADR-012 (post-Approve действие Documentation Worker при прохождении Phase 4 write-gates; падение gate блокирует RU-запись и эскалируется оператору, EN-часть не страдает). Отдельного `no_auto_translation` opt-out нет. Обоснование: низкая цена поддержания паритета (approval-lifecycle почти статичен), отсутствие висящего долга «new doc without translation», готовность движка (`techdoc-translator`, ADR-014). Заложенное следствие Phase 2 changeset: `approval-surface.md` — non-index path в существующей папке `documenter-service/` → frontmatter `allow_non_index_paths: true` (прецедент `layer-2.md`); RU-зеркало `docs/ru/documenter-service/approval-surface-RU.md`, регистрация `has_translation` в манифесте.
- **O-5 (RESOLVED 2026-11-17, вариант A — симметричная changelog-запись):** при Phase 2 история переноса записывается с обеих сторон:
  - `CHANGELOGS/operator-surface.changes.md`: «§Documenter Integration removed (moved to `documenter-service/approval-surface.md`); version 0.2.0 → 0.3.0»;
  - новый `CHANGELOGS/approval-surface.changes.md`: первая запись «extracted from `operator-surface/index.md` §Documenter Integration; canonical source mvp-contract.md §4».
  Обоснование: traceability замыкается с обеих сторон (читатель любого документа находит второй через changelog; git-дифф v0.2→v0.3 operator-surface объяснён). Frontmatter нового документа: `changelog-path: CHANGELOGS/approval-surface.changes.md` (конвенция §7 `CHANGELOGS/<id>.changes.md`, документ со своим id; аналог-прецедент — `operator-surface.changes.md`). Отклонён вариант B (история только у нового документа) — обрыв audit trail у operator-surface.

## Open questions (для оператора)

Все O-1..O-5 решены оператором 2026-11-17 (см. Operator decisions). Открытых вопросов нет.

- O-1: РЕШЕНО — см. Operator decisions.
- O-2: Placement Phase 2-документа: `docs/en/documenter-service/approval-surface.md` (Architect/Ops/HCD/Security склоняются сюда — canonical ownership) vs `docs/en/operator-surface/approval-surface.md` (локальность). Решение оператора.
- O-3: CI link-integrity check: warn-only в MVP (Security) или hard fail (Ops)?
- O-4: RU-перевод нового документа: сразу при Phase 2 или отложить до final-стабильности (HCD)?
- O-5: Changelog traceability переноса (HCD): запись в changelog operator-surface при Phase 2.

## Action items

- [x] AI-1 (operator → Documentation Worker skill): proposed changeset Phase 1 — правки `operator-surface/index.md` (пункты 1–5 Decision), `mvp-contract.md` §4 (пометка canonical), 3 кодовых комментария (`patterns.py`, `write.py`, `status.py`) — единый changeset, propose → Approve (шаг 5) → write. Исполнен 2026-11-17: propose → Approve («Approve, всё как предложено») → execute → verify (`check_all.py` baseline, manifest OK, drift 0, pytest 655 passed) + RU auto-sync ×3 verified. Отклонения от формулировки: E-1 — `status.py` не правился (ссылка на ADR-013 dual-interlock, не на §Documenter Integration); E-2 — добавлены 2 ссылки вне инвентаря (`policy-reference.md`, `documenter-service/index.md` → канон §4, патч-бампы); E-4 — Owner-колонка verbs-таблицы обёрнута в backticks (фикс translation-engine fallback).
- [x] AI-2 (operator): решения по O-1..O-5 приняты 2026-11-17 — см. Operator decisions.
- [x] AI-3 (deferred, post-trigger): Phase 2 changeset — `approval-surface.md`, манифест, RU, кросс-ссылки, CI guard (при условии AI-2). Исполнено 2026-11-17 после закрытия триггера O-1 (условие (i) — коммит cf4573f p3 MVP + sentinel; условие (ii) — link-integrity шаг в `tools/check_all.py`; (iii) ранее). Changeset через skill: propose → Approve → write → verify.
- [x] AI-4 (optional): фиксация Activation Gate Norm в `documenter-service/index.md` §Trust Tiers или ADR (решение оператора: норма vs заметка). Исполнено 2026-11-17: оператор выбрал ADR → **ADR-016** зарегистрирован в `planned-architecture-decisions` v0.12.0 (норма — дословно из п.2 Normative rules adopted).

## Escalations

Нет. blocked-escalation не объявлялось; эскалации по ходу не возникали.

## Critical findings downgraded

Критические находки с валидным обоснованием (механизм отказа + subjects) не понижались: D-001 (Architect, partial-split/drift), SUBJ-002-критика Security (self-approval через семантический дрейф), HCD critical (два источника правды). Все переведены в Decision/Norms/reservations.
