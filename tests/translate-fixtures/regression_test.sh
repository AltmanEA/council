#!/usr/bin/env bash
# regression_test.sh — Verify translator integration per BRIEF acceptance criteria.
#
# Run: bash tests/translate-fixtures/regression_test.sh
# Exit 0 if all 4 fixtures pass, 1 otherwise.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR"/../.. && pwd)"
cd "$PROJECT_DIR"

FIXTURES="in_T1.md in_T2.md in_T3.md in_TRAP.md"
GLOS="$SCRIPT_DIR/glossary.md"
PASS=0
FAIL=0

# ADR-014: the engine is external; locate it via the lock file.
LOCK="$PROJECT_DIR/defaults/translation.lock"
TRANSLATOR_PATH=$(grep '^local_path:' "$LOCK" | sed 's/^local_path:[[:space:]]*//')
CONTRACT_VERSION=$(grep '^contract_version:' "$LOCK" | sed 's/^contract_version:[[:space:]]*//' | tr -d '"')
if [ -z "$TRANSLATOR_PATH" ] || [ ! -x "$TRANSLATOR_PATH/translate.sh" ]; then
    echo "ERROR: Translation Project not found at local_path from lock ($TRANSLATOR_PATH); fix: checkout the pinned engine (ADR-014)"; exit 2
fi

# Integration tests run offline against the local OpenAI-compatible dev server only,
# pinned to loopback — no external endpoint, no provider secrets (ADR-012 privacy gate).
# The engine's "cloud" mode names any OpenAI-compatible API backend; here it is local.
# Model/backend defaults come from the engine's own .env; only the endpoint is pinned.
if [ -f "$TRANSLATOR_PATH/.env" ]; then
    TRANSLATE_MODEL=$(grep -m1 '^TRANSLATE_MODEL=' "$TRANSLATOR_PATH/.env" | cut -d= -f2-) || TRANSLATE_MODEL=""
    export TRANSLATE_MODEL
fi
export TRANSLATE_BACKEND=cloud
export TRANSLATE_API_BASE=http://127.0.0.1:8000/v1
export TRANSLATE_API_KEY=dummy

run_test() {
    local name="$1" infile="$2"
    local outf errf report
    outf="$(mktemp)"
    errf="$(mktemp)"
    report="$(mktemp)"

    # Council-specific frontmatter keys are passed as data (ADR-014; AGENTS.md §7.2)
    # "cloud" here only selects OpenAI-compatible API mode; the endpoint is pinned to
    # loopback by the exports above, so no data leaves the machine (ADR-012 privacy gate).
    bash "$TRANSLATOR_PATH/translate.sh" --input-en "$infile" --output-ru "$outf" \
        --glossary "$GLOS" --report "$report" --contract-version "$CONTRACT_VERSION" --allow-cloud \
        --skip-pattern '^Abstraction:' --skip-pattern '^changelog-path:' \
        --skip-pattern '^has_translation:' --skip-pattern '^references:' \
        --skip-pattern '^allow_non_index_paths:' --skip-pattern '^no_auto_translation:' \
        > /dev/null 2> "$errf" && exit_code=0 || exit_code=$?

    if [ $exit_code -ne 0 ]; then
        echo "FAIL [$name]: exit code $exit_code"
        FAIL=$((FAIL+1)); return
    fi

    # (a) metadata line-parity (T1 only — has YAML header)
    if [[ "$name" == "T1" ]]; then
        local diff_out
        diff_out=$(diff <(head -6 "$infile") <(head -6 "$outf") 2>&1) || true
        if [ -n "$diff_out" ]; then
            echo "FAIL [$name]: metadata header changed"
            FAIL=$((FAIL+1)); return
        fi
    fi

    # (b) code-tokens preserved (T3 only — has backtick tokens)
    if [[ "$name" == "T3" ]]; then
        local diff_codes
        diff_codes=$(diff \
            <(grep -o '`[^`]*`' "$infile" | sort) \
            <(grep -o '`[^`]*`' "$outf" | sort) 2>&1) || true
        if [ -n "$diff_codes" ]; then
            echo "FAIL [$name]: code-tokens mismatch"
            FAIL=$((FAIL+1)); return
        fi
    fi

    # (c) no [FAIL] on stderr (table separators returning as-is are ok)
    local fail_lines
    fail_lines=$(grep '\[FAIL\]' "$errf" 2>/dev/null || true)
    if [ -n "$fail_lines" ] && ! echo "$fail_lines" | grep -qvE '---'; then
        echo "FAIL [$name]: [FAIL] found on stderr"
        FAIL=$((FAIL+1)); return
    fi

    # (d) TRAP: output contains "значени" and NOT "замечания \`ConsensusVerdict"
    if [[ "$name" == "TRAP" ]]; then
        if ! grep -q 'значени' "$outf"; then
            echo "FAIL [$name]: missing 'значени' (contamination)"
            FAIL=$((FAIL+1)); return
        fi
        if grep -q 'замечания' "$outf"; then
            echo "FAIL [$name]: contamination 'замечания' found"
            FAIL=$((FAIL+1)); return
        fi
    fi

    echo "PASS [$name]"
    PASS=$((PASS+1))
    rm -f "$outf" "$errf"
}

for f in $FIXTURES; do
    base="${f%.md}"
    run_test "$base" "$SCRIPT_DIR/$f"
done

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
exit $?
