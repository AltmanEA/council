# Session Task Brief — Fast Operator Confirmation of All Documenter Operations

Session: sess-solo-operator-fast-approval (fallback mode)
Date: 2026-11-19
Mode: fallback per fallback/index.md (Moderator = human operator; secretary = primary agent)

## Session Goal

Decide how the single (solo) operator can confirm Documenter write operations **quickly and with minimal friction**, determining: which confirmation path(s) to use (ADR-017 solo approval vs Tier 3 pattern auto-apply vs new mechanism), what checks MUST remain regardless of the operator's speed preference, and what changeset (docs / code / policy-overlay / operator acts) is required.

## Problem Statement (operator request, verbatim intent)

"У нас в системе будет один оператор. Нужно сделать так, чтобы он мог подтверждать все операции Документатора, причем достаточно быстро, с минимальными тестами-проверками."

Operator wants: one operator confirms ALL Documenter operations; confirmation should be fast; verification steps should be minimal.

## Current State (ground truth from manifest documents)

- Documenter Tier 0–1 operational; Tier 2+ write branch implemented but DORMANT behind ADR-013/ADR-016 dual interlock (policy state + sentinel `documenter/.operator_ingress_ready`); MCP unregistered. Activation is an operator act out-of-session.
- `approver ≠ proposer` is the norm (mvp-contract.md §4). **ADR-017** already created a solo-operator exception (sess-solo-operator-activation, 2026-11-17, consensus Conditionally Resolved): self-approval permitted ONLY when all of: `allow_solo_approval: true`; matched operation `trust_level: safe` (mechanical update only); typed acknowledgment token `CONFIRMED_SOLE_REVIEWER`; `min_approval_delay_seconds` elapsed (range [60,86400], consensus floor 300). Bias-warning banner mandatory. Ramp: +1 change_type OR +1 target per 5 consecutive clean cycles. Mandatory review ≤30 days. Rollback: `active_tier: 1` + git-revert + `--reconcile`.
- `review`-trust operations (`split`, `create_ru`, `custom`, non-mechanical `update`) cannot be solo-approved under ADR-017 — the exception is safe-only.
- Tier 3 pattern auto-apply exists in the spec: operator pre-authorizes explicit `type: pattern` entries; matching changes auto-apply (still with diff preview; critical items require per-item review). Advancement gate: ≥90% approval rate over preceding 2 weeks of event log.
- Mandatory fail-closed checks that no tier removes: diff-hash binding + single-use `approval_id` + `approval_expiry_window`; changed-diff invalidation; pre-audit gate (`audit_freshness`, blocking findings); `critical` findings block writes at every tier; protected-paths blocklist (`docs-manifest.yaml`, `documenter_policy.yml`); policy file edits are activation acts reserved to the operator out-of-session.
- `documenter.override_gate` allows one-time override of an audit-gate failure with reason (never for `critical`).
- Activation overlay (ADR-020): external YAML, scope presets `pilot-safe-v1`, `docs-maint-safe`, `docs-content-review`, `ru-sync-review`; base policy stays Tier 1 baseline.
- Constraints: fallback/ is frozen; agents MUST NOT edit policy files or register MCP; no direct edits to docs/ (Documentation Worker skill only, after operator approval step).

## Focus Areas

- Which confirmation path gives the operator "fast confirmation of ALL operations" WITHOUT breaking fail-closed invariants — and whether "all operations" is achievable at all under current norms or requires an explicit new risk-acceptance decision (new ADR).
- The minimum irreducible check set (what MUST NOT be minimized away) vs the checks whose friction can legitimately be reduced (delay seconds, per-item ceremony, batch/group summaries, audit_freshness window, operator_approval_timeout).
- Is Tier 3 pattern auto-apply the correct "fast path" answer, and what is the legitimate route to reach it from dormant Tier 2+ (the ≥90%/2-weeks evidence gate vs solo-experiment reality)?
- What exactly must change: policy/overlay values, docs amendments, code (implementation skill), and operator out-of-session acts.

## Questionnaire per Role

**Architect:**
- Q1: Does "confirm all operations quickly" map onto existing mechanisms (ADR-017 ramp, Tier 3 patterns, scope presets/overlay), or does it demand a new mechanism/interface? Where would each option live (Layer 1/2, policy, spec)?
- Q2: Does a per-batch group-summary confirmation (Tier 2 batch approve) or pattern auto-apply conflict with any canonical contract in mvp-contract.md §4?

**Reliability & Security Specialist:**
- Q1: Which fail-closed checks become attack vectors if we minimize them (name concrete failure modes: prompt-injection self-approval, changed-diff swap, stale audit replay, protected-path overwrite)?
- Q2: What is the minimum irreducible check set for a solo deployment, and which proposed speed-ups cross the risk threshold and must be rejected?

**Human-Centric Designer:**
- Q1: What confirmation cadence (delay seconds, batch size, single ack token reused vs retyped) keeps a single human honest without fatiguing them into rubber-stamping?
- Q2: Which friction reductions would increase rubber-stamping risk more than they save time?

**Operations Engineer:**
- Q1: What is the concrete activation sequence (overlay, scope preset, sentinel, MCP registration, briefing) to get the operator to a working fast-confirmation state, and what values for operational knobs (min_approval_delay_seconds, approval_expiry_window, audit_freshness, operator_approval_timeout, rescan_batch_ceiling) serve "fast" safely?
- Q2: What observability/rollback guarantees must exist before friction is reduced (clean-cycle counting, reconcile, event-log evidence for Tier 3)?

## Output Limits
- Maximum findings per role: 5–7
- Maximum recommendations per role: 3–5
- Maximum open questions per role: 2–3
- Total output: ~150 lines per role; brevity encouraged.

## Expected Discussion Rounds
- 1 round (medium complexity).

## Subject List
- SUBJ-001: Scope — can "all operations" be fast-confirmed; which operations are non-negotiable per-item review (review-trust, critical, protected paths)?
- SUBJ-002: Mechanism choice — extend ADR-017 solo path vs Tier 3 pattern auto-apply vs batch/group-summary confirmation vs new mechanism.
- SUBJ-003: Irreducible check set vs legitimately reducible friction (delay, expiry, timeout, audit freshness, ceremony).
- SUBJ-004: Ramp/evidence gate to fast path — is the ≥90%/2-week Tier 3 evidence gate compatible with solo reality; what ramp is admissible?
- SUBJ-005: Required changeset — policy/overlay values, docs amendments (which documents), code work (which files), operator out-of-session acts; sequencing.

## Additional Context / Constraints
- Read (via manifest paths): `docs/en/documenter-service/approval-surface.md`, `docs/en/operator-ingress/index.md`, `docs/en/documenter-service/policy-reference.md`, `docs/en/documenter-service/mvp-contract.md` §4, `docs/en/documenter-service/index.md` §Trust Tiers/§Trust Classification, `docs/en/planned-architecture/decisions/index.md` (ADR-013/016/017/020), prior consensus `sessions/sess-solo-operator-activation/consensus-doc.md`.
- The previous session already accepted solo approval as a BOUNDED experiment; this session must respect or explicitly (via operator risk acceptance) amend that decision — not silently contradict it.
- Agents cannot activate anything themselves; outcome is a recommended changeset + operator acts.
