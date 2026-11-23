# Consensus Document — Вынос Translation Project из Documenter

Session: sess-translation-extraction
Date: 2026-11-15
Mode: fallback (fallback/index.md v0.6.0)
Roster: Architect, Reliability & Security Specialist, Human-Centric Designer, Operations Engineer, Documentation Compliance Ombudsman (extended)
Rounds: 5 индивидуальных ревью + 1 раунд дискуссии (C1–C7). Все роли — `agree`.

---

## Decision

**Извлечь переводческий движок в самостоятельный репозиторий `Translation Project` с CLI-контрактом «файлы + отчёт + exit code», оставив в Council/Documenter только интеграционный адаптер, верификационный слой и операционные артефакты прогонов. `index-RU.md` не меняется ни на символ; provenance и статус живут в sidecar и сгенерированном `STATUS.md`.**

Rationale:
- Движок переиспользуем вне Council; «знание о Council» (frontmatter, manifest, line-parity) остаётся в Council.
- Право записи не переезжает: новый проект не пишет в чужой git и не обходит commit protocol.
- Контракт CLI изолирует процессы, версионируется и тестируется без сети.
- Провал перевода fail-closed: exit ≠ 0 блокирует запись; «частичный успех» не становится `verified`.
- Артефакты отделены от кода: RU-файл — project document, provenance/status — operational-артефакты вне manifest.

---

## Architecture Decision

### 1. Граница (SUBJ-001)

**Переезжает в `Translation Project`:**
`local_translate.py`; CLI-обёртка; системные промпты и `PROMPT_VERSION`; backend-клиенты (локальный OpenAI-совместимый, облачный); парсер глоссария; примитивы структурной сохранности (`needs_skip`, restore heading/list/code/paths); unit/mock/live-тесты и фикстуры; `EXPERIMENTS.md`; producer-side спецификация контракта; рецепт развёртывания vLLM.

**Остаётся в Council/Documenter:**
RU-файлы `docs/ru/**`; manifest `has_translation`; `check_drift.py` и норма structural preservation (line-parity + metadata fingerprint) — **Council-owned**; `docmeta.py`; `documenter_service/create_ru`, trust-классификатор, hash store, intent/commit protocol, audit trail; адаптер «глоссарий → JSON terms» (если нужен); `defaults/translation-project.lock`; `documenter/artifacts/translation/**`; AGENTS.md, SKILL.md, contract doc.

**Жёсткие запреты:** новый проект не импортирует `docmeta`, не знает manifest/RU-пути, не пишет в Council, не имеет собственного term-store. Council-адаптер передаёт движку список metadata-ключей и путь к глоссарию как входные параметры.

### 2. Контракт (SUBJ-002)

CLI-процесс, файловый I/O. Документ **не** передаётся через stdout.

```
translate \
  --input-en <path> --output-ru <path> --glossary <path> \
  --report <path> --source-lang en --target-lang ru \
  --glossary-schema-version <v> --contract-version <v> \
  [--cloud-key-file <0600-file>] [--allow-cloud] [--version]
```

