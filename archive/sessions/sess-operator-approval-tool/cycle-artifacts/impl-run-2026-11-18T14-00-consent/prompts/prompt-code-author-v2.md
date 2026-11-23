# prompt-code-author-v2 (2026-11-18) — iteration 3, TARGETED fixes from orchestrator diff-review
Role: roles/code-author.md. Tests are green (37/37); you are fixing THREE defects found in diff-review that the tests don't cover yet. Change ONLY WT/tools/consent_terminal.py (plus, if strictly needed, WT/tools/consent_review.sh). Test additions for these behaviors will be handled separately — implement to the SPEC below; keep all existing public APIs and behaviors intact; all 37 current tests must remain green.

FIX 1 — flock on EVERY JSONL access (consensus: all access paths locked):
- _jsonl_read_all currently reads WITHOUT a lock and silently drops torn lines (JSONDecodeError: pass). Make it acquire fcntl.flock(LOCK_SH) (open the file, LOCK_SH, read all, LOCK_UN) in a dedicated open() (lock BEFORE reading, release in finally). Keep skipping genuinely malformed complete lines ONLY when they are torn/unparseable — but add a module-level counter or return-value signal is NOT required; simply locking read+write consistently is the requirement.
- Ensure _jsonl_write_all and _jsonl_append_locked already lock (they do) — keep.

FIX 2 — no busy-spin in raw TTY mode (_cmd_review):
- Replace select.select([sys.stdin],[],[],0) with a BLOCKING wait: select.select([sys.stdin],[],[],None) (or timeout=0.2 with a continue that prints nothing) so the loop sleeps while waiting for a key. Must not consume CPU while idle.

FIX 3 — Ctrl-C as deny in raw mode:
- With tty.setraw, ISIG is off, so Ctrl-C arrives as byte "\x03". In the raw branch, if k == "\x03": treat as denied (outcome="denied", reason ctrl_c, write signed decision exactly as pressing n does), exit code 1. Same for EOF (Ctrl-D / "\x04") → denied. In non-raw fallback the existing KeyboardInterrupt path stays.

VERIFY after changes: run python3 -m unittest tests.test_consent_terminal -v from WT (cwd=WT) → must stay 37/37 OK. Also python3 -c "import consent_terminal" with sys.path including tools/ must not touch real documenter/ (it doesn't — no import-time side effects; keep it that way).

OUTPUTS: WT/tools/consent_terminal.py, (consent_review.sh only if unavoidable), WS/artifacts/code-files.json (update signatures list; note the three fixes).
Forbidden: editing tests; touching anything outside whitelist; Tier 2+ markers.
Return: what changed per fix + unittest tail.
