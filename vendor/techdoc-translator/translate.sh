#!/usr/bin/env bash
# translate.sh — Wrapper for techdoc_translator.py with preflight checks.
#
# Usage:
#   ./translate.sh --input-en src.md --output-ru out.md --glossary glossary.md
#
# Environment variables (set in .env or exported):
#   TRANSLATE_BACKEND   — "cloud" (default) or "local"
#   TRANSLATE_API_BASE  — API base URL (default http://127.0.0.1:8000/v1)
#   TRANSLATE_API_KEY   — API key
#   TRANSLATE_MODEL     — Model name
#   TRANSLATE_TEMP      — Temperature (default 0.2)
#   TRANSLATE_TOP_P     — top_p (default 0.95)
#   TRANSLATE_HINT_STYLE — glossary-hint style: plain|verbose|strict
#   TRANSLATE_METADATA  — "1" to translate metadata lines
#   TRANSLATE_PROMPT    — System prompt variant: codeguard
#   TRANSLATE_FORCE_SECTION — "1" to merge all prose into one block
#   REQUEST_TIMEOUT     — Curl timeout in seconds (default 120)
#   MAX_RETRIES         — Retries per chunk (default 2)
#   TOTAL_DEADLINE_SECONDS — Global deadline (default 0 = off)
#   TRANSLATE_RUN_LOG   — JSONL run-log path
#
# Output: Only the translated text goes to stdout.
#         Debug/warnings/preflight messages go to stderr.
#
# Exit codes:
#   0 — success
#   1 — invalid arguments / python error
#   2 — missing config / cloud not allowed
#   3 — model server unreachable
#   4 — incomplete translation

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Load .env if present (does not override already-set env vars) ──
_env_file="$SCRIPT_DIR/.env"
if [ -f "$_env_file" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        # Skip comments and empty lines
        case "$line" in
            \#*|"") continue ;;
        esac
        # Only set if not already exported
        if [[ "$line" == *"="* ]] && ! env | grep -q "^${line%%=*}="; then
            export "$line"
        fi
    done < "$_env_file"
fi

# ── Validated defaults ──
export TRANSLATE_BACKEND
: "${TRANSLATE_BACKEND:=cloud}"

export TRANSLATE_API_BASE
: "${TRANSLATE_API_BASE:=http://127.0.0.1:8000/v1}"

export TRANSLATE_MODEL
: "${TRANSLATE_MODEL:=local-model}"

export TRANSLATE_TEMP
: "${TRANSLATE_TEMP:=0.2}"

export TRANSLATE_TOP_P
: "${TRANSLATE_TOP_P:=0.95}"

# Default value for TRANSLATE_CHAT_KWARGS is JSON
export TRANSLATE_CHAT_KWARGS
_CKDW='{"enable_thinking":false}'
: "${TRANSLATE_CHAT_KWARGS:=$_CKDW}"

# ── Preflight: check API server availability ──
preflight_api() {
    if ! curl -sf --max-time 3 \
        -H "Authorization: Bearer ${TRANSLATE_API_KEY}" \
        "${TRANSLATE_API_BASE}/models" > /dev/null 2>&1; then
        echo "[preflight] API server unreachable at ${TRANSLATE_API_BASE}; fix: start local model server or set TRANSLATE_API_BASE to a working endpoint" >&2
        return 1
    fi
    # Verify model is listed on the server (warn-only on parse failure)
    local model_list
    model_list=$(curl -sf --max-time 5 \
        -H "Authorization: Bearer ${TRANSLATE_API_KEY}" \
        "${TRANSLATE_API_BASE}/models" 2>/dev/null) || {
        echo "[preflight] [WARN] could not fetch /models for model check" >&2
        return 0
    }
    local found
    found=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
    ids = [m.get('id','') for m in data.get('data',[])]
    target = sys.argv[1]
    if target in ids:
        print('yes')
    else:
        print('no')
except Exception:
    print('parse-error')
" "${TRANSLATE_MODEL}" <<< "${model_list}" 2>/dev/null)
    if [ "$found" = "no" ]; then
        local ids_json
        ids_json=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
    ids = [m.get('id','') for m in data.get('data',[])]
    print(', '.join(ids))
except Exception:
    print('N/A')
" <<< "${model_list}" 2>/dev/null)
        echo "[preflight] model '${TRANSLATE_MODEL}' not found; available: ${ids_json}" >&2
        return 1
    fi
    if [ "$found" = "parse-error" ]; then
        echo "[preflight] [WARN] could not parse /models response" >&2
    fi
    return 0
}

if [ "${TRANSLATE_BACKEND}" = "cloud" ]; then
    if ! preflight_api; then
        exit 3
    fi
fi

# ── Auto-inject --allow-cloud when TRANSLATE_BACKEND=cloud ──
_extra_args=""
[ "${TRANSLATE_BACKEND}" = "cloud" ] && _extra_args="--allow-cloud"

# ── Dispatch ──
exec python3 "${SCRIPT_DIR}/techdoc_translator.py" ${_extra_args} "$@"
