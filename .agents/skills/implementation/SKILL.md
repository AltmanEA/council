---
name: implementation
description: When a task requires writing or changing program code for a project element — new module, tool, or tests under tools/, documenter_service/ (Tier 0-1), or tests/. Runs an orchestrated sequential TDD subagent cycle (test author → code author → test runner → analyst) with worktree isolation, deterministic verification, and escalation to the operator after three unsuccessful iterations. Do NOT use for documentation, config, typo fixes, or changes of 2 files / 50 lines or less.
metadata:
  version: "1.0.1"
---

# Implementation Worker

## Overview

You are an **Implementation Worker** — an orchestration skill that produces program code for project elements via a sequential TDD cycle of four subagents running on the local model, while the primary agent (you) retains all control decisions: prompt refinement, verdict acceptance, merging, and escalation. You are NOT the Documentation Worker: any change touching `docs/`, `docs-manifest.yaml`, or `CHANGELOGS/` is out of scope and must be routed to `skill("documentation")`.

You never write target code yourself. Subagents write code; you orchestrate, verify deterministically, and merge. Subagents run through the `subagent` tool with `agent=general` and the local model `freetoken/Qwen3.6-35B-A3B-NVFP4` (one concurrent local subagent — the pipeline is strictly sequential, never parallel).

This is a long-running process: a full cycle of 4 phases × 3 iterations ≈ 12 subagent invocations, roughly 20–30 minutes on the local model. Warn the operator before starting if the estimated scope exceeds 10 minutes.

---

## Activation

Activate only when the operator explicitly asks to implement a programmatic element of the project, AND the activation matrix holds:

| Class | Criteria | Call skill |
|---|---|---|
| Trivial | ≤ 2 files or ≤ 50 lines of expected diff; typos; logging; config values; documentation | **NO** — do the work directly |
| Moderate | 1–3 new files; the target module already has tests under `tests/` | YES |
| Complex | > 3 files or new modules; or the target module has no existing tests | YES |

### When NOT to call

- Any edit to `docs/`, `docs-manifest.yaml`, `CHANGELOGS/` → use the `documentation` skill (Write Rule, `AGENTS.md` §2).
- Fixes of `fallback/`, `AGENTS.md`, `.opencode/`, `defaults/`, `archive/`, `.agents/skills/documentation/` → forbidden (see §Governance Gates); require explicit operator handling.
- Tier 2+ Documenter functionality (write branch, registry activation, Operator Surface) → dormant per ADR-013; escalate, do not implement.
- One-line or cosmetic changes; the cycle's cost is unjustified.

### Pre-gate (mandatory before cycle start)

1. Compose a **target task** and write it to the cycle workspace: goal, acceptance criteria, target files, allowed paths, test command.
2. Confirm the target areas are within the operator-approved default whitelist: **new files** under `tools/`, `documenter_service/` (Tier 0–1 only, ADR-011), and `tests/` (new `test_*.py`). Existing files are writable **only if the operator listed them explicitly in the task**.
3. Static ADR-011/013 check: if the task references Tier 2+ surface (`write_handler`, registry activation, `OperatorSurface`, changes to `documenter_policy.yml`), STOP — escalate to the operator, do not start the cycle.

---

## Cycle Workspace and Isolation

Each cycle gets an isolated **git worktree** — subagents write only inside it, never in the main working tree:

- Create: `tools.opencode.worktree_create({name: "impl-run-<run-id>"})` where `run-id = <YYYY-MM-DDTHH-mm>-<seq>`.
- All four subagent phases run with the worktree as working directory.
- Cycle artifacts live in `sessions/<session-id>/impl-run-<run-id>/`:
  - `target-task.md` — the operator-approved task
  - `cycle-state.json` — checkpoint + progress record (updated after every phase)
  - `artifacts/` — per-phase outputs (`test-files.json`, `code-files.json`, `test-output-<n>.txt`, `test-results.json`, `verdict.json`)
  - `prompts/` — every subagent prompt actually used, versioned (`prompt-<role>-v<n>.md`)
