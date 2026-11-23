# Consensus Document — Operator Consent Terminal

Session: `sess-operator-approval-tool`
Date: 2026-11-18
Mode: fallback v0.6.0, local model (`freetoken/Qwen3.6-35B-A3B-NVFP4`), strictly sequential subagents (documentation-rules §5.4)
Roster: Architect, Reliability & Security Specialist, Human-Centric Designer, Operations Engineer
Rounds: Phase 2 (individual reviews) + 1 discussion round; all roles final status **agree**. No escalations; no critical findings downgraded for invalid justification.

---

## Decision

Build a standalone stdlib-Python **consent terminal** — `tools/consent_terminal.py` — as the operator's single point of approval for step-(5) documentation changesets. The agent registers a pending approval request; the operator runs one short command in a separate terminal and decides with one keypress (safe tier) or Enter-to-expand + `y`/`n` (review tier). Reliability is preserved via a file-based spool with hash-bound, HMAC-detected, single-use decision records and deny-by-default semantics. The §4 `documenter.approve` / ADR-017 solo / Tier 2 paths are explicitly **out of MVP** pending a dedicated adapter.

## Subjects and Outcomes

### SUBJ-001 — Architecture (agreed)
Standalone tool, file-based spool at `documenter/intent/approvals.jsonl` (git-tracked per ADR-008). No daemon, no JSON-RPC coupling to the dormant Operator Ingress, no MCP registration. The tool reuses `ApprovalRegistry` (`operator_ingress/core/approval.py`) **as schema and guard-logic reference** (import), not as a shared instance; every reader/writer MUST coordinate via `fcntl.flock(LOCK_EX)` — note: the current `ApprovalRegistry._save()`/`_load()` do NOT lock; flock must be added around all access paths (tool + agent) as part of implementation.

Lifecycle states: `pending` (agent writes via `request`) → `approved`/`denied` (consent terminal writes, only writer of decisions) → `consumed` (agent writes after apply/acknowledge). Prune = append `state: denied` + `reason` records (expired / corrupted / diff_file_missing); no line deletion (append-only, audit preserved).

New agent-side integration point (Architect, critical): today no code reads `approvals.jsonl`; the agent-side consumption contract (below) is part of delivery.

### SUBJ-002 — Contract mapping (agreed)
The tool is the **faithful carrier of step-(5) Approve** (documentation-rules §5.1–5.2), not a bypass: the change is applied only when the record shows `state: approved` with matching HMAC and diff hash; missing/expired/malformed/tampered record = denial. Distinct from §4 `documenter.approve` (different contract, different store); conflation forbidden. ADR-017 solo flow (`CONFIRMED_SOLE_REVIEWER`, delay) is OUT of MVP; when the future `ConsentRegistry → AuditRegistry` adapter is built it MUST (a) translate flat records to `token_record` envelopes with chain integrity, (b) preserve/pass through the `hmac` field (Security MUSTs).

### SUBJ-003 — Informed-consent presentation (agreed)
Screen shows: request id (short), `target_path`, change level, diff hash prefix, tier, expiry countdown, agent-authored `summary` (≤200 chars, treated as a pointer only), and diff stats. Verbatim diff always reachable via `s` (no-LLM-paraphrase rule binds the diff, not the summary). Before presenting, the tool verifies `sha256(diff_text) == diff_hash`; mismatch → auto-deny `INTEGRITY FAIL`. Anti-rubber-stamp gate: `y` ignored for `review` tier until `Enter` expands the diff; `safe` tier (zero-diff metadata) accepts `y` immediately — this realizes the operator's "one keypress" mandate without habituation coercion. One item per run (FIFO oldest); no batch/`--watch` in MVP.

### SUBJ-004 — Security controls (agreed)
- **HMAC-SHA256** over canonical sorted-JSON of `{request_id, diff_hash, proposer_operator_id, state, created_at}` keyed by `~/.council/operator_secret`, stored on decision records (`hmac`, `signed_at`). Prose contract must state verbatim: signing provides **procedural separation and tamper *detection*, not cryptographic isolation** (same-UID threat model, mirroring `tools/start_operator_ingress.sh` SECURITY note). A forged decision is a *detectable incident*, not a prevented one.
- **Two independent hash checks**: tool at decision time (anti diff-swap), agent at apply time (anti post-decision tampering).
- **Deny-by-default**: expiry enforced both sides (tool refuses expired items; agent treats expired/absent/malformed as denial). Timeout never hangs the operator.
- **Agent-side Verification Gate** (enforcement point: Documentation Worker skill wrapper contract): before any step-(5) write — state==approved ∧ HMAC valid ∧ diff hash match; anything else → do not write.
- Honest threat model: agent CAN read the secret and forge records — accepted as out of model (adversary = buggy/overreaching agent + inattentive operator, not crypto-adversarial); agent ignoring denial is neutralized by "record governs, absence = denial".

