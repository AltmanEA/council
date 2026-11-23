# Consensus Document — First External Host Launch

Session: sess-first-host-launch-2026-11-22
Mode: fallback (sequential subagents, operator as Moderator)
Date: 2026-11-22
Result: **Resolved**
Roles: Architect (agree), Reliability & Security (concerns → agree), Human-Centric (concerns → agree), Operations (agree с reservations → сняты)
Rounds: 1 полный + 1 целевой разрешающий
Predecessor: sess-tooling-separation-2026-11-22

---

## Decision

Определён минимально достаточный DoD для запуска первого внешнего хоста через канал
`dist/`. Перестройка канала не требуется (OP-2); набор — локальные правки скриптов,
один новый smoke-скрипт, runbook и одна чистка.

### До запуска первого хоста (must-have)

1. **SHA256SUMS при сборке** (`dist/build.sh`): генерация `SHA256SUMS` рядом с архивом
   единым шагом с `tar czf` — оператор не может «забыть» чексумму. (SUBJ-013)
2. **Авто-проверка хеша при обновлении** (`dist/update.sh`): при наличии `SHA256SUMS`
   рядом с архивом проверка `sha256sum -c` выполняется автоматически, без флага
   (оператору не надо помнить). GPG — не требуется при доверенном канале единственного
   оператора; триггер GPG — публичный URL-канал. (SUBJ-013)
3. **Политика версии вместо «dev»** (`dist/build.sh`): `git describe --tags` без
   `--always`; при неудаче — предупреждение и префикс `dev-` в VERSION (визуальный
   сигнал вместо hard abort — тестовые сборки не ломаются). В `dist/README.md` —
   раздел «Releasing»: `git tag → build.sh → copy → update.sh`. (SUBJ-012)
4. **Безопасное удаление core-файлов** (`dist/update.sh`): перед каждым `[removed]` —
   предупреждение с backup-путем. (Решение оператора: core-файлы на хосте не
   правятся → `.council/customizations.txt` исключён из must-have, перенесён в
   backlog.) (SUBJ-013)
5. **Явные сигналы оператору хоста** (`dist/install.sh`/`update.sh`): отсутствие
   PyYAML → ERROR для core-инструментов в update.sh, WARNING в install.sh; явное
   подтверждение режима: «Installing in OVERLAY mode — existing files will NOT be
   overwritten». (SUBJ-014, SUBJ-015)
6. **Runbook** (`dist/RUNBOOK.md`, новый файл): выбор init vs overlay (чек-лист),
   установка, hooks после install, update, откат из `.council/backup-*`, emergency
   («сломанный core-файл → restore → edit-in-place → commit как отход от pinned»),
   «`.env` переводчика опционален», проверка версии `cat .council/version.lock`.
   (SUBJ-015)
7. **Smoke-скрипт** (`dist/test-dry-run.sh`, новый файл): init → update → restore →
   overlay, exit 0/1. Запуск — один раз до первого реального хоста (не pre-commit).
   (SUBJ-015)
8. **Чистка `defaults/policy.yaml`**: удалить stale v0.x Documenter ключи
   (`audit_freshness`, `trust_floor_safe_changes`, `approval_expiry_window`,
   `rescan_batch_ceiling`) — до tag первого релиза. (SUBJ-014)

### После первого хоста (backlog с триггерами)

| Пункт | Триггер |
|-------|---------|
| `check_core_drift.py` (манифест vs source, advisory) | первый успешный `update.sh` |
| Semver-политика dist/ | первый релиз (tag v1.0.0+) / >1 хост |
| Отдельная emergency hotfix-механика | >1 хост (сейчас покрыто RUNBOOK) |
| GPG-подпись архивов | публичный канал передачи |
| `--skip-vendor` / опциональность translation | запрос хоста без EN→RU |

## Rationale

- Триггер «первый внешний хост» наступил (оператор подтвердил планы) — backlog-пункты
  прошлой сессии с этим триггером переведены в must-have: SHA256SUMS (было «сейчас»),
  проверка хеша (было backlog).
- Критический сценарий Reliability (corruption/substitution при SCP/USB, `tar xzf` без
  проверки) закрывается пунктами 1–2 минимальной ценой (по строке в скрипте); GPG
  отклонён как избыточный при единственном операторе и доверенном канале.
