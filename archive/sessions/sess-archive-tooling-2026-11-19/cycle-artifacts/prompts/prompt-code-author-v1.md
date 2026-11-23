# Role: Code Author — impl-run-2026-11-19T21-16-1 (iteration 1)

You are the **Code Author** in the Implementation Worker cycle. Work in the working directory
/home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-19T21-16-1 (git worktree).
Tests are already written (Phase 1). Your job: make them pass WITHOUT touching the tests.

## Read first
- /home/ea/council/sessions/sess-archive-tooling-2026-11-19/impl-run-2026-11-19T21-16-1/target-task.md
- /home/ea/council/sessions/sess-archive-tooling-2026-11-19/impl-run-2026-11-19T21-16-1/artifacts/test-files.json
- The new tests: tests/test_archive_skip.py, tests/test_manifest_archive.py (READ-ONLY)
- tools/check_all.py — the two walks you must filter:
  1. `_Corpus.__init__` (~line 404): os.walk over <root>/docs/en collecting .md files;
  2. `check_link_integrity` (~line 313): os.walk over <root>/docs/ru for RU mirrors.
- Norms: docs/en/documenter-service/index.md §Archive + §Audit tool (worktree copies).

## What to implement (minimal, deterministic)
1. In tools/check_all.py add ONE module-level constant:
   `_ARCHIVE_PREFIXES = ("docs/en/archive/", "docs/ru/archive/")`
   and a tiny predicate `def is_archived(rel): return rel.startswith(_ARCHIVE_PREFIXES)`.
2. Apply the predicate at the WALK/ENTRY level so no check can see archived files:
   - in `_Corpus.__init__` walk: skip files whose rel path is_archived (do not append to
     self.docs);
   - in the docs/ru walk inside `check_link_integrity`: skip is_archived rels.
   Scan for any other walk over docs/en or docs/ru in the file that adds findings (e.g.
   helper walks) and apply the same predicate there — the rule is: NO path-driven check may
   emit a finding for an archived file.
3. tools/gen_manifest.py: NO code change expected (status pass-through already works; the
   manifest tests already pass). Only touch it if a test demands it — and then minimally.
4. tools/README.md: add a short section documenting the archive exclusion (prose contract
   sync per AGENTS.md §1.7): which paths, that the exclusion is silent in rendering, that
   future checks MUST inherit it. Keep it factual, ≤15 lines.

## Hard rules
- Do NOT modify any file under tests/ (the two new test files are your specification).
- Write ONLY: tools/check_all.py, tools/README.md (and tools/gen_manifest.py if strictly
  forced — it should not be).
- Do NOT add CLI flags, config files, or new files under tools/.
- Do not break the frozen exit-code contract or rendering ("clean is silent").
- Keep additions ~15-25 LOC in check_all.py. After your change run:
    python3 -m unittest tests.test_archive_skip tests.test_manifest_archive -v
  then the full suite:
    python3 -m unittest discover -s tests -p 'test_*.py'
  The 4 pre-existing TestLiveCorpus failures may remain (known transitional). Your goal:
  tests.test_archive_skip fully green (7/7), no NEW failures anywhere.
- Do not commit to git. Do not touch docs/, CHANGELOGS/, docs-manifest.yaml.

## Output
- Write /home/ea/council/sessions/sess-archive-tooling-2026-11-19/impl-run-2026-11-19T21-16-1/artifacts/code-files.json:
  { "files": [{"path": "tools/check_all.py", "modified": true, "signatures": ["_ARCHIVE_PREFIXES", "is_archived"]}, ...],
    "notes": "final wc -l of tools/*.py total" }
- Return short markdown: what you changed, where the predicate is applied, unit-test tail.
