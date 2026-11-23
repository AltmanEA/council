# Translation Project — CLI Contract Specification

id: translation-project-contract
Version: 0.2.0
Status: draft
Abstraction: format
changelog-path: CHANGELOGS/translation-project.changes.md
references:
  - planned-architecture-decisions
  - glossary
  - translation-project
allow_non_index_paths: true

---

## CLI Flags

The Translation Project CLI accepts the following flags:

| Flag | Required | Description |
|------|----------|-------------|
| `--input-en <PATH>` | yes | Source English markdown file path |
| `--output-ru <PATH>` | yes | Output Russian markdown file path (temp during invocation) |
| `--glossary <PATH>` | no | Glossary file in markdown format (`**English** (Russian)`); generic parser, not Council-specific |
| `--report <PATH>` | no | Write JSON run report to file |
| `--allow-cloud` | no | Enable cloud backend mode; requires `TRANSLATE_API_KEY` / `TRANSLATE_API_BASE` |
| `--skip-pattern <REGEX>` | no | Skip lines matching regex (repeatable flag); used to preserve Council metadata |
| `--summary-json` | no | Print JSON summary to stderr (diagnostic) |
| `--version` | no | Print version info and exit (before translation) |
| `--contract-version <N>` | no | Check contract version; exit 5 if mismatch against lock file |
| `--help, -h` | no | Show help and exit |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TRANSLATE_BACKEND` | `local` | `local` or `cloud` |
| `TRANSLATE_API_BASE` | — | Cloud API base URL (cloud mode) |
| `TRANSLATE_API_KEY` | — | Cloud API key (cloud mode) |
| `TRANSLATE_MODEL` | — | Model name |
| `TRANSLATE_TEMP` | `0.2` | Sampling temperature |
| `TRANSLATE_TOP_P` | `0.95` | top_p parameter |
| `TRANSLATE_HINT_STYLE` | `plain` | `plain` / `verbose` / `strict` |
| `TRANSLATE_PROMPT` | `none` | `codeguard` option |
| `TRANSLATE_CHAT_KWARGS` | — | Extra JSON kwargs for chat request |
| `TRANSLATE_METADATA` | `0` | Translate metadata lines |
| `TRANSLATE_FORCE_SECTION` | — | Merge all prose into one block |
| `TRANSLATE_RUN_LOG` | — | JSON run-log file path |
| `REQUEST_TIMEOUT` | `120` | Curl timeout in seconds |
| `MAX_RETRIES` | `2` | Retries per chunk |
| `TOTAL_DEADLINE_SECONDS` | `0` | Global deadline (0 = off) |
| `TRANSLATE_MOCK_DIR` | — | Path to mock responses (testing) |

---

## Exit Codes

| Code | Name | Meaning | Recovery |
|------|------|---------|----------|
| 0 | success | Translation completed successfully (`ok` lines in report) | Proceed to Phase 4 write-gates |
| 1 | invalid input | Invalid input path, glossary parse error, or malformed file | Check source file and glossary format |
| 2 | usage error | Missing required flag, bad flag value, or cloud without `--allow-cloud` | Fix invocation arguments |
| 3 | backend unavailable | Local server down or cloud API unreachable | Check backend status (health-check / `.env`) |
| 4 | incomplete | Some lines failed translation (`fail > 0`) | No write; retry or reduce scope |
| 5 | contract mismatch | `--contract-version` does not match lock file version | Update lock file; do not proceed |
| 6 | report error | Failed to write the report JSON file | Check file permissions and disk space |

---

## Report JSON Schema

The run report written to `--report` path is a JSON object with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `ok` | int | Number of lines successfully translated |
| `skip` | int | Number of lines skipped (metadata, fenced code, etc.) |
| `fail` | int | Number of lines that failed translation |
| `backend` | string | Backend used: `local` or `cloud` |
| `model` | string | Model name that performed translation |
| `prompt_version` | string | Prompt version identifier (e.g. `2026.11-r5`) |
| `glossary_applied` | int | Number of glossary terms applied |
| `source_sha256` | string | SHA-256 hex of the input EN file |
| `output_sha256` | string | SHA-256 hex of the output RU file |
| `exit_code` | int | Process exit code (0 = success) |
| `contract_version` | string | Contract version that was verified |
| `timestamp` | string | ISO 8601 timestamp (UTC) |
| `message` | string | Human-readable summary message |

---

## Glossary Input Format

The `--glossary` argument expects a generic markdown glossary file. Each entry uses the format:

```markdown
**English term** (Russian equivalent) — optional description
```

The parser extracts the English and Russian pairs; no Council-specific metadata is required. Unknown terms in the source that have no glossary entry are translated without glossary mapping.

---

## Lock File Schema

The lock file (`defaults/translation.lock`) is a YAML file with the following structure:

```yaml
repo: AltmanEA/techdoc-translator
local_path: path/to/translate.sh
tag: v0.1.0
commit: <sha256-hex>
contract_version: "1.0.0"
mode: external|legacy
updated_by: <operator-id>
```

- `repo`: GitHub repository identifier.
- `local_path`: Absolute path to the CLI wrapper script.
- `tag`: Semver tag of the pinned release.
- `commit`: Commit SHA for the pinned version.
- `contract_version`: CLI contract version (integer, compared against `--contract-version`).
- `mode`: `external` (current external project) or `legacy` (rollback path).
- `updated_by`: Operator identifier who last updated the lock.

---

## Status Index & Sidecar Schemas

### Sidecar (`documenter/artifacts/translation/<id>.json`)

Derived from the run report with additional Council metadata:

| Field | Type | Description |
|-------|------|-------------|
| `api_version` | string | API version from report |
| `engine_version` | string | Engine version from report |
| `model` | string | Model that performed translation |
| `backend` | string | Backend used |
| `prompt_version` | string | Prompt version |
| `glossary_schema_version` | string | Glossary schema version |
| `ok` | int | Successful lines |
| `skip` | int | Skipped lines |
| `fail` | int | Failed lines |
| `glossary_applied` | int | Glossary terms applied (diagnostic only: known engine defect reports 0 even when terms were applied; authoritative term counts are the gate-4 provenance line `terms`/`matched`) |
| `ai_review` | string | Gate-5 AI quality review verdict: `passed` / `failed` / `not_run` (the Documentation Worker skill's mandatory AI quality review gate; `verified` status requires `passed`) |
| `source_sha256` | string | SHA-256 of EN source |
| `output_sha256` | string | SHA-256 of RU output |
| `target_id` | string | Council document ID |
| `ru_path` | string | Relative path to index-RU.md |
| `en_sha256_at_commit` | string | SHA-256 of EN file at commit time |
| `status` | string | Verification status: verified / unverified / drift / error-N |
| `write_gates` | object | Phase 4 gate results |
| `timestamp` | string | ISO 8601 timestamp |

### Status Index (`documenter/artifacts/translation/STATUS.md`)

Generated markdown table with columns: `id | status | model | prompt_version | backend | timestamp | report_ref`. Rebuilt deterministically from `runs/runs.jsonl` using `tools/translation_status.py`.
