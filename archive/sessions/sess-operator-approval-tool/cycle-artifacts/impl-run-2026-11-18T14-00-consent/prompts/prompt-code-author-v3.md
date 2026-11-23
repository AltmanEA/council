# prompt-code-author-v3 (2026-11-18) — iteration 4, TARGETED fixes (orchestrator diff-review, findings F4–F8)
Role: roles/code-author.md. Change ONLY WT/tools/consent_terminal.py. Public API (create_request/read_pending/prune_pending/verify_decision/mark_consumed/decide) and all existing tests' expectations MUST remain intact (decide() keeps its pure stateless contract; flow state lives in _cmd_review).

F4 — header info: in _cmd_review, after Summary print, display:
  - Diff stats computed from record["diff_text"]: count lines starting with "+" (excluding "+++") and "-" (excluding "---"); print f"Stats:   +{add} -{del}".
  - Expiry countdown: parse expiry_deadline; print f"Expires: {expiry_deadline} ({mm}m {ss}s left)"; if unparsable, print "Expires: ?".

F5 — 's' shows verbatim diff: in the review loop BEFORE calling decide(), handle k == "s": print "--- BEGIN DIFF (verbatim) ---", the full record["diff_text"], "--- END DIFF ---"; then continue the loop (no decision). Do not route 's' through decide().

F6 — engagement gate semantics in the LOOP (decide() stays pure):
  - Maintain loop variables: confirming=False.
  - review tier: k=="y" (via decide → "confirming") → set confirming=True, print "(confirm with Enter to approve)", continue.
  - k is Enter ("\\n" after normalization): if confirming is True → approve (route decide(["\n"]) → approved). If confirming is False → EXPAND ONLY: same verbatim diff display as 's', keep confirming=False, continue (Enter alone must NEVER approve).
  - safe tier unchanged (y approves).
  Note: to keep existing unit tests of decide() passing, do not change decide(); the Enter-without-confirming case is intercepted in the loop before decide() (call expand+continue when k=="\n" and not confirming).

F7 — raw-mode Enter normalization: raw TTY delivers Enter as "\r". In the raw branch: k = raw.decode(...); if k == "\r": k = "\n".

F8 — non-raw EOF/empty-line safety: in the non-raw branch, line = sys.stdin.readline(); if line == "": EOF → outcome="denied" with decision reason "operator_deny" path (same as n), break. Otherwise k = line.strip(); if k == "": treat as Enter → k = "\n" (route through the F6 loop logic).

F9 — review presents PENDING only (single-use): tests pin read_pending() to return latest records regardless of state (consumed included) — do NOT change read_pending. Instead, in _cmd_review filter candidates: [r for r in records if r.get("state") == "pending"] before selecting --request-id match or oldest. A record already approved/denied/consumed must never be presented again.

F10 — request_id uniqueness: format(random.randint(0,0xFFFF),"08x") gives only 16 bits of entropy — replace with secrets.token_hex(4)... actually use os.urandom-based: import secrets; request_id = secrets.token_hex(8) (16 hex chars). Collision check: if request_id already exists in latest map, regenerate (max 5 tries).

Also update the docstring usage note: keys y/n/s/q, Enter (expand; confirm after y), Ctrl-C deny.

VERIFY: run python3 -m unittest tests.test_consent_terminal -v from WT → existing 43 tests must stay OK. Also write a quick manual smoke with a here-doc driving the NON-raw path (echo y | python3 tools/consent_terminal.py review --request-id <id>) against a TEMP state root (set via env? CLI uses _REPO_ROOT — for smoke you may temporarily exercise _cmd_review via python3 -c with a temp state_root; do NOT commit scratch files; delete after).
OUTPUTS: WT/tools/consent_terminal.py, WS/artifacts/code-files.json (update notes).
Return: per-fix summary + unittest tail + smoke transcript.
