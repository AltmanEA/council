# Tier 2 Delegation Briefing — Documenter write branch

Status: archived operator briefing (reserved artifact; `briefing_ref` target).
Adopted: 2026-11-14, operator decision (Tier 2+ implementation session,
plan `sess-doc-reliability-algo`). Referenced from
`documenter-service/policy-reference.md` §Authorization Workflow step 4.

**Runtime state:** the write branch is implemented but the repository policy
(`documenter_policy.yml`) stays at `active_tier <= 1` with `briefing_ref: null`.
Activating a write path requires an explicit operator edit setting
`active_tier: 2`, `briefing_ref: briefings/tier2-delegation.md`, and a
non-empty `allowed_operations` list in the same edit (policy-reference
§Authorization Workflow step 5). Until then every non-preview call fails
closed with `tier_interlock`.

## Scope of delegated authority

- change_type values: `update` only. `split`, `create_ru`, `custom` remain
  review-floor operations; `create_ru` auto-fix stays banned (MVP rule).
- Documents: only manifest-tracked IDs enumerated in
  `allowed_operations[].targets` of the active policy; an empty `targets`
  list means every manifest document and MUST NOT be used without a second
  operator review of this briefing.
- Single invocation may touch **one** document (`target_ids` length 1).
  Multi-file commits are reserved by mvp-contract §2.2.5 and not delegated.
- Every write requires: a fresh in-scope `audit_id` (pre-audit gate rules
  1–5), a canonical `diff_hash` bound approval resolved out-of-band by an
  operator principal distinct from the proposer, and apply-time sha256
  verification (conflict C2).

## Reversal procedure

1. `git restore <file>` — the service never commits; every applied write is
   an unstaged working-tree change (threat model, mvp-data-models §Purpose).
2. Registry records (`documenter/audit_registry.jsonl`) are append-only
   evidence: propose/approve/apply/intent records remain for the audit
   trail; a reversal is itself recorded by a follow-up restore plus an
   operator note in the next session log.
3. Registry damage: restore the registry file from any prior commit
   (`git restore documenter/audit_registry.jsonl`).

## Non-delegated (explicitly withheld)

- `override_gate` for `critical` findings (unavailable by mvp-contract §4).
- Tier 3 pattern auto-apply: requires `active_tier: 3`, explicitly
  enumerated `type: pattern` entries, ≥90% approval rate over VIEWED diffs,
  and quarantine per policy-reference §Authorization Workflow step 7.
- Any autonomous re-proposal after refusal; every refusal routes to
  `next_action` per mvp-interfaces §4.
