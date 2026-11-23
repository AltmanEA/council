# prompt-test-author-v4 (2026-11-18) — iteration 3 additions: pin the three diff-review fixes
Role: roles/test-author.md. Surgical ADDITIONS to WT/tests/test_consent_terminal.py (append new test methods/class; do not alter existing 37 tests). The implementation (WT/tools/consent_terminal.py) already contains the fixes — your job is to pin them so regressions surface.

ADD exactly these behaviors as tests (import module via existing convention):
1. LOCKED READ: monkeypatch/inspect: call ct._jsonl_read_all(state_root) and verify it uses fcntl.flock — acceptable approach: wrap fcntl.flock with a recorder (unittest.mock.patch on the module's fcntl.flock if the module imports `fcntl` as a module, else patch builtins open-based lock via mock.patch("consent_terminal.fcntl.flock", wraps=fcntl.flock)) and assert flock was called with LOCK_SH (or LOCK_EX) at least once during a read, and at least once during append. If the module imports flock directly from fcntl, patch accordingly (READ the module first).
2. NO BUSY-SPIN: static/behavioral guard — assert inspect.getsource(ct._cmd_review) contains no select-timeout-zero spin: parse source; assert that any select.select call does not pass 0 as timeout (accept None or float>=0.05). Simple source-scan test is acceptable (document why in a comment: behavioral CPU measurement is flaky in CI).
3. CTRL-C RAW DENY: feed the raw-mode branch: unit-test decide(record, ["\x03"]) == "denied" AND decide(record, ["\x04"]) == "denied" (safe tier record; if module maps ctrl in _cmd_review only, ALSO test that the module-level mapping exists by source-scan for '"\\x03"'). Prefer the decide() level; add a source-scan fallback asserting \x03 handling exists in _cmd_review.

All tests must pass against current WT implementation (run suite: expect 40/40 OK). Update WS/artifacts/test-files.json files list and test_command unchanged.
WRITE ONLY: WT/tests/test_consent_terminal.py, WS/artifacts/test-files.json.
Return: new test names + unittest tail.
