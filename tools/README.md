# tools/ — deterministic documentation tooling

Operational scripts for the Council documentation pipeline (implementation
files, outside Documenter scope per `AGENTS.md` §1.6). Current phase: Stage A
+ B + C + D of plan `sess-doc-reliability-algo`.

## Tools

| Tool | Purpose | Status | Contract |
| --- | --- | --- | --- |
| `docmeta.py` | Parse and validate document frontmatter headers (required fields, versions, changelog refs). Library used by the tools below. | operational (Stage A) | `docs/en/translation-project/index.md` (header schema) |
| `gen_manifest.py` | Generate `docs-manifest.yaml` from document frontmatter (`--write` / `--check`, byte-exact, atomic). Sole writer of the manifest. | operational (Stage A) | `tools/gen_manifest.py` (CLI contract) |
| `check_all.py` | Deterministic compliance validator CLI (see rule coverage below). Rule groups: line-count, changelog, cross-ref, manifest-parity, naming, schema, link-integrity, **vendor-integrity** (vendored engine tree must match the pinned release, or its deviation must be recorded as a patch artifact under `documenter/artifacts/translation/patches/` with a `# patched:` lock annotation; findings informational, medium). Optional `--core-root DIR`: a second, read-only resolution space — when a docs/en reference token fails to resolve in the audited corpus it is looked up under `<DIR>/docs/en/` (host installs audit with `--root . --core-root .council`; the core corpus is never merged into the host corpus — no parity/orphan exposure; host root wins on same-path collisions; missing `<DIR>/docs/en` → exit 2). Includes the **link-integrity** step: docs→manifest references are hard-fail (high); there is no code→docs scan any more (the `documenter_service/` / `operator_ingress/` packages were deleted in the 2026-11-19 reconstruction; `LINK_INTEGRITY_CODE_DIRS` is empty). Exit codes are informational, never gating: `0` clean (silent when clean), `1` findings reported with none high, `2` at least one high reported (critical) — or internal error / bad `--rule` token (distinguished on output: `check_all: INTERNAL ERROR` / `ERROR:`, never the `🚨` marker). `--severity` sets the minimum **reported** severity (default `low`; `--strict` ≡ `--severity warning`). Human rendering: clean = silent; otherwise `⚠ findings: N` / `🚨 critical: N` header(s) plus severity-sorted hint lines obeying the token contract. The agent runs it as the mandatory advisory pre-commit audit (silent when clean); the operator runs it post-commit on demand (OP-3). | operational (frozen contract, Phase 0) | `tools/check_all.py` (CLI contract) |
| `bump_version.py` | Deterministic version writer: frontmatter `Version:` → changelog entry (prepend) → manifest (regenerated last); atomic writes with rollback. Dispatched only by the Documentation Worker skill after operator Approve (documentation-rules §5.1). Exit codes: 0 success or `--dry-run`, 2 refusal/rolled back. | operational (Stage D) | `tools/bump_version.py` (CLI contract) |
| `classify_bump.py` | Read-only diff→bump classifier ("AI proposes — algorithm records"): proposes `patch`/`minor`/`major` for a full candidate document; never writes documents, changelogs, or the manifest — only its JSONL decision log `tools/state/classify_log.jsonl`. Reuses the `check_all.py` §-reference resolver and `gen_manifest.build_entries` path resolution; ambiguous → minor with a §7.5 warning; escalations printed in documentation-rules §6 format; `--report` gate: escalation rate > 20% → `classifier requires redesign`, exit 3. Exit codes: 0 classification/identical/report-within-gate, 2 usage/refusal, 3 gate exceeded. | operational (Stage C) | `tools/classify_bump.py` (CLI contract) |
| `hooks/pre-commit` | Versioned pre-commit hook running `check_all.py`; warn-only by default (best-effort advisory gate, never a hard block under OP-3; bypassable). Resolves `check_all.py` location-relative from the hook file itself (`../check_all.py`), falling back to `<repo-root>/tools/check_all.py` — so the same hook works both in the source repo (`tools/hooks`) and on hosts (`.council/tools/hooks`). Root selection: the audited root is the checker's parent-of-parent, except on host installs where that path (`.council/`) differs from the git root — then the hook audits the host root with `--core-root .council` (dual-root), so host documents are checked against the host manifest instead of the core one. | operational, warn-only | `tools/hooks/pre-commit` |
| `translation_status.py` | Deterministic rebuild of translation provenance: per-document sidecar + `STATUS.md` status index from stored run reports under `documenter/artifacts/translation/runs/` (ADR-014). Idempotent; exit 0 ok, 2 nothing to do. | operational | `tools/translation_status.py` (CLI contract) |
| `check_drift.py` | Deterministic EN↔RU structural comparison — the sole Council-side structural judge; translation itself is external (ADR-014). Drift mode: structural rules (headings, tables, fences, etc.). `--phase4` mode: four translation write-gates (`phase4-fail`, `phase4-parity`, `phase4-identity`, `phase4-glossary`). In phase4, `--glossary` flag is mandatory (no implicit default): `--glossary none` → gate 4 vacuous (exit 0); missing/invalid path → exit 2. Provenance line always printed: `glossary: path=<resolved|none> | terms=<N> | matched=<M> | status=checked|vacuous` (human: stdout tail; `--json`: stderr only). | operational | `tools/check_drift.py` (CLI + phase4 gates), `.agents/skills/documentation/SKILL.md` (phase4 contract) |
| `record_vendor_patch.py` | Records the current working-tree deviation of the vendored engine (`defaults/translation.lock` → `local_path`) as a `.patch` artifact under `documenter/artifacts/translation/patches/`. Makes a local vendor patch visible to the `vendor-integrity` rule instead of a silent working-tree edit. Exit 0 written, 1 usage, 2 no deviation / git error. | operational | `tools/check_all.py` (`vendor-integrity` rule), `AGENTS.md` §1.7 |
| `install-hooks.sh` | One-time setup per clone: sets `core.hooksPath <hooks-dir>` and self-checks. Optional first argument sets the hooks dir (default `tools/hooks`; hosts pass `.council/tools/hooks`). | operational (Stage B) | `tools/install-hooks.sh` |
| `tests_helpers.py` | Shared slugify / line-accounting rules used by `check_all.py` and its tests. | operational | `tools/tests_helpers.py` |
| `tests/` | (empty after ADR-014; the translation test suite moved to the external project) | removed | — |
| `collect_telemetry.sh` | Local opt-in diagnostics collector: reads JSONL from stdin, redacts sensitive data, bundles to gzip-tar. Manual, no network, no daemon. | operational | `dist/RUNBOOK.md` §Telemetry |

