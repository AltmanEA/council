# Target task: delegate_consent — consent-terminal ↔ Documenter delegate integration

## Goal

New orchestrator `tools/delegate_consent.py` that couples the operator consent
terminal (`tools/consent_terminal.py`, commit e6d51f9) with the Documenter
Service Tier 2+ write branch (CLI `python3 -m documenter_service`), so the
operator approves a delegate write with ONE out-of-band action and zero
parameters:

    operator terminal:  tools/consent_review.sh        (reads pending, y/n)

Everything else is automated by the orchestrator.

## Commands (CLI of the new tool)

    python3 tools/delegate_consent.py propose --target ID --diff-file FILE \
        [--change-type update] [--trust-level safe] [--root DIR]
    python3 tools/delegate_consent.py consume [--root DIR]

### propose (agent/proposer side)
1. `--verify-activation --root DIR --json`: require state == "active" and
   interlock.tier2_authorized == true; else structured refusal exit 2.
2. Fresh `--audit --target "*" --pre-check --json` → audit_id (last JSON line).
3. `--delegate-write --target ID --change-type ... --trust-level ... --diff-base64
   <b64 of FILE> --audit-id AUDIT --json` (env COUNCIL_OPERATOR_ID from
   environ or ~/.council/operator_id, like consent_terminal) → approval_id,
   diff_hash. Non-zero exit / missing approval_id → propagate stderr, exit 2.
4. Consent request creation via the REAL consent_terminal API (verified facts):
   - draft schema (strict): JSON object at `documenter/intent/consent_draft.json`
     with exactly keys {target_path, summary, tier, diff_file} (+ optional
     expiry_minutes); unknown keys => quarantine. tier in {safe, review};
     summary <= 200 chars.
   - the diff file itself must live at `<state_root>/documenter/intent/diffs/<diff_file>`
     (raw bytes, <= 64 KB); consent_terminal computes
     `diff_hash = sha256:<hex>` over the RAW diff bytes.
   - call create_request(state_root) importable API (no CLI subprocess).
   - NOTE: consent diff_hash (raw bytes) != delegate diff_hash (normalized
     bytes). Binding relies on raw bytes identity, NOT on cross-hash equality.
5. Persist link file `documenter/intent/delegate_consent_link.json`:
   {request_id, approval_id, diff_b64 (base64 of the EXACT raw bytes staged
   for consent), consent_diff_hash ("sha256:"+sha256(raw), must equal the
   consent record's diff_hash), target_id, change_type, trust_level,
   created_at}.
6. Print a human summary: request_id, approval_id, review command hint.

### consume (after operator decision; run by the proposing side)
1. Load link file `documenter/intent/delegate_consent_link.json`; missing →
   exit 1 "nothing to consume".
2. read_pending / latest-record-wins lookup of the record for link.request_id
   (latest record for that request_id wins — lifecycle pending→approved/
   denied→consumed). If state still "pending" → exit 1 "no decision yet".
   If "consumed" → exit 1 "already consumed" (no side effects).
3. denied → remove link file, print decision, exit 1 (approval left to
   expire; NO service call).
4. approved: run prune_pending first (expiry) and re-check; then:
   a. verify_decision(record, decision) MUST pass (HMAC signature +
      integrity); failure → exit 2, keep link.
   b. decision's diff_hash (the consent record's diff_hash — what the
      operator approved) must equal link.consent_diff_hash AND
      sha256(raw bytes from link.diff_b64) must also equal it (link
      self-consistency); mismatch → refuse exit 2, keep link, NO service
      call.
5. min_approval_delay is enforced server-side by --approve; call
   `--approve --approval-id ID --acknowledge CONFIRMED_SOLE_REVIEWER --json`;
   on refusal propagate exit 2.
6. Apply: `--delegate-write --target ID --change-type ... --trust-level ...
   --diff-base64 <link.diff_b64> --approval-id ID --json` — the EXACT bytes
   from the link (identical to what the operator reviewed); expect
   applied: true; else exit 2.
7. mark_consumed(request_id, state_root); remove link file. Print summary.
   Exit 0.

## Hard constraints (safety)

- NEVER write documents directly; all writes go through documenter_service CLI.
- NEVER create/remove the sentinel; never touch ~/.council files (read-only
  fallback for operator id/secret is fine); never edit documenter_policy.yml.
- consume MUST NOT call --approve before verify_decision passes AND hash
  binding matches.
- No commits. Stdlib only (subprocess to invoke the service CLI is fine).
- Import consent_terminal from tools/ (sys.path handling like other tools).
- If consent_terminal API differs from the description, ADAPT to its real
  API; do not modify consent_terminal.py.

## Acceptance criteria (tests: tests/test_delegate_consent.py, unittest)

1. propose: with stubbed service CLI (fake argv capture) and a real temp-dir
   consent draft creation: activation gate fail-closed (state != active → exit
   2, no delegate call); happy path calls audit→delegate-write→create_request
   in order with bound metadata; link file written.
2. consume: no decision → exit 1, no service calls; denied → exit 1, no
   --approve call, link removed; approved with hash mismatch → exit 2, no
   --approve; approved with match → approve then apply called in order,
   mark_consumed called, link removed, exit 0.
3. Refusal path: delegate-write error (exit 2 JSON error) → propose exits 2.
4. Tamper: link file hash differs from stored → consume refuses.

## Whitelist (writable)

- tools/delegate_consent.py (new)
- tests/test_delegate_consent.py (new)

## Test command

    python3 -m unittest tests.test_delegate_consent -v

Framework: unittest (repo standard). Run from repo root.
