# Task Brief — Целесообразность разделения спецификации Operator Surface

Session: sess-operator-surface-split
Mode: fallback (fallback/index.md v0.6.0)
Date: 2026-11-17
Operator decision requested: целесообразно ли разделять `docs/en/operator-surface/index.md` на «документаторскую» и «общепроектную (Council/Moderator)» части.

## Task description

**Контекст.** `docs/en/operator-surface/index.md` (v0.2.0, Status: draft, SPECIFICATION ONLY) — спецификация Layer 2 адаптера: транспорт MCP stdio, аутентификация трёх классов вызывающих (operator/agent/service), таблица verbs (`council.*` + `documenter.*`), гейт `pre_check`, модель эскалаций (stop-and-resume), notices, доставка событий. Документ смешивает две обязанности: (а) общий человеческий ingress для всего Council (эскалации, управление сессиями — нужны MVP-модератору); (б) интеграцию с Документатором (out-of-band approval Tier 2+, `documenter.approve`, interlock-notice — нужны для активации ветки записи Документатора по ADR-013).

**Предлагаемое разделение (гипотеза для оценки).**
- `operator-surface/index.md` остаётся: транспорт, общий AuthN/AuthZ-механизм, `council.*` verbs, эскалации, notices, события, `pre_check` (как гейт фаз протокола).
- Документаторская часть (verbs `documenter.*`, §Documenter Integration, out-of-band approval lifecycle, override_gate) выносится в отдельный документ — кандидат- placement обсуждается: подпапка `docs/en/operator-surface/` (например `documenter-integration.md`) или `docs/en/documenter-service/` (например `approval-surface.md`).
- Общий AuthN-механизм НЕ дублируется — только ссылки.

**Известные аргументы «за».** Дублирование out-of-band approval (описан и в operator-surface, и в `documenter-service/mvp-contract.md` §4 — риск prose-contract drift, прецедент sess-prevention-measures 2026-11-14); разные циклы развития (эскалации → MVP-модератор; Documenter-интеграция → активация Tier 2+); разные аудитории (разработчик модератора vs разработчик/оператор Документатора).

**Известные риски/ограничения.**
- Единая граница доверия: AuthN — общий механизм, его расщепление недопустимо (риск расходящихся трактовок «кто оператор», подрыв ADR-013).
- Код ссылается на прозу: `documenter_service/core/patterns.py`, `core/policy.py` цитируют «operator-surface §Documenter Integration»; перенос секции требует синхронизации в том же changeset.
- Кросс-ссылки: `planned-architecture/layer-2.md` (строка 57), `documenter-service/*` (index, mvp-contract, mvp-interfaces), глоссарий, `planned-architecture/decisions/index.md` (текст ADR-013 цитирует путь), AGENTS.md §1.7.
- Манифест `docs-manifest.yaml` и RU-перевод (`has_translation: docs/ru/operator-surface/index-RU.md`) — новый документ потребует регистрации и решения по переводу.
- ADR-015 (OD-1–OD-3) нормативно привязан к `operator-surface/index.md` §pre_check Gate — трогать его нельзя без явного акта.
- Все изменения docs/ идут только через Documentation Worker skill после Approve оператора (AGENTS.md §2).

**Ограничения сессии.** Это session оценки целесообразности (go/no-go), НЕ проектирование итоговой структуры. Роли оценивают: стоит ли делить; если да — при каких условиях и куда; если нет — чем заменить (например, только устранение дублирования approval-контракта без переезда секций).

## Subject list

- SUBJ-001: сам факт разделения (вынести документаторскую часть из operator-surface/index.md в отдельный документ) — support/oppose.
- SUBJ-002: целостность общего AuthN/AuthZ-механизма (единая граница доверия, запрет дублирования описания аутентификации).
- SUBJ-003: устранение дублирования out-of-band approval контракта (operator-surface ↔ mvp-contract.md §4) — как отдельная проблема, независимо от разделения.
- SUBJ-004: размещение гейта `pre_check` (council-гейт фаз, вердикт от Документатора) — остаётся ли в council-части.
- SUBJ-005: синхронизация проза-контрактов с кодом (комментарии `documenter_service/core/patterns.py`, `core/policy.py`, ссылки в ADR-013) при переносе секций.
- SUBJ-006: издержки сопровождения разделения (манифест, RU-перевод, кросс-ссылки, future-merge риск при сборке модератора).
- SUBJ-007: альтернатива «не делить» — оставить один документ, только устранить дублирование approval-контракта ссылки-на-источник.

## Output limits

Каждая роль: структура из fallback/index.md §Output Structure (Summary Position, Key Findings с severity и subject-id, Recommendations, Open Questions, Status, Escalation Reason при необходимости). Не более ~120 строк на роль. findings обязаны ссылаться на SUBJ-xxx.
