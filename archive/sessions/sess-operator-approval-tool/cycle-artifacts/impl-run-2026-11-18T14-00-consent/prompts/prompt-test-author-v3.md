# prompt-test-author-v3 (2026-11-18) — TARGETED PATCH ONLY
Role: roles/test-author.md. This is iteration 2. The implementation WT/tools/consent_terminal.py exists and passes 36/37; the single failure is a defect in YOUR test file (Analyst-confirmed). 

TASK (surgical, do not restructure):
1. In WT/tests/test_consent_terminal.py `_make_approved` (~line 309): replace literal `"hmac": "computed"` with a REAL HMAC over the 5 signed fields {request_id, diff_hash, proposer_operator_id, state, created_at} computed with the SAME formula the module's verify_decision uses: hmac.new(secret, json.dumps(fields, sort_keys=True, separators=(",",":")).encode(), hashlib.sha256).hexdigest(). Use the module's own signing path if it exposes one (READ tools/consent_terminal.py first; prefer calling the module helper so the test exercises real signing, e.g. a sign function; if none is public, compute inline with the secret the tests prepare via _prepare_council_dir — match the exact secret value used there).
2. In `test_hmac_state_flip_denied_to_approved` (~line 338): the base denied record carries "hmac":"bad" — compute the REAL HMAC for the denied state first, then flip state to approved WITHOUT re-signing, so the test's stated property (state change breaks HMAC) is actually isolated from the invalid-base confound.
3. Apply the same real-signing fix to any other helper writing hmac literals, keeping every test's ASSERTION direction unchanged (valid→True, tampered→False).
4. Do not weaken any test; do not delete tests; do not touch tools/ implementation.

Baseline expectation: before your patch the file is red on exactly test_hmac_verify_valid; after your patch all 37 should pass — RUN the suite from WT to confirm, but the authoritative run belongs to Test Runner. Update WS/artifacts/test-files.json baseline_run note to {"exit_code":1,"note":"iteration-2 patch: 1 known test defect fixed; pre-patch red confirmed by test-results iteration 1"}.

OUTPUTS: WT/tests/test_consent_terminal.py (patched in place), WS/artifacts/test-files.json (updated). Nothing else.
Return: diff summary of what you changed in the two helpers + observed unittest result.
