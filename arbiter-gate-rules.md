# Arbiter Gate Rules

Status: active (pre-switch-over) · Owner: dev workspace (`council-dev/`, branch `v2-dev`)
Origin: consensus `sessions/sess-branch-version-strategy/consensus-doc.md`, operator decision №3 (C, two-pin contract), 2026-11-23.
Scope: acceptance criteria for the dogfood gate (3–5 sessions after feature freeze) preceding v2 go-live. Advisory per OP-1: the arbiter issues a verdict, the operator approves it.

**Правила арбитра gate** (полномочия — только вердикт, не правки):

1. **Состав:** арбитр — одна сессия на движке v1 (`arbiter: <semver>@<sha>`, разрешённое значение, без алиасов), locked Core (Architect + Reliability&Security + Human-Centric Designer), без Extended-ролей; арбитр не редактирует `draft/`.
2. **Вход:** gate-окно = 3–5 сессий после feature freeze; каждая обязана иметь `task-brief.md` + `consensus-doc.md` с **двумя пинами** в шапке (`engine: draft@<sha>`, `arbiter: <semver>@<sha>`) и канонической строкой `MODE: dev-dogfood/...`. Отсутствие артефакта или пина ⇒ сессия не засчитывается.
3. **Единый пин:** все сессии окна идут по одному и тому же `draft@<sha>`; смена sha черновика внутри окна ⇒ gate **FAIL**, окно перезапускается.
4. **Статусы сессий:** `completed` (consensus-doc + пины + MODE) — засчитывается; `aborted` (без consensus-doc) — не засчитывается, требует перезапуска; `premise-drift` — засчитывается только с операторской пометкой; `invalid` (черновик правился во время сессии от Фазы 1 до consensus-doc) — засчитывается как провал.
5. **Проход gate:** ≥3 сессии `completed` на едином пине, ноль незакрытых critical-находок ролей арбитра, черновик выполним на себе (ни одна сессия окна не сорвалась по причине противоречия в самом черновике).
6. **Провал gate:** любое нарушение заморозки, <3 completed, critical-дефект протокола, найденный арбитром. Провал ⇒ фикс отдельным approved-коммитом, заморозка заново, **новое окно** (счётчик не переносится).
7. **Формат вердикта:** в consensus-doc арбитра — секция `GATE VERDICT: PASS|FAIL` + таблица статусов сессий окна + обоснование; этот документ — основание для go-live шага switch-over. Оператор утверждает вердикт (OP-1, без гейтинга).
