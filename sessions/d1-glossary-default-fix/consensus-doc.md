# Consensus Document — sess-d1-glossary-default-fix

Date: 2026-11-22 · Mode: fallback (4 roles: Architect, Reliability & Security, Human-Centric Designer, Operations) · Moderator: operator (human)
Defect: D-1 (high) — `tools/check_drift.py --phase4` при отсутствии `--glossary` подставляет глоссарий фреймворка (резолв от `__file__`) в хост-прогон → ложная находка `phase4-glossary: glossary terms untranslated: Subject`.

## Decision (consensus)

Единый атомарный коммит **A + B + D + E**; кандидат **C отклонён** (единогласно, раунд 2). Инструмент остаётся информационным (exit-коды 0/1/2 never gating). **Единственный неразрешённый ролями пункт — строгость при отсутствии флага (SUBJ-001): решение оператора, см. «Operator decision» ниже.**

1. **A — удалить неявный дефолт** (`check_drift.py`, строки 638–639). Никакого резолва от `__file__` и от CWD (CWD-default отклонён единогласно: вердикт, зависящий от каталога запуска, — тот же класс скрытой конфигурации). Vacuous-прогон возможен только в явно объявленной форме (форма — на решении оператора).
2. **B — provenance всегда**: stderr-строка `glossary: path=<resolved> | terms=<N> | status=checked|vacuous`; stdout остаётся line-per-finding (`--json` совместим). Явно переданный, но отсутствующий/нечитаемый путь → **exit 2** (ошибка конфигурации вызывающего, «прогон не состоялся»), отдельно от exit 1 (содержательные findings). Оба `except OSError: return []` пути в `_check_phase4_glossary` закрываются.
3. **C — rejected**: `re.IGNORECASE` инертен (EN/RU-тела уже `.lower()`); настоящая регистрозависимость даёт false negatives (fail-open). Остаточный риск (омонимы глоссария в хостовой прозе) фиксируется как **отдельный пункт «курирование глоссария»** без кода в этом changeset.
4. **D — prose-sync в том же коммите**: `SKILL.md` (строка ~246: `--glossary` обязателен в wrapper-контракте; семантика vacuous; убрать «all gates pass (write permitted)» — при вакууме гейт 3 не проверен) и `tools/README.md` (строка 18). §Provenance: статус читается как `verified (glossary: vacuous)` — аннотация, без нового значения STATUS.md.
5. **E — регрессия**: тест host-сценария (скрипт в `X/.council/tools/`, cwd = проект Y; EN-тело содержит строчное «subject») → нет finding `phase4-glossary`, в stderr `VACUOUS`, exit 0; кейс «хост-глоссарий есть → используется он»; кейс «явный битый путь → exit 2». Лживый `test_glossary_no_glossary_flag_uses_default` переименовать/переписать. **21 вызов теста без `--glossary` перевести на явный `mini-glossary.md`** — иначе после A покрытие гейта молча обнулится под зелёным CI.
6. **dist**: `dist/out/council-dist/**/tools/check_drift.py` — синхронная пересборка в том же коммите (опубликованный артефакт не должен расходиться с источником).

## Subject outcomes

| Subject | Outcome |
|---------|---------|
| SUBJ-001 default-path | agreed (оператор выбрал **(b)**) — дефолт удалён; CWD-default rejected; отсутствие `--glossary` → exit 2; осознанный пропуск — только явный `--glossary none` с печатью VACUOUS (exit 0) |
| SUBJ-002 observability | agreed — provenance-строка всегда (в `--json` — stderr; human-режим — coverage-блок, line-per-finding не трогать); exit 2 для явно переданного нечитаемого пути (единогласно); **+Reliability: непустое EN-тело, но 0 распарсенных терминов → exit 2** (сломанный формат глоссария = тихий false pass); gate-summary попадает в run-артефакт (HCD) |
| SUBJ-003 case-sensitivity | rejected (consensus, раунд 2) — IGNORECASE инертен (тело уже `.lower()`), настоящая регистрозависимость = fail-open; residual risk → item «курирование омонимов» |
| SUBJ-004 prose-contract | agreed — SKILL.md + README.md в том же коммите; вместо нового enum STATUS.md — структурная аннотация вида `verified | gates 3/4 | unchecked: glossary`, выводимая из gate-summary, не из exit_code |
| SUBJ-005 tests | agreed — E (тест обязан быть **красным на старом коде**, зафиксировать в сообщении коммита) + миграция 21 вызова на явный `mini-glossary.md` (**дифф только аддитивный** — добавлен `--glossary`, ассерты не изменены) + переименование лживого `test_glossary_no_glossary_flag_uses_default` |

