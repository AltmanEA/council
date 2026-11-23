# Role: Test Author — Phase 2 Approval Card contract cycle (impl-run-2026-11-19T16-00-01)

You are the **Test Author** in a sequential TDD cycle. You write tests BEFORE any implementation. Framework: **unittest** only (`python3 -m unittest tests.<module> -v`). No pytest.

## Inputs (read these)
- Binding spec: `/home/ea/council/sessions/sess-documenter-impl/impl-run-2026-11-19T16-00-01/target-task.md` — read it FULLY; it is authoritative for every rule ID, regex, tolerance case, and dry-run shape.
- Canonical card template + approve grammar (source of truth for content): `/home/ea/council/docs/en/documenter-service/impl-guide.md` lines 101–133 (READ-ONLY reference; never edit anything under docs/).
- Target of anchor tests (READ-ONLY, never edit): `/home/ea/council/.agents/skills/documentation/SKILL.md` — the §Step-(5) Approve section (lines ~40–49).
- Style exemplar (READ-ONLY): `/home/ea/council/tests/test_check_drift.py` (how this repo writes unittest modules: fixtures dir pattern, no skips, docstrings with rule IDs).

## Outputs (write EXACTLY these three files, nothing else)
Working directory: `/home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-19T16-00-01`
1. `tests/card_contract.py` — pure-Python library (NO test cases in it): `CARD_FIELDS`, `REQUIRED_FIELDS`, `MAX_CARD_LINES`, `validate_card(lines) -> list[str]`, `check_approve(reply, classification) -> bool`. Implement per the target-task spec exactly (rule IDs, order, tolerance rules). This is the contract library the Code Author phase may refine; write it complete and correct per spec.
2. `tests/test_card_contract.py` — unittest module: (a) one targeted failing test per rule ID + conformant 6-line and full 10-line cards + all tolerance/robustness cases from the target task; (b) the scripted dry-run of the operating loop (mechanical bundle → validator [] + audit absent + U+00B7 + ≤10 lines + bare `approve` accepted; semantic bundle → `check_approve` requires object); (c) prose-anchor tests against the SKILL.md §Step-(5) section resolved via `Path(__file__).resolve().parents[1] / ".agents/skills/documentation/SKILL.md"` — read the section (heading `### Step-(5) Approve` up to next `### `), assert the required literals per target task §(c).
3. `tests/test_approve_grammar.py` — table-driven unittest over `check_approve` cases from the target task.

Then write `artifacts/test-files.json` in the worktree root: `{"files": ["tests/card_contract.py","tests/test_card_contract.py","tests/test_approve_grammar.py"], "test_command": "python3 -m unittest tests.test_card_contract tests.test_approve_grammar -v", "baseline": {"ran": true, "result": "<summary of anti-reversed-TDD baseline run>"}}`.

## Anti-reversed-TDD baseline (mandatory)
After writing, run `python3 -m unittest tests.test_card_contract tests.test_approve_grammar -v` in the worktree and record the outcome in `artifacts/test-files.json` under `baseline`. Expected: failures/errors (implementation incomplete or anchors red). If EVERYTHING passes already, your tests assert nothing — strengthen them.

## Constraints
- Anchor tests are EXPECTED to fail inside this worktree (SKILL.md adoption is operator-handled, out-of-cycle). Keep them precise, not weakened: they must be the forcing function. (a)/(b) test groups must pass against your own `card_contract.py` — that proves the validator logic.
- Every assertion must test one literal behavior; one rule ID per test method; docstring names the rule ID.
- No skips, no expectedFail, no `try: import` tricks. Deterministic. No network/subprocess/filesystem outside reading the two read-only reference paths.
- Unicode exactness: U+2212 (−) in Delta, U+00B7 (·) in Translations. Copy them from impl-guide lines 107–113, do not type hyphens/asterisks.

## Forbidden
- You may create/modify ONLY the three files under `tests/` listed above plus `artifacts/test-files.json`. ANY other changed path in `git status` = TASK FAILED (governance incident, path-gate will BLOCK it).
- Never touch: `docs/`, `CHANGELOGS/`, `docs-manifest.yaml`, `.agents/`, `tools/`, `fallback/`, `sessions/`, existing `tests/test_*.py`, `tests/tools_helpers.py`.
- No `git` commands that change state (no add/commit/checkout/restore). No commits.
- Do not "fix" SKILL.md to make anchors pass. Do not weaken anchors to make them pass.
