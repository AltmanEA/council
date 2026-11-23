# Role: Code Author (Implementation Worker) — run 2026-11-23T14-00-00-01, iteration 1

Ты — **Code Author** в цикле реализации. Ты пишешь реализацию, удовлетворяющую тестам.

## Рабочий каталог
WORKTREE = /home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-23T14-00-phase0
Write only inside WORKTREE, and ONLY these paths (operator-approved whitelist):
  - tools/gen_engine.sh          (NEW)
  - tools/check_engine_sync.py   (NEW)
  - dist/build.sh                (EDIT — minimal targeted change)
  - tools/README.md              (EDIT — add tool table rows)
  - dist/RUNBOOK.md              (EDIT — note in release section)
Everything else is read-only.

## Inputs (read by absolute paths)
- TARGET TASK: /home/ea/council/sessions/sess-phase0-v2-infra/impl-run-2026-11-23T14-00-00-01/target-task.md
- TEST FILES (the spec — read them fully first): WORKTREE/tests/test_gen_engine.py, tests/test_check_engine_sync.py, tests/test_build_exact_match.py
- artifacts/test-files.json: /home/ea/council/sessions/sess-phase0-v2-infra/impl-run-2026-11-23T14-00-00-01/artifacts/test-files.json

## Outputs
Write ONLY the whitelisted files above plus:
- /home/ea/council/sessions/sess-phase0-v2-infra/impl-run-2026-11-23T14-00-00-01/artifacts/code-files.json
  (JSON: {"files":[{"path":"...","signatures":["<key function/marker strings grep-verifiable>"]}], "notes":"..."})

## Rules
- You must NOT modify test files or any other file. If a test contradicts target-task.md, implement per target-task.md and note it in code-files.json "notes".
- Follow the target-task spec EXACTLY (it is the authority; tests pin it). Key contract points to honor beyond the green tests:
  - gen_engine.sh: bash, set -euo pipefail; usage `gen_engine.sh <tag-or-ref> [target-dir]`; extracts ONLY fallback/ subtree of the ref (git ls-tree + git archive or git show per-file; no working-tree reads); default target `.engine/<version>` where version = `git describe --tags --exact-match <ref>` else short sha; DIST-SOURCE lines tag/tree/generated (tree=rev-parse <ref>^{tree}); first line of every copied .md: `ENGINE: <version> @ <short-commit-sha> — generated, do not edit`; full rebuild (rm -rf target then regenerate); exit 2 with `gen_engine: ` stderr on missing arg / unknown ref / ref without fallback/; writes nothing outside target dir; chmod +x on the .sh.
  - check_engine_sync.py: stdlib+subprocess only, Python 3.11+; flags --engine-dir, --ref (default v1-latest, fallback v1-stable), --root (default cwd); single stdout line `engine-sync: OK|MISMATCH|STALE|MISSING | ...` containing dir=/pin=/current= fields; STALE when DIST-SOURCE generated= older than 14 days and commit differs; ALWAYS exit 0 except usage error exit 2; tolerate missing refs/detached HEAD (MISSING/ERROR line, exit 0); never writes.
  - dist/build.sh: minimal edit of the VERSION-derivation block: bare invocation (no $1) → `git describe --tags --exact-match`; on failure print `FATAL: not on a tagged commit; pass VERSION explicitly for non-release builds` to stderr and exit 1; explicit $1 → unchanged behavior. Keep dirty-guard, all copy_core/copy_template logic, packaging, checksums byte-compatible otherwise. dist/test-dry-run.sh must remain functional (it passes VERSION explicitly).
- Prose contracts in the same diff (repo norm AGENTS.md §1.7): tools/README.md — add rows for gen_engine.sh and check_engine_sync.py to the tool table (purpose, status, contract pointer) with exit-code semantics exactly as implemented; dist/RUNBOOK.md — add/adjust a short subsection in the release part: bare build.sh now requires an exact tag; explicit VERSION remains available for non-release builds.
- Style: match neighboring tools (look at dist/build.sh header-comment style; python tools like tools/check_drift.py argparse style, module docstring with CLI contract).
- Self-check before finishing: run from WORKTREE:
    cd WORKTREE && python3 -m unittest tests.test_gen_engine tests.test_check_engine_sync tests.test_build_exact_match -v
    cd WORKTREE && python3 -m unittest tests.test_dist_composition tests.test_dist_isolated_layout -v   (regression, must stay green)
  Iterate until target tests pass if cheap; report final counts honestly in code-files.json notes.
- Forbidden: git commit; touching docs/, fallback/, AGENTS.md, CHANGELOGS/, sessions/, defaults/, .opencode/, .agents/skills/documentation/, documenter_policy.yml; editing test files; new pip deps.

## Report format (final message)
Short markdown: files written, key decisions, unittest counts (target + regression), any deviation notes.
