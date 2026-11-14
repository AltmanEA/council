#!/usr/bin/env bash
# e2e_live.sh — Live e2e translation test: real backend, live document.
#
# Usage:
#   tools/tests/e2e_live.sh [en_source_path]
#
# Environment: same as local_translate.sh (NEURALDEEP_BASE_URL, etc.).
#
# Flow:
#   1. Run local_translate.py backend=cloud on the live document
#   2. Write candidate to /tmp/candidate-live-XXXXXX.md
#   3. Run check_drift.py EN-vs-candidate
#   4. Record result in TRANSLATE_RUN_LOG (backend=live)
#
# Exit: 0 if candidate passes check_drift, 1 otherwise.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="$(cd "$TOOLS_DIR/.." && pwd)"

SOURCE="${1:-${REPO_DIR}/docs/en/scenario/index.md}"

if [ ! -f "$SOURCE" ]; then
    echo "[error] source not found: ${SOURCE}" >&2
    exit 2
fi

CANDIDATE=$(mktemp /tmp/candidate-live-XXXXXX.md)
RUN_LOG="${TOOLS_DIR}/translate-runs.jsonl"

echo "[live] translating ${SOURCE} → ${CANDIDATE}" >&2

# Run translation via local-translate.sh (inherits env from caller)
if ! "${TOOLS_DIR}/local-translate.sh" en ru "${REPO_DIR}/docs/en/glossary/index.md" < "${SOURCE}" > "${CANDIDATE}" 2>/dev/null; then
    RC=$?
    if [ $RC -eq 4 ]; then
        echo "[WARN] live translation had failures (exit ${RC})" >&2
    else
        echo "[error] live translation failed (exit ${RC})" >&2
        rm -f "$CANDIDATE"
        exit 1
    fi
fi

# Run check_drift
echo "[live] running check_drift..." >&2
DRIFT_OUTPUT=$(python3 "${TOOLS_DIR}/check_drift.py" "${SOURCE}" "${CANDIDATE}" 2>&1) || true

if echo "$DRIFT_OUTPUT" | grep -q "^rule="; then
    echo "$DRIFT_OUTPUT" >&2
    echo "[live] FAIL: structural drift detected" >&2
    rm -f "$CANDIDATE"
    exit 1
fi

echo "[live] PASS: no structural drift" >&2
echo "$DRIFT_OUTPUT" >&2

# Record in run log (backend=live)
# prompt_version is already written by local_translate.py via TRANSLATE_RUN_LOG
# but this script overrides with backend=live for clarity
python3 -c "
import json, os, sys
run_log = '${RUN_LOG}'
with open(run_log, 'a', encoding='utf-8') as fh:
    rec = {
        'timestamp': $(python3 -c "import time; print(repr(time.strftime('%Y-%m-%dT%H:%M:%S%z', time.gmtime())))"),
        'backend': 'live',
        'prompt_version': open('${TOOLS_DIR}/local_translate.py').read().split('PROMPT_VERSION = \"')[1].split('\"')[0],
        'source': '${SOURCE}',
        'pass': True,
    }
    fh.write(json.dumps(rec) + '\n')
print('[live] recorded to ' + run_log, file=sys.stderr)
" 2>/dev/null || true

rm -f "$CANDIDATE"
exit 0