- Merge is performed by **you** (the primary agent), only after a verified pass: inspect `git diff` in the worktree, apply only whitelisted paths to the repository, then `tools.opencode.worktree_remove()`. Merge without diff review is prohibited. Subagents never commit and never touch the main tree.

Machine-readable contracts (schemas in `helpers/`): `cycle-state.json` per `helpers/cycle-state.schema.json`, `verdict.json` per `helpers/verdict.schema.json`. Subagents receive the relevant role prompt from `roles/` plus the current `cycle-state.json` and prior artifacts by path. Free-text is never a phase interface — every handoff is a JSON file.

---

## The Pipeline (sequential, one subagent at a time)

### Phase 1 — Test Author (`roles/test-author.md`)

Writes tests for the target task **before** any implementation.

- Writes NEW test files under `tests/` (never modifies existing `test_*.py` unless the task lists them).
- Framework detection is mandatory: this repository uses **unittest** (`python3 -m unittest tests.<module> -v`), not pytest. Detect via `import unittest` / `import pytest` in `tests/*.py`; default to unittest.
- **Anti-reversed-TDD baseline:** immediately after writing, the tests are run against the CURRENT (pre-implementation) code. Expected: new tests fail. If they pass without implementation, the tests assert nothing — the Analyst will flag this and the Test Author prompt is refined.
- Output: `artifacts/test-files.json` (list of created files + intended test command).

### Phase 2 — Code Author (`roles/code-author.md`)

Writes the implementation satisfying the tests.

- Writable paths = target-task whitelist only (see Pre-gate). All other paths are read-only.- Must read `artifacts/test-files.json` and the new test files; must not modify them.
- Output: `artifacts/code-files.json` (created/modified files, key signatures exported).

### Phase 3 — Test Runner (`roles/test-runner.md`)

Executes tests, collects raw evidence. Interprets nothing.

- Discovers modules: `ls tests/test_*.py`; runs `python3 -m unittest tests.<module> -v` per relevant module (no `discover`).
- Output: `artifacts/test-output-<n>.txt` (verbatim) + `artifacts/test-results.json` (`exit_code`, `passed`, `failed`, `errors`, `collection_error`).
- Cleans `__pycache__` / temp artifacts it produced.

### Phase 4 — Analyst (two-level) (`roles/analyst.md`)

- **Level 0 (script, not LLM):** `exit_code == 0`; pass-count grew versus previous iteration; grep check that code-files.json signatures exist in the produced files; diff-path check (see Governance Gates). This level is deterministic and authoritative for `pass`.
- **Level 1 (LLM, only if Level 0 failed):** diagnoses causes, formulates hypotheses and `next_steps`; NEVER issues `pass`.
- Output: `artifacts/verdict.json` — `pass`, `progress` (`improving|stalled|regressing`), `reasons`, `next_steps`, `critical_blocker`.
- `progress` is computed deterministically, not by LLM opinion: pass-count strictly increased → `improving`; worktree diff identical to previous iteration → `stalled`; otherwise no improvement for ≥ 2 consecutive iterations → `regressing`.

---

## Outer Loop (primary agent)

After each full cycle:

1. Read `verdict.json` + `test-results.json`. Update `cycle-state.json` (`iteration`, `fail_count`, `progress`, prompt version references).
2. **pass (Level 0)** → diff-review and merge whitelisted files, then **re-run the target tests in the main working tree** — a green verdict inside the worktree is not sufficient: environment-dependent tests (CWD, existing repo data) may only fail post-merge. Green in both trees → archive artifacts, report to operator; failure in the main tree → roll back the merged files and treat as an iteration (refine prompts, count `fail_count`). Final acceptance of functionality always belongs to the operator.
3. **not pass** → refine prompts per policy:
   - `improving` → refine only the failing role's `constraints` section; do NOT increment `fail_count`.
   - `stalled` → rework that role's `context` (feed it the Analyst's hypotheses and the failing test names).
   - `regressing` → consider re-scoping: the task statement itself may be ambiguous; state your reasoning before relaunching.
   - Increment `fail_count` for `stalled`/`regressing` iterations.
4. Save each refined prompt under `prompts/` with a new version — never silently reuse an unchanged prompt for a second iteration (a retry with identical prompt is invalid).

