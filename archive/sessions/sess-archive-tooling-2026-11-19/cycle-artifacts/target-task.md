# Target Task — Archive Audit Exclusion in Tooling (item 3, sess-archive-design-2026-11-19)

## Goal
Make the deterministic tooling enforce the Archive convention ratified in the specs
(docs/en/documenter-service/index.md §Archive + §Audit tool; docs/en/documentation-rules/index.md §2.6):
1. `tools/check_all.py` filters archived documents out of the audit battery by path prefix,
   so superseded content is not held to the rules live documents follow.
2. `tools/gen_manifest.py` prints archived documents in the manifest with their
   `Status: archive` frontmatter value (pass-through already present; lock it with a test).

## Background (norms just ratified — READ THESE FIRST)
- `docs/en/documenter-service/index.md`, section `## Archive`: dual-layer recognition —
  `Status: archive` frontmatter (manifest truth) + path prefix `docs/en/archive/` /
  `docs/ru/archive/` (audit exclusion marker). The exclusion is silent in audit rendering
  (the frozen "clean is silent" contract is untouched).
- Same file, `### Audit tool`: "Documents under the archive path prefix (`docs/en/archive/`,
  `docs/ru/archive/`) are filtered out before every check pass ... Every future member of
  the check battery MUST inherit this exclusion."
- `docs/en/documentation-rules/index.md` §2.6: archived docs stay manifest-tracked, follow
  §7.1 naming, are exempt from content-compliance audit and from scheduled translation duty.

## Acceptance criteria
- A helper/predicate `is_archived(rel)` (single source of truth for the prefix set
  `("docs/en/archive/", "docs/ru/archive/")`) exists in `tools/check_all.py`.
- NO check produces a finding for a file whose relative path starts with either archive
  prefix: content-compliance, cross-reference/link-integrity (both the `docs/en` corpus walk
  AND the `docs/ru` mirror walk in `check_link_integrity`), and any other path-driven walk over
  docs trees. The filter is applied at the walk/entry level so it cannot be bypassed by a
  check that iterates the corpus list.
- With an archived fixture present (e.g. `docs/en/archive/foo/index.md` with deliberately
  non-compliant content: unresolvable §cross-refs, missing changelog), a full `check_all.py`
  run reports ZERO findings attributable to that file.
- `gen_manifest.py --write` emits an entry for `docs/en/archive/foo/index.md` whose `status:`
  is exactly `archive` and whose `path:` is the archive path (pass-through of frontmatter, no
  special-casing, no drop).
- Existing behavior for NON-archived docs is unchanged; the existing test suite stays green.
- Exit-code contract preserved: still 0/1/2, still advisory, still read-only.

## Target files (WRITE WHITELIST — operator-confirmed)
- `tools/check_all.py`            (existing file, explicitly listed by operator)
- `tools/gen_manifest.py`         (existing file, explicitly listed by operator)
- `tests/test_archive_skip.py`    (NEW — archive-exclusion tests for check_all; unittest)
- `tests/test_manifest_archive.py`(NEW — gen_manifest archive pass-through test; unittest)
- `tools/README.md`               (prose-contract sync per AGENTS.md §1.7 — mandatory in same
                                   changeset: document the archive exclusion of check_all)

## Allowed paths = exactly the whitelist above. Everything else is READ-ONLY.
## Forbidden (governance deny-list — never write):
`docs/`, `docs-manifest.yaml`, `CHANGELOGS/`, `fallback/`, `AGENTS.md`, `defaults/`,
`.opencode/`, `documenter_policy.yml`, `archive/`, `sessions/`, `.agents/skills/documentation/`.

## Framework / test command
- Repository uses **unittest**, not pytest. New tests: `python3 -m unittest tests.test_archive_skip -v`
  and `python3 -m unittest tests.test_manifest_archive -v`.
- Full regression: `python3 -m unittest discover -s tests -p 'test_*.py'` (must stay green;
  note: the repo has pre-existing audit findings under `docs/` but the PYTHON test suite passes).
- Test fixtures: build a temp tree in-process (tempfile + shutil) mimicking docs/en + docs/ru,
  invoke check_all's public entry (e.g. its main/report function or the corpus+check functions)
  against that temp root. Do NOT depend on the live repo `docs/` tree for the new assertions
  (anti-fragility), but you may assert the live tree contains no archive fixtures yet.

## Determinism / style constraints
- Keep total executable-tooling LOC within OP-2 ceiling (~3,600; currently 3,459). The
  archive filter should be small (~15-20 LOC in check_all.py). Report the final `wc -l` of
  tools/*.py in the code-files.json notes.
- Single operator-facing command preserved: no new CLI flags required; if you add none, the
  acceptance stays. Do NOT add a `--no-archive-skip` flag (OP-2).
- One constant `_ARCHIVE_PREFIXES` tuple; do not scatter string literals across checks.
