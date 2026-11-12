# tools/ — deterministic documentation tooling

Operational scripts for the Council documentation pipeline (implementation
files, outside Documenter scope per `AGENTS.md` §1.6). Current phase: Stage A
+ B of plan `sess-doc-reliability-algo`.

## Tools

| Tool | Purpose | Status |
| --- | --- | --- |
| `docmeta.py` | Parse and validate document frontmatter headers (required fields, versions, changelog refs). Library used by the tools below. | operational (Stage A) |
| `gen_manifest.py` | Generate `docs-manifest.yaml` from document frontmatter (`--write` / `--check`, byte-exact, atomic). Sole writer of the manifest. | operational (Stage A) |
| `check_all.py` | Deterministic compliance validator CLI (see rule coverage below). Exit codes: 0 clean, 1 findings, 2 internal error. | operational (Stage B) |
| `hooks/pre-commit` | Versioned pre-commit hook running `check_all.py`; warn-only (soak) by default, blocking once the marker file exists. | operational, soak mode (Stage B) |
| `install-hooks.sh` | One-time setup per clone: sets `core.hooksPath tools/hooks` and self-checks. | operational (Stage B) |
| `tests_helpers.py` | Shared slugify / line-accounting rules used by `check_all.py` and its tests. | operational |

## Rule coverage (check_all.py)

`check_all.py` implements deterministic **rules 1, 2, 4, 6** from
`docs/en/documenter-service/mvp-interfaces.md` (line count, changelog
existence, cross-reference anchors, manifest parity) plus the **naming and
schema** checks. Rules **3 (glossary terms)** and **5 (abstraction
consistency)** remain skill/AI-reserved judgments and are NOT implemented
here — never describe this tool as implementing "rules 1–6"
(see `AGENTS.md` §8).

## Dependencies

Python **3.11+**, standard library plus **PyYAML** only. No other third-party
imports are permitted in `tools/*.py`.

## Installation (once per clone)

```bash
bash tools/install-hooks.sh
```

This sets `git config core.hooksPath tools/hooks` (repository-local) so the
versioned hook runs on commit; nothing is copied into `.git/hooks`.

## Soak → block flip

The hook starts in **WARN-ONLY (soak)** mode: findings are printed, commits
always pass. After ~10 clean documentation commits with no false positives,
the operator flips it to blocking mode manually:

```bash
touch tools/hooks/block-mode.flag    # flip to BLOCK
rm tools/hooks/block-mode.flag       # back to warn-only
```

In BLOCK mode a commit is rejected when `check_all` reports a
**high**-severity finding or crashes (exit 2); medium/low findings are
printed as warnings. The hook is a best-effort gate only — `git commit
--no-verify` bypasses it (see consensus `sess-doc-reliability-algo`).
