# Rehearsal → Gate Plan (двухэтапный протокол dogfood-окон)

Version: 1.0.0
Status: active (execution pending operator start)
Owner: operator; исполняет agent-оператор сессии
Anchors: consensus `sess-branch-version-strategy` (`/home/ea/council/sessions/sess-branch-version-strategy/consensus-doc.md`), `arbiter-gate-rules.md`, `switch-over-procedure.md`
changelog-path: none (implementation file, outside Documenter scope per AGENTS.md §1.6)

## Зачем

`draft/` содержательно пока == операционный `fallback/` v1 (отличается только
баннерами: `index.md` 6+/5−, три файла по 1+1−, коммит `178e63a`). Freeze и
gate на таком пине дали бы формальный PASS без покрытия v2 (решение №3
консенсуса требует: v2 уходит в production, проверенный на **собственных**
правилах). Поэтому — два этапа: репетиция механизма на пустом черновике,
настоящий gate на содержательном.

## Схема

```
Этап R (репетиция)                          Этап G (настоящий gate)
draft@15c5a1e                               draft@<B> (после v2-контента)
  │ правок в draft/ нет ──► окно 2–3 сессии  │ freeze ──► окно 3–5 сессий
  │ + gate-сессия арбитра                    │ + gate-сессия арбитра
  ▼                                          ▼
consensus-doc: purpose: rehearsal            GATE VERDICT: PASS ──► switch-over
  -- NOT a switch-over gate                  (по switch-over-procedure.md, 7 шагов)
```

## Пинов (разрешённые значения, никогда алиасы)

| Объект | Пин | Разрешение |
|---|---|---|
| Движок этапа R | `engine: draft@15c5a1e` | HEAD `v2-dev` на момент плана; advisory-тег `draft-rehearsal-1` |
| Арбитр (оба этапа) | `arbiter: v0.6.1@3d29792` | `v1-latest`/`v1-stable` peel = `3d29792` |
| Движок этапа G | `engine: draft@<B>` | новый коммит с содержательными правками `draft/`, тег `draft-freeze-1` |

Если до старта R появятся новые коммиты в `v2-dev`, тронувшие `draft/`, —
перезапинить R на новый HEAD и обновить таблицу (сдвиг между окнами свободен).

## Правила (чтобы R не подменил G)

1. Разные теги: `draft-rehearsal-<N>` / `draft-freeze-<N>`. Не смешивать.
2. Каждый consensus-doc этапа R: строка `purpose: rehearsal — not a switch-over gate`.
3. Арбитр репетиционной gate-сессии: вердикт `ADVISORY PASS/FAIL`, не `PASS`.
4. Пин G ≠ пин R: обязателен коммит с содержательными правками `draft/`
   (не баннеры). Если к моменту G черновик не изменился — G не запускается.
5. Находки R правятся в `arbiter-gate-rules.md` / `switch-over-procedure.md`
   / этом плане **до** freeze G (это не `draft/`, на пин не влияет).
6. Сессии R не входят в счётчик «3–5 completed» окна G (правило 3 арбитра:
   единый пин окна).
7. Правка `draft/` внутри активного окна = FAIL этого окна, новое окно,
   счётчик не переносится (правило 3/6 арбитра).

## Чеклист исполнения (для новой сессии)

### П.0 Подготовка (agent-оператор, ~5 мин)
- [ ] `cd /home/ea/council-dev && git tag -a draft-rehearsal-1 15c5a1e -m "rehearsal pin — NOT a switch-over gate"`
- [ ] Секция «Rehearsal mode» в `switch-over-procedure.md` (5–6 строк: теги,
      пометка purpose, ADVISORY-вердикт) — коммит в `v2-dev`.
- [ ] Смоук старт-чеклиста: `cd /home/ea/council && bash tools/gen_engine.sh v1-latest`
      (для арбитр-сессии) и генерация движка из `draft`-пина;
      `python3 tools/check_engine_sync.py …` → OK;
      `python3 tools/check_forward_port.py --base v1-stable --source HEAD --path fallback/ --branch v2-dev --against draft/` → пустой вывод.

### П.1–П.3 Репетиционное окно (2–3 сессии)
Каждая сессия:
- [ ] Каталог `council-dev/sessions/sess-rehearsal-<N>/` с `task-brief.md` +
      `consensus-doc.md` (трекаются; `cp -a sessions/` перед удалением worktree).
- [ ] Шапка брифа: `MODE: dev-dogfood/rehearsal`, `engine: draft@15c5a1e`,
      `arbiter: v0.6.1@3d29792`, `purpose: rehearsal — not a switch-over gate`.
- [ ] Старт по чеклисту dev-режима (генерация движка из пина, sync-проверка).
- [ ] Задача сессии — не протокол, а обкатка: формат брифа, фазы, роли,
      фиксация находок **о самой процедуре** в consensus-doc.
- [ ] По завершении: статус `completed` (или `invalid` с причиной).

### П.4 Репетиционная gate-сессия арбитра
- [ ] Одна сессия на движке v1 (`arbiter: v0.6.1@3d29792`), locked Core,
      вход — completed-сессии окна R со всеми пинами.
- [ ] Вердикт-секция: `GATE VERDICT: ADVISORY PASS` / `ADVISORY FAIL`
      + список находок процедуры.
- [ ] Находки → правки `arbiter-gate-rules.md`/`switch-over-procedure.md`/плана (коммиты `v2-dev`).

### П.5 Контент для этапа G (параллельно)
Кандидаты содержательных правок `draft/` (оба прямо про регламент, из
консенсуса `sess-council-role-selection`):
- [ ] контракт анализатора ролей (advisory-роль: вход/выход/триггеры);
- [ ] порог сложности (критерии выбора расширенного состава).
Порядок: консилиум-сессии (dogfood-режимом допустимо) → решение оператора →
коммит(ы) в `draft/` вне окна.

### П.6 Freeze G + настоящее окно
- [ ] `git tag -a draft-freeze-1 <B>` (B — коммит с v2-контентом `draft/`);
- [ ] окно 3–5 completed-сессий, единый `engine: draft@<B>`, без purpose-пометки;
- [ ] gate-сессия арбитра → `GATE VERDICT: PASS` ⇒ переход к
      `switch-over-procedure.md` (7 шагов; открытые решения Р1 `draft/→fallback/`
      при merge и Р2 окно сверки пинов — approve оператора при исполнении).

## После switch-over

Операционные сессии пинят `engine: v2.x.y@<sha>` (семантические релизы);
арбитражный пин сдвигается с хотфиксами v1 (`v1.0.x@sha`).
