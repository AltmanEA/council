# Task Brief — sess-rehearsal-2

## Overview / Why

Dogfood gate = two-phase rehearsal before v2 switch-over.
- **Phase R (rehearsal):** test the procedure itself on a frozen empty draft. 2–3 sessions.
- **Phase G (gate):** after content changes to draft/, freeze + 3–5 sessions + arbiter verdict PASS → switch-over.

This session continues Phase R testing. We are NOT doing a switch-over.

## Provenance

- **worktree-path:** `/home/ea/council-dev`
- **mode:** dev-dogfood / rehearsal
- **engine:** `draft@15c5a1e`
- **arbiter:** `v0.6.1@3d29792`
- **purpose:** rehearsal — not a switch-over gate
- **pin:** `draft-rehearsal-1` (= `15c5a1e`)
- **session-number:** 2 of N in rehearsal window

## Session Goal

Провести вторую репетиционную сессию на том же пине, проверяя:
1. Улучшился ли бриф по сравнению с R1?
2. Как работает процесс consolidation между ролями при internal-processing fallback?
3. Фиксация находок о процедуре в consensus-doc (включая meta-evaluation).

## Focus Areas

- Работа с улучшенным брифом (added Purpose section, simplified structure).
- Внутренняя обработка ролей (fallback mode): воспроизводимость результатов.
- Проверка usability consensus-doc format.
- Выявление new friction points не найденных в R1.
- Оценка readiness для gate-arbiter (П.4).

## Quick Reference — R→G Guard Rules (condensed)

1. Different tags: `draft-rehearsal-N` / `draft-freeze-N`. Never mix.
2. Each R consensus-doc MUST contain: `purpose: rehearsal — not a switch-over gate`.
3. Arbitrator verdict at rehearsal: `ADVISORY PASS/FAIL`, never `PASS`.
4. G pin ≠ R pin: requires content commits in `draft/` (not banners only).
5. Findings from R are fixed in rules/procedures BEFORE freeze G (not in draft/).
6. R sessions don't count toward the "3–5 completed" G window.
7. Draft edit during active window = FAIL this window, new window starts.

## Expected Output

- Each role produces: 3–5 findings, 2–3 recommendations, 1–2 open questions.
- If output exceeds limits: prioritize structural issues > integration > detail.

## Subject List

- [P0] SUBJ-001: Is the improved task-brief easier to follow vs R1? Where does friction remain?
- [P0] SUBJ-002: Internal processing reproducibility — can we trust agent-produced findings without subagent isolation?
- [P1] SUBJ-003: Consensus-doc structure — is it readable and actionable for the next step (arbitration)?
- [P1] SUBJ-004: Gate readiness assessment — what must be fixed before launching П.4 (arbiter gate session)?
- [P2] SUBJ-005: Pin governance — should pins get immutability guarantees (tags, hooks)?
- [P2] SUBJ-006: Navigation/index gap — one-pager or overview doc to replace reading 3+ files?
