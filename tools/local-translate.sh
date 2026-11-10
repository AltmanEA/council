#!/usr/bin/env bash
# local-translate.sh — Wrapper for local_translate.py with glossary-aware translation.
#
# Usage:
#   tools/local-translate.sh en ru < glossary.md < input.txt
#   echo "text" | tools/local-translate.sh en ru docs/en/glossary/index.md file.md > out.md
#
# Environment variables (defaults set for validated configuration):
#   TRANSLATE_BACKEND   — "cloud" (default) or "ollama"
#   NEURALDEEP_BASE_URL — OpenAI-compatible endpoint (default http://127.0.0.1:8000/v1)
#   NEURALDEEP_API_KEY  — API key (default: dummy; only used if no key in opencode.json)
#   CLOUD_MODEL         — Model name (default Qwen3.6-35B-A3B-NVFP4)
#   CLOUD_CHAT_KWARGS   — Extra kwargs for chat request, e.g. {"enable_thinking":false}
#   TRANSLATE_TEMP      — Temperature (default 0.2)
#   TRANSLATE_TOP_P     — top_p (default 0.95)
#   TRANSLATE_HINT_STYLE — glossary-hint header style: plain|verbose|strict (default plain)
#   TRANSLATE_METADATA  — "1" to translate metadata lines (default: skip them)
#   TRANSLATE_PROMPT    — System prompt variant: codeguard (default none)
#   TRANSLATE_FORCE_SECTION — "1" to merge all prose into one block (default paragraphs)
#   REQUEST_TIMEOUT     — Curl timeout in seconds (default 120)
#   MAX_RETRIES         — Number of retries per chunk (default 2)
#
# Output: Only the translated text goes to stdout.
#         Debug/warnings/preflight messages go to stderr.
#
# Exit codes:
#   0 — success
#   1 — invalid arguments / python error
#   2 — cloud backend key missing
#   3 — local model server unreachable (no fallback to cloud without explicit override)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Validated defaults (only applied when operator has not set them).
#    export is mandatory: `exec python3` inherits only env vars,
#    unexported shell variables are lost. ──
export TRANSLATE_BACKEND
: "${TRANSLATE_BACKEND:=cloud}"

export NEURALDEEP_BASE_URL
: "${NEURALDEEP_BASE_URL:=http://127.0.0.1:8000/v1}"

export NEURALDEEP_API_KEY
: "${NEURALDEEP_API_KEY:=dummy}"

export CLOUD_MODEL
: "${CLOUD_MODEL:=Qwen3.6-35B-A3B-NVFP4}"

# Default value for CLOUD_CHAT_KWARGS is JSON; use a temp var to avoid shell mangling
export CLOUD_CHAT_KWARGS
_CKDW='{"enable_thinking":false}'
: "${CLOUD_CHAT_KWARGS:=$_CKDW}"

# ── Preflight: check local server availability when backend=cloud ──
preflight_local() {
    if curl -sf --max-time 3 "${NEURALDEEP_BASE_URL}/models" > /dev/null 2>&1; then
        return 0
    fi
    echo "[preflight] local model server unreachable; run with " \
         "NEURALDEEP_BASE_URL=https://api.neuraldeep.ru/v1 " \
         "CLOUD_MODEL=qwen3.6-35b-a3b-noreason" >&2
    return 1
}

if [ "${TRANSLATE_BACKEND}" = "cloud" ]; then
    if ! preflight_local; then
        exit 3
    fi
fi

# ── Dispatch ──
exec python3 "${SCRIPT_DIR}/local_translate.py" "$@"
