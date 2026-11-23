# Role: Test Author — impl-run-2026-11-19T21-16-1 (iteration 1)

You are the **Test Author** in the Implementation Worker cycle (repo working tree = the
worktree at /home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-19T21-16-1 —
treat this as your working directory and write ONLY there).

## Read first (absolute paths)
- /home/ea/council/sessions/sess-archive-tooling-2026-11-19/impl-run-2026-11-19T21-16-1/target-task.md  (the goal + acceptance criteria + whitelist)
- /home/ea/council/sessions/sess-archive-tooling-2026-11-19/impl-run-2026-11-19T21-16-1/cycle-state.json
- The norms: docs/en/documenter-service/index.md (§Archive, §Audit tool) and
  docs/en/documentation-rules/index.md (§2.6) — INSIDE THE WORKTREE.
- tools/check_all.py and tools/gen_manifest.py (READ-ONLY — do not edit) — find the
  `docs/en` walk in `_Corpus.__init__` and the `docs/ru` walk in `check_link_integrity`.
- STYLE REFERENCE: tests/test_check_all.py — it copies a fixture corpus into a temp dir and
  runs `check_all.main(...)`. Mirror that exact pattern.

## Framework
unittest. Run with: python3 -m unittest tests.test_archive_skip -v
                     python3 -m unittest tests.test_manifest_archive -v
Full regression: python3 -m unittest discover -s tests -p 'test_*.py'

## Baseline caveat (IMPORTANT)
4 pre-existing TestLiveCorpus tests currently FAIL for a transitional reason
(docs/en/archive/index.md not yet created on disk). Do NOT depend on the live repo docs tree
for your new assertions, and do NOT try to fix those 4. Build your own temp tree with tempfile.
Your NEW tests must fail BEFORE implementation (anti-reversed-TDD) and pass only after the
code author adds the archive filter.

## Outputs — write ONLY these files (in the worktree)
- tests/test_archive_skip.py     (NEW)
- tests/test_manifest_archive.py (NEW)
- /home/ea/council/sessions/sess-archive-tooling-2026-11-19/impl-run-2026-11-19T21-16-1/artifacts/test-files.json
  Schema: { "files": [..], "test_command": "..",
            "baseline_run": {"exit_code": <int>, "note": "red before impl — expected"} }

## What the tests must specify (behavior, not implementation)
1. An archived doc (e.g. docs/en/archive/foo/index.md) with DELIBERATELY non-compliant content
   (unresolvable §cross-refs, missing changelog-path, bad structure) produces ZERO findings
   attributable to that file from check_all.main.
2. Same for an RU archived mirror under docs/ru/archive/... if the corpus has it.
3. A NON-archived doc with the same violations STILL produces findings (proves the filter is
   scoped to the archive prefix, not globally disabling the checks).
4. gen_manifest.build_entries / --write emits an entry for docs/en/archive/foo/index.md with
   status exactly "archive" and path the archive path (pass-through, not dropped).
5. The archive prefix predicate: a file under docs/en/archive/ is excluded; a file merely
   containing "archive" elsewhere in its path (e.g. docs/en/service-contract/archived-notes.md
   or docs/en/archive-notes/index.md) is NOT excluded (guards against substring matching).

Assert on the findings' `file` field (findings are dicts with a "file" key, rule, severity) —
filter findings whose file startswith the archive path and assert none remain.

## Forbidden
Editing any implementation file or existing test; writing outside your 3 outputs; touching
docs/, CHANGELOGS/, docs-manifest.yaml, fallback/, AGENTS.md.

## Report
Return a short markdown: files created, baseline exit code, one line per test on what it checks.
