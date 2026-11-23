# Test Author v1 (iteration 1)

Split into chunked writes after first attempt exceeded output limits.
Inputs: target-task.md (Commands + Acceptance criteria), tests/test_consent_terminal.py
(style + HMAC decision fixtures), tools/consent_terminal.py (real API, read-only).
Output: tests/test_delegate_consent.py + artifacts/test-files.json.
Result: 9 tests, red baseline exit 1 (8 ModuleNotFoundError, 1 baseline check).
