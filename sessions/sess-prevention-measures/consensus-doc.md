# Consensus Document — Превентивные меры против дефектов переводчика

Session: sess-prevention-measures | Date: 2026-11-14
Mode: fallback | Roster: Architect, Reliability, HCD, Operations, Compliance Ombudsman
Rounds: 1 (все статусы `concerns`, противостоящих позиций по идентичным subject нет)

## Decision taken и rationale

**Меры A–E принимаются условно, с существенными модификациями.** Корневые причины (нет тестов, прозаические контракты, неконвертированные предупреждения консилиумов) реальны; предложенные средства — верны по направлению, но в наивной форме порождают собственные риски (ложная уверенность mock-зелени, дублирование проверок, неисполнимые нормы).

## Subjects with outcomes

| Subject | Outcome | Решение |
|---|---|---|
| SUBJ-001 A: mock-регрессия | conditionally agreed | Принята как **двухслойная** схема: (1) **quick-слой** — unit-тесты без сети/LLM (needs_skip, enforce_glossary regex, restore_*, инвариант границ идентификаторов, табличные разделители, метаданные), <5 с, всегда; (2) **mock-слой** — фикстуры с канонизированными ответами, opt-in (не в pre-commit); (3) **live-слой e2e** — отдельный скрипт `tools/tests/` с реальным сервером, прогон по запросу оператора, результат — в TRANSLATE_RUN_LOG с полем `backend`. Отчёты ВСЕГДА маркируют слой (`mock` vs `live`) — защита от ложной уверенности (critical у трёх ролей). Отдельный раннер `tools/tests/run_translate_tests.sh` — exit-коды хука (0/1/2) не расширяем (Architect high). |
| SUBJ-002 B: check_drift.py | conditionally agreed | **Отдельный детерминированный тул** (не часть check_all.py), строго **structural-only**: заголовки/иерархия, строки таблиц, фенсы, маркеры списков, идентичность inline-code-спанов, fingerprint метаданных. ИСКЛЮЧЕНО: line-parity ( owned Phase 4 gate — no-rule-fork), глоссарий и абстракция (AI-резерв, правила 3/5). Вызывается: из mock-слоя A как инвариант (Ops) И из drift-audit-режима skill'а (вместо «глазами»). В выводе — `coverage` секция: что проверено детерминированно, что осталось AI (HCD high). |
| SUBJ-003 C: единый needs_skip | conditionally agreed | Прямое слияние множеств ключей отвергнуто (разные семантики — Architect high). Реализация: `local_translate.py` **односторонне импортирует** `KNOWN_KEYS` из `docmeta.py` (Compliance подтвердил: циклов нет) как базис `is_metadata_line`; расхождения (например, `has_translation:`) — явный дополненный список с комментарием-ссылкой. Табличные разделители — в `needs_skip` (уже). «Что skip» — таблица на одном экране в tools/README.md. |
| SUBJ-004 D: warning→test | conditionally agreed | Норма: каждая finding high/critical консилиума порождает action item «тест/гейт, воспроизводящий failure mode»; owner — **primary agent** (проверяет при формировании task brief'а Phase 1). Закрепление: **SKILL.md + tools/README.md**, НЕ AGENTS.md (HCD — против раздувания; Ops — L-priority). В AGENTS.md §8 — только при отказе оператора от SKILL.md-варианта (Compliance допустим с owner). ADR-013 — не требуется (норма процесса, не архитектура), operator's call. |
| SUBJ-005 E: точечные страховки | agreed | Поглощаются quick-слоем A; unit-тест инварианта regex (термин не заменяется внутри `[A-Za-z0-9_]`) — retained как явный дешёвый кейс. |
| SUBJ-006 Приоритеты, хвост SKILL.md | agreed | Порядок: **M1** quick-слой + unit regex → **M2** check_drift.py (B) с coverage-выходом → **M3** mock-слой фикстуры + live-скрипт + версионирование фикстур привязкой к `PROMPT_VERSION` (Ops high: смена промпта → явный регламент обновления фикстур) → **M4** C-импорт → **M5** D-норма. **Хвост прошлой сессии:** контракт SKILL.md «headings … copied verbatim» лжёт после починки — правка §Translation via project translator + bump **0.7.0→0.8.0** (minor, contract change). Дополнительно (Compliance): нормативный пункт в AGENTS.md §1.7 — «prose-контракты tools обязательны к сверке при изменении поведения tools» (корень бага 3). |
| SUBJ-007 Риски самих мер | conditionally agreed | Приняты ограничения: pre-commit — только quick-слой (LLM-прогон 6–150 с/блок в хук недопустим); `--no-verify` обход — осознанное допущение MVP (гейт не безопасность, а дисциплина; live e2e по запросу остаётся); четвёртый раннер избеган — один скрипт `run_translate_tests.sh`, stdlib-стиль (без pytest, по образцу tests_helpers.py); фикстуры — замороженные копии с явной версией + линт «фикстура не новее исходника» (fixture decay, Reliability high). |

## Role reservations

- **Architect:** критична граница B↔Phase 4 (иначе fork); C без общего модуля — иначе цикл импортов.
- **Reliability:** mock — necessary but insufficient; property-инварианты на пути/идентификаторы/line-parity (аналогия ADR-001) включить в quick-слой; EN-identity scan не ловит partial-EN-leakage — добавить скан кириллической доли в check_drift.
- **HCD:** маркировка слоёв mock/live обязательна во всех отчётах; coverage-секция B; D не в AGENTS.md.
- **Operations:** сегментация quick<5с/full-opt-in; B как инвариант A; версионирование фикстур к PROMPT_VERSION; сводный статус последнего live-e2e — в jsonl.
- **Compliance:** B вне check_all.py и без правил 3/5/line-parity; SKILL.md 0.8.0 за лгущий контракт; C-импорт безопасен; глоссарий +3 термина (drift checker, structural fingerprint, mock-регрессия); D с owner.

## Процедура легитимизации (перечень файлов)

1. `tools/tests/` (новые: `run_translate_tests.sh`, unit/mocks/, fixtures/, `e2e_live.sh`) — operational, вне манифеста.
2. `tools/check_drift.py` — новый детерминированный тул.
3. `tools/local_translate.py` — импорт KNOWN_KEYS из docmeta; сводный e2e-статус в run log.
4. `tools/README.md` — quick/full/live слои, «что skip», D-норма (операторская часть).
5. `SKILL.md` 0.7.0→0.8.0: правка лгущего контракта headings; drift-audit режим вызывает check_drift.py; D-норма (агентская часть, owner: primary agent); в §Deterministic Delegation — строка для check_drift.py.
6. `AGENTS.md` §1.7 — пункт про сверку prose-контрактов (minor 0.14.0→0.15.0). [Опция оператора вместо SKILL.md-варианта D.]
7. Глоссарий 0.13.0→0.14.0: drift checker, structural fingerprint, mock-регрессия.
8. Манифест — `gen_manifest.py --write` последним.

## Open questions (оператору)

1. ADR-013 для D-нормы — нужен или SKILL.md/README достаточно?
2. Пункт AGENTS.md §1.7 (prose-contract review) — принимаем?
3. Частота live-e2e: только по запросу оператора, или напоминание при смене PROMPT_VERSION?

## Downgraded critical findings

Нет (все critical аргументированы failure mode + subject).

## References
review-architect.md, review-reliability.md, review-hcd.md, review-operations.md, review-compliance.md; предыстория: ../sess-translate-automation/consensus-doc.md
