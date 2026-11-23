# Task Brief — Вынос подсистемы перевода из Documenter в отдельный проект

Session ID: sess-translation-extraction
Date: 2026-11-15
Mode: fallback (fallback/index.md v0.6.0)
Roster: Architect, Reliability & Security Specialist, Human-Centric Designer, Operations Engineer, Documentation Compliance Ombudsman (extended)
Expected rounds: 1 (medium-complex); targeted resolution only if a block persists

---

## Task Description

**Запрос оператора (дословно):** «Нам нужно вынести часть Документатора в отдельный проект. Это проект по переводу технической информации на русский язык. Этот проект должен лежать в отдельном репозитории, а в Документаторе — только артефакты этого проекта. Проведи консилиум, как это лучше сделать».

**Интерпретация для консилиума.** Требование «отдельный репозиторий» считается фиксированным (это не предмет голосования). Предмет решения — **как именно** провести границу и организовать взаимодействие так, чтобы:

1. Переиспользуемый переводческий движок (LLM-перевод EN→RU, работа с глоссарием, структурная целостность markdown, верификация, тесты, эксперименты, конфигурация бэкендов) жил самостоятельным проектом в собственном репозитории.
2. В Council/Documenter оставались **только артефакты** этого проекта, а не его код, промпты, тесты и конфигурация.
3. Существующие гарантии не деградировали: line-parity, write-gates, запрет автозаписи до Approve (AGENTS.md §5.1), post-Approve RU-синхронизация (ADR-012), единственный источник глоссария (AGENTS.md §4), приватность облачной ветки, отсутствие rule fork.

**Что уже существует (инвентарь, обязательный к учёту):**

- `tools/local_translate.py` (944 строки) — движок: чанкинг по абзацам, `needs_skip`, `enforce_glossary`, `restore_heading_prefix`, `restore_list_marker`, `restore_code_spans`, `restore_paths`, line-parity fallback, `PROMPT_VERSION`, `--summary-json`, `TRANSLATE_RUN_LOG`.
- `tools/local-translate.sh` (115 строк) — обёртка: env-дефолты, preflight локального OpenAI-совместимого сервера (vLLM), коды выхода 0–4.
- `tools/check_drift.py` (420 строк) — детерминированное EN↔RU структурное сравнение (8 правил), завязано на `tools/docmeta.py` и frontmatter Council-документов.
- `tools/tests/` — unit (209 строк), mock-backend, `run_translate_tests.sh`, `e2e_live.sh`; `tests/translate-fixtures/`.
- `tools/EXPERIMENTS.md` (473 строки) — E-001…E-008, обоснование дефолтов.
- `.agents/skills/documentation/SKILL.md` §Create or Update Russian Translation, §Translation via project translator — контракт вызывающего агента, Phase 4 write-gates.
- `documenter_service/` — `create_ru` в trust-классификаторе, write-путь, hash store, commit protocol; RU-путь берётся из manifest `has_translation`.
- `docs/en/glossary/index.md` — канонический глоссарий с русскими эквивалентами (единственный источник, AGENTS.md §4).
- `docs/ru/**` — существующие переводы (артефакты документации), `docs-manifest.yaml` поле `has_translation`.
- AGENTS.md §3.3 + ADR-012 — post-Approve auto-sync, opt-out `no_auto_translation`.

**Терминологическая развилка, которую обязаны разрешить роли:** что считается «артефактом проекта перевода» в Documenter. Кандидаты: (а) только итоговые RU-файлы; (б) RU-файлы + машиночитаемый отчёт верификации/provenance на каждый прогон; (в) плюс run-log/журнал, кандидаты и diff'ы, контрактная схема. Позиция «код адаптера тоже артефакт» должна быть явно отклонена или обоснована.

---

## Subject List (канонический; ссылаться только на эти ID)

- **SUBJ-001 — Граница извлечения.** Что переезжает в новый репозиторий, что остаётся в Council/Documenter, где проходит шов (движок vs. адаптер; `check_drift` vs. write-gates; глоссарий vs. его парсер).
- **SUBJ-002 — Контракт интеграции.** Способ вызова (CLI-процесс / HTTP-сервис / библиотека / MCP), формат входа-выхода, коды ошибок и их семантика, версия контракта, таймауты, provenance-поля, поведение при недоступности.
- **SUBJ-003 — Артефакты в Documenter.** Какие выходы проекта перевода хранятся в Council/Documenter, где (например `docs/ru/…`, `documenter/artifacts/translation/…`), формат, срок жизни, кто пишет, как связаны с manifest/hash store/audit trail.
- **SUBJ-004 — Репозиторий и релизы.** Имя/структура нового репозитория, лицензия, направление зависимостей, пиннинг версии (git tag / submodule / пакет), CI, тестовая матрица, миграция git-истории, локальный dev-workflow, обратная совместимость.
- **SUBJ-005 — Governance и соответствие.** ADR, изменения AGENTS.md/SKILL.md/спецификации Documenter/манифеста, владение глоссарием, права записи, privacy-gate, границы ответственности и процесс изменений между репозиториями.
- **SUBJ-006 — План миграции и откат.** Последовательность этапов, feature flag / thin shim, критерии готовности и parity-тесты, rollback, критерии удаления старого кода.

