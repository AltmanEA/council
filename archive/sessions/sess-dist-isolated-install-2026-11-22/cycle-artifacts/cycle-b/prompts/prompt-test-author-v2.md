# Role: Test Author — cycle B iteration 1.1 (contract gaps to close)

Working directory = worktree:
/home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-22T15-40-2
Your baseline suite exists (tests/test_dist_isolated_layout.py, 20 tests; 19 red).
Orchestrator review found TWO coverage gaps against target-task.md. Close them.

## Gap 1 — AC-5 banner untested
target-task.md AC-5 requires the installer to print a "Where is Council?" box
listing docs/tools/skills/updater locations. No test asserts it.
ADD: after a successful init install into a temp host, assert the install stdout
contains a "Where is Council" header line AND the strings `.council/docs/en`,
`.council/tools`, `.council/skills`, `.council/update.sh` (case-insensitive ok).
This test MUST be red now (current banner has no such box).

## Gap 2 — AC-9 argument readback untested
test_custom_hooks_dir only verifies the DEFAULT behavior (green already, keep it
as regression). The actual AC-9 requirement is: `bash tools/install-hooks.sh
.council/tools/hooks` must set `core.hooksPath` to the GIVEN dir.
ADD a test: temp git repo, copy tools/install-hooks.sh + a hooks dir at
.council/tools/hooks (with pre-commit inside), run
`bash tools/install-hooks.sh .council/tools/hooks`, then assert
`git config --local core.hooksPath` == `.council/tools/hooks` AND the script
self-check passes (exit 0). Red now (current script hardcodes tools/hooks).

## Also tighten (small, keep green-safe)
- In test_pre_commit_falls_back_to_root_check_all, keep as-is (green regression is fine).
- Do NOT otherwise modify existing tests or test_dist_composition.py.

## Outputs (ONLY these)
- tests/test_dist_isolated_layout.py (extended: add the two red tests; update docstring count)
- /home/ea/council/sessions/sess-dist-isolated-install-2026-11-22/impl-run-2026-11-22T15-40-02-1/artifacts/test-files.json (update file list/test count + baseline exit code re-run)

## Verification
python3 -m unittest tests.test_dist_isolated_layout -v   → expect previous reds + 2 NEW reds
Record new baseline exit code and per-AC table.

## Forbidden
Modifying dist/*, tools/*, other tests; git commits; weakening existing assertions.

## Report format
Short markdown: added test names, AC they pin, new baseline counts (red/green), exit code.
