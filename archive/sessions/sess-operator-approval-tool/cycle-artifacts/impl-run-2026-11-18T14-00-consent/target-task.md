# Target Task — Consent Terminal (MVP, step-(5) only)

Run: `impl-run-2026-11-18T14-00-consent`
Source of design: `/home/ea/council/sessions/sess-operator-approval-tool/consensus-doc.md` (read it fully — normative).
Operator-approved: 2026-11-18.

## Goal

Implement the operator consent terminal per the consensus document:

1. `tools/consent_terminal.py` — stdlib-only Python CLI:
   - `request` (NO positional/parameter inputs beyond flags listed below; inputs come from draft file):
     - Reads `documenter/intent/consent_draft.json` with keys: `target_path` (str, repo-relative), `summary` (str ≤200 chars), `tier` (`"safe"|"review"`), `diff_file` (path to diff text file, typically under `documenter/intent/diffs/`), optional `expiry_minutes` (int >0, default 30).
     - Fail-closed ingest validation: malformed JSON, missing/extra-required keys, unknown tier, summary too long, diff file missing/unreadable, diff > 64 KB → exit 2, quarantine the draft to `documenter/intent/quarantine/<timestamp>_<name>` , print reason.
     - On success: **tool computes** `diff_hash = "sha256:" + sha256(diff_text_bytes).hexdigest()` and generates `request_id` = `<hex8>`; appends a `pending` record to `documenter/intent/approvals.jsonl` (all line access under `fcntl.flock(LOCK_EX)`); record fields: `request_id, target_path, summary, tier, diff_hash, diff_text, proposer_operator_id, created_at, expiry_deadline, state:"pending", single_use:true` (+ `diff_text_truncated: true` with `diff_text:""` if over cap — but ingest rejects >64KB, so truncation path only if flag `--allow-truncate` given... **Decision: NO truncate flag. Over 64 KB = reject exit 2.**). Removes the consumed draft (and leaves diff file for audit). Prints the operator command: `tools/consent_review.sh --request-id <id>` and exits 0.
     - `proposer_operator_id`: read env `COUNCIL_PROPOSER_ID` else `"agent"`.
   - `review [--request-id <id>]` (operator, one-shot): flock-locked read of spool; prune pass first — expired records or records failing integrity (`sha256(diff_text) != diff_hash`) or malformed → append `state:"denied"` + `reason` (`expired|corrupted|integrity_fail`) records, print `Pruned N items`; then present oldest `pending` (or the `--request-id` one):
     - Screen fields: short id, target, tier, hash prefix (first 8 hex after `sha256:`), summary, expiry countdown, diff stats (+/- line counts).
     - Keypress grammar: safe tier: `y` approve immediately; review tier: `y` ignored until `Enter` pressed (then unlock); `n` deny; `s` pager verbatim diff; `q` quit exit 0 without decision; Ctrl-C = deny exit 1; unknown key re-prompt. Before accepting `y`, re-check expiry (expired → deny with reason `expired`, exit 1).
     - On decision: append decision record `{request_id, state:"approved"|"denied", reason?, approver_operator_id, signed_at, hmac}` where `hmac = hmac_sha256(operator_secret, canonical_json({request_id, diff_hash, proposer_operator_id, state, created_at}))` — canonical = `json.dumps(obj, sort_keys=True, separators=(",",":")).encode()`. `approver_operator_id` from env `COUNCIL_OPERATOR_ID` else file `~/.council/operator_id` (first line, stripped); `operator_secret` from env `COUNCIL_OPERATOR_SECRET` else file `~/.council/operator_secret` (chmod 600 recommended; if secret unavailable → error exit 2, do NOT write unsigned decision).
     - Prints receipt line: `APPROVED | id=<full> | target=<path> | diff=<hash prefix 8> | time=<ISO>` (or `DENIED | ...`). Exit codes: 0 approved (or `q`), 1 denied/expired, 2 usage/error.
   - Also expose an importable API for the agent-side consumption (used by tests): module-level functions, each taking explicit `state_root` (default: repo root = parent of `tools/`): `create_request(draft: dict, state_root) -> record` (validation + ingest logic), `prune_pending(state_root) -> list[dict]` (returns pruned records), `verify_decision(record_pair, state_root) -> bool` (recompute HMAC over the five fields of the *decision* record and compare; used as agent Verification Gate helper), `mark_consumed(request_id, state_root) -> bool`, `read_pending(state_root) -> list[dict]`. Decision records append; latest record per `request_id` wins (append-only log semantics: a later record with the same `request_id` supersedes earlier states).
   - All JSONL reads/writes through one helper that acquires `fcntl.flock(LOCK_EX)` on the file before read-modify-write.

2. `tools/consent_review.sh` — thin bash launcher, executable: resolves repo root from script location, execs `python3 tools/consent_terminal.py review "$@"`. No secrets printed. `set -euo pipefail`.

## Acceptance criteria (what tests must pin)

- request happy path: draft + diff file → pending record appended, correct computed `diff_hash`, `request_id` generated, exit 0.
- request rejects: malformed JSON draft; missing key; `tier` not in {safe,review}; summary >200 chars; diff file missing; diff > 64 KB — each exit 2 + quarantine + no pending record.
- decision append + HMAC: approve decision record verifies via `verify_decision` with correct secret; tampering any of the 5 signed fields or flipping state → verify fails.
- integrity auto-deny: spool record whose `diff_text` doesn't match `diff_hash` → pruned as `denied reason=integrity_fail`.
- expiry: record past `expiry_deadline` → pruned `denied reason=expired`; review never presents expired items.
- latest-record-wins: pending then approved then consumed → read returns consumed; agent flow (approve → apply → mark_consumed) works.
- mark_consumed on unknown/non-decided id → False.
- review one-shot presents oldest pending FIFO (test via injecting decisions through importable API; interactive UI loop must be split out so logic is testable without TTY — separate `decide(record, keypresses)`-style pure function or similar).
- no Tier 2+ interlock interaction: file must not touch `documenter_policy.yml`, `active_tier`, `briefing_ref`, no `OperatorSurface` imports.

## Constraints

- Stdlib only (+ nothing beyond what tools/ already uses; NO pyyaml needed). Python 3.11+.
- Tests: **unittest** framework, `python3 -m unittest tests.<module> -v`. Tests MUST use `tempfile.TemporaryDirectory` as `state_root` — never write into the real `documenter/`.
- No commits. No network. No curses (plain stdout input loop via `input()` or termios-free approach so it's testable).
- Style: follow existing `tools/` conventions (see `activation_helper.py` docstring header, argparse).

## Whitelist (writable paths)

```
tools/consent_terminal.py
tools/consent_review.sh
tests/test_consent_terminal.py
sessions/sess-operator-approval-tool/impl-run-2026-11-18T14-00-consent/**
```

## Test command

`python3 -m unittest tests.test_consent_terminal -v`

## Explicitly OUT of scope (do NOT build)

§4 documenter.approve integration; ADR-017 solo flow / `CONFIRMED_SOLE_REVIEWER`; `--watch`/batch; Operator Ingress coupling/MCP; edits to `operator_ingress/core/approval.py`; SKILL.md/README prose sync (orchestrator handles post-merge).