---

## Questionnaire per Role

**Architect:**
- Q1: Где должен проходить шов, чтобы новый проект был переиспользуемым вне Council, а Documenter не превратился в его форк?
- Q2: Кто владеет «знанием о Council» (frontmatter, manifest, line-parity, глоссарий) — движок или адаптер?
- Q3: Какой контракт (SUBJ-002) минимизирует связность и не создаёт распределённый монолит?

**Reliability & Security Specialist:**
- Q1: Какие failure modes появляются на границе двух репозиториев/процессов (version skew, partial output, TOCTOU, тихая порча, потеря provenance)?
- Q2: Где могут утечь данные (облачная модель, ключи, логи, промпты, артефакты) и какие гейты обязательны?
- Q3: Как обеспечить доказуемость «перевод не хуже текущего» при переключении и как откатиться?

**Human-Centric Designer:**
- Q1: Не добавляет ли разделение лишний шаг/когнитивную нагрузку оператору и вызывающему агенту? Как должен выглядеть UX?
- Q2: Поймёт ли человек, откуда взялся перевод, чем он верифицирован и что делать при сбое?
- Q3: Достаточно ли «артефактов» в Documenter для доверия к переводу без чтения чужого репозитория?

**Operations Engineer:**
- Q1: Как эксплуатировать два репозитория: релизы, пиннинг, CI, секреты, observability, журналы прогонов, стоимость?
- Q2: Что делать с локальной зависимостью vLLM/GPU и облачным fallback в разрезе нового проекта?
- Q3: Какие операционные риски у bus factor, лицензии, версионирования и синхронизации документации?

**Documentation Compliance Ombudsman:**
- Q1: Какие документы и в каком порядке должны измениться (ADR, AGENTS.md, SKILL.md, documenter-service, glossary, manifest)?
- Q2: Не нарушает ли предлагаемая схема §1.6 (project vs implementation files), §2.2 (manifest), §3.3/ADR-012, §4 (глоссарий), §5.1 (Approve)?
- Q3: Где проходит граница между «артефактом проекта» и «implementation file», и как это отразить в manifest/changelog?

---

## Constraints & Explicit Risks

- **Совет advisory.** Никаких записей в документы, манифест, changelog или код до шага (5) Approve (AGENTS.md §5.1). Итог сессии — только `consensus-doc.md` и обсуждение.
- **Отдельный репозиторий — фиксированное требование.** Обсуждается механика, а не целесообразность.
- **«В Documenter — только артефакты».** Роли обязаны дать проверяемое определение артефакта и перечень того, что в Documenter НЕ попадает (код, промпты, тесты, конфигурация бэкендов).
- **Глоссарий — единственный источник** (AGENTS.md §4); параллельный term-store запрещён; новый проект получает глоссарий как вход, а не как копию-источник.
- **Никаких советов по правке `fallback/`** (§1.5, заморожен).
- **Запрет на вызовы `council.*`/`documenter.*` MCP** (§1.7); MCP-сервер не регистрировать.
- **Локальный backend — основной**, облако — только с per-run согласием оператора (ADR-012).
- **Текущие `docs/ru/**` не удалять** и не переводить заново в рамках миграции без отдельного решения.
- **Бюджет:** ≤150 строк на ревью; 5–7 findings; 3–5 recommendations; 2–3 open questions. Без пересказа брифа.
- **Риски, которые нельзя игнорировать:** version skew между репозиториями; двойная запись/частичный output; тихая деградация качества перевода; supply-chain и секреты; расползание «знания о Council» по двум репозиториям; рост когнитивной нагрузки; невозможность отката.

---

## Expected Output Structure (fallback/index.md)

```markdown
# <Role Name> Review

## Summary Position
(One sentence.)

## Key Findings
- [severity] Finding text referencing `<SUBJ-ID>`; для critical — названный failure mode/attack scenario.

## Recommendations
- Actionable suggestion tied to a subject.

## Open Questions
- Clarification needed.

## Status
agree / concerns / blocked-in-scope / blocked-escalation

## Escalation Reason
(if blocked-escalation) information-gap / irresolvable-conflict / risk-threshold-breach
```

Ревью пишется на русском языке (заголовки — как выше), в файл `sessions/sess-translation-extraction/review-<role>.md`; в ответ оркестратору — только 10–15 строк резюме (позиция, статус, 3 главных пункта, 1–2 open questions).