### SUBJ-005 — Operator UX flow (agreed)
Keypress grammar: `y` approve (tier-gated), `n` deny, `Enter` expand/unlock, `s` verbatim diff pager, `q` quit (exit 0, no decision), `Ctrl-C` deny (exit 1); unknown key → re-prompt. Exit codes: 0 approved, 1 denied/expired, 2 usage. Receipt line printed on every decision: `APPROVED | id=<full_request_id> | target=<path> | diff=<hash[:8]> | time=<ISO>` (DENIED equivalent); full id for log correlation.

## CLI (implementation-ready) — amended by operator decision, 2026-11-18

Parameterless request + launcher scripts (operator directive: request must take no CLI parameters; the agent writes inputs to a file; launchers are plain runnable scripts).

```
# 1. Agent writes (via its normal file tools):
#    documenter/intent/consent_draft.json  {target_path, summary, tier, diff_file, expiry_minutes?}
#    documenter/intent/diffs/<id>.diff     (the verbatim diff text)
# 2. Agent ingests the draft, NO parameters (returns immediately, exit 0):
python3 tools/consent_terminal.py request
# 3. Operator, in a SEPARATE terminal, run by name only (one-shot):
tools/consent_review.sh            # thin wrapper: flock-checked review, pass-through of optional --request-id for resume/tests
```

Ingest rules for parameterless `request`: validate draft schema fail-closed (malformed JSON / unknown tier / missing diff file → reject, quarantine the draft under `documenter/intent/quarantine/`, exit 2); **the tool itself computes `diff_hash` from the diff file and generates `request_id`** (the agent supplies neither); summary ≤200 chars; `diff_text` cap 64 KB (over cap: `diff_text_truncated: true`, operator reads diff via pager on target path). Default expiry 30 min (aligns `approval_expiry_window`). Credentials reuse `COUNCIL_DOTDIR` / `~/.council` exactly as `start_operator_ingress.sh` (no new env vars).

Security delta (positive): moving from CLI parameters to tool-computed `diff_hash` / `request_id` removes two agent-authored trust inputs; review-time integrity check `sha256(diff_text) == diff_hash` unchanged.

## Agent-side operational contract (to be embedded in skill wrapper guidance)

1. Compose changeset → run `request` → print the exact `review` command for the operator → tell the operator you are waiting until `expiry_deadline`.
2. Bounded poll of `approvals.jsonl` (flock-locked read, every ~5 s, bounded by expiry; harness timeout ≥ poll window). If the poll is killed by harness limits: record stays `pending`, poll resumes next turn — no data loss.
3. Verification Gate (SUBJ-004): approved ∧ HMAC ∧ hash.
4. Apply if approved; transition to `consumed` (flocked write). On denial/expiry: do not apply; transition to `consumed`.

## Reservations (recorded, non-blocking)

- **Security**: the `ApprovalRegistry` import is a **frozen dependency** — safe only while the Tier 2+ interlock is closed (ADR-016); must be audited if the interlock ever opens.
- **Architect**: MVP must not gain a §4 surface by accretion; the adapter is a separate future decision with the two MUSTs as admission criteria.
- **HCD**: tier discriminator (`safe|review`) is the highest-leverage UX switch; mislabeling `review` items as `safe` defeats the anti-rubber-stamp control — the agent must set tier honestly (zero-diff only).
- **Ops**: bounded poll vs harness timeout ceiling is environment-dependent; behavior on mid-poll kill is defined (resume), accepted.

## Open Questions (non-blocking, deferred)

- OQ-1: Should `check_all` grow the stale-pending (>24 h) subcheck at MVP or fast-follow? (Ops proposed MVP; decide at implementation review.)
- OQ-2: Exact `request_id` format convention (session-scoped `sess-<id>/<hex>` assumed) — finalize in implementation.
- OQ-3: Whether to add flock upstream into `operator_ingress/core/approval.py` vs wrap in the tool — implementation decision, must satisfy "all access paths locked".

## Action Items

1. Implement `tools/consent_terminal.py` (request/review, spool, HMAC, flock, tier-gated UI, prune) — code work via the normal implementation process (code author, not Documentation Worker).
2. Tests: `tests/test_consent_terminal.py` — happy approve path, deny path, integrity-fail (hash mismatch), expired-deny.
3. Prose-contract sync (AGENTS.md §1.7): `tools/README.md` entry + Documentation Worker skill wrapper contract update (step-(5) gate now reads the spool; Verification Gate wording), same changeset as the tool.
4. Ops: confirm `documenter/intent/` git-tracking policy lands with the tool (commit spool records).
5. Explicitly deferred (do NOT build in MVP): §4 adapter, ADR-017 solo flow, `--watch`/batch, Operator Ingress coupling.

## References

- Reviews: `review-Architect.md`, `review-Security.md`, `review-HCD.md`, `review-Ops.md`
- Round 1: `discussion-round-1-{Architect,Security,HCD,Ops}.md`
- Controlling docs: `docs/en/documentation-rules/index.md` §5, `docs/en/documenter-service/mvp-contract.md` §4, `docs/en/documenter-service/approval-surface.md`, ADR-008/016/017, `fallback/index.md`
- Code touched at implementation time: `tools/consent_terminal.py` (new), `operator_ingress/core/approval.py` (import; possible flock patch), `tools/README.md`, `.agents/skills/documentation/SKILL.md` (wrapper contract)
