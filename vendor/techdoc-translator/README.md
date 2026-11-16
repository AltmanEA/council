# techdoc-translator

Generic EN→RU markdown technical translator. Paragraph-based pipeline with
glossary-enforced terminology, code-span preservation, and line-parity output.

## Quickstart

```bash
# 1. Copy env template and edit
cp .env.example .env
# Edit .env: set TRANSLATE_API_BASE, TRANSLATE_API_KEY, etc.

# 2. Run
./translate.sh --input-en source.md --output-ru output.md --glossary glossary.md
```

## Distribution

Build a self-contained archive for use in another project (no registry, no
dependencies), then verify it:

```bash
scripts/build_dist.sh          # → dist/techdoc-translator-<version>.tar.gz
scripts/verify_dist.sh         # checksums, MANIFEST, smoke tests, stub round-trip
```

The archive bundles the engine, wrapper, docs, tests, `MANIFEST.txt` and
`SHA256SUMS`. Integration contract, platform requirements and vendoring
instructions: [docs/INTEGRATION.md](docs/INTEGRATION.md).

## Requirements

- Python 3.11+ (stdlib only)
- OpenAI-compatible server or Ollama-compatible endpoint

Example local server (vLLM or similar):

```bash
python -m vllm.entrypoints.api_server \
    --model generic-moe-model --port 8000 --api-key YOUR_KEY
```

## Usage

```bash
# CLI wrapper (recommended — loads .env, preflights API)
./translate.sh --input-en src.md --output-ru out.md --glossary terms.md

# Direct Python
python3 techdoc_translator.py --input-en src.md --output-ru out.md \
    --glossary terms.md --report run-report.json
```

### Flags

| Flag | Description |
|---|---|
| `--input-en PATH` | Source English markdown file (required) |
| `--output-ru PATH` | Output Russian markdown file (required) |
| `--glossary PATH` | Glossary file (`**English** (Russian)`) |
| `--report PATH` | Write JSON run report to file |
| `--allow-cloud` | Enable cloud backend mode |
| `--skip-pattern REGEX` | Skip lines matching regex (repeatable) |
| `--summary-json` | Print JSON summary to stderr |
| `--version` | Print version info and exit |
| `--contract-version N` | Check contract version (exit 5 if mismatch) |
| `--help, -h` | Show help |

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Invalid input / missing args / parse error |
| 2 | Missing config / cloud not allowed |
| 3 | Backend unavailable (server not running) |
| 4 | Incomplete translation (some lines failed) |
| 5 | Contract version mismatch |
| 6 | Report write failure |

## Glossary format

Two accepted formats in a markdown file:

```
**English term** (Русский перевод) — optional definition
**Another term** (Другой термин)
```

## Report JSON schema

Fields written to `--report` path:

| Field | Type | Description |
|---|---|---|
| `ok` | int | Lines translated successfully |
| `skip` | int | Lines skipped (structural) |
| `fail` | int | Lines that failed translation |
| `backend` | string | Active backend (`local` or `cloud`) |
| `model` | string | Model name used |
| `prompt_version` | string | System-prompt version |
| `contract_version` | string | CLI contract version |
| `source_sha256` | string | SHA-256 of input file |
| `output_sha256` | string | SHA-256 of output file |
| `exit_code` | int | Final exit code |
| `timestamp` | string | ISO UTC timestamp |
| `message` | string | Summary message |
| `glossary_applied` | int | Total forced glossary substitutions |

## Config reference

All config via `.env` file or exported environment variables.

| Variable | Default | Description |
|---|---|---|
| `TRANSLATE_BACKEND` | `local` | `local` or `cloud` |
| `TRANSLATE_API_BASE` | `http://127.0.0.1:8000/v1` | API base URL |
| `TRANSLATE_API_KEY` | _(none)_ | API key (cloud mode required) |
| `TRANSLATE_MODEL` | `local-model` (override in `.env`) | Model name |
| `TRANSLATE_TEMP` | `0.2` | Sampling temperature |
| `TRANSLATE_TOP_P` | `0.95` | Nucleus sampling top_p |
| `TRANSLATE_HINT_STYLE` | `plain` | Glossary hint style: plain/verbose/strict |
| `TRANSLATE_PROMPT` | _(none)_ | Use `codeguard` prompt variant |
| `TRANSLATE_CHAT_KWARGS` | `{"enable_thinking":false}` | Extra JSON kwargs |
| `TRANSLATE_METADATA` | `0` | Set `1` to translate metadata lines |
| `TRANSLATE_FORCE_SECTION` | `0` | Set `1` to merge all prose into one block |
| `REQUEST_TIMEOUT` | `120` | Curl timeout in seconds |
| `MAX_RETRIES` | `2` | Retries per chunk |
| `TOTAL_DEADLINE_SECONDS` | `0` | Global deadline (0 = off) |
| `TRANSLATE_RUN_LOG` | _(none)_ | JSONL run-log path |
| `TRANSLATE_MOCK_DIR` | _(none)_ | Mock responses dir (testing only) |

## Limitations

- EN→RU English to Russian only — no reverse direction.
- Markdown input/output only.
- Cloud backend requires explicit `--allow-cloud` flag and `.env` config.
- Local backend requires an OpenAI-compatible or Ollama-compatible server.
- No third-party dependencies — stdlib Python only.