- `stdout` — пуст/зарезервирован; диагностика — `stderr`; машиночитаемый результат — `--report`.
- Exit codes: `0` ok; `1` invalid input/parse/glossary; `2` usage; `3` backend unavailable; `4` incomplete (`fail>0`); `5` version/contract mismatch; `6` report/contract schema error. **В текущем коде реализованы только 1 и 4 (plus usage-path); 2/3/5/6 — pending implementation, обязательная часть producer-релиза v0.1.0 (AI #4); consumer-side фиксирует их как binding только после conformance-теста продюсера.**
- Version handshake: `--version` → сверка с lock → при mismatch exit 5 **до** перевода.
- Секреты: только `--cloud-key-file` (0600); запрещены argv/env; ключ не логируется. Облако — только при `--allow-cloud` и per-run согласии оператора.
- Нормативная спецификация — **dual spec**: consumer-side `docs/en/translation-project/index.md` (project document, обязательное `api_version` во frontmatter) + producer-side spec в новом репозитории. Mismatch — fail-closed.

### 3. Артефакты (SUBJ-003)

- `index-RU.md` **не меняется**: ни provenance, ни status, ни комментарии — иначе ломаются line-parity и metadata fingerprint.
- `documenter/artifacts/translation/<id>.json` — sidecar последнего прогона: `api_version`, engine version, model, backend, `prompt_version`, `glossary_schema_version`, ok/skip/fail, `gloss_applied`, `source_sha256`, `output_sha256`, write-gates, timestamp.
- `documenter/artifacts/translation/STATUS.md` — генерируемая таблица `id | status | model | prompt_version | backend | timestamp | report_ref`. Статусы: `verified` (100% гейтов), `unverified` (часть гейтов не выполнена/бэкенд упал), `drift` (EN изменился после перевода / глоссарий-дельта), `error-<code>`.
- `documenter/artifacts/translation/runs/` — неизменяемые отчёты прогонов; append-only `runs.jsonl`; retention 30 дней, daily rotation, backup/restore runbook.
- Все перечисленные файлы — **operational, вне manifest**; запрещено добавлять их в `docs-manifest.yaml`.
- **Единое решение по хранению (заменяет расхождение ролей «вне git»):** sidecar, `STATUS.md`, runs и lock — **git-tracked** по образцу `documenter/` (ADR-008) и `defaults/`: «operational» ≠ «вне git» (`.gitignore` их не исключает). Это закрывает потерю provenance при rebuild. Итоговое подтверждение — OQ-2.
- **Автор sidecar/STATUS:** адаптер `create_ru` в Documenter (trust floor `review`), не Translation Project (self-registering запрещён: движок не пишет в Council, §1.4 запреты).

### 4. Транзакция записи (SUBJ-001/005)

1. Pre-translate: SHA-256 EN → intent record (`tx_id`, `target_id`, EN path, `before_hash`).
2. Вызов движка: кандидат и отчёт — только во временный каталог; Council ничего не пишет до exit 0.
3. Verify: exit 0 + schema отчёта + все гейты; `fail>0` → отказ.
4. `check_drift.py` EN↔кандидат; line-parity; EN-identity scan; glossary compliance.
5. Повторный SHA-256 EN перед commit (TOCTOU); изменение → `hash_mismatch`, отказ.
6. Temp-RU в целевой директории → `rename` в `index-RU.md` — **точка фиксации**.
7. Hash store (RU), audit event, затем sidecar и `STATUS.md` **изводятся из сохранённого отчёта**.

**Уточнение модератора (несовместимость):** два `rename` (RU + sidecar) не атомарны, а intent record по §Safety Protocol #9 допускает только manifest-пути. Поэтому sidecar **не** входит в атомарную транзакцию: RU — источник истины, отчёт — неизменяемый источник provenance; sidecar/STATUS rebuildable. Сбой записи sidecar не откатывает RU: статус `unverified`, post-commit scan восстанавливает sidecar из отчёта. Сбой rename RU → полный откат, temp удаляются.

**Механизм post-commit regeneration (закрыт QC-блокером):** отдельная утилита `tools/translation_status.py` (Council, deterministic, dispatched skill'ом) — вход: каталог `runs/` (JSONL, запись = завершенный прогон) + manifest; выход: перезапись sidecar `<id>.json` (последняя запись по `target_id`) и агрегированного `STATUS.md` (полная регенерация таблицы, не инкрементальная правка). Утилита идемпотентна, вызывается: (а) после каждого успешного прогона адаптером `create_ru`; (б) cold-start как пост-коммит-скан, сверяющий наличие sidecar для каждого `has_translation`. Прогон без сохранённой записи в `runs/` → `unverified`. Включение утилиты — AI #6a.

### 5. Глоссарий (SUBJ-001/005)

- Канон — `docs/en/glossary/index.md` (AGENTS.md §4); новый проект получает его read-only; собственного term-store нет.
- Парсер — в `Translation Project`; `glossary-schema.json` версионируется вместе с движком; unknown/invalid → exit 1.
- Кэш глоссария — только в пределах прогона (ключ — hash файла); межпрогонного кэша нет.
- Изменение глоссария инвалидирует `verified` для затронутых документов (`drift`). MVP: консервативно — повторный прогон затронутых документов до следующего `verified`; если маппинг «термин → документы» не реализован, допустим режим «все документы» только по явному решению оператора (OQ-5).

### 6. Пиннинг и окружение (SUBJ-004)

- Новый репозиторий: semver-теги `vX.Y.Z`; `api_version` контракта версионируется отдельно.
- `defaults/translation-project.lock`: repo URL, tag, commit SHA, `api_version`, `min_engine_version`, `mode=legacy|external`. Владелец — Operations; изменение через review. Council проверяет lock при старте прогона; mismatch → exit 5.
- CI: pinned checkout по SHA; offline unit/mock обязательны; live e2e — по запросу оператора; облако в CI по умолчанию запрещено.
- vLLM: контейнер/рецепт, health-check `/models` (≤3 s), auto-restart (systemd/supervisord), GPU/VRAM requirements — **в новом репозитории**; Council ссылается, не дублирует.
- Секреты и приватность: ключ только в 0600-файле; в логах — метаданные, не текст документов; облачный прогон фиксируется в provenance.

### 7. Миграция (SUBJ-006)

| Фаза | Содержание | Критерий перехода |
|---|---|---|
| 0 | ADR-014, glossary-термины, consumer contract doc, SKILL.md, documenter-service, AGENTS.md §1.6/§1.7; manifest последним | Approve оператора; единый changeset |
| 1 | Новый репозиторий: перенос кода с историей, CI, тесты, producer spec, vLLM-рецепт, релиз v0.1.0 | unit+mock зелёные; релиз подписан/запинен |
| 2 | Shim + lock + флаг `TRANSLATION_IMPL=legacy|external`; старый код остаётся | shim вызывает pinned CLI; exit 5 работает |
| 3 | Parity 3×3: 3 документа (conceptual/protocol/reference) × 3 сбоя (backend down, version mismatch, invalid glossary) + happy path; canary 1–2 документа | структурное совпадение; 0 gate-fail |
| 4 | Cutover: post-Approve auto-sync через внешний проект; legacy fallback доступен | Approve; наблюдение ≥10 прогонов |
| 5 | Cleanup: удалить старый движок из `tools/`, обновить docs; manifest последним | ≥20 чистых прогонов, 0 gate-fail, conformance green, Approve |

**Откат:** `mode=legacy` в lock/флаге; старый код хранится до фазы 5. Обратный перевод (RU→EN) не поддерживается и не проектируется.

---

## Subjects with Outcomes

| Subject | Outcome | Ключевое решение |
|---|---|---|
| SUBJ-001 Граница | Agreed | Движок — в новый репо; `check_drift`, `docmeta`, `create_ru`, write-gates — в Council; жёсткие запреты на импорт manifest/frontmatter |
| SUBJ-002 Контракт | Agreed | CLI file I/O; exit 0/1/2/3/4/5/6; `--version` handshake; `--cloud-key-file`; dual spec с `api_version` |
| SUBJ-003 Артефакты | Agreed | RU не меняется; sidecar + `STATUS.md` + runs; operational, вне manifest; retention 30 дней |
| SUBJ-004 Репозиторий/релизы | Agreed | semver-теги + SHA lock `defaults/translation-project.lock`; CI pinned checkout; vLLM-рецепт в новом репо |
| SUBJ-005 Governance | Agreed | ADR-014; glossary-термины; contract doc; новый репо = implementation file; §3.3/ADR-012 не меняются |
| SUBJ-006 Миграция | Agreed | 6 фаз; parity 3×3; canary; rollback `mode=legacy`; cleanup после ≥20 чистых прогонов |

### Contested Points (C1–C7)

| ID | Outcome | Решение |
|---|---|---|
| C1 Артефакты/видимость | Agreed после исправления | RU неизменен; sidecar + `STATUS.md`; `verified` только при 100% гейтов |
| C2 Контракт | Agreed | Файловый I/O; exit codes; handshake; ключ 0600; dual spec |
| C3 Drift | Agreed | `check_drift.py` остаётся Council; норма structural preservation — Council-owned |
| C4 Пиннинг | Agreed | git tag + SHA lock; owner Operations; vLLM-рецепт в новом репо |
| C5 Транзакция | Agreed с уточнением | RU rename — точка фиксации; sidecar/STATUS производны от отчёта; fail-closed |
| C6 Глоссарий | Agreed | Парсер в новом репо; schema versioned; delta → `drift`, повторный прогон затронутых |
| C7 Миграция | Agreed | Фазы 0–5; readiness matrix; rollback; cleanup по метрикам |

---

## Conflicts & Disagreements

— None. Единственное содержательное расхождение (C1: provenance внутри RU-файла vs отдельный артефакт) снято в раунде: HCD признал, что вставка ломает line-parity/metadata fingerprint.

**Фактические уточнения модератора (не меняют позиций ролей, но исправляют предпосылки):**
1. «Operational» не означает «вне git»: `documenter/` git-tracked по ADR-008, `defaults/` — тоже. Вопрос хранения sidecar/lock вынесен в OQ-2.
2. Два `rename` (RU + sidecar) не дают кросс-файловой атомарности; sidecar/STATUS сделаны производными от неизменяемого отчёта, а не частью атомарной транзакции.

---

## Reservations (by role)

- **Architect:** `STATUS.md` требует захода в `documenter/artifacts/translation/`; приемлемо, но не «в том же файле». Sidecar вне git теряется при rebuild — компенсируется intent+audit+hash store; постоянное хранение — отдельный запрос на §1.6.
- **Reliability:** intent retention ≥30 дней и backup нужны, иначе provenance частична; `STATUS.md` без CLI-view — приемлемо для MVP.
- **HCD:** self-describing ошибки обязаны содержать «что делать», но в `STATUS.md` — только краткий код; CLI-view статуса — post-MVP.
- **Operations:** GPU/VRAM requirements и vLLM-рецепт — зона нового проекта; backup/restore runbook для operational-файлов нужен до первого миграционного прогона.
- **Compliance:** lock не заменяет нормативный `api_version` в contract doc; если lock не в git, нужен ops-механизм синхронизации CI.

---

## Open Questions (operator decisions)

1. **Имя, хостинг, лицензия и видимость нового репозитория**; кто владелец и secondary maintainer.
2. **Git-хранение sidecar и lock:** рекомендовано track (малый объём, аудит, CI), несмотря на «operational»; альтернатива — вне git + backup/runbook.
3. **Строгость границы «только артефакты»:** допустим ли тонкий adapter в `documenter_service/create_ru`, или Documenter должен быть полностью пассивным (трансляцию запускает только skill/CLI, Documenter лишь ingest'ит артефакты)? Это определяет объём правок `create_ru`.
4. **ID и место consumer contract doc:** `docs/en/translation-project/index.md`? Требуется новая запись в manifest и cross-refs.
5. **Политика glossary delta:** обязательный повторный прогон всех документов vs только затронутых (нужен маппинг «термин → документы»); стоимость и допустимая задержка.
6. **vLLM:** чей хост/GPU, требования VRAM, контейнерный runtime, кто отвечает за auto-restart.
7. **Облачный fallback:** стоимость/квоты, UX per-run согласия, допустимость отправки каких категорий документов.
8. **Provenance retention:** 30 дней достаточно? Нужен ли долговременный архив отчётов для аудита.
9. **Термин:** `Translation Project` или `Project Translation` — зафиксировать одно имя в glossary.
10. **История:** сохранять git-историю переносимых файлов через `filter-repo`/subtree? Переносить ли теги/issues.

---

## Action Items

| # | Действие | Где | Приоритет |
|---|---|---|---|
| 1 | ADR-014: cross-repo boundary, ownership, release model, новый репо = implementation file | `docs/en/planned-architecture/decisions/` | P0 (post-Approve) |
| 2 | Glossary: `Translation Project`, `Translation Project Artifact`, `Status Index`, `Translation Contract`; выбрать одно имя | `docs/en/glossary/index.md` | P0 |
| 3 | Consumer contract spec с `api_version`, schema отчёта, exit codes, handshake | `docs/en/translation-project/` | P0 |
| 4 | Producer spec + CLI file I/O + `--version` + report schema + exit 4 fix | новый репозиторий | P0 |
| 5 | Секреты: `--cloud-key-file` 0600, удалить ключ из argv/env, redaction логов | новый репозиторий | P0 |
| 6 | Sidecar + `STATUS.md` + runs + retention/rotation/backup runbook | `documenter/artifacts/translation/`, новый репо | P1 |
| 7 | Транзакция: EN hash → intent → verify → temp-RU → check_drift → rename → hash/audit → derive sidecar | `documenter_service/` + SKILL.md | P1 |
| 8 | Lock `defaults/translation-project.lock` + CI pinned checkout + exit 5 | Council + CI | P1 |
| 9 | vLLM: контейнер, health-check, auto-restart, GPU/VRAM docs | новый репозиторий | P1 |
| 10 | Parity 3×3 + canary + failure injection; записать метрики | sessions/ + CI | P1 |
| 11 | Shim + `TRANSLATION_IMPL=legacy|external`; сохранить старый код | Council `tools/` | P1 |
| 12 | SKILL.md: generic `translation-project`, Phase 4 gates неизменны; `tools/local-translate.sh` → optional/deprecated | `.agents/skills/documentation/SKILL.md` | P2 (post-Approve) |
| 13 | documenter-service docs: create_ru, RU alignment, artifact paths; AGENTS.md §1.6/§1.7 | docs/ | P2 |
| 14 | Manifest regenerate последним; changelog для каждого документа | `tools/gen_manifest.py`, `CHANGELOGS/` | P2 |
| 15 | Cleanup старого движка после ≥20 чистых прогонов и Approve | `tools/` | P3 |

---

## Escalation References

— None. Все initial `concerns` сняты в раунде; `blocked-*` не зафиксировано. `risk-threshold-breach` Reliability и `information gap` Compliance закрыты решениями C1/C2/C4/C5 и OQ-2/OQ-5.

## Downgraded Critical Findings

— None. Все critical-находки имели корректную аргументацию; они не понижены, а закрыты решениями (fail-closed, provenance, транзакция, пиннинг).

---

## QC & Audit Amendments (post-consensus)

Консенсус прошёл две независимые контрольные проверки (облачная модель, роли не из консилиума): `consensus-qc.md` — verdict **принять с правками**; `consensus-compliance-audit.md` — verdict **исполним с уточнениями**. Их блокеры учтены выше (storage, post-commit regeneration, exit-коды) и ниже — дополнительными пунктами.

Дополнительные Action Items:

| # | Действие | Где | Приоритет |
|---|---|---|---|
| 6a | `tools/translation_status.py` — детерминированная регенерация sidecar/`STATUS.md` из `runs/` + manifest; идемпотентна, cold-start scan | `tools/` | P1 |
| 16 | Обновить ВСЕ ссылки на переносимый инструмент единым changeset фазы 0: `SKILL.md` (7 мест: L186, 213, 218, 234, 236, 265–266), `tools/README.md` (L17, 20, 117, 140, 142–143, 64–175), `documenter-service/mvp-contract.md:25`, ссылка на `EXPERIMENTS.md` | docs/ + SKILL.md | P0 (§1.7 prose-contract) |
| 17 | Consumer contract doc разделить на два: `translation-project/` (Protocol) + `translation-project-contract/` (Format: JSON schema, exit-code table) — требование §7.4/§7.3 | `docs/en/` | P0 |
| 18 | Rollback checklist для `mode=legacy`: порядок отката, проверка hash store, верификация | новый репо + ops docs | P1 |
| 19 | Privacy gate: перечислить категории документов, запрещённые к облачному переводу; проверка перед `--allow-cloud` | contract doc + SKILL.md | P0 |
| 20 | Секьюрити-скан git-истории переносимых файлов (API-ключи, credentials) до создания нового репо (`git filter-repo --invert-paths` при находках); лицензия/copyright header | новый репо | P0 |
| 21 | Совместимость при breaking change контракта (`api_version` bump): conformance-тест + shim-обнаружение несовместимости | новый репо + CI | P2 |

Версионные bump'и затронутых документов — в `consensus-compliance-audit.md` (Version Bumps Table). Ключевые: `AGENTS.md` 0.16.0→0.17.0 (minor, §1.6/§1.7), `SKILL.md` major (переход на внешний движок), `decisions` 0.8.0→0.9.0 (ADR-014), `glossary` 0.15.0→0.16.0, документер-service — patch, новые `translation-project*` — 0.1.0. Формулировка §1.6 о внешних репозиториях — корректирующее дополнение (одно предложение), по мнению аудитора допустимо без отдельного ADR; финальное подтверждение — OQ-11.

Дополнительные Open Questions:

11. **§1.6 amendment**: подтверждаете одно предложение про внешние репозитории без отдельного ADR?
12. **Лицензия и авторство переносимого кода** (944 строки + фикстуры + `EXPERIMENTS.md`); история коммитов — скан на секреты перед переносом.
13. **Хранение provenance в git** — финальное подтверждение решения «git-tracked, вне manifest» (вместо исходного «вне git»).
14. **Разделение contract doc** (§7.4) — два документа или одобренное исключение-монолит.

---

## Operator Decisions (2026-11-15, Phase 2 Align)

1. Имя репозитория: **techdoc-translator**, GitHub, текущий пользователь.
2. **Полная независимость**: новый проект ничего не знает о Council/Documenter — никаких Council-ключей frontmatter, манифеста, путей и терминов в коде и документации нового проекта. Свой файл конфигурации LLM. Своя документация. Свой AGENTS.md (пишется заново после переезда).
3. **На время переезда Documenter не используется**; подключается позже.
4. План переезда (порядок оператора): (1) переписать английскую документацию и скрипты в новый проект → (2) создать упрощённый AGENTS.md → (3) создать артефакты в новом проекте → (4) в Council заменить уехавшее на артефакты.
5. Это уточнение имеет приоритет над пунктами консенсуса, предполагавшими Council-знание в движке (передача metadata-ключей адаптером, Council-формат глоссария как вход движка) — детали пересматриваются вопросами Q1–Q10 ниже (в чате 2026-11-15).

### Ответы оператора на Q1–Q10 (2026-11-15)

- **Q1 = A.** Глоссарий передаётся как `--glossary <путь>`; в новом проекте описан generic-формат файла пар терминов, без упоминания Council.
- **Q2 = модифицированная A.** Движок сам знает markdown и сам распознаёт/не трогает metadata-линии (generic-детект, не Council-ключи); `--skip-pattern` — дополнительная опция переопределения. Совет Council по-прежнему проверяется `check_drift.py` (metadata fingerprint — единственный судья).
- **Q3 = A.** Интеграция на переход — один вызов CLI из Documentation Worker skill, путь из lock-файла `defaults/translation.lock`; Phase 4 write-gates неизменны.
- **Q4 = A.** Жёсткая замена: движок+обёртка+тесты+EXPERIMENTS+run-log переезжают, из `tools/` удаляются (откат через git revert/tag, без shim); ссылки SKILL.md/README обновляются единым changeset.
- **Q5 = A.** Разделение артефактов: свои (golden-фикстуры, mock, run-log движка, summary-json) — в techdoc-translator; интеграционные (RU + provenance/STATUS) — в Council, пишет Council.
- **Q6 = изменено оператором.** Конфигурация LLM — **`.env` (в `.gitignore`) + `.env.example`** (вместо config.toml). Секреты только в `.env`.
- **Q7 = A.** AGENTS.md нового проекта — минимальный инженерный регламент (код, тесты, изменения, секреты/облако), без ceremony (без своего глоссария/манифеста/RU-политики).
- **Q8 = изменено оператором.** Собственный тестовый корпус движка создаётся **отдельной сессией**; на переезде — минимальные смоук-тесты CLI. Council integration-тесты (mock/e2e с check_drift) остаются в Council.
- **Q9 = B.** Public + лицензия (MIT/Apache-2, выбрать при создании), обязательный скан секретов до первого push, `EXPERIMENTS.md` деперсонифицируется (убрать провайдера/эндпоинты). Перенос без git-истории.
- **Q10.** На время переезда **текущий проект (Council-документация) замораживается**; EN-правок нет → drift-audit не требуется на период переезда.
  - **Заморозка снята 2026-11-15** после коммита `a89d67f` (Council) и публикации `techdoc-translator@v0.1.0`. Обычный workflow (§5.2, ADR-012 post-Approve auto-sync) восстановлен; RU-кандидаты генерируются только через внешний CLI по `defaults/translation.lock`, запись — только Documentation Worker skill после Phase 4 write-gates; provenance — sidecar + STATUS.md via `tools/translation_status.py`.

---

## References

- `task-brief.md`, `discussion-input.md`
- `review-Architect.md`, `review-ReliabilitySecurity.md`, `review-HumanCentricDesigner.md`, `review-OperationsEngineer.md`, `review-Compliance.md`
- `review-Architect-r1.md`, `review-ReliabilitySecurity-r1.md`, `review-HumanCentricDesigner-r1.md`, `review-OperationsEngineer-r1.md`, `review-Compliance-r1.md`
- `review-Architect.stray-cloud.md` — ошибочный первый запуск, в консенсус не входит
- `consensus-qc.md` — adversarial QC-ревью (облачная модель, независимый агент)
- `consensus-compliance-audit.md` — процедурный комплаенс-аудит плана (облачная модель, независимый агент)

**Compliance note:** в ходе сессии документы, manifest и код не изменялись. Все нормативные изменения — только после шага (5) Approve (AGENTS.md §5.1).

---

*Consensus status: Resolved (unanimous agree); OQ-1…OQ-10 — решения оператора, не блокеры.*
