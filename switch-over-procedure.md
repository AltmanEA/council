# Switch-Over Procedure (v1 → v2)

Status: active (pre-switch-over) · Owner: dev workspace (`council-dev/`, branch `v2-dev`)
Origin: consensus `sessions/sess-branch-version-strategy/consensus-doc.md`, 7-step procedure (Operations) + operator decisions №1–№4, 2026-11-23.
Advisory per OP-1: every check informs; the operator makes every go/stop/rollback decision in chat. No automated gating.

Executant legend: **[O]** — operator, **[A]** — agent, **[AO]** — agent executes, operator confirms result.

## Pre-conditions (шаг 0) — all must hold before step 1

| # | Check | Command / evidence | Hold condition |
|---|---|---|---|
| 0.1 | Feature freeze объявлен на `draft/` | последний commit в `draft/` — freeze-коммит; с этого момента `draft/` не меняется | [O] объявляет, фиксируется в чате |
| 0.2 | Gate пройден | `GATE VERDICT: PASS` в consensus-doc арбитра по `arbiter-gate-rules.md`, утверждён [O] | PASS + операторское approve |
| 0.3 | Нет in-flight сессий | `ls sessions/*/task-brief.md` vs наличие `consensus-doc.md` (оба workspace) | ни одной начатой незавершённой сверх маркированных incomplete |
| 0.4 | Движок синхронен | `python3 tools/check_engine_sync.py` | `engine-sync: OK` |
| 0.5 | Оба дерева чистые | `git status --short` (council/, council-dev/) | пусто (untracked sessions/archive допустимы) |

## Шаг 1 — Pre-flight [AO]

```bash
cp -a /home/ea/council-dev/sessions/ /home/ea/council/archive/sessions/council-dev-<DATE>/
```

- Обязателен **до** любых git-операций (сессии dev-worktree не все в git — без архива потеря доказательной базы).
- Незавершённые сессии (нет `consensus-doc.md`): добавить `status: incomplete` + archival-note в task-brief; НЕ блокировать процедуру (консенсус: «дождаться всех» нереализуемо).
- Успех: архив существует, количество каталогов совпадает.

## Шаг 2 — Forward-port / premise-shift аудит [A]

```bash
cd /home/ea/council && python3 tools/check_forward_port.py --base v1-stable --branch v2-dev --path fallback/
```

- **Пустой вывод = проход** (exit 0). Вывод = список нарушений (`MISSING-TRAILER` / `MISSING-CONTENT` / `BAD-PREMISE-SHIFT`) ⇒ стоп: доделать парные forward-port коммиты в `v2-dev` (трейлеры `backport-of: <sha>`, `premise-shift: none|affects=<session-id>`), повторить шаг.
- Аудит по содержимому, не только по трейлерам (консенсус R3/Reliability): добавленные строки фикса `fallback/` ищутся в `draft/` ветки `v2-dev`.
- Скрипт advisory (OP-1): non-zero смысла не имеет, всегда exit 0, кроме usage-error exit 2.

## Шаг 3 — Сверка engine-пинов [A]

- N = все сессии gate-окна + сессии после freeze в `council-dev/sessions/`.
- Для каждой: `engine:` пин из task-brief vs `git rev-parse v1-latest^{commit}` (для `draft@` пинов — vs freeze-коммит `draft/`).
- Допустимое несоответствие: задокументировано в consensus-doc + помечено [O]. Иначе ⇒ стоп.

## Шаг 4 — Merge [O]

```bash
cd /home/ea/council && git merge --no-ff v2-dev -m "merge: v2-dev -> master (switch-over v2.0.0)"
```

- Конфликты ожидаемы: `fallback/` (master) ↔ `draft/` (v2-dev). Разрешение — **v2-сторона**; не отпортированные фиксы (список шага 2) переносятся вручную ДО коммита merge.
- **4a [O]:** после merge — коммит-переименование `draft/ → fallback/` на master (см. «Открытые решения» Р1): имя `fallback/` восстанавливается как операционное, `tools/gen_engine.sh` (hardcode `fallback/`) и перекрёстные ссылки `docs/en/* → fallback/index.md` продолжают работать без правок.
- **4b [A]:** `python3 tools/check_all.py` — ожидаемо exit 0 после 4a (4 известных high-находки dev-worktree про отсутствующий `fallback/` на master не воспроизводятся).

## Шаг 5 — Release [O]

```bash
git tag -a v2.0.0 -m "v2.0.0: first operational v2 (switch-over)"
bash dist/build.sh              # exact-match guard: тег обязателен
bash dist/test-dry-run.sh       # однократно, зелёный
ls dist/out/council-dist-v2.0.0.tar.gz dist/out/SHA256SUMS
```

- Хосты обновляются по dist/RUNBOOK.md (install/update flow) только после зелёного dry-run.

## Шаг 6 — v1-maintenance [O]

```bash
git branch v1-maintenance v1-stable
```

- Назначение (консенсус): **аварийный указатель** — экстренный фикс v1 после go-live без `reset` магистрали. Обычное развитие — master (=v2). Не ветка долгой поддержки.

## Шаг 7 — Переключение [AO]

1. `fallback/index.md` (master, после 4a): баннер → «ОПЕРАЦИОННАЯ ВЕРСИЯ v2.0.0 — правки только по подтверждённым дефектам», `MODE: operational/v2.0.0`; Version: 2.0.0.
2. Root `AGENTS.md`: §1.8 переписывается из dev-роутера в операционный (master = единственный операционный источник v2; dev-worktree для v3-разработки в будущем — по той же схеме, v2-dev замораживается).
3. Якорь отката фиксируется ДО контрольной сессии: `git rev-parse HEAD` (после шага 5) записывается в consensus-файл процедуры.
4. **Контрольная сессия:** одна реальная операционная сессия на v2 из root, пины `engine: v2.0.0@<sha>`.
5. Провал контрольной сессии ⇒ **решение [O]** (OP-1): либо фикс точечным коммитом и повтор, либо откат (Appendix A). Автоматического revert нет.

## Appendix A — Rollback

- **Триггеры:** критический дефект v2 в контрольной сессии; бракованный релизный артефакт; подтверждённая невозможность работы по v2.
- **Решение и подтверждение:** только [O] в чате.
- **Команды:**
  ```bash
  cd /home/ea/council
  git reset --hard v1-stable            # зафиксированный якорь
  git tag -d v2.0.0 || true             # илиretain с пометкой в RUNBOOK
  # dist: откатить хосты на последний v1.0.x артефакт (SHA256SUMS)
  ```
- `v1-maintenance` остаётся; post-mortem — обычная сессия на восстановленном v1.

## Post-conditions

- `council-dev/` worktree сохраняется до закрытия post-go-live сессий; удаление — только после `cp -a sessions/ archive/sessions/...` (решение №2).
- Направление слияний после switch-over: `master(v2) → v1-maintenance` только экстренно; `v2-dev` архивна (якорь `v2-pre-dev`).
- Следующий цикл развития (v3) открывается новым consilium по той же схеме (worktree + якоря + draft/ + gate).

## Открытые решения (требуют явного approve [O] при исполнении)

- **Р1 (шаг 4a):** переименование `draft/ → fallback/` на master после merge — сохраняет имена для `gen_engine.sh` и `docs/en` ссылок; альтернатива «operational v2 lives in draft/» потребовала бы правки `gen_engine.sh --path` + 4 cross-ref в `docs/en` через Documentation Worker.
- **Р2 (шаг 3):** N сессий для сверки пинов = gate-окно + после-freeze (предложено); если [O] хочет фиксированное 5 — заменить.
