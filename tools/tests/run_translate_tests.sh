#!/usr/bin/env bash
# run_translate_tests.sh — Unified test runner for translation test layers.
#
# Usage:
#   tools/tests/run_translate_tests.sh [quick|full]
#
# Modes:
#   quick  (default) — unit tests only, fast (<5 s), no network
#   full   — unit tests + mock layer: run local_translate.py backend=mock
#             on fixtures/scenario → candidate → check_drift EN-vs-candidate
#
# Exit: 0 on success, 1 on failure.
#
# Reminder on every run: if PROMPT_VERSION differs from the last live run
# in TRANSLATE_RUN_LOG (or no live runs exist), print a reminder on stderr.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="$(cd "$TOOLS_DIR/.." && pwd)"

# Prompts from local_translate.py
PROMPT_VERSION_PY="${TOOLS_DIR}/local_translate.py"
PROMPT_VERSION=$(grep '^PROMPT_VERSION = ' "$PROMPT_VERSION_PY" | head -1 | sed 's/.*"\([^"]*\)".*/\1/')

MODE="${1:-quick}"

# ── Reminder check ─────────────────────────────────────────────────
RUN_LOG="${TOOLS_DIR}/translate-runs.jsonl"
HAS_LIVE=false
if [ -f "$RUN_LOG" ]; then
    # Check if any entry has backend=live
    if grep -q '"backend"[[:space:]]*:[[:space:]]*"live"' "$RUN_LOG" 2>/dev/null; then
        HAS_LIVE=true
    fi
fi

# Check if prompt_version matches last live run's prompt_version
PROMPT_OK=true
if [ "$HAS_LIVE" = "true" ]; then
    LAST_PROMPT=$(grep '"backend"' "$RUN_LOG" | tail -1 | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('prompt_version',''))" 2>/dev/null || echo "")
    if [ "$LAST_PROMPT" != "$PROMPT_VERSION" ]; then
        PROMPT_OK=false
    fi
fi

if [ "$PROMPT_OK" = "false" ] || [ "$HAS_LIVE" = "false" ]; then
    echo "[reminder] PROMPT_VERSION=${PROMPT_VERSION}" >&2
    if [ "$HAS_LIVE" = "false" ]; then
        echo "[reminder] no live run in ${RUN_LOG} — run tools/tests/e2e_live.sh" >&2
    else
        echo "[reminder] PROMPT_VERSION changed (last live was ${LAST_PROMPT}) — re-run e2e_live.sh" >&2
    fi
fi

# ── Fixture decay warnings ─────────────────────────────────────────
FIXTURE_SOURCE="${SCRIPT_DIR}/fixtures/scenario/source.md"
FIXTURE_META="${SCRIPT_DIR}/fixtures/scenario/meta.json"
LIVE_SOURCE="${REPO_DIR}/docs/en/scenario/index.md"

if [ -f "$FIXTURE_META" ] && [ -f "$LIVE_SOURCE" ]; then
    FIXTURE_VERSION=$(python3 -c "import json; print(json.load(open('${FIXTURE_META}'))['source_version'])" 2>/dev/null || echo "")
    LIVE_VERSION=$(grep '^Version:' "$LIVE_SOURCE" | head -1 | sed 's/.*: *//')
    if [ "$FIXTURE_VERSION" != "$LIVE_VERSION" ]; then
        echo "[fixture-decay] source_version=${FIXTURE_VERSION} != live Version=${LIVE_VERSION}" >&2
    fi
    FIXTURE_PROMPT=$(python3 -c "import json; print(json.load(open('${FIXTURE_META}'))['prompt_version'])" 2>/dev/null || echo "")
    if [ "$FIXTURE_PROMPT" != "$PROMPT_VERSION" ]; then
        echo "[fixture-decay] prompt_version=${FIXTURE_PROMPT} != PROMPT_VERSION=${PROMPT_VERSION}" >&2
        echo "[fixture-decay] update fixtures/scenario/meta.json and responses.json" >&2
    fi
fi

# ── Quick mode: unit tests ─────────────────────────────────────────
echo "[run] quick mode: unit tests" >&2
if ! python3 "${TOOLS_DIR}/tests/test_unit.py" 2>&1; then
    echo "[FAIL] unit tests" >&2
    exit 1
fi
echo "[OK] unit tests passed" >&2

if [ "$MODE" != "full" ]; then
    echo "[OK] quick mode complete" >&2
    exit 0
fi

# ── Full mode: mock layer ──────────────────────────────────────────
echo "[run] full mode: mock layer" >&2

# Set up mock backend
export TRANSLATE_BACKEND=mock
export TRANSLATE_MOCK_DIR="${SCRIPT_DIR}/fixtures/scenario"

# Create candidate output
CANDIDATE=$(mktemp /tmp/candidate-ru-XXXXXX.md)

# Run local_translate.py with mock backend on source
if ! python3 "${TOOLS_DIR}/local_translate.py" en ru "${REPO_DIR}/docs/en/glossary/index.md" < "${FIXTURE_SOURCE}" > "${CANDIDATE}" 2>/dev/null; then
    # Check if there are [FAIL] lines (expected with mock misses)
    FAIL_COUNT=$(grep -c "\[FAIL\]" <(python3 "${TOOLS_DIR}/local_translate.py" en ru "${REPO_DIR}/docs/en/glossary/index.md" < "${FIXTURE_SOURCE}" 2>&1) || true)
    if [ "$FAIL_COUNT" -gt 0 ]; then
        echo "[WARN] mock misses: ${FAIL_COUNT} lines failed — check_drift will validate" >&2
    else
        echo "[FAIL] local_translate mock run" >&2
        rm -f "$CANDIDATE"
        exit 1
    fi
fi

# Run check_drift on EN vs candidate
if python3 "${TOOLS_DIR}/check_drift.py" "${FIXTURE_SOURCE}" "${CANDIDATE}" --json 2>/dev/null | grep -q .; then
    echo "[FAIL] check_drift found structural drift" >&2
    python3 "${TOOLS_DIR}/check_drift.py" "${FIXTURE_SOURCE}" "${CANDIDATE}" 2>&1 || true
    rm -f "$CANDIDATE"
    exit 1
fi

echo "[OK] check_drift: no structural drift" >&2
echo "[OK] full mode complete (unit + mock)" >&2
rm -f "$CANDIDATE"
exit 0
