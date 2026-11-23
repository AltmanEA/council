# prompt-test-author-v2 (2026-11-18) — REFINED after v1 baseline violation
Role: roles/test-author.md. Changes vs v1:
1. REPO CONVENTION (mandatory): follow tests/test_check_all.py pattern exactly — `sys.path.insert(0, <repo>/tools)` then `import consent_terminal as ct` at module top. NO `from tools import ...`. DO NOT create tests/__init__.py (repo uses namespace packages; file is off-whitelist) — delete it if present.
2. ANTI-REVERSED-TDD HARD REQUIREMENT: baseline run MUST exit non-zero (tests failing, not skipped). Remove ALL `@unittest.skipUnless` guards. Missing module at import time → collection error is an acceptable red; a failing assertion is preferred. Green-with-skips baseline is INVALID (v1 failure).
3. Keep test semantics/coverage from v1 (39 cases per acceptance criteria incl. decide() contract, FIFO, HMAC tamper, prune reasons, latest-record-wins, subprocess CLI smoke).
4. Artifacts same schema; baseline_run.exit_code must be != 0 with note "red before implementation".
Outputs: WT/tests/test_consent_terminal.py (overwrite), cycle ws artifacts/test-files.json. Forbidden: implementing implementation code, tools/__init__.py, tests/__init__.py, any other file.
