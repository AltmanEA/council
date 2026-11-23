# Consensus Document — sess-documenter-extraction

Date: 2026-11-17
Mode: Subagent Fallback v0.6.0 (fallback/index.md)
Task: Имеет ли смысл выделить Documenter Service в отдельный проект (по образцу ADR-014)?
Roster: Architect, Reliability & Security Specialist, Human-Centric Designer, Operations Engineer
Rounds: 1 general + 1 targeted resolution (Operations Engineer)

---

## Decision

**Нет — выделение Documenter Service в отдельный репозиторий на текущем этапе нецелесообразно.**
Решение: **conditionally resolved** (все роли — `concerns`, блоков нет). Оговорки зафиксированы ниже; решение пересматривается по триггерам (см. Revisit Triggers).

## Rationale

1. **Связность двунаправленная и глубокая — паттерн ADR-014 не трансферируем** (конвергенция всех четырёх ролей, SUBJ-006).
   techdoc-translator — stateless generic CLI, не знающий о Council, с versioned контрактом (exit codes 0–6, `contract_version`, пин через `defaults/translation.lock`). Documenter, напротив, знает о Council на глубине: читает `docs-manifest.yaml` (порт `ManifestSource`, `adapters/fs_manifest.py`), policy-файл `documenter_policy.yml` (`core/policy.py:91`), path-конвенции (`documenter/` state), вызывает Documentation Worker skill с диска. One-way контракт в стиле ADR-014 построить нельзя без перестройки этих портов.

2. **Dual interlock (ADR-013) — код-уровневый страж внутри репо; вынос его ослабляет** (Security + Ops, SUBJ-004).
   Гейты: `active_tier: 1` + `allowed_operations: []` + `briefing_ref: null` в `documenter_policy.yml` (repo root, единый источник, verified) И surface-гейт `operator_surface_ready()` / sentinel `documenter/.operator_surface_ready` (`core/policy.py:360–409`), отсутствующий by default (fail-closed). После выноса: policy-файл приходится копировать/монтировать между репо (drift-риск), а страж «MCP-сервер физически не зарегистрирован» (AGENTS.md §1.7) деградирует из фактического отсутствия кода до административной записи в `.opencode/opencode.jsonc` — registration bypass attack vector.

3. **Стабильного контракт-конца нет — ранний вынос законсервирует промежуточное состояние** (Architect + Ops, SUBJ-002).
   Нет `contract_version`, нет packaging-метаданных (pyproject.toml/setup.py отсутствуют — verified), CLI exit codes (0/2/3) и `StructuredError` не имеют гарантий обратной совместимости, `resolve_operator_id()` дублирована в `__main__.py` и `mcp_stdio.py`. Policy schema, audit gate rules и event schema — draft.

4. **Операционная и когнитивная стоимость неоплатима для одного оператора на MVP** (HCD + Ops, SUBJ-001).
   Этап Specification→MVP (ADR-011). Второй репозиторий = второй CI, второй release-цикл, второй lock-файл, второй briefing/activation workflow, удвоение prose-contract synchronization obligation (известная defect surface, sess-translate-automation 2026-11-14). Overhead оценён в >30% нагрузки на компонент. Когнитивная нагрузка — дефицитнейший ресурс; документированной операционной боли от in-tree размещения нет.

5. **Тесты и state непереносимы без Council-контекста** (Ops, SUBJ-005).
   21–22 из 29 тестовых файлов (~14.5k строк, 76–87%) — документер-специфичны; фикстуры `tests/fixtures/documenter/` — мини-корпус Council (alpha/beta/gamma, манифест, CHANGELOGS, policy fixtures, golden JSON/YAML). `documenter/` state (hash store ADR-010, audit registry, intent records, artifacts/translation) — операционный контур Council.

6. **Write authority остаётся за Documentation Worker skill — вынос этого не меняет, но размывает контур** (Security + HCD, SUBJ-003).
   Цепочка «Documenter → delegate() → skill → filesystem» при внешнем репо добавляет слой доверия к неконтролируемой кодовой базе; мост Documenter→Worker сейчас implicit и потребовал бы явного binding contract (отдельный ADR) ещё до любого выноса.

## Subjects with outcomes

| Subject | Outcome |
|---------|---------|
| SUBJ-001 — решение о выносе | **Agreed: не выносить сейчас**; пересмотр по триггерам |
| SUBJ-002 — контракт и версионирование | Conditionally agreed: сначала versioned contract layer *внутри* репо (`contract_version`, JSON schemas, consumer-contract doc) — предпосылка любого будущего выноса |
| SUBJ-003 — write authority / audit trail | **Agreed:** skill остаётся единственным исполнителем записей; `documenter/` (registry, hashes, intent) остаётся в Council; мост Documenter→Worker формализовать |
| SUBJ-004 — dual interlock | **Agreed:** interlock — код-уровневый страж в Council; вынос его ослабляет (registration bypass, env `COUNCIL_OPERATOR_ID`); при будущем выносе — «MCP registration = activation act» + ingress вне env |
| SUBJ-005 — specs/tests/state | **Agreed:** спецификации (`docs/en/documenter-service/`), тесты и state остаются в Council |
| SUBJ-006 — трансфер ADR-014 | **Agreed:** паттерн не трансферируем из-за разной топологии связности (one-way stateless CLI vs bidirectional core service) |

