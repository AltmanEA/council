# Session Task Brief — sess-documenter-extraction

Date: 2026-11-17
Mode: Subagent Fallback (fallback/index.md v0.6.0)

### Session Goal

Решить, имеет ли смысл выделить Документатор (Documenter Service) в отдельный проект (отдельный репозиторий), по образцу ADR-014 (вынос движка перевода в techdoc-translator), и если да — каковы условия и границы такого выноса.

### Focus Areas

- Границы связности: что связывает `documenter_service/` с репозиторием Council (манифест, политика, Operator Surface, `documenter/` state, артефакты).
- Направление зависимостей и контракт взаимодействия (по образцу ADR-014: one-way dependency, lock file, CLI/exit-code контракт).
- Модель доверия и безопасности: dual interlock (ADR-013), authenticated operator ingress (`COUNCIL_OPERATOR_ID`), ownership write-полномочий.
- Эксплуатационная цена: CI, тесты, версионирование, синхронизация спецификаций и прозаических контрактов.
- Прецедент ADR-014: что сработало, что болит; переносим ли этот паттерн на Documenter.

### Questionnaire per Role

**Architect:**
- Q1: Является ли Documenter слабое связанным компонентом или он прорастает в Council-инфраструктуру (manifest port, operator surface, skill)?
- Q2: Какой контракт (CLI/exit codes vs MCP vs Python-порт) устойчив при выносе и что станет точкой дрейфа?

**Reliability & Security Specialist:**
- Q1: Не ослабляет ли вынос dual interlock (ADR-013) и требование approver ≠ proposer?
- Q2: Где проходят write-полномочия и кто владеет аудит-трейлом при разделении репозиториев?

**Human-Centric Designer:**
- Q1: Станет ли оператору проще или сложнее (два репозитория, два CI, lock-файлы, briefing/activation workflow)?
- Q2: Не потеряется ли связь спецификация↔реализация для участников, работающих с docs/en/documenter-service/?

**Operations Engineer:**
- Q1: Какова эксплуатационная стоимость двух репозиториев на текущем этапе (один оператор, MVP)?
- Q2: Что с тестами, hash store, артефактами (`documenter/`, provenance) — переносимы ли они без Council-окружения?

### Output Limits

- Maximum findings per role: 5–7
- Maximum recommendations per role: 3–5
- Maximum open questions per role: 2–3
- Total output per role: ~150 lines

### Expected Discussion Rounds

1 round (medium task)

### Subject List

- `SUBJ-001`: Решение о выносе Documenter в отдельный репозиторий (да/нет/условно)
- `SUBJ-002`: Контракт взаимодействия Council ↔ Documenter при выносе (CLI/exit codes vs MCP vs port-пакет) и его версионирование (аналог translation.lock)
- `SUBJ-003`: Владение write-полномочиями и аудит-трейлом (Documentation Worker skill остаётся единственным исполнителем записей?)
- `SUBJ-004`: Сохранность dual interlock (ADR-013) и authenticated operator ingress при разделении репозиториев
- `SUBJ-005`: Владение спецификациями, тестами и state/артефактами (docs/en/documenter-service/, tests, documenter/, documenter/artifacts/translation/)
- `SUBJ-006`: Сравнение с прецедентом ADR-014 (techdoc-translator): переносимость паттерна one-way dependency

### Additional Context / Constraints

- `documenter_service/` — пакет в корне repo Council (implementation file, вне манифеста): CLI (`python3 -m documenter_service`), MCP stdio (не зарегистрирован — решение оператора), core/adapters/ports.
- Спецификации остаются project documents под `docs/en/documenter-service/` (манифест).
- Documenter читает `docs-manifest.yaml` read-only через `ManifestSource` port; генератор манифеста — `tools/gen_manifest.py` (Council).
- ADR-013: Tier 2+ write-ветка реализована, но dormant за dual interlock (policy gate + Operator Surface как код). Tier 2+ не активируема, пока Operator Surface не существует как код с authenticated ingress (`COUNCIL_OPERATOR_ID` из окружения).
- ADR-014: движок перевода вынесен в standalone `techdoc-translator`; контракт — CLI v1, exit codes 0–6, `.env`; Council пинит версию через `defaults/translation.lock`; движок ничего не знает о Council; запись — только через Documentation Worker skill.
- Текущий статус: Tier 0–1 Operational; Tier 2+ Dormant; MCP-сервер не зарегистрирован (страж — отсутствие регистрации в `.opencode/opencode.jsonc`).
- Этап проекта: Specification→MVP implementation started (ADR-011). Один оператор.
