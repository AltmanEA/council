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

run_test() {
    local name="$1" infile="$2"
    local outf errf
    outf="$(mktemp)"
    errf="$(mktemp)"

    bash tools/local-translate.sh en ru "$GLOS" < "$infile" > "$outf" 2> "$errf"
    local exit_code=$?

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
