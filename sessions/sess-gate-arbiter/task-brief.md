# Task Brief — sess-gate-arbiter

> `MODE: dev-dogfood/arbiter` · движок v1 (locked Core)

## Overview / Why

Gate-сессия арбитра для окна G. По `arbiter-gate-rules.md` арбитр — одна сессия на движке v1, locked Core (Architect + Reliability&Security + Human-Centric Designer), без Extended-ролей, не редактирует `draft/`, выносит вердикт `GATE VERDICT: PASS|FAIL` + таблица статусов сессий окна + обоснование.

## Provenance

- **worktree-path:** `/home/ea/council-dev`
- **mode:** dev-dogfood/arbiter
- **engine:** `v0.6.1@3d29792` (v1-latest peel; generated at `/home/ea/council/.engine/3d29792`)
- **arbiter:** `v0.6.1@3d29792`
- **pin under gate:** `draft@ec0caa7` (= `draft-freeze-1`)
- **status:** (arbitration verdict recorded in consensus-doc)

## Arbiter Pre-Phase (locked Core)

- analyzer_enabled: **false** (arbiter is locked Core by rule 1; analyzer cannot alter Core, and Extended roles are forbidden for arbiter).
- core_locked: true — Architect, Reliability & Security, Human-Centric Designer.
- extended_roles: none (forbidden by arbiter-gate-rules rule 1).

## Session Goal

Вынести вердикт по окну G (3 completed-сессии на `draft@ec0caa7`) согласно arbiter-gate-rules rule 5/6/7.

## Input (window evidence)

| Session | engine pin | arbiter pin | MODE | status | consensus | critical-unclosed |
|---------|-----------|-------------|------|--------|-----------|-------------------|
| sess-g-1 | `draft@ec0caa7` ✓ | `v0.6.1@3d29792` ✓ | dev-dogfood ✓ | completed ✓ | present ✓ | 0 |
| sess-g-2 | `draft@ec0caa7` ✓ | `v0.6.1@3d29792` ✓ | dev-dogfood ✓ | completed ✓ | present ✓ | 0 |
| sess-g-3 | `draft@ec0caa7` ✓ | `v0.6.1@3d29792` ✓ | dev-dogfood ✓ | completed ✓ | present ✓ | 0 |

## Verification checks (rule-by-rule)

- **Rule 2 (вход, два пина + MODE):** all 3 have engine `draft@ec0caa7`, arbiter `v0.6.1@3d29792`, MODE `dev-dogfood`. PASS.
- **Rule 3 (единый пин):** all 3 on `ec0caa7`; `git rev-parse draft-freeze-1` = `ec0caa7`. No mid-window sha change. PASS.
- **Rule 4 (статусы):** all `completed` (consensus-doc + пины + MODE present). PASS.
- **Rule 5 (проход):** ≥3 completed on single pin = 3 ✓; zero unclosed critical findings ✓; draft executable on itself — each of G-1/G-2/G-3 ran Pre-Phase 0 + Phases 1–5 end-to-end without a draft-internal contradiction causing a session break ✓.
- **Rule 6 (провал):** no freeze violation (draft not edited in window — verify `git diff` clean); ≥3 completed; no critical protocol defect found by arbiter (high findings F1[G-1], F2[G-2], F1[G-3] are non-critical, OP-1 operator-in-loop absorbs).
- **Rule 7 (формат вердикта):** verdict section + status table + justification below.

## Subject List
- [P0] SUBJ-001: соответствие окна arbiter-gate-rules 1–7
- [P0] SUBJ-002: отсутствие незакрытых critical-находок
- [P1] SUBJ-003: выполнимость черновика на себе (gate criterion)

## Additional Context / Constraints
- Арбитр НЕ редактирует draft/ (rule 1). Находки high из окна — advisory, к оператору.
- OP-1: вердикт advisory, оператор утверждает.
- R-сессии (rehearsal-1/2) НЕ входят в счётчик (правило 6 R→G Guard).
