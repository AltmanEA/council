# Target Task — tools/check_forward_port.py (forward-port / premise-shift audit)

**Origin:** switch-over procedure step 2 (`council-dev/switch-over-procedure.md`, commit 31739e9), consensus `sess-branch-version-strategy` (2026-11-23): «аудит forward-port/premise-shift — пустой вывод обязателен», аудит по содержимому, не только по трейлерам (Reliability). Advisory per OP-1.

## CLI contract

```
python3 tools/check_forward_port.py --base <ref> --branch <ref> --path <dir> \
    [--source <ref>] [--against <dir>] [--root DIR] [--min-len N]
```

- `--base` (required): ref marking the starting point (e.g. `v1-stable`).
- `--branch` (required): ref whose commits are audited for paired backports (e.g. `v2-dev`).
- `--path` (required): source-side directory prefix (e.g. `fallback/`) — only commits touching files under it are audited.
- `--source` (default `HEAD`): ref the source-side fix commits are enumerated from (`git log <base>..<source>`).
- `--against` (default = `--path`): branch-side directory prefix searched for fix content (e.g. `draft/`).
- `--root` (default cwd): git repo.
- `--min-len` (default 10): added lines shorter than this (after strip, ignoring `+++` headers, blank/comment-marker-only lines) are exempt from content check.
- Unknown/missing flags → exit 2 (usage error) + usage on stderr, prefix `check_forward_port: `.

## Audit semantics (per source-side fix commit)

A **fix commit** = commit reachable from `--source` and NOT from merge-base with… precisely: `git log --format=%H <base>..<source> -- <path>` (path filter). For each fix commit `<sha>`:

1. **Trailer check:** there exists a commit on `--branch` (`git log <branch> --format=%H --grep=...`) whose message contains a line matching `^backport-of: <sha>` (full sha) or `^backport-of: <sha-prefix>=7+hex` matching the fix sha. If none → violation line:
   `MISSING-TRAILER <sha8> <subject>`
2. **Premise-shift check:** for each backport commit found in (1), its message must contain `^premise-shift: ` with value `none` or `affects=<non-empty>`; otherwise:
   `BAD-PREMISE-SHIFT <backport-sha8>`
   (If several backport commits reference the same fix, ALL must satisfy the trailer check; any violation reported once per backport commit.)
3. **Content check:** added lines of the fix (`git show <sha> -- <path>`, lines starting with `+`, not `+++`, stripped; skip lines shorter than `--min-len` or consisting only of markdown syntax chars/whitespace) must each appear verbatim as a stripped line in SOME file of the branch tree under `--against` (`git ls-tree -r --name-only <branch> -- <against>` + `git show <branch>:<file>`). If any added line is absent:
   `MISSING-CONTENT <sha8> <count> missing lines`
   (single line per fix commit, count of missing added lines)

## Output & exit codes (advisory, OP-1)

- stdout: exactly one line per violation, in fix-commit order (newest first, git log default). Empty output + exit 0 = forward-port audit PASSES (this is the switch-over criterion).
- Unresolvable refs / not a git repo / empty repo → single line `ERROR: <what>` on stdout, exit 0 (advisory — never blocks).
- Usage error (missing required flag, bad flag, bad `--min-len` value) → stderr `check_forward_port: ...`, exit 2.
- NEVER writes to the repo, never modifies anything (plumbing reads only).

## Acceptance criteria (tests must pin)

1. Clean state → empty stdout, exit 0. (fix on source + paired backport on branch with `backport-of:` + `premise-shift: none` + content present in `draft/`)
2. Missing backport commit → `MISSING-TRAILER` line, exit 0.
3. Backport without `premise-shift:` trailer or with malformed value → `BAD-PREMISE-SHIFT`, exit 0.
4. Backport present but fix text absent from `--against` tree → `MISSING-CONTENT <sha8> N missing lines`, exit 0.
5. `--against draft/` maps content search to the branch-side dir while `--path fallback/` filters source commits (the fallback↔draft duality is THE core use case).
6. Content check: `--min-len` exemption works; markdown-syntax-only lines skipped; multiple fix commits → per-commit lines; sha-prefix (≥7 hex) trailer accepted.
7. Unresolvable `--base`/`--branch`/`--path`-less repo → `ERROR:` line on stdout, exit 0.
8. Usage errors → exit 2, `check_forward_port:` on stderr.

## Allowed paths (whitelist, operator-approved via "запускай" 2026-11-23)

- NEW: tools/check_forward_port.py, tests/test_check_forward_port.py
- EDIT: tools/README.md (add table row — prose contract per AGENTS.md §1.7, exact CLI/exit semantics)

## Test command

`python3 -m unittest tests.test_check_forward_port -v`

Regression gate: existing suites must stay green (run `tests.test_gen_engine tests.test_check_engine_sync tests.test_build_exact_match tests.test_dist_composition tests.test_dist_isolated_layout` after implementation; note `test_dist_isolated_layout.test_gitignore_created` is a KNOWN pre-existing failure, not yours).

## Constraints (established cycle lessons — mandatory)

- unittest only; each test builds its own scratch repo via tempfile.TemporaryDirectory + `git init` + `-c user.email/name`; NO council-repo tags/refs; NO network.
- **`.git` may be a FILE in worktrees** — any fixture copying from WORKTREE must skip `{'.git', '.impl-whitelist', 'artifacts', '__pycache__'}` by name; after `git init` assert isolation: `git tag -l` empty and `git rev-parse --show-toplevel` == repo.
- Two-branch fixture: base commit; tag base (e.g. `v1-stable`); master-side fix commit touching `fallback/`; branch `v2-dev` created at base with backport commit touching `draft/` carrying trailers in message (`git commit -m "fix x" -m "backport-of: <sha>" -m "premise-shift: none"`).
- Script invoked by ABSOLUTE path inside WORKTREE.
- No commits by anyone (subagents): worktree must stay at base with dirty/ untracked changes only; NO new tags in the shared repo.
- Python 3.11+, stdlib+subprocess only (argparse style of tools/check_engine_sync.py; module docstring = CLI contract).
