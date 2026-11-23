# Target Task — Cycle B: .council/ isolated installation layout for dist scripts

Session: sess-dist-isolated-install-2026-11-22 (operator-approved consensus 2026-11-22)
Run: impl-run-2026-11-22T15-40-02-1
Worktree (absolute): /home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-22T15-40-2
Cycle A (check_all --core-root) is MERGED (a643152) and available in this worktree.

## Goal

Rewire the Council distribution so a host install places ALL framework files under
`.council/` (zero intersection with the host tree except mandated wiring), per the
consensus layout:

```
.council/
├── docs/en/<core-docs>/          (documentation-rules, documenter-service,
│                                  translation-project, protocol-core, glossary)
├── CHANGELOGS/                   (core seed changelogs)
├── tools/                        (audit tools incl. hooks/)
├── skills/                       (was .agents/skills/ — registered via opencode.jsonc)
├── vendor/techdoc-translator/
├── defaults/translation.lock
├── fallback/
├── docs-manifest.yaml            (core manifest, generated with gen_manifest --root .council)
├── version.lock, core-manifest.txt, update.sh
└── backup-<ts>/
```

Host root receives ONLY:
- `AGENTS.md` (template, thin, references `.council/` paths) — already template-owned
- `opencode.jsonc` Council wiring block: `"skills": ["./.council/skills"]`
  (merge into existing host config if present; if host config exists and has a
  `skills` array, append the entry unless already present; never clobber other keys)
- `.opencode/agents/selector.md` (harness-fixed location; unchanged content)
- root `.gitignore` managed block (see AC-7)
- host `docs-manifest.yaml` + host `docs/en/project-concept/` + host CHANGELOGS seed (templates, unchanged behavior)

## Acceptance criteria

AC-1  build.sh: `core-manifest.txt` entries carry the `.council/` prefix
      (e.g. `.council/tools/check_all.py`). Archive `core/` keeps its current
      relative layout (no .council/ in the archive); the prefix is manifest-only.
      update.sh/install.sh derive archive src paths by stripping the `.council/`
      prefix from the manifest entry.

AC-2  install.sh (init and overlay): every core item lands under `<target>/.council/`
      (docs, CHANGELOGS, tools, skills from core/.agents/skills → .council/skills,
      vendor, defaults, fallback). Host root gets none of these paths.
      Overlay never overwrites existing host files outside `.council/`; inside
      `.council/` overlay still merges core files.

AC-3  install.sh writes/merges the opencode config wiring: creates `opencode.jsonc`
      with `"$schema"`, `"$comment"` (Council-managed marker) and
      `"skills": ["./.council/skills"]` if absent; if host opencode.json(c) exists,
      adds the skills entry (and `./.council/skills` only once) without removing
      host keys; if a host file exists WITHOUT a skills array it is left untouched
      with a loud warning telling the operator to add the entry manually
      (never silently reformat a host config).
      `.opencode/agents/selector.md` installed as today (skip-if-exists).

AC-4  install.sh generates the CORE manifest at `.council/docs-manifest.yaml`
      (python3 .council/tools/gen_manifest.py --root <target>/.council --write) and
      the HOST manifest at root only when the host has docs to register (existing
      behavior kept: generate when docs-manifest.yaml absent).

AC-5  install.sh success-verification checks the NEW paths
      (.council/tools/check_all.py, .council/update.sh, AGENTS.md,
      .council/fallback/index.md, .council/docs/en/documentation-rules/index.md)
      and prints the "Where is Council?" box (docs/tools/skills/updater locations).

AC-6  update.sh works with `.council/`-prefixed manifest entries end-to-end:
      backup into `.council/backup-<ts>/` storing entries verbatim (prefix kept);
      apply with dst = manifest entry verbatim; orphan removal removes prefixed
      paths from the host; final restore hint prints the layout-aware command
      `cp -R .council/backup-<ts>/* .` AND writes restore-instructions.txt
      inside the backup dir containing that exact command.