## Reservations (conditionally agreed)

- **Operations**: vacuous-прогон без флага оставлен легитимным (exit 0) — fail-closed ломает ad-hoc диагностику; SKILL.md после D передаёт флаг всегда. Альтернатива (exit 2 + sentinel `none`) тоже совместима с его чек-листом — не блок.
- **Human-Centric**: «vacuous должен быть произнесён, а не промолчан» — при любом решении оператора vacuous-статус обязан читаться словом в выводе и в run-артефакте; provenance в stdout живёт до закрытия терминала, поэтому gate-summary пишется в артефакт прогона.
- **Reliability**: приняла fail-open при условии вечной видимости provenance; молчаливый пропуск provenance-строки = дефект того же класса, что D-1.

## Operator decision (RESOLVED 2026-11-22)

**Решение оператора: (b)** — отсутствие `--glossary` в CLI → **exit 2** (ошибка вызывающего, «прогон не состоялся»); осознанный пропуск гейта — только явным `--glossary none`, который печатает `VACUOUS` (exit 0). Каждый прогон обязан назвать свой глоссарий или объявить его отсутствие. Второй флаг (`--no-glossary`) отвергнут (OP-2).

**Ещё два решения оператора:** запись в `CHANGELOGS/` при смене CLI-контракта (роли склоняются «да, механическая»); подтверждение, что фреймворковый глоссарий к host-документам не применим никогда (тогда ветка «глоссарий фреймворка» в хосте — всегда ошибка, special-case не нужен).

## Action items (один атомарный коммит, OP-3)

1. `tools/check_drift.py`: удалить дефолт (638–639); provenance-вывод (всегда; `--json` → stderr); различать «нет флага» (по решению оператора) / «путь не читается» (exit 2); закрыть silent-OSError; `N=0 терминов при непустом EN-теле` → exit 2.
2. `tools/tests/test_check_drift.py`: E-тесты (красные до фикса — задокументировать в сообщении коммита); миграция 21 вызова аддитивно; кейсы: чужой глоссарий не читается / vacuous виден словом / явный битый путь → exit 2; `--json` stdout без посторонних строк.
3. `.agents/skills/documentation/SKILL.md` + `tools/README.md`: `--glossary` обязателен в wrapper-контракте; убрать «all gates pass (write permitted)»; статус `verified | gates 3/4 | unchecked: glossary` из gate-summary.
4. Копия в `dist/out/council-dist/**/tools/` — пересборка в том же коммите + примечание: существующим хостам нужен `update.sh`.
5. Верификация: `pytest tools/tests/test_check_drift.py`; `python3 tools/check_all.py` (advisory); ручное host-репро; `diff` dist-копии и источника; drift-режим — нулевое изменение поведения.
6. Откат — `git revert` одного коммита.

## Open questions (решение оператора)

- Запись в `CHANGELOGS/` при смене CLI-контракта: роли склоняются «да, механическая» — подтвердите.
- Отдельные будущие items (вне этого коммита): курирование омонимов глоссария; эвристика 4-символьного RU-стема; вопрос Reliability о легитимности применения фреймворкового глоссария к host-документам (сейчас — всегда ошибка конфигурации).

## Final statuses (Phase 4)

Architect — agree · Reliability — agree · Operations — concerns (резервации, не блок) · Human-Centric — concerns (резервации, не блок). Блоков нет → **conditionally resolved**; резервации и вопрос оператора записаны выше.

## Escalations

Нет. Critical findings ролей с валидными обоснованиями (конкретный режим отказа + субъекты) — 0 даунгрейдов.
