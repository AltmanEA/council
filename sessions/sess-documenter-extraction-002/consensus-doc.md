# Consensus Document — sess-documenter-extraction-002

Date: 2026-11-17
Mode: Subagent Fallback v0.6.0 (`fallback/index.md`)
Task: Независимый пересмотр — имеет ли смысл выделить Documenter Service в отдельный проект (образец ADR-014)?
Roster: Architect, Reliability & Security Specialist, Human-Centric Designer, Operations Engineer
Rounds: 1 individual + 1 discussion (последовательный запуск ролей per constraint оператора)
Relation to prior consensus: `sessions/sess-documenter-extraction/consensus-doc.md` (тот же день) — **самостоятельное подтверждение** независимым проголом; ключевые новые входные данные проверены (Operator Surface как код, vendoring-модель ADR-014, ADR-016).

---

## Decision

**Нет — выделение Documenter Service в отдельный проект на текущем этапе нецелесообразно.** Независимый повторный консилиум подтверждает prior consensus. Статус: **conditionally resolved** (три роли `agree`, Architect `concerns` — оговорки без блоков; блоков и эскалаций нет).

## Rationale

Конвергентные находки (все 4 роли):

1. **Ни один revisit-триггер prior consensus не выполнен (SUBJ-001, SUBJ-007).** Наличие Operator Surface как кода (p3 MVP) ≠ MVP-завершённость: `active_tier: 1`, `allowed_operations: []`, `briefing_ref: null`; sentinel `documenter/.operator_surface_ready` отсутствует; MCP не зарегистрирован; релиза пакета нет. Trigger-gaming проверен и отвергнут (Ops).
2. **Versioned contract отсутствует — вынос законсервирует draft (SUBJ-002).** Нет `contract_version`, `pyproject.toml`/`setup.py`; MCP tools list монолитен (`mcp_stdio.py:76–311`); CLI exit codes и `StructuredError` без гарантий совместимости; `resolve_operator_id()` дублирована (`__main__.py:125`, `mcp_stdio.py:51`). Все четыре роли: `contract_version` + JSON schemas — обязательная предпосылка любого будущего выноса.
3. **Интерлок: код-гейты location-independent, операционная гарантия деградирует (SUBJ-004, разрешённое уточнение раунда).** R&S/Architect сошлись: `check_tier2_authorized()` (`core/policy.py:360–415`) ломается не из-за структуры репо, но in-tree обеспечивает единый git-источник policy+sentinel; кросс-репо → drift-риск (root — параметр вызова, `policy.py:123–129`). Threat model скорректирован раундом: не «злонамеренный оператор», а **accidental misconfiguration / operator error** при single-operator deployment. Guard «MCP не зарегистрирован» деградирует из физического отсутствия до административной записи (registration bypass — нашли все 4 роли). Shared state-root (symlink/bind-mount) снижает severity critical→high, но «делает два репозитория когнитивно-монолитными» и не снимает operator error burden (Ops).
4. **Cost переносимости не оплачен (SUBJ-005).** Согласованная метрика раунда: **23/40 тестов (~58%) с >50% Council-coupling; ~71% строк тестов (≈14.5k/20.4k) документер-специфичны**; coupling типов: 1 deep import (`fs_manifest.py` → `import gen_manifest` из `tools/`), 14 state-references на `documenter/`. Фикстуры — мини-корпус Council. Порог переносимости не достигнут.
5. **Паттерн ADR-014 не трансферируем (SUBJ-006).** techdoc-translator — stateless one-way CLI с versioned contract и lock-пином; Documenter — bidirectional service, читающий manifest/policy и вызывающий Documentation Worker skill. Vendored-модель (`vendor/` + `defaults/translation.lock`) демонстрирует цену выноса простого компонента (lock, sync script, consumer docs, ~35 файлов на коммит) — для Documenter это цена «с нуля» без готового контракта.
6. **Подтверждённой операционной боли от in-tree размещения нет (SUBJ-001, HCD).** Отрицательный результат поиска по CHANGELOGS/ и session records — зафиксировано как факт, не как допущение. Ментальная модель «один репо = один policy + один sentinel» — аргумент в пользу сохранения.

Изолированные наблюдения: Write authority (skill — единственный исполнитель записей) при выносе размывает audit-контур и требует явного Documenter→Worker binding contract (SUBJ-003, R&S/HCD).

## Subjects with Outcomes

| Subject | Outcome |
|---------|---------|
| SUBJ-001 — решение о выносе | **Agreed: не выносить сейчас**; пересмотр по триггерам + early-revisit по признакам боли |
| SUBJ-002 — контракт и версионирование | **Agreed:** `contract_version` + JSON schemas + consumer-contract doc — предпосылка внутри репо до любого выноса; транспорт не выбран (OQ-1) |
| SUBJ-003 — write authority / audit-контур | **Agreed:** skill остаётся единственным исполнителем записей; `documenter/` state остаётся в Council; мост Documenter→Worker формализовать (ADR при выносе) |
| SUBJ-004 — dual interlock | **Agreed:** код-гейты сохраняются при выносе, операционная single-source гарантия деградирует; threat model = operator error; shared state-root — лишь mitigation (critical→high), не ответ на вынос |
| SUBJ-005 — specs/tests/state | **Agreed:** спецификации, тесты и state остаются в Council; согласованная метрика coupling 23/40 (~58%) / 71% строк |
| SUBJ-006 — трансфер ADR-014 | **Agreed:** не трансферируем (топология one-way stateless CLI ≠ bidirectional core service) |
| SUBJ-007 — Operator Surface как код | **Agreed:** существование как код — подтверждение предпосылки ADR-013/016, НЕ выполнение триггера; баланс решения не меняет |

