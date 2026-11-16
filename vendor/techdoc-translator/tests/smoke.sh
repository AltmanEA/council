#!/usr/bin/env bash
# tests/smoke.sh — Smoke tests for techdoc-translator.
# No network required. Tests CLI validation, exit codes, and unit tests.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PASS=0
FAIL=0
FAILURES=""

pass() { PASS=$((PASS + 1)); }
fail() { FAIL=$((FAIL + 1)); FAILURES="$FAILURES\n  - $1"; }

check_exit() {
    local desc="$1" expected="$2" actual="$3"
    if [ "$actual" -eq "$expected" ]; then
        pass
    else
        fail "${desc}: expected exit $expected, got $actual"
    fi
}

echo "=== techdoc-translator smoke tests ==="
echo ""

# 1. No args → exit 1 (missing required args)
echo -n "[1] No args → exit 1: "
cd "$PROJECT_DIR"
python3 techdoc_translator.py >/dev/null 2>&1
rc=$?
check_exit "no args" 1 "$rc"

# 2. Missing --input-en → exit 1
echo -n "[2] Missing --input-en → exit 1: "
python3 techdoc_translator.py --output-ru /tmp/out.md >/dev/null 2>&1
rc=$?
check_exit "missing --input-en" 1 "$rc"

# 3. Missing --output-ru → exit 1
echo -n "[3] Missing --output-ru → exit 1: "
python3 techdoc_translator.py --input-en /dev/null >/dev/null 2>&1
rc=$?
check_exit "missing --output-ru" 1 "$rc"

# 4. Non-existent source file → exit 1
echo -n "[4] Non-existent source → exit 1: "
python3 techdoc_translator.py --input-en /no/such/file.md --output-ru /tmp/out.md >/dev/null 2>&1
rc=$?
check_exit "bad source" 1 "$rc"

# 5. Cloud backend without --allow-cloud → exit 2
echo -n "[5] Cloud without --allow-cloud → exit 2: "
TRANSLATE_BACKEND=cloud python3 techdoc_translator.py --input-en /dev/null --output-ru /tmp/out.md >/dev/null 2>&1
rc=$?
check_exit "cloud no allow" 2 "$rc"

# 6. Cloud backend without API key → exit 2
echo -n "[6] Cloud without API key → exit 2: "
TRANSLATE_BACKEND=cloud TRANSLATE_API_BASE="http://127.0.0.1:9999/v1" python3 techdoc_translator.py --input-en /dev/null --output-ru /tmp/out.md --allow-cloud >/dev/null 2>&1
rc=$?
check_exit "cloud no key" 2 "$rc"

# 7. --version → exit 0
echo -n "[7] --version → exit 0: "
python3 techdoc_translator.py --version >/dev/null 2>&1
rc=$?
check_exit "version" 0 "$rc"

# 8. Contract version mismatch → exit 5
echo -n "[8] Contract mismatch → exit 5: "
python3 techdoc_translator.py --input-en /dev/null --output-ru /tmp/out.md --contract-version 9.9.9 >/dev/null 2>&1
rc=$?
check_exit "contract mismatch" 5 "$rc"

# 9. Backend unavailable (local, API unreachable) → exit 3 or 4
echo -n "[9] Local backend (unreachable API) → exit 3 or 4: "
mkdir -p "$PROJECT_DIR/.smoke-test"
echo "This is a test paragraph." > "$PROJECT_DIR/.smoke-test/src.md"
REQUEST_TIMEOUT=2 MAX_RETRIES=1 TRANSLATE_BACKEND=local python3 techdoc_translator.py --input-en .smoke-test/src.md --output-ru .smoke-test/out.md >/dev/null 2>&1
rc=$?
if [ "$rc" -eq 3 ] || [ "$rc" -eq 4 ]; then
    pass
else
    fail "backend unreachable: expected exit 3 or 4, got $rc"
fi

# 10. Unknown option → exit 1
echo -n "[10] Unknown option → exit 1: "
python3 techdoc_translator.py --unknown-flag >/dev/null 2>&1
rc=$?
check_exit "unknown flag" 1 "$rc"

# 11. Invalid regex in --skip-pattern → exit 1
echo -n "[11] Invalid regex → exit 1: "
python3 techdoc_translator.py --input-en /dev/null --output-ru /tmp/out.md --skip-pattern '[' >/dev/null 2>&1
rc=$?
check_exit "invalid regex" 1 "$rc"

# 12. Unit tests
echo -n "[12] Unit tests: "
if python3 tests/test_unit.py 2>&1 | grep -q "^OK"; then
    pass
else
    fail "unit tests failed"
fi

# 13. Report writing (json valid)
echo -n "[13] --report writes JSON: "
rm -f "$PROJECT_DIR/.smoke-test/report.json"
REQUEST_TIMEOUT=2 MAX_RETRIES=1 TRANSLATE_BACKEND=local python3 techdoc_translator.py \
    --input-en .smoke-test/src.md \
    --output-ru .smoke-test/out.md \
    --report .smoke-test/report.json >/dev/null 2>&1
rc=$?
if [ -f "$PROJECT_DIR/.smoke-test/report.json" ] && python3 -c "import json; json.load(open('$PROJECT_DIR/.smoke-test/report.json'))" 2>/dev/null; then
    pass
else
    fail "report JSON not valid (rc=$rc)"
fi

# Cleanup
rm -rf "$PROJECT_DIR/.smoke-test"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ $FAIL -gt 0 ]; then
    echo -e "Failures:$FAILURES"
    exit 1
fi
exit 0
