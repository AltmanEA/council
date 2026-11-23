# Target Task — Phase 0: rewrite `tools/check_all.py` to the frozen audit contract

Run: impl-run-2026-11-19T13-00-01
Source of requirement: `docs/en/documenter-service/impl-guide.md` §"Deterministic core" (Audit engine) and §Phasing Phase 0; `docs/en/documenter-service/index.md` §Audit tool (frozen contract).

## Goal

Rewrite the CLI behavior of `tools/check_all.py` (check logic / check battery stays) so its
exit codes and human rendering match the frozen contract. Update `tools/hooks/pre-commit`
so its MODE × outcome table matches the new codes. No new scripts.

## Binding behavioral decisions (the tests MUST encode exactly these)

Severity levels (unchanged, in `tools/tests_helpers.py`): `warning`(0) < `low`(1) < `medium`(2) < `high`(3).
`high` IS the critical tier. There is no separate "critical" label.

1. **Exit codes** (computed over REPORTED findings after the `--severity` filter):
   - `0` — no reported findings (clean).
   - `1` — findings reported, none `high`.
   - `2` — at least one `high` finding reported (critical).
   - `2` is ALSO used for internal error / bad `--rule` token (unchanged), distinguished on
     output: internal error prints a line beginning with the literal `check_all: INTERNAL ERROR`;
     bad `--rule` prints `ERROR:` to stderr. A crash never looks like `🚨`.
2. **`--severity SEV`** now means *minimum reported severity* (was: minimum blocking).
   Choices `warning|low|medium|high`.
   **AMENDED (orchestrator decision, iteration 1):** default `low` (was: high). Rationale:
   frozen rendering contract requires a visible severity-sorted findings list (skill §Audit
   Compliance, checklist "every medium/low finding explained or fixed"); the guide's token
   contract enumerates only `high|medium|low`. Default `low` keeps genuine `warning`s hidden
   unless `--strict`.
3. **`--strict`** lowers the report filter to report every finding regardless of severity
   (equivalent to `--severity warning`); it no longer has separate "blocking" semantics —
   exit codes come out of the table in (1).
4. **Human rendering** (non-`--json`):
   - Clean: NO output at all on stdout (silent when clean). Remove the `OK — no findings ...`
     line and the old `check_all: N finding(s) ... blocking ...` summary line.
   - Findings, no high: first line `⚠ findings: N` (N = reported count), then one hint line per
     finding, grouped and severity-sorted (high, medium, low, warning), each hint line carrying
     the stable token contract `rule=<id> severity=<sev> file=<path> <one-line hint>`.
   - Findings with ≥1 high: first line `🚨 critical: N` (N = count of high findings), second
     line `⚠ findings: M` (M = total reported), then the hint lines as above.
   - `⚠`/`🚨` markers are visual only; the grep targets remain the literal tokens
     `severity=high|medium|low` in the hint lines and in `--json` output.
5. **`--json`**: unchanged — one object per line `{"rule","severity","file","description"}`,
   for all REPORTED findings. No marker lines in `--json` mode.
6. **`--rule`** group filtering, `--root`, `--strict-links` keep their current semantics.
7. **Hook `tools/hooks/pre-commit`** updated table (warn-only soak unchanged in spirit):
   - exit 0 → exit 0 (both modes). NOTE: clean is now silent, so the hook must NOT treat
     "empty output" as failure; only the exit code decides.
   - exit 1 → print output; warn-mode exit 0; block-mode exit 0 too (no high reported by
     definition of exit 1) — block-mode additionally greps `severity=high` as a belt-and-braces
     check and blocks (exit 1) if it appears.
   - exit 2 → if output contains `🚨 critical` (critical findings): warn-mode exit 0,
     block-mode exit 1. If output contains `check_all: INTERNAL ERROR` or neither marker
     (crash / non-contract code): fail-closed as today (warn 0 / block 1).
   - The existing TOKEN CONTRACT comment block must be updated to the new rendering.
8. `tools/tests_helpers.py` unchanged (severity ranks stay).

## Acceptance criteria

- New tests in `tests/test_check_all.py` (listed writable for this task) cover: clean=silent+exit 0;
  low-only → `⚠ findings: N`, exit 1; high present → `🚨 critical:` + `⚠ findings:` exit 2;
  `--severity` filter changes what is reported AND the exit code; `--strict` reports all;
  `--json` has no markers and keeps schema; token contract holds on every hint line;
  internal-error path prints `check_all: INTERNAL ERROR` and exit 2 distinguishable from
  `🚨`; hook script text updated (grep-level assertions as in `tests/test_install_hooks.py` style —
  new file `tests/test_check_all_hook_contract.py` allowed).
- Existing tests in `tests/test_check_all.py` updated ONLY where they assert the old
  blocking/exit-code rendering semantics; findings-detection assertions stay.
- `python3 -m unittest tests.test_check_all tests.test_check_all_hook_contract -v` green.
- `python3 tools/check_all.py` on the live repo (after AMENDED default=low): prints
  `⚠ findings: 32` + hints, exit 1. Clean fixture corpora: silent, exit 0.
- Line count of check_all.py stays within OP-2 ceiling (≤ ~1300 LOC).

## Allowed paths (whitelist)

- `tools/check_all.py` (existing, explicitly listed)
- `tools/hooks/pre-commit` (existing, explicitly listed)
- `tests/test_check_all.py` (existing, explicitly listed — contract change requires it)
- `tests/test_link_integrity.py` (existing, explicitly listed — AMENDED iteration 3: it
  calls `check_all.main` directly and encodes the OLD blocking exit-code semantics; docs→
  manifest high findings now yield rc=2 (critical), not rc=1. Contract consumer of the
  rewritten CLI.)
- `tests/test_check_all_hook_contract.py` (new)
- `.impl/*` (cycle artifacts inside the worktree)

## Forbidden

- Any path under `docs/`, `CHANGELOGS/`, `fallback/`, `.agents/`, `defaults/`, `sessions/`, `archive/`
- `tools/tests_helpers.py`, `tools/gen_manifest.py`, other tools (read-only)
- No commits. Never modify the check battery rules themselves.

## Test command

`cd <worktree> && python3 -m unittest tests.test_check_all tests.test_check_all_hook_contract -v`