<!-- check_parity.py displaced by check_drift.py phase4 rules — 2026-11-19, impl-guide Phase 1 -->

**Safety:** `check_all.py` does not initiate telemetry collection; the collector
is not git-aware — it never touches `.git/` or registers hooks, and it never
transmits data.

## Rule coverage (check_all.py)

`check_all.py` implements deterministic **rules 1, 2, 4, 6** from
`docs/en/documentation-rules/index.md` §8 (line count, changelog
existence, cross-reference anchors, manifest parity) plus the **naming and
schema** checks and the **link-integrity** CI guard (O-3):

- **docs→manifest (hard fail):** a document under `docs/en` or `docs/ru`
  whose body references a `docs/...md` path that is missing or not
  registered in `docs-manifest.yaml` yields a high-severity
  `docs-manifest-link` finding (critical, exit 2). Precedent for a hard CI on a prose
  invariant: ADR-003.

Rules **3 (glossary terms)** and **5 (abstraction
consistency)** remain skill/AI-reserved judgments and are NOT implemented
here — never describe this tool as implementing "rules 1–6"
(see `documentation-rules` §8).

## Archive exclusion

Documents under `docs/en/archive/` and `docs/ru/archive/` are silently
excluded from every check pass in `check_all.py` (single source:
`_ARCHIVE_PREFIXES` constant + `is_archived()` predicate). The predicate
uses exact prefix matching — paths like `docs/en/archive-notes/` are
**not** excluded. Future members of the check battery MUST inherit this
exclusion so archived content is never held to live-document rules.