- Сценарий «замороженный дефектный инструмент» для первого хоста закрывается связкой
  backup + restore + RUNBOOK + smoke-прогон, без новой механики (OP-2).
- Hard abort при безтеговом build отклонён (сломал бы тестовые прогоны); префикс
  `dev-` даёт сигнал без блокировки — консенсус Reliability и Ops.
- Детекция кастомизаций через `.council/customizations.txt`: git-индекс хоста
  ненадёжен (install.sh сам делает `git init`, коммиты оператора позже), молчаливый
  warning = потеря данных.

## Subjects — Outcomes

| Subject | Outcome |
|---------|---------|
| SUBJ-011 — состав DoD | Agreed: 8 must-have, 5 backlog с триггерами |
| SUBJ-012 — версионирование/релизный цикл | Agreed: префикс `dev-` вместо «dev», раздел «Releasing», version.lock виден в выводе; semver отложен |
| SUBJ-013 — целостность канала | Agreed: SHA256SUMS единым шагом, авто-проверка, предупреждения при удалениях + customizations.txt |
| SUBJ-014 — конфигурация периферии | Agreed: PyYAML ERROR в update.sh; .env опционален (документировать); vendor без --skip-vendor до запроса; policy.yaml чистка до tag |
| SUBJ-015 — тестирование и запуск | Agreed: RUNBOOK.md + smoke-скрипт до хоста; emergency покрыт backup/restore процедурой |

## Role Reservations

- **Reliability (условия, учтены в must-have):** SHA256SUMS обязан генерироваться
  единым шагом с архивом (иначе B-02: оператор забывает — проверка молча пропускается);
  `dev-` префикс обязателен как визуальный сигнал.
- **Operations:** smoke-скрипт однократный до хоста, не pre-commit (иначе overhead);
  R2 (--safe-remove) и R3 (smoke) остаются блокираторами до их реализации — сняты
  включением в must-have.
- **HCD (осознанный компромисс, не дефект):** оператор хоста — не-техническая роль;
  проактивного предупреждения «что-то пошло не так» нет — покрывается дисциплиной
  «прочитал RUNBOOK → применил»; авто-обновление сознательно НЕ делается (риск).
  Осведомлённость о версиях (MVP-политика): ручная проверка — блок «Update complete»,
  `cat .council/version.lock`, changelog source repo; без подписки/push. Прокладка —
  Code-based Moderator (будущее).

## Open Questions — закрыты оператором (2026-11-22)

1. **Перевод первому хосту нужен.** `vendor/techdoc-translator` ставится штатно,
   `.env` настраивается по `.env.example`. В RUNBOOK: не «.env опционален», а
   «перевод используется — настройте .env». `--skip-vendor` остаётся в backlog.
2. **Файлы Консилиума на хосте не правятся** (решение оператора). Следствие:
   `.council/customizations.txt` **исключается из must-have** — остаётся только
   предупреждение с backup-путем перед каждым `[removed]` (п.4 in-place).
   customizations.txt → backlog (при изменении практики).
3. **Первый релиз: тег `v0.1.0`** — точка отсчёта pinned-канала.

## Escalations

Не было.

## Downgraded Critical Findings (transparency)

- Reliability R3 «abort при отсутствии тега» → понижено консенсусом до предупреждения
  с `dev-` префиксом (довод Ops/Architect: ломает тестовые прогоны; OP-2).
- Reliability GPG-подпись → в backlog с триггером «публичный канал» (довод: единственный
  оператор, доверенный transfer).
- HCD «аннотация в version.lock», «skip-remove list», «summary-карточка» → отклонены
  консенсусом как дублирование существующих выводов (решения Reliability/Ops).

## References

- Round 1: `review-architect-round1.md`, `review-reliability-round1.md`,
  `review-human-centric-round1.md`, `review-operations-round1.md`
- Resolution round: `discussion-round-1.md`
- Бриф: `task-brief.md`; предшественник: `../sess-tooling-separation-2026-11-22/consensus-doc.md`
- Основания: `dist/build.sh`, `dist/install.sh`, `dist/update.sh`, `dist/README.md`,
  `tools/sync_translator.sh` (прецедент верифицированного цикла), AGENTS.md §1.5–1.7
