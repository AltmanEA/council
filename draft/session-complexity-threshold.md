# Task Complexity Threshold

Version: 0.7.0-draft
Status: draft
Origin: consensus `sess-council-role-selection` (2026-11-23), action items №2–3
Abstraction: operational
changelog-path: CHANGELOGS/fallback-mode.changes.md

> `MODE: dev-dogfood/v2@<pin>` — ЧЕРНОВИК v2, объект обсуждения, НЕ регламент.

Determines when to launch the advisory Role Analyzer (§Pre-Phase 0 in `index.md`) versus proceeding directly with Core-only roles. This criterion prevents unnecessary overhead for simple tasks while ensuring complex ones get extended expertise.

---

## Simple vs Complex Classification

A task is classified by evaluating **all four** dimensions below. The default decision rule:

| # | Dimension | Simple | Moderate | Complex |
|---|-----------|--------|----------|---------|
| D1 | Input size (files referenced in task brief) | ≤ 3 files | 4–8 files | > 8 files |
| D2 | Total line count of input documents | ≤ 50 lines total | 51–200 lines total | > 200 lines total |
| D3 | Directory diversity | ≤ 2 directories | 3–5 directories | > 5 directories |
| D4 | Active role count (from task brief or analyzer estimate) | 1–3 roles active | 4–6 roles active | > 6 roles active |

**Classification rule:**

- If **all** four dimensions are Simple → class **Simple**. No analyzer needed. Skip to Phase 1.
- If **any** dimension is Moderate (and none Complex) → class **Moderate**. Auto-launch analyzer; operator can disable via flag.
- If **any** dimension is Complex OR two+ dimensions Moderate → class **Complex**. Mandatory analyzer with mandatory Extended roles.

## Implementation: Tool Support

The following tools may assist classification (advisory, not blocking):

- `tools/classify_bump.py` — computes input size metrics (files, lines, dirs).
- `tools/check_forward_port.py` — indirectly indicates scope cross-worktree involvement.

Tool output is advisory only. Operator overrides always take precedence.

## Fallback Mode Classification

In fallback mode (no Moderator, no tool automation), the operator performs classification manually using the checklist above. The checklist must appear at the top of every session workspace before any subagents are launched.

### Manual Checklist Template

```markdown
## Task Complexity Assessment (auto-generated or manual)

- [ ] D1: Files ≤ 3 → YES / NO
- [ ] D2: Lines ≤ 50 → YES / NO  
- [ ] D3: Directories ≤ 2 → YES / NO
- [ ] D4: Roles ≤ 3 → YES / NO

Classification: Simple / Moderate / Complex
Analyzer enabled: auto/yes/no (operator override)
Operator note: ...
```

## Meta-task Exemption

Per Operations Engineer position in `sess-council-role-selection`:

Meta-tasks (analyzing the procedure itself, dogfood gate sessions, process improvement reviews) should **NOT** trigger the role analyzer for Extended-roles unless explicitly required. Reasoning: recursive dependency — analyzing an analysis framework risks infinite regression in meta-evaluation loops.

Operator shall set `analyzer_enabled: false` for all meta-task sessions unless they concern concrete protocol-level changes (not procedural critique).

## Default Decision Rule

Unless operator explicitly sets `analyzer_enabled: true` or `false` in the task brief:

- **Simple** → `analyzer_enabled: false` (default)
- **Moderate** → `analyzer_enabled: true` (default, operator may reject)
- **Complex** → `analyzer_enabled: true` (mandatory unless operator explicitly disables with documented reason)

## Calibration

After 20–30 operational sessions, empirical calibration of thresholds is recommended:

1. Collect actual role activation patterns.
2. Measure correlation between classifier predictions and post-session effectiveness (did extended roles help?).
3. Adjust thresholds if false-positive rate > 20% or false-negative rate > 30%.

Report calibration results in a dedicated session (e.g., `sess-complexity-calibration-N`).
