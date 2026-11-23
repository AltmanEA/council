# Consensus Document — Автоматизация RU-перевода документации

Session: sess-translate-automation
Date: 2026-11-14
Mode: fallback (fallback/index.md v0.6.0)
Roster: Architect, Reliability & Security, Human-Centric Designer, Operations Engineer, Documentation Compliance Ombudsman (extended)
Rounds: 1 (индивидуальное ревью). Дискуссия не проводилась: все статусы `concerns`, противостоящих позиций по идентичным subject нет (§Phase 3 — допустим ноль раундов).

## Decision taken и rationale

**Идея оператора приемлема условно, в форме «post-Approve auto-dispatch», но НЕ в наивной форме «автозапуск при каждой правке EN».**

Rationale: ядро идеи (LLM-переводчик с конфигурируемой моделью, обход непереводимых элементов, инъекция глоссария, вызывающий агент верифицирует и пишет RU) уже реализовано в связке `SKILL.md §Translation via project translator` + `tools/local-translate.sh`/`local_translate.py` + контракт Phase 4. Реально новые элементы идеи — только (1) автоматический триггер и (2) strip-then-reinsert. Первый нарушает AGENTS.md §5.1 (запрет записей до Approve) и §3.3 (действующая приостановка RU-синхронизации); второй — регресс относительно уже валидированного structural passthrough (E-005/E-006).

## Subjects with outcomes

| Subject | Outcome | Решение |
|---|---|---|
| SUBJ-001 Триггер | conditionally agreed | «Авто» = post-Approve делегирование primary agent → skill `create_ru` (`use_project_translation: true`) внутри утверждённого changeset «правка EN + синхронизация RU». Git-hook с автозаписью запрещён; hook — только report-only. Оркестрационный слой «EN изменён → предложить перевод» — штатное место: будущий Documenter service (read-only propose). |
| SUBJ-002 Strip-then-reinsert | disagreed → отклонено | Сохранить существующий structural passthrough (skip-блоки в обёртке). Вынос метаданных/кода в агентский слой даёт риск потери line-parity при реинсерции без измеренного выигрыша (E-005/E-006). |
| SUBJ-003 Глоссарий | agreed | Существующая механика (`find_relevant_terms` — фильтрация по блоку + `enforce_glossary`) полностью покрывает идею «встретившиеся термины». Глоссарий — единственный источник эквивалентов (§4); параллельные term-store запрещены. |
| SUBJ-004 Конфигурация модели | conditionally agreed | Конфигурация остаётся в env-переменных + задокументированных defaults (precedent: EXPERIMENTS.md); НЕ попадает в манифест/frontmatter (§2.2). Fallback-цепочка local → cloud (только явный override) → native skill. Cloud-ветка — с явным предупреждением о приватности, per-run opt-in. |
| SUBJ-005 Верификация и запись | conditionally agreed | Право записи RU — только у skill после Phase 4. `[FAIL]` блокирует `safe` → `review`. Добавочные гейты от Reliability приняты (см. Action items): машинный код выхода при `[FAIL]`, EN-identity-скан, pre-flight сверка модели, сквозной дедлайн, staging-кандидат. |
| SUBJ-006 Соответствие AGENTS.md | conditionally agreed | Требуется процедура легитимизации до любой автозаписи (см. ниже). |

## Role reservations (tied to subjects)

- **Architect:** автозапись до Approve = нарушение §5.1; hook-писатель ломает exit-контракт существующего `tools/hooks/pre-commit` и даёт stale-index failure mode (SUBJ-001).
- **Reliability:** [critical] тотальная тихая порча при exit 0 — неверная модель/ключ → все строки `[FAIL]` → в stdout EN-оригинал, exit 0; line-parity цел, ловит только leakage-скан (SUBJ-005) — **верифицировано orchestrator'ом по коду** (`local_translate.py` L604–614, 616–618). [critical] hook-писатель устраняет единственного блокирующего агента при `[FAIL]` (SUBJ-001/005). [high] TOCTOU-окно на время перевода; нет сквозного дедлайна; cloud-override без аудит-трейла. [medium] ключ в `curl -H` виден в `ps`; `enforce_glossary` может ломать кириллизацией URL.
- **HCD:** риск ложного доверия convenience-копии; диф-ревью каждого автоперевода — лишняя нагрузка, достаточно структурированного Translation Verification Report, но FAIL/drift/высокий gloss-apply обязаны принудительно эскалировать к diff-ревью (SUBJ-005).
- **Operations:** [high] автозапуск не оправдан масштабом (11 EN-документов, ~10 коммитов/мес; ~100–150 с на документ в критическом пути ради не-gate копии); [high] хук-носитель отклонён (сеть/GPU/LLM-недетерминизм в commit-путь); наблюдаемость не персистентна — append-only журнал прогонов; vLLM — незарегистрированная зависимость (строка запуска/health в README `tools/`); версионировать промпты (`PROMPT_VERSION` + привязка к E-xxx); конфигурацию «env + документированные дефолты + provenance» не менять (SUBJ-004). Рекомендация: при снятии §3.3 — batch по явному запросу оператора, максимум post-Approve асинхронно через skill.
- **Compliance:** без ADR и правки §3.3 реализация была бы заблокирована; версии: AGENTS.md 0.13.0→0.14.0 (minor), SKILL.md 0.6.0→0.7.0, decisions-index 0.6.0→0.7.0; манифест — только `gen_manifest.py --write` последним (SUBJ-006).

