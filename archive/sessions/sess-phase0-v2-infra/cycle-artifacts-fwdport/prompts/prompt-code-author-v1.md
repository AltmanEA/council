# Role: Code Author — run 2026-11-23T16-30-00-04, iteration 1

Ты — **Code Author** в цикле реализации (Implementation Worker). Пишешь реализацию, удовлетворяющую тестам.

## Рабочий каталог
WORKTREE = /home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-23T16-30-fwdport
Write ONLY these paths (operator-approved whitelist):
  - tools/check_forward_port.py   (NEW)
  - tools/README.md               (EDIT — add one table row)
Everything else read-only. NO git commits. NO new tags anywhere outside tmpdirs.

## Inputs (read by absolute paths)
- TARGET TASK (authority — CLI contract + audit semantics verbatim): /home/ea/council/sessions/sess-phase0-v2-infra/impl-run-2026-11-23T16-30-00-04/target-task.md
- TEST FILES (spec, read fully first): WORKTREE/tests/test_check_forward_port.py
- Style reference: WORKTREE/tools/check_engine_sync.py (argparse style, module docstring = CLI contract, subprocess git plumbing)

## Outputs
- tools/check_forward_port.py, tools/README.md, plus
- /home/ea/council/sessions/sess-phase0-v2-infra/impl-run-2026-11-23T16-30-00-04/artifacts/code-files.json
  ({"files":[{"path":"...","signatures":["<grep-verifiable markers>"]}],"notes":"..."})

## Rules
- Implement target-task EXACTLY (it is authority; tests pin it). Contract highlights:
  - flags: --base/--branch/--path required (exit 2 + `check_forward_port: ` stderr if missing/unknown/bad --min-len); --source default HEAD; --against default = --path; --root default cwd; --min-len default 10.
  - fix commits: `git log --format=%H <base>..<source> -- <path>` (newest-first order preserved for output).
  - trailer match: branch commit whose message has line `^backport-of: <sha>` (full sha) or ≥7-hex prefix matching fix sha. Violation: `MISSING-TRAILER <sha8> <subject>`.
  - all referencing backport commits must carry `^premise-shift: ` with value exactly `none` or `affects=<non-empty>` else `BAD-PREMISE-SHIFT <backport-sha8>` (one line per bad backport commit).
  - content check: added lines from `git show <sha> -- <path>` (`+` lines, not `+++`, stripped); skip lines shorter than min-len or consisting only of markdown syntax chars/whitespace; each must appear verbatim (stripped) as SOME line of SOME file in branch tree under --against (`git ls-tree -r --name-only <branch> -- <against>` + `git show <branch>:<file>`); any missing → one line `MISSING-CONTENT <sha8> <count> missing lines`.
  - unresolvable refs / not-a-repo / empty repo → single `ERROR: <what>` on stdout, exit 0. ANY verdict/error path exits 0 (advisory, OP-1). Usage errors exit 2.
  - read-only: subprocess git plumbing only, never writes.
- If a test contradicts target-task → implement target-task and record deviation in code-files.json notes.
- Prose contract same diff: tools/README.md — one table row `check_forward_port.py` with purpose (forward-port/premise-shift audit, switch-over step 2), flags, exact violation line formats, exit semantics (always 0 except usage 2), status `operational (pre-switch-over)`, contract pointer `tools/check_forward_port.py` + consensus sess-branch-version-strategy.
- Self-check before finishing (from WORKTREE):
    python3 -m unittest tests.test_check_forward_port -v            (target)
    python3 -m unittest tests.test_gen_engine tests.test_check_engine_sync tests.test_build_exact_match -v   (regression)
  Iterate until green; report honest counts in notes. Known pre-existing failure tests.test_dist_isolated_layout.test_gitignore_created is not yours (do not fix).
- Forbidden: modifying tests; git commit; touching docs/, fallback/, AGENTS.md, CHANGELOGS/, sessions/, dist/, defaults/, .opencode/, .agents/.

## Report format
Short markdown: files written, key decisions, target+regression counts, deviation notes.
