# Target Task — Cycle A: check_all.py cross-root link resolution (--core-root)

Session: sess-dist-isolated-install-2026-11-22 (operator-approved consensus of 2026-11-22)
Run: impl-run-2026-11-22T14-30-01-1
Worktree (all work happens here, absolute path):
  /home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-22T14-30-1

## Goal

In the dual-root Council layout, host docs reference core framework docs by the
canonical abstract path `docs/en/<id>/index.md`, but the core corpus physically
lives under `.council/docs/en/`. Extend `tools/check_all.py` with an optional
`--core-root <path>` so that when the host corpus is audited, any doc-path
reference token that does NOT resolve within the audited root resolves against
`<core-root>/docs/en/` as a second resolution space. Without the flag, behavior
must be byte-identical to today (full backward compatibility).

## Acceptance criteria (each must have at least one test)

AC-1  With `--root R --core-root C`: a host doc under R referencing
      `docs/en/foo/index.md` (a file that exists only at C/docs/en/foo/index.md)
      produces NO missing-reference/link-integrity finding for that reference.

AC-2  Without `--core-root` (audit of R alone), the same reference DOES produce
      the existing high-severity missing-file finding (regression guard proving
      the flag is what changes behavior).

AC-3  Core corpus is NOT merged into the host audit corpus: core docs are not
      subject to host manifest-parity checks (docs→manifest), do not appear in
      the host docs list, and are not reported as orphans of the host manifest.

AC-4  Precedence: if the same relative path exists under BOTH roots, resolution
      uses the audited root's (host) copy; the core copy is ignored for that
      token. (No new finding required.)

AC-5  If `--core-root` is given but `<core-root>/docs/en` does not exist, the
      tool exits with a clear error message naming `--core-root` (same error
      style as the existing "no docs/en directory under --root" error).

AC-6  `--root` only (no `--core-root`): existing behavior unchanged — the whole
      existing suite `tests.test_check_all` stays green.

AC-7  Exit-code semantics unchanged: 0 = clean, 1 = findings at/above threshold,
      2 = scan/usage errors (AC-5 uses this path style).

## Target files (whitelist — the ONLY writable paths)

- `tools/check_all.py` (modify; explicitly listed by operator)
- `tests/test_check_all_core_root.py` (new — cycle A test file)

All other paths are read-only. Never modify other tests, `tests/fixtures/`,
`dist/`, `docs/`, `fallback/`, `AGENTS.md`, `CHANGELOGS/`, `defaults/`,
`.opencode/`, `sessions/`.

## Test command

    python3 -m unittest tests.test_check_all_core_root -v

Regression (must stay green, run after implementation):

    python3 -m unittest tests.test_check_all -v

Framework: unittest (repo standard; run from worktree root).

## Implementation guidance (non-binding, for the code author)

- `_Corpus` is constructed from one root; the minimal design is an optional
  second read-only path set consulted by the file-reference/§ref resolvers when
  the primary corpus lookup fails. Do NOT merge the two roots into one corpus
  (AC-3 forbids it).
- The flag must appear in `main()`'s argparse with help text; the tool's module
  docstring rule list should mention core-root resolution in one line.
- Prose contract sync (`tools/README.md`) is OUT of scope for this cycle (it is
  a docs/ implementation-file change handled separately by the operator per
  AGENTS.md §2); do not touch it.

## Environment facts (verified by orchestrator pre-gate)

- check_all.py has argparse `--root` (default: parent of tools/), `--json`,
  `--severity`, `--rule`, `--strict`, `--strict-links` already.
- Existing corpus error message: `"no docs/en directory under --root ..."`.
- tests/test_check_all.py is unittest-based and builds temp corpora — mirror its
  fixture-building style.