## Dependencies

Python **3.11+**, standard library plus **PyYAML** only. No other third-party
imports are permitted in `tools/*.py`.

## Installation (once per clone)

```bash
bash tools/install-hooks.sh
```

This sets `git config core.hooksPath tools/hooks` (repository-local) so the
versioned hook runs on commit; nothing is copied into `.git/hooks`.

## On hosts (installed via `dist/`)

On a host project the entire framework lives under `.council/` (isolated
layout, consensus `sess-dist-isolated-install-2026-11-22`): these tools run
from `.council/tools/`, e.g.

```bash
python3 .council/tools/check_all.py --root . --core-root .council
```

where `--root .` audits the host corpus and `--core-root .council` resolves
references into the core docs without merging the two corpora. Hosts generate
two manifests: `.council/docs-manifest.yaml` (core) and `docs-manifest.yaml`
(host root). Hooks on hosts use `core.hooksPath=.council/tools/hooks`; the
block-mode flag lives at `.council/tools/hooks/block-mode.flag`.

## Soak → block flip

The hook starts in **WARN-ONLY (soak)** mode: findings are printed, commits
always pass. After ~10 clean documentation commits with no false positives,
the operator flips it to blocking mode manually:

```bash
touch tools/hooks/block-mode.flag    # flip to BLOCK
rm tools/hooks/block-mode.flag       # back to warn-only
```

In BLOCK mode a commit is rejected when `check_all` reports a
**high**-severity finding (`🚨 critical`, exit 2) or crashes / reports an
internal error (exit 2 without the critical marker, fail-closed); findings at
medium/low or below are printed as warnings (exit 1, never blocking — OP-3).
The hook is a best-effort gate only — `git commit
--no-verify` bypasses it (see consensus `sess-doc-reliability-algo`).

## Translation (external — ADR-014)

The EN→RU translation engine is no longer part of `tools/`. It lives in the
standalone **Translation Project** (`techdoc-translator`), consumed as a
**vendored distribution** unpacked into `vendor/techdoc-translator/` from the
project's distributable archive (built by `scripts/build_dist.sh`). The invocation
path is read from `defaults/translation.lock` (`local_path`), which defaults to
the vendored copy. See `docs/en/translation-project/index.md` (procedure) and
`docs/en/translation-project/contract.md` (flags, report schema, exit codes
0–6).

To update the vendored copy from the Translation Project repository:

```bash
python3 tools/sync_translator.sh   # builds archive, verifies, unpacks, updates lock
```

Council keeps the **verification** layer:
- `check_drift.py` — the sole deterministic EN↔RU structural judge (exit 0 clean,
  1 findings, 2 internal error).
- `translation_status.py` — rebuilds provenance sidecars + `STATUS.md` from stored
  run reports under `documenter/artifacts/translation/runs/`.
- `tests/translate-fixtures/regression_test.sh` — Council-side integration test:
  drives the pinned external CLI over 4 fixtures and checks metadata parity,
  code-token preservation, and contamination traps. Runs against the local
  OpenAI-compatible dev server (endpoint pinned to loopback; no external calls).

The engine's own backend/model configuration lives in its `.env` (never read by
Council, never committed — see `.gitignore`). Council-side translation unit/mock/live
tests were removed with the engine; the engine ships its own test suite
(`tests/smoke.sh`, `tests/test_unit.py` in the vendored distribution).
