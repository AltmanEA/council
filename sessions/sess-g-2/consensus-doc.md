# Consensus Document — sess-g-2

## Provenance

- **worktree-path:** `/home/ea/council-dev`
- **mode:** dev-dogfood
- **engine:** `draft@ec0caa7`
- **arbiter:** `v0.6.1@3d29792`
- **pin:** `draft-freeze-1` (= `ec0caa7`)
- **status:** completed
- **date:** 2026-11-24
- **session-number:** 2 of 3–5 in gate window G

## Pre-Phase 0 Record

- analyzer_enabled: false (META-TASK EXEMPTION — validating the classifier itself)
- self_assessed_complexity: moderate
- extended_roles: none (exempt)
- operator_decision: accepted (Core-only via exemption)

## Session Execution

Empirical run of the §Task Complexity Threshold classifier against 4 historical sessions:

| Session | D1 | D2 | D3 | D4 | Classifier | Actual | Match |
|---------|----|----|----|----|-----------|--------|-------|
| branch-version-strategy | mod | mod | mod | mod | Complex | medium | ✗ over |
| council-role-selection | simple | mod | simple | mod | Moderate | medium | ✓ |
| rehearsal-1 | simple | mod | simple | simple | Moderate | moderate | ✓ |
| rehearsal-2 (meta) | simple | simple | simple | simple | Simple→exempt | meta | ✓ |

## Findings (consolidated)

| # | Role | Severity | Finding | Subject |
|---|------|----------|---------|---------|
| F1 | Arch | medium | D2 (raw line count) dominates; padding inflates classification to Complex. Add D5: SUBJ-subject count as independent axis | SUBJ-001 |
| F2 | Rel | high* | Classifier manipulable: adversary fills task-brief with filler to force Complex (or strips to force Simple, skipping analyzer) | SUBJ-003 |
| F3 | Rel | medium | Meta-task exemption is operator-judgment-gated → abuse surface: mark everything meta to always skip analyzer | SUBJ-004 |
| F4 | HCD | low | D2 thresholds (50/200) lack worked examples; not scannable in ≤2 min manually | SUBJ-002 |
| F5 | Arch | low | Rule "2+ Moderate → Complex" fired on branch-version-strategy producing Complex for an actually-medium task | SUBJ-001 |

\* high finding F2 retains high (concrete manipulation vector named); none escalated to critical (no critical justification claimed).

## Role Statuses

| Role | Status |
|------|--------|
| Architect | concerns |
| Reliability & Security | concerns |
| Human-Centric Designer | agree (with F4) |

No blocked-escalation → **Conditionally resolved**.

## Decisions

- Classifier is EXECUTABLE end-to-end (4 cases run) — gate criterion «выполним на себе» met for this session.
- Empirical finding: D2 over-weights; recommend D5 axis (deferred to post-gate calibration, threshold.md §Calibration already anticipates this).
- Manipulability (F2) is a design limitation acknowledged by §Calibration; not a critical protocol defect (analyzer is advisory only, operator holds final decision per OP-1).

## Open Questions

1. Should a D5 (subject count) be added now or deferred to calibration? (F1)
2. Is meta-task exemption abuse worth a machine guard, or is OP-1 operator check sufficient? (F3)

## Critical findings downgraded

None.

## Escalations

None.

## Operator Note

Internal processing (subagents ECONNRESET). Empirical data collected from real historical briefs — this session exercised the draft's classifier against actual inputs, satisfying the «выполним на себе» gate requirement with evidence.