### Escalation to operator

Escalate when ANY holds:

- `fail_count >= 3` (three iterations without `improving`);
- `verdict.critical_blocker == true`;
- hard timeout 20 minutes total cycle time;
- governance stop (`BLOCKED_GOVERNANCE`).

Escalation payload (`escalation-payload.md` in the cycle workspace, mandatory sections): stop reason `TIMEOUT | GOVERNANCE | MAX_ITERATIONS | CRITICAL_BLOCKER`; per-iteration verdicts; diff of target code; last 3 test outputs; all prompt versions used; Analyst hypotheses; checksums of target files. Present it to the operator and STOP — do not start a fourth cycle on your own.

### Operator controls

- **Early acceptance:** if the operator says the current implementation is sufficient, write `operator-approve` in the cycle workspace, set `status: "operator-approved"`, merge after diff-review.
- **Checkpoint recovery:** on restart, if `cycle-state.json` shows an unfinished `run_id`, resume at `phase` recorded there — do not restart from scratch.

---

## Governance Gates

Enforced BEFORE merge and at every phase boundary; violation → immediate stop with verdict `BLOCKED_GOVERNANCE` (this is a protective stop, not a failure — label it as such to the operator):

1. **Path gate** (`helpers/path-gate.sh <worktree> <whitelist-file>`): every changed path in `git diff` must match the whitelist and must NOT match the unconditional deny list: `docs/`, `fallback/`, `AGENTS.md`, `CHANGELOGS/`, `defaults/`, `.opencode/`, `documenter_policy.yml`, `archive/`, `sessions/`, `.agents/skills/documentation/`. Existing `tests/test_*.py` are read-only unless the task lists them. Non-zero exit → stop.
2. **ADR-013 Tier 2+ scan:** grep the diff for Tier 2+ markers (`write_handler`, registry activation calls, `OperatorSurface`, `active_tier`, `allowed_operations`, `briefing_ref`). Any hit → stop.
3. **MCP guard:** the skill never invokes `council.*` / `documenter.*` MCP tools and never registers the Documenter MCP server (`AGENTS.md` §1.7).
4. **No auto-commit, no policy edits.** Subagents never commit; `documenter_policy.yml` is untouchable.

---

## Subagent Prompt Contract

Each role prompt (templates in `roles/`) is composed of:

```
role identity + responsibility        (fixed, from roles/<role>.md)
inputs:  absolute paths to read       (from cycle-state.json + artifacts)
outputs: absolute paths to write      (fixed per role)
constraints                          (task-specific; refined between iterations)
forbidden: deny-list + "write only your outputs"
```

Launch with `subagent(agent="general", model="freetoken/Qwen3.6-35B-A3B-NVFP4")`, workdir = cycle worktree. Validate the role's output file parses against its schema before advancing the phase; malformed output = phase retry once, then count as iteration failure.

---

## Compliance Checklist

- [ ] Pre-gate done: task written, whitelist operator-confirmed, ADR check passed
- [ ] Worktree created; all subagents ran inside it; main tree untouched until merge
- [ ] Every phase output validated against schema
- [ ] Anti-reversed-TDD baseline recorded (tests ran before implementation)
- [ ] Analyst Level 0 (script) was the sole source of `pass`
- [ ] `progress` computed deterministically; prompt refinement matches the policy
- [ ] No unchanged prompt reused between iterations
- [ ] Path gate + Tier 2+ scan passed before merge
- [ ] Merge: whitelisted paths only, after diff review; worktree removed
- [ ] Artifacts archived to `archive/sessions/<session-id>/cycle-artifacts/`; summary given to operator
- [ ] No commits by subagents; no `documenter_policy.yml` or MCP registration

---

## References

- `sessions/sess-implement-skill/consensus-doc.md` — design consensus this skill implements (2026-11-15)
- `AGENTS.md` §1.5–§1.7 — project stage, ADR-011/013 boundaries, tooling separation
- `fallback/index.md` — Council protocol (this skill is separate; its escalation follows the fallback escalation semantics)
- `roles/` — the four role prompts; `helpers/` — contracts and path gate