## Процедура легитимизации (порядок обязательных изменений)

1. **ADR-012** в `docs/en/planned-architecture/decisions/index.md`: «Post-Approve automatic RU synchronization», формулировка снятия приостановки — рекомендуемая: §3.3 «lifted conditionally: post-Approve auto-dispatch allowed, per-document opt-out, write only via skill after Phase 4».
2. **AGENTS.md §3.3**: снять приостановку в утверждённой формулировке (0.13.0→0.14.0).
3. **SKILL.md**: зафиксировать авто-dispatch как post-Approve действие и новые write-gates (0.6.0→0.7.0).
4. **Glossary**: новые термины (например, *write-gate*, *translation verification report*) — только при фактическом закреплении.
5. **Манифест**: `python3 tools/gen_manifest.py --write` последним.

Все изменения — через Documentation Worker skill, после явного Approve оператора (AGENTS.md §5.1), каждое — с changelog-записью через `tools/bump_version.py`.

## Open questions (для оператора) — РАЗРЕШЕНЫ 2026-11-14

1. **Форма снятия §3.3:** → «lifted conditionally: post-Approve only» (ADR-012).
2. **Гранулярность Approve:** → единый Approve пакета «EN + RU-синхронизация»; RU пишется сразу при прохождении write-gates, провал гейта → просмотр полного перевода.
3. **Opt-out per документ:** → да, флаг `no_auto_translation: true` во frontmatter.
4. **Порог gloss-apply:** → отдельного порога нет; эскалация по факту провала write-gates, сводка gloss-apply в отчёте.
5. **Cloud-ветка:** → не автоматически; при недоступности локального сервера — вопрос оператору каждый раз.

## Action items (реализация после Approve)

| # | Действие | Где | Тип |
|---|---|---|---|
| 1 | Машинный код выхода `4` при `stats_fail > 0` (сейчас exit 0 при полном `[FAIL]`) | `tools/local_translate.py` | defect fix (critical) |
| 2 | `--summary-json` в stderr/stdout: counts ok/skip/fail, backend, model, gloss-apply лог | `local_translate.py` | enhancement |
| 3 | Составной write-gate в Phase 4: fail=0 + line-parity + EN-identity-скан (RU-файл, побайтово равный EN, запрещён к записи) | `SKILL.md` Phase 4 | contract |
| 4 | Pre-flight: сверка `CLOUD_MODEL` с ответом `/models` (сейчас проверяется только доступность) | `local-translate.sh` | enhancement |
| 5 | Сквозной дедлайн прогона (timeout×retries) и temp+rename с сохранением предыдущей версии RU | wrapper + skill | enhancement |
| 6 | SHA256-перепроверка EN-источника перед записью (TOCTOU) | skill (read-before-write усиление) | enhancement |
| 7 | ADR-012 + правки документов по процедуре выше | docs/ | post-Approve |
| 8 | Отказ от нового `change_type` — переиспользовать `create_ru` + `use_project_translation` | SKILL.md | no-op (принято как есть) |
| 9 | Append-only журнал прогонов перевода (backend, model, counts, gloss-apply, verdict) | `tools/` | enhancement |
| 10 | Задокументировать vLLM как зависимость: строка запуска + health-check в `tools/README.md` | `tools/README.md` | docs |
| 11 | `PROMPT_VERSION` с привязкой к экспериментам E-xxx | `local_translate.py` | enhancement |

## Downgraded critical findings

Нет. Все critical находки имели корректную аргументацию (названный failure mode + subject).

## References

- Рецензии: `review-architect.md`, `review-reliability.md`, `review-hcd.md`, `review-operations.md`, `review-compliance.md`
- Эскалации, разрешённые по ходу: нет