## Conflicts & Disagreements

— None. Единственное расхождение (Architect «интерлок location-independent» vs R&S «ослабевает») разрешено в раунде явным разграничением уровней (код-гейты vs операционная гарантия) без изменения вывода. Метрика тестовой coupling согласована (Architect скорректировал «>80% файлов» → 23/40 по файлам + 71% по строкам от Ops). Модераторская проверка: 46/49 тестовых файлов ссылаются на документер/оператор-контур — согласуется с направлением метрик.

## Reservations

- **Architect (SUBJ-002):** без `contract_version` и consumer-contract любой вынос замораживает эволюционирующий интерфейс; транспорт (CLI/MCP/port-package) не выбран.
- **R&S (SUBJ-004):** env `COUNCIL_OPERATOR_ID` — единая точка отказа AuthN Tier 2+ (deployment-проблема, решается регистрацией Surface, не структурой репо); approve≠proposer при single-operator требует двух разных id в двух процессах — MVP-ограничение, не следствие размещения.
- **HCD (SUBJ-001):** вывод «боли нет» — отрицательный результат поиска; незафиксированная фрикция возможна → приняты early-revisit признаки.
- **Operations (SUBJ-005):** порог >30% переносимых тестов не достигнут ни по одной метрике; shared state-root не рекомендуется как обоснование выноса.

## Open Questions

1. Транспорт при будущем выносе: CLI/exit codes vs MCP stdio vs Python port-package (Architect/Ops).
2. Судьба `documenter/` state (hashes, registry, intent) при выносе: за сервисом или в Council — cross-repo state dependency (все роли).
3. Появится ли реальный второй потребитель Documenter (multi-council deployment) — практический стимул выноса (R&S/HCD).
4. Документировал ли оператор реальную фрикцию от in-tree Documenter — прямо к оператору (HCD).

## Revisit Triggers

Приоритет — три проверяемых триггера prior consensus (не изменены): (1) `active_tier >= 2` И опубликованный versioned релиз пакета; (2) versioned consumer contract (`contract_version`, JSON schemas) + ≥80% параметризованных тестов на Council-нейтральных фикстурах; (3) явное решение оператора вне сессии о приемлемости двухрепозиториевой стоимости.
Дополнительно (принято раундом, HCD→Ops): **early-revisit по документированной операционной боли** — (a) >30 мин/неделя на навигацию между компонентами в одной задаче, (b) ≥2 ошибки из-за путаницы размещения, (c) запрос внешнего потребителя. Фиксация — в CHANGELOG/session record.

## Action Items

Все — вне этой сессии, через Documentation Worker skill / operator out-of-session (AGENTS.md §2); в сессии документы, manifest и код не изменялись.

1. `contract_version` + JSON schemas для `audit()`/`delegate()` внутри репо (все роли, P1).
2. Consumer-contract документ по образцу `docs/en/translation-project/` (Architect, P1).
3. `ManifestSource.from_dict()` + параметризация путей (`manifest_path`, `data_dir`, `policy_path`) через policy/env — снижает глубину coupling и хрупкость будущего выноса (Architect/Ops, P2).
4. Устранить дублирование `resolve_operator_id()` (Architect, P2).
5. Карта «спецификация → модуль кода» + фактический coupling в `documenter_service/README.md` (Architect/HCD, P2).
6. НЕ создавать `defaults/documenter.lock` до появления versioned внешнего артефакта (prior consensus AI-5, reaffirmed).

## Escalation References

— None. `blocked-*` не зафиксировано ни в одном раунде.

## Downgraded Critical Findings

— None (все критические находки с корректными failure modes и subject-ссылками). Фактические поправки раунда (не понижения): R&S — threat model «operator error» вместо «злонамеренный оператор»; Architect — метрика coupling уточнена; R&S — interlock-аргумент разведён по уровням (код vs операционная гарантия).

## References

- `task-brief.md`, `discussion-input.md`
- `review-Architect.md`, `review-ReliabilitySecurity.md`, `review-HumanCentricDesigner.md`, `review-OperationsEngineer.md`
- `discussion-round-1-Architect.md`, `discussion-round-1-ReliabilitySecurity.md`, `discussion-round-1-HumanCentricDesigner.md`, `discussion-round-2-OperationsEngineer.md`
- `../sess-documenter-extraction/consensus-doc.md` (prior consensus, подтверждён)

*Session note: ролевые субагенты фазы 3 запускались строго последовательно (constraint оператора от 2026-11-17); фаза 2 стартовала параллельно до ввода ограничения.*
