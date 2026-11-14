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
| `bump_version.py` | Deterministic version writer: frontmatter `Version:` → changelog entry (prepend) → manifest (regenerated last); atomic writes with rollback. Dispatched only by the Documentation Worker skill after operator Approve (AGENTS.md §5.1). Exit codes: 0 success or `--dry-run`, 2 refusal/rolled back. | operational (Stage D) |
| `classify_bump.py` | Read-only diff→bump classifier ("AI proposes — algorithm records"): proposes `patch`/`minor`/`major` for a full candidate document; never writes documents, changelogs, or the manifest — only its JSONL decision log `tools/state/classify_log.jsonl`. Reuses the `check_all.py` §-reference resolver and `gen_manifest.build_entries` path resolution; ambiguous → minor with a §7.5 warning; escalations printed in AGENTS.md §6 format; `--report` gate: escalation rate > 20% → `classifier requires redesign`, exit 3. Exit codes: 0 classification/identical/report-within-gate, 2 usage/refusal, 3 gate exceeded. | operational (Stage C) |
| `hooks/pre-commit` | Versioned pre-commit hook running `check_all.py`; warn-only (soak) by default, blocking once the marker file exists. | operational, soak mode (Stage B) |
| `local-translate.sh` / `local_translate.py` | Glossary-aware EN→RU translation via a local OpenAI-compatible LLM server (preflight, paragraph chunking, post-processing). See §Translation backend dependency below. | operational |
| `install-hooks.sh` | One-time setup per clone: sets `core.hooksPath tools/hooks` and self-checks. | operational (Stage B) |
| `tests_helpers.py` | Shared slugify / line-accounting rules used by `check_all.py` and its tests. | operational |
| `check_drift.py` | Deterministic EN↔RU structural comparison: 8 rules (heading count/depth, table rows/blocks, code fences, list markers, inline code count/set, hr count/pos, metadata fingerprint, EN-leakage). Used by full mode tests and e2e. | operational (M2) |
| `tests/` | Translation test suite: unit tests (`test_unit.py`), mock backend (`gen_mock_responses.py` + `responses.json`), unified runner (`run_translate_tests.sh`), live e2e (`e2e_live.sh`). | operational (M3) |
| `../documenter_service/` | Documenter Service MVP scaffold (Tier 0–1 read-only): `audit()`/`status()`/`delegate(preview:true)` поверх tools-ядра, без форка правил; status: scaffold (Stage 4, sess-doc-reliability-algo). | scaffold (Stage 4) |

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

## Translation backend dependency

`local-translate.sh` / `local_translate.py` require an **OpenAI-compatible**
LLM server running locally (or a remote one with `NEURALDEEP_BASE_URL`
override).

### Required server

A typical vLLM-based server:

```bash
vllm serve Qwen3.6-35B-A3B-NVFP4 --served-model-name Qwen3.6-35B-A3B-NVFP4 \
    --chat-template-kwargs '{"enable_thinking":false}'
```

Health-check command (used internally by preflight):

```bash
curl -sf http://127.0.0.1:8000/v1/models
```

Default server URL: `http://127.0.0.1:8000/v1` (`NEURALDEEP_BASE_URL`).
Default model: `Qwen3.6-35B-A3B-NVFP4` (`CLOUD_MODEL`).

The preflight step (exit 3) verifies:
1. `/models` endpoint is reachable (≤ 3 s).
2. The configured model name is listed among `data[].id` entries.

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | All lines translated successfully |
| 1 | Invalid arguments or Python error (e.g. no input) |
| 2 | Cloud backend API key missing |
| 3 | Local model server unreachable / model not found on server |
| 4 | **Translation incomplete** — one or more lines failed; `stdout` still contains partial output; stderr has `[exit] N lines failed translation` |

### Flags

**`--summary-json`** — After translation, prints a single JSON object to stderr:

```json
{"ok": 30, "skip": 5, "fail": 0, "backend": "cloud", "model": "Qwen3.6-35B-A3B-NVFP4", "prompt_version": "2026.11-r1", "gloss_applied": 12}
```

| Field | Description |
| --- | --- |
| `ok` | Lines successfully translated |
| `skip` | Structural / metadata lines passed through untranslated |
| `fail` | Lines where model output matched input exactly (treated as fail) |
| `backend` | Active backend (`cloud` or `ollama`) |
| `model` | Model name used |
| `prompt_version` | Prompt spec version (see `EXPERIMENTS.md` E-003, E-004) |
| `gloss_applied` | Total glossary term replacements performed by `enforce_glossary` |

### Run log (`TRANSLATE_RUN_LOG`)

Set `TRANSLATE_RUN_LOG` to a file path to append one JSONL record per run:

```json
{"timestamp":"2026-11-14T12:00:00+0000","backend":"cloud","model":"Qwen3.6-35B-A3B-NVFP4","prompt_version":"2026.11-r1","ok":30,"skip":5,"fail":0,"exit_reason":"ok","gloss_applied":12,"input_lines":35}
```

**No default file is created** — the environment variable must be set explicitly.

## Translation test layers (M2–M4)

Translation scripts ship with a layered test suite that validates correctness
without requiring a live model backend.

### Layer overview

| Layer | What it tests | How it runs |
| --- | --- | --- |
| Unit (M3) | `needs_skip()`, `enforce_glossary()`, `restore_heading_prefix()`, `restore_list_marker()` | `tools/tests/test_unit.py` — stdlib `unittest`, no deps |
| Mock (M3) | End-to-end translation via mock backend → structural validation via `check_drift.py` | `tools/tests/run_translate_tests.sh full` |
| Live (M3) | Real model call, candidate generation, `check_drift` EN-vs-candidate | `tools/tests/e2e_live.sh` |
| Drift CLI (M2) | Deterministic EN↔RU structural comparison: 8 rules (heading count/depth, table rows/blocks, code fences, list markers, inline code count/set, hr count/pos, metadata fingerprint, EN-leakage) | `python3 tools/check_drift.py <en_path> <ru_path> [--json]` |
| Docmeta import (M4) | `local_translate.py` imports `KNOWN_KEYS` from `docmeta.py` with fallback | `grep -n "docmeta" tools/local_translate.py` |

### Running tests

```bash
# Quick mode — unit tests only (< 5 s, no model, no network)
tools/tests/run_translate_tests.sh quick

# Full mode — unit tests + mock layer (local_translate.py → candidate → check_drift)
tools/tests/run_translate_tests.sh full

# Live e2e — real model call on source → check_drift EN-vs-candidate
tools/tests/e2e_live.sh
```

### Mock backend

The mock backend (`TRANSLATE_BACKEND=mock`) reads pre-generated responses from
`tools/tests/fixtures/scenario/responses.json`, keyed by `sha256(user_prompt)`.
Mock responses preserve inline code (backticks), headings, list markers, and
table structure; body text lines receive Cyrillic + `[RU]` markers.

### Drift check exit codes

| Code | Meaning |
| --- | --- |
| 0 | No structural drift found (EN and RU match on all 8 deterministic rules) |
| 1 | Findings present — structural differences detected |
| 2 | Internal error (file read failure, missing file) |

When checking EN vs EN (same file), `check_drift` exits 1 and reports
`en-leakage` for every non-structural body line, confirming the English-in-RU
detection works.
