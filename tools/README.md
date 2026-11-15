# tools/ — deterministic documentation tooling

Operational scripts for the Council documentation pipeline (implementation
files, outside Documenter scope per `AGENTS.md` §1.6). Current phase: Stage A
+ B + C + D of plan `sess-doc-reliability-algo`.

## Tools

| Tool | Purpose | Status |
| --- | --- | --- |
| `docmeta.py` | Parse and validate document frontmatter headers (required fields, versions, changelog refs). Library used by the tools below. | operational (Stage A) |
| `gen_manifest.py` | Generate `docs-manifest.yaml` from document frontmatter (`--write` / `--check`, byte-exact, atomic). Sole writer of the manifest. | operational (Stage A) |
| `check_all.py` | Deterministic compliance validator CLI (see rule coverage below). Exit codes: 0 clean, 1 findings, 2 internal error. | operational (Stage B) |
| `bump_version.py` | Deterministic version writer: frontmatter `Version:` → changelog entry (prepend) → manifest (regenerated last); atomic writes with rollback. Dispatched only by the Documentation Worker skill after operator Approve (documentation-rules §5.1). Exit codes: 0 success or `--dry-run`, 2 refusal/rolled back. | operational (Stage D) |
| `classify_bump.py` | Read-only diff→bump classifier ("AI proposes — algorithm records"): proposes `patch`/`minor`/`major` for a full candidate document; never writes documents, changelogs, or the manifest — only its JSONL decision log `tools/state/classify_log.jsonl`. Reuses the `check_all.py` §-reference resolver and `gen_manifest.build_entries` path resolution; ambiguous → minor with a §7.5 warning; escalations printed in documentation-rules §6 format; `--report` gate: escalation rate > 20% → `classifier requires redesign`, exit 3. Exit codes: 0 classification/identical/report-within-gate, 2 usage/refusal, 3 gate exceeded. | operational (Stage C) |
| `hooks/pre-commit` | Versioned pre-commit hook running `check_all.py`; warn-only (soak) by default, blocking once the marker file exists. | operational, soak mode (Stage B) |
| `translation_status.py` | Deterministic rebuild of translation provenance: per-document sidecar + `STATUS.md` status index from stored run reports under `documenter/artifacts/translation/runs/` (ADR-014). Idempotent; exit 0 ok, 2 nothing to do. | operational |
| `check_drift.py` | Deterministic EN↔RU structural comparison (see below) — the sole Council-side structural judge; translation itself is external (ADR-014). | operational |
| `install-hooks.sh` | One-time setup per clone: sets `core.hooksPath tools/hooks` and self-checks. | operational (Stage B) |
| `tests_helpers.py` | Shared slugify / line-accounting rules used by `check_all.py` and its tests. | operational |
| `check_drift.py` | Deterministic EN↔RU structural comparison: 8 rules (heading count/depth, table rows/blocks, code fences, list markers, inline code count/set, hr count/pos, metadata fingerprint, EN-leakage). Used by full mode tests and e2e. | operational (M2) |
| `tests/` | (empty after ADR-014; the translation test suite moved to the external project) | removed |
| `../documenter_service/` | Documenter Service MVP scaffold (Tier 0–1 read-only): `audit()`/`status()`/`delegate(preview:true)` поверх tools-ядра, без форка правил; status: scaffold (Stage 4, sess-doc-reliability-algo). | scaffold (Stage 4) |

## Rule coverage (check_all.py)

`check_all.py` implements deterministic **rules 1, 2, 4, 6** from
`docs/en/documenter-service/mvp-interfaces.md` (line count, changelog
existence, cross-reference anchors, manifest parity) plus the **naming and
schema** checks. Rules **3 (glossary terms)** and **5 (abstraction
consistency)** remain skill/AI-reserved judgments and are NOT implemented
here — never describe this tool as implementing "rules 1–6"
(see `documentation-rules` §8).

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

## Translation (external — ADR-014)

The EN→RU translation engine is no longer part of `tools/`. It lives in the
standalone **Translation Project** (`techdoc-translator`), invoked through its
versioned CLI contract. See `docs/en/translation-project/index.md` (procedure)
and `docs/en/translation-project/contract.md` (flags, report schema, exit codes
0–6). The pinned checkout is recorded in `defaults/translation.lock`.

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
Council). Council-side translation unit/mock/live tests were removed with the
engine; the engine ships its own test suite (see its repository).