AC-7  install.sh appends a Council-managed block to host `.gitignore` (create if
      missing, idempotent — marker comment `# Council framework (managed block)`,
      never duplicated): lines `.council/backup-*/`, `.council/**/__pycache__/`,
      `.council/telemetry/**/*.jsonl`, `**/techdoc-translator/.env`.

AC-8  Pre-flight (update.sh): before touching anything, verify `.council/` exists
      and is a real directory (not a symlink) → else exit 1 with clear message;
      verify version.lock + core-manifest.txt readable (existing checks kept).

AC-9  hooks: tools/install-hooks.sh accepts an optional hooks dir argument
      (default tools/hooks) and sets core.hooksPath to it; tools/hooks/pre-commit
      resolves check_all.py location-relative from the hook file itself
      (BASH_SOURCE → ../check_all.py) so it works from .council/tools/hooks;
      falls back to <root>/tools/check_all.py if the location-relative path is
      absent (backward compat for Council's own repo).

AC-10 test-dry-run.sh updated for the new layout (install→update→restore→overlay
      smoke) and MUST exit 0. tests/test_dist_composition.py rewritten for the
      new layout and MUST pass; existing assertions about core-vs-template
      ownership semantics (Variant B: no RU, no v0.x specs) must be kept, only
      re-pathed.

AC-11 Council's OWN repo keeps working unchanged: `python3 tools/check_all.py --root .`
      still exit 0 in the main tree; existing tests (tests.test_check_all,
      tests.test_install_hooks) stay green; tools/check_all.py default --root
      resolution (parent of tools/) untouched.

## Target files (whitelist — ONLY writable paths; operator-approved via consensus action items)

- dist/build.sh
- dist/install.sh
- dist/update.sh
- dist/test-dry-run.sh
- tools/install-hooks.sh
- tools/hooks/pre-commit
- tests/test_dist_composition.py (existing file — explicitly listed)
- tests/test_install_hooks.py (existing file — explicitly listed, if needed for AC-9)
- tests/test_dist_isolated_layout.py (new — Cycle B test file)

Read-only reference: dist/README.md, dist/RUNBOOK.md (prose sync is a SEPARATE
changeset after code merge — do not touch docs prose in this cycle), everything
under the unconditional deny list (docs/, CHANGELOGS/, fallback/, AGENTS.md,
defaults/, .opencode/, sessions/, .agents/).

## Test commands

    python3 -m unittest tests.test_dist_isolated_layout -v      # new suite
    python3 -m unittest tests.test_dist_composition -v          # rewritten
    python3 -m unittest tests.test_install_hooks -v             # AC-9
    bash dist/test-dry-run.sh                                    # exit 0 (AC-10)

Framework: unittest from worktree root. Build helper pattern from
tests/test_dist_composition.py (build_archive + temp host dirs) is the style to reuse.

## Environment facts (orchestrator-verified)

- update.sh already implements MF-3 union orphan removal; keep it, only prefix-aware.
- install-hooks.sh hardcodes `git config core.hooksPath tools/hooks` and checks
  `tools/hooks/pre-commit` under ROOT; pre-commit hook computes
  ROOT=git rev-parse --show-toplevel then ROOT/tools/check_all.py (breaks under
  .council/ — AC-9 fixes it).
- build.sh line ~298: `find . -type f | sed 's|^\./||' > ../core-manifest.txt`
  (inside core/ staging) — AC-1 adds the `.council/` prefix here.
- Archive core/ currently stages: tools, .agents, vendor, defaults, 5 docs/en dirs,
  archive guard, CHANGELOGS seeds, fallback.
- templates/: AGENTS.md.template, docs/en/project-concept, CHANGELOGS seed.
- .opencode/agents/selector.md ships from core (.opencode dir is NOT on the deny
  list for the ARCHIVE staging inside dist scripts, but .opencode/ in the WORKTREE
  tree is deny-listed; install.sh writes into the HOST target dir, which is a temp
  dir under tests — allowed. Do not write into the worktree's own .opencode/.)

## Escalation triggers (report instead of hacking around)

- Any test that would force weakening an existing audit/ownership assertion.
- Any need to touch deny-listed paths.
