# Target Task — v2 dev-worktree engine infrastructure (Phase 0)

**Consensus:** sessions/sess-branch-version-strategy/consensus-doc.md (2026-11-23, operator decisions №1–№4).
**Operator whitelist confirmed 2026-11-23** (new tools + tests + edits of dist/build.sh, tools/README.md, dist/RUNBOOK.md).

## Goal
Three deterministic tools supporting the v1/v2 dual-life workflow:

### 1. `tools/gen_engine.sh` (NEW) — materialize the engine
Usage: `bash tools/gen_engine.sh <tag-or-ref> [target-dir]`
- Extracts the `fallback/` subtree of the given git ref into `<target-dir>` (default `.engine/<version>` relative to repo root, where `<version>` is `git describe --tags --exact-match <ref>`, falling back to the short sha when the ref is not an exact tag).
- Must copy ONLY `fallback/` content (files under `fallback/`), preserving names.
- Writes `.engine/.../DIST-SOURCE` file with lines: `tag=<ref>`, `tree=<git rev-parse <ref>^{tree}>`, `commit=<sha>`, `generated=<ISO8601 UTC>`.
- Prepends a first line `ENGINE: <version> @ <short-commit-sha> — generated, do not edit` to EVERY copied .md file (before its H1; a blank line follows).
- Idempotent: full rebuild each run (removes the target engine dir first, regenerates). Running twice yields byte-identical output except the `generated=` timestamp line.
- Exit codes: 0 success; 2 usage error (missing argument), ref does not exist, or ref contains no `fallback/` files. Errors printed to stderr, prefix `gen_engine: `.
- Must work in a plain scratch git repo (tests create tmp repos) and in the council repo.
- Does NOT write anything outside `<target-dir>`; never touches the working tree's `fallback/`.

### 2. `tools/check_engine_sync.py` (NEW) — advisory engine-pin check
Usage: `python3 tools/check_engine_sync.py [--engine-dir DIR] [--ref REF] [--root DIR]`
- Reads `<engine-dir>/DIST-SOURCE` (default: first `DIST-SOURCE` found under `<root>/.engine/`, lexicographically; if several, compare against each `tag=` listed).
- Resolves the expected commit: `git rev-parse <ref>^{commit}` where `<ref>` defaults to `v1-latest` (fall back to `v1-stable` if `v1-latest` missing), over repo `--root` (default cwd).
- Verdicts (always single line on stdout):
  - `engine-sync: OK | dir=<d> pin=<tag>@<sha8> current=<sha8>` — pin commit == resolved commit;
  - `engine-sync: MISMATCH | ...` — DIST-SOURCE tree/commit differs from resolved ref;
  - `engine-sync: STALE | ...` — DIST-SOURCE generated time older than 14 days AND != resolved (informational variant of MISMATCH; emit instead of MISMATCH when age > 14 days);
  - `engine-sync: MISSING | ...` — no DIST-SOURCE found / engine dir absent.
- **ALWAYS exit 0** (warn-only by OP-1), except exit 2 on usage error (bad flags). Never writes, never modifies.
- Must tolerate detached HEAD / missing refs gracefully (verdict MISSING or ERROR line, exit 0).

### 3. `dist/build.sh` (EDIT) — exact-match release guard
- Current: bare invocation uses `git describe --tags`; untagged HEAD silently produces `dev-<sha>` builds.
- New: when called WITHOUT an explicit VERSION argument, require `git describe --tags --exact-match`; on failure print to stderr `FATAL: not on a tagged commit; pass VERSION explicitly for non-release builds` and exit 1. When VERSION is passed explicitly, behavior unchanged (any string accepted).
- Do not break: `dist/test-dry-run.sh` (calls build.sh with explicit VERSION + COUNCIL_ALLOW_DIRTY), existing tests `tests/test_dist_composition.py`, `tests/test_dist_isolated_layout.py`.

## Acceptance criteria (tests must pin this behavior)
1. gen_engine.sh happy path: extracts fallback/ .md files; each starts with `ENGINE: ... — generated, do not edit`; DIST-SOURCE has tag/tree/generated.
2. gen_engine.sh idempotency: second run → same file set, same content modulo `generated=` line.
3. gen_engine.sh errors: missing arg → 2 + stderr; unknown ref → 2; ref without fallback/ → 2.
4. gen_engine.sh version: exact tag → `.engine/<tag>/...`; non-tag ref → directory named by short sha.
5. check_engine_sync OK/MISMATCH/STALE/MISSING verdicts per spec; always exit 0; usage error exit 2.
6. build.sh exact-match: bare run on untagged scratch repo → exit 1 + FATAL message; explicit VERSION → success; exact tag bare run → success.

## Allowed paths (whitelist)
- NEW: tools/gen_engine.sh, tools/check_engine_sync.py, tests/test_gen_engine.py, tests/test_check_engine_sync.py, tests/test_build_exact_match.py
- EDIT (operator-listed): dist/build.sh, tools/README.md, dist/RUNBOOK.md

## Test command
`python3 -m unittest tests.test_gen_engine tests.test_check_engine_sync tests.test_build_exact_match -v`
Framework: unittest (repo standard). Regression gate: existing `tests.test_dist_composition`, `tests.test_dist_isolated_layout` must stay green (run them too).

## Constraints
- Python 3.11+, stdlib only (PyYAML allowed by repo policy; do not add imports beyond stdlib+yaml).
- Shell: bash, `set -euo pipefail`, no external deps beyond git/tar/coreutils.
- Tests create throwaway git repos in tmpdirs (git init, config user.email/name, commit files, tag). No network. Tests must not depend on council repo tags.
- No changes to: docs/, fallback/, AGENTS.md, CHANGELOGS/, sessions/, defaults/, .opencode/, .agents/skills/documentation/, documenter_policy.yml.
- Prose contracts (tools/README.md tool table row(s), dist/RUNBOOK.md release-section note) MUST be updated in the same diff to match implemented behavior.
