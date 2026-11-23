# Consensus Document — Tooling Separation

Session: sess-tooling-separation-2026-11-22
Mode: fallback (sequential subagents, operator as Moderator)
Date: 2026-11-22
Result: **Conditionally Resolved**
Roles: Architect (agree), Reliability & Security (concerns → условные, см. reservations), Human-Centric Designer (agree), Operations Engineer (agree)
Rounds: 2 (Phase 3 discussion complete)

---

## Decision

Разделение «разработки проекта» и «инструментов разработки» **признано целесообразным
только как двухуровневая модель**; плоская pinned-модель (инструменты как зафиксированный
дистрибутив и внутри исходного репозитория) **отклонена**.

**Уровень 1 — Source repo (Council):**
- `docs/` — project documents, под контролем Documenter (Write Rule, manifest).
- `tools/`, `dist/`, `defaults/`, `tests/` — implementation files (уже разделены в
  AGENTS.md §1.6), редактируются **напрямую (edit-in-place)**, коммит в тот же
  репозиторий, hotfix = один коммит. Никакого pinning и lock-файлов для внутренних
  инструментов.

**Уровень 2 — Downstream (хост-проекты):**
- `dist/` — единственный канал дистрибуции: `build.sh` → архив → `install.sh`/`update.sh`.
  Здесь и только здесь инструменты существуют как зафиксированный набор из дистрибутива
  (pinned snapshot через `core-manifest.txt`).
- Lock-файлы — **только внешним зависимостям** с независимым жизненным циклом
  (прецедент: `defaults/translation.lock`, ADR-014). Lock для внутреннего кода —
  антипаттерн.
- Dist maintainer — сам оператор (шаг 5 approve документа циcla), без введения новой роли.

Формулировка AGENTS.md §1.6 признана достаточной; требуется лишь уточнение
позиционирования (см. Action Items).

## Rationale

1. Граница «проект vs инструменты» уже существует (§1.6) и dist/ уже реализует
   core-vs-templates; новое разделение внутри source repo добавило бы уровень
   версионирования без пользы и создало бы обратную зависимость «проект знает о версии
   инструментов» (Architect, SUBJ-001/005).
2. Pinning внутренних инструментов нарушил бы OP-1/OP-2 для единственного оператора:
   hotfix из «одного коммита» превращается в цикл «сборка → архив → обновление»,
   а дефектный pinned-инструмент становится замороженным (Reliability critical #2,
   HCD high; снято разведением уровней — в source repo hotfix остаётся коммитом).
3. Прецедент фиксации (translation.lock) оправдан именно внешностью зависимости;
   перенос той же механики на внутренний код размывает источник истины (HCD).
4. Для downstream-хостов pinned-модель, напротив, уместна — и она уже реализована
   каналом dist/ (Ops).

## Subjects — Outcomes

| Subject | Outcome |
|---------|---------|
| SUBJ-001 — границы разделения | Agreed: двухуровневая модель; source repo — edit-in-place, без pinning |
| SUBJ-002 — модель фиксации | Agreed: pinning только downstream (dist/); lock-файлы только внешним зависимостям |
| SUBJ-003 — влияние на контракты | Agreed: §1.6 достаточна при уточнении позиционирования; Write Rule и prose-contract synchronization (§1.7) не меняются |
| SUBJ-004 — обновление и drift | Conditionally agreed: dist maintainer = оператор; downstream-интегрити — backlog (см. reservations) |
| SUBJ-005 — общая целесообразность | Agreed: целесообразна двухуровневая модель; плоская pinned-модель отклонена как нарушение OP-2 |

## Role Reservations (условия «conditionally»)

От Reliability & Security (SUBJ-003/004/005, привязаны к downstream-эксплуатации):
- [critical→backlog] `build.sh` (`tar czf`) не генерирует checksum, `update.sh`
  (`tar xzf`) не проверяет целостность — transfer-канал не верифицирован.
  Консенсус: **генерация `SHA256SUMS` в build.sh — сделать сейчас** (одна команда,
  защищает от corruption); **проверка хеша в update.sh — backlog** до появления
  внешнего хоста.
- [critical→backlog] Нет patch/micro-release механизма для downstream hotfix;
  emergency edit-in-place на хосте — откат к не-pinned. Консенсус (Ops): для одного
  оператора приемлемо (OP-1), semver/patch-релизы — при >1 хосте.
- [high→backlog] `build.sh` не верифицирует вход (compile/smoke по `tools/` перед
  упаковкой). Консенсус: advisory-подход + OP-3 достаточны сейчас.
- [medium, не оспорено] `defaults/policy.yaml` содержит ссылки на удалённые v0.x
  концепции Documenter — чистка как отдельный inline-fix вне рамок данного решения.

## Action Items

Сейчас (мелкие, в одном changeset при одобрении оператора):
1. `dist/README.md` / `AGENTS.md` §1.7: зафиксировать двухуровневую модель —
   «tools/ в source repo — edit-in-place, lock не требуется; dist/ — единственный
   downstream-канал; lock-файлы только внешним зависимостям» (уточнение, не новая механика).
2. `dist/build.sh`: генерация `SHA256SUMS` рядом с архивом.
3. Документировать dist lifecycle одним параграфом: `git commit → build.sh →
   council-dist-VERSION.tar.gz → copy → update.sh`.

Backlog (триггер — появление первого внешнего downstream-хоста):
4. Проверка sha256 в `update.sh` (optional flag); GPG — опционально.
5. Emergency hotfix-процедура downstream (edit-in-place поверх pinned с фиксацией отхода от pin).
6. Advisory `check_core_drift.py` (pinned core vs source).
7. Semver для dist/ (блокирующие обновления, changelog per release) — при >1 хосте.
8. Очистка `defaults/policy.yaml` от stale v0.x ключей.

## Open Questions (к оператору)

1. Подтверждён ли план использования Council как фреймворка в других проектах
   (внешние downstream-хосты)? От этого зависит, переводить ли backlog-пункты 4–7
   в текущую работу.
2. Кто, кроме оператора, может получать архивы dist/ (доверенный канал передачи)?

## Escalations

Не было. Ни одна роль не объявляла blocked-in-scope / blocked-escalation.

## Downgraded Critical Findings (transparency)

Критические находки Reliability (подмена дистрибутива, frozen defect) сохранены с
обоснованием; переклассифицированы консенсусом из «blocker» в «backlog/сейчас-частично»
на основании довода Ops: single-operator, build и install на одной машине, атакуемая
поверхностьtransfer-канала отсутствует до появления внешних хостов.

## References

- Раунд 1: `review-architect-round1.md`, `review-reliability-round1.md`,
  `review-human-centric-round1.md`, `review-operations-round1.md`
- Раунд 2: `discussion-round-1.md`
- Бриф: `task-brief.md`
- Основания в репозитории: AGENTS.md §1.5–1.7, `dist/README.md`, `tools/README.md`,
  `defaults/translation.lock` (ADR-014)