## Role reservations (tied to subjects)

- **Architect (SUBJ-002):** без `contract_version` и consumer-contract any extraction freezes an evolving implementation; транспорт (CLI vs MCP vs port-package) не выбран.
- **Security (SUBJ-004):** `COUNCIL_OPERATOR_ID` из env — единая точка отказа Tier 2+; при будущем выносе требуется механизм вне env (sealed secret / TPM-backed); process isolation proposer/approver при shared-запуске не гарантирована.
- **HCD (SUBJ-001):** решение основано на теоретической оценке — подтверждённой операционной боли от in-tree размещения оператор не сообщал; если она появится, пересмотреть раньше триггеров.
- **Operations (SUBJ-005):** 76–87% тестов непереносимы; до любого выноса — Council-нейтральные фикстуры (порог ~80% параметризованных тестов) и `ManifestSource.from_dict()`.

## Revisit Triggers (все три проверяемы)

1. **MVP-завершённость:** `active_tier >= 2` в `documenter_policy.yml` И пакет имеет стабильный `pyproject.toml` с версионированным release-тегом (минимум один опубликованный релиз).
2. **Стабилизация контракта:** versioned consumer contract (`contract_version`, JSON schemas для `audit()`/`delegate()`) существует с гарантиями обратной совместимости; ≥80% тестов параметризованы против внешних (не Council-специфичных) фикстур.
3. **Решение оператора:** явное решение оператора вне сессии (per AGENTS.md authority model), что стоимость двухрепозиториевой эксплуатации приемлема при текущих паттернах развёртывания.
   *Примечание оператора-фасилитатора:* формулировка субагента «50% vote of eligible operators» нормализована до «явное решение единственного оператора» — при single-operator deployment голосование неприменимо (ср. ADR-013: single-operator deployment не валиден для Tier 2+ approver≠proposer, но валиден для активационных решений).
   Дополнительно (не блокирующе): практический стимул появится при реальном втором потребителе (multi-council deployment, external audit service).

## Action items (для оператора; все — через Documentation Worker skill / operator out-of-session, не в этой сессии)

1. Заложить versioned contract layer внутри репо: `contract_version` + JSON schemas для `audit()`/`delegate()` (per Architect rec. 2).
2. Создать consumer-contract документ по образцу `docs/en/translation-project/index.md` (CLI signature, exit codes, contract_version) — предпосылка будущего выноса (per Architect rec. 4).
3. `documenter_service/README.md`: карта спецификация→модуль кода (per HCD rec. 3); задокументировать фактический coupling и предпосылки выноса, чтобы ADR-014-аналогия не применялась слепо (per Ops rec. 5).
4. Вынести пути (`manifest_path`, data dir) из кодовых конвенций в policy/env-конфиг (per Architect rec. 3) — снижает хрупкость при будущем выносе.
5. НЕ создавать `defaults/documenter.lock` сейчас (pre-emptive lock-файл без пинованного внешнего артефакта — ложный паттерн; Ops rec. 4 отклонён фасилитатором как преждевременный: lock-файл имеет смысл только при наличии внешнего репозитория).

## Open questions (unresolved, carried forward)

1. Транспорт при будущем выносе: CLI/exit codes vs MCP stdio vs Python port-package.
2. Судьба `documenter/` state при выносе: за сервисом или остаётся в Council (кросс-репо state dependency).
3. Порядок: Operator Surface как код — до или после любого выноса (Ops Q3). Рабочее предположение consensus: до (interlock-предпосылка ADR-013).
4. Испытывал ли оператор реальную фрикцию от in-tree Documenter (HCD Q1).

## Escalations

Ни одна эскалация не состоялась: `blocked-in-scope` Operations Engineer разрешён targeted-раундом (reclassify → concerns) до Phase 4. Первичные эскалационные пометки (risk-threshold-breach ×3, information-gap ×1) были условными — «при извлечении сейчас», — и консенсус «не извлекать сейчас» их снимает.

## Downgraded findings (transparency)

Критические находки с корректно названными failure modes и subjects — автоматических понижений не потребовалось. Фактические поправки раунда: (а) Ops — policy читается из `documenter_policy.yml` в корне, не из `defaults/policy.yaml`; packaging-метаданных нет; (б) sentinel `.operator_surface_ready` существует как код-гейт (`core/policy.py:360`), на диске отсутствует by default — тезис HCD подтверждён.
