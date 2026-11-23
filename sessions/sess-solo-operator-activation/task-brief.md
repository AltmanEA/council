# Task Brief — Tier 2+ activation under a single (solo) operator

Session: sess-solo-operator-activation (fallback mode, 2026-11-17)
Orchestrating agent: primary agent acting as secretary; operator acts as fallback Moderator.

## Task description

The Council project is maintained by **one human operator**. The Documenter Service
(`documenter_service/`) has its Tier 2+ write branch implemented but dormant behind
the ADR-013 dual interlock (policy gate `active_tier:1`+`briefing_ref:null` AND the
absent Operator Surface sentinel `documenter/.operator_surface_ready`). Phase A of the
activation plan is complete: candidate policy and draft briefing exist under
`documenter/artifacts/`.

Blocker: `docs/en/documenter-service/mvp-contract.md` §4 (Tier 2+ Reachability) states:
*"Single-operator deployment is not a valid Tier 2+ configuration — approver ≠ proposer
cannot be satisfied by one person with two IDs."* The operator cannot recruit a second
human principal in the foreseeable future, yet wants Documenter write capability active
so that approved documentation changesets (and RU synchronization) are executed by the
service rather than by hand.

**Question for the consilium:** what is the best way to enable Documenter Tier 2+ under a
solo operator? Consider at least these stances and any better alternative:

- (a) Keep §4 strict; do not activate Tier 2+ at all (status quo, manual writes via
  Documentation Worker skill only).
- (b) Amend §4 to admit solo operation with compensating controls, e.g.: out-of-band
  approval ingress (approval token delivered/confirmed via a channel not reachable from
  the proposing session), minimum delay between propose and approve, mandatory item-by-item
  diff review, narrow `allowed_operations` (safe metadata only at first, expand later),
  reconcile-after-reversal duty, git-only reversal path.
- (c) Two logical principals operated by one person, accepting the §4 violation as a
  documented, time-boxed exception with review date.
- (d) Tier-limited activation: Tier 2 enabled only for `safe` mechanical change types
  (metadata/changelog tails), content edits stay Tier 1 preview + manual apply.

Note: per ADR-016, activation conditions are set by code (policy file + sentinel);
prose may describe but not create gates. §4's approver≠proposer is enforced in code
(`core/policy.py`/`core/write.py`: operator_id from `COUNCIL_OPERATOR_ID` env only,
approver ≠ proposer check on approve). Any chosen option (b)/(d) may require a small
code change or a policy-shape change — identify exactly what must change in code vs docs.

## Context available to reviewers (read-only)

- `docs/en/documenter-service/mvp-contract.md` §4 (canonical Tier 2+ contract)
- `docs/en/documenter-service/policy-reference.md` (Authorization Workflow, allowed_operations)
- `docs/en/documenter-service/approval-surface.md`, `docs/en/operator-surface/index.md`
- `documenter_service/core/policy.py`, `documenter_service/core/write.py` (interlock + approval mechanics)
- `operator_surface/core/auth.py`, `operator_surface/core/verbs.py` (HMAC token AuthN; op-* sub format)
- `documenter/artifacts/policy-candidate-20261117.yml`, `documenter/artifacts/operator-briefing-20261117.draft.md`
- ADR-013/015/016 rows in `docs/en/planned-architecture/decisions/index.md`

## Canonical subject list

- SUBJ-001: §4 amendment vs exception vs status-quo (governance stance on solo Tier 2+)
- SUBJ-002: compensating controls set (out-of-band ingress, delay, narrowed ops, review duty)
- SUBJ-003: code changes required (approver≠proposer enforcement, auth changes) vs docs-only changes
- SUBJ-004: attack-surface delta (prompt-injection self-approval, secret handling, token issuance to self)
- SUBJ-005: reversibility and audit trail under solo operation (git-only reversal, reconcile, event log)
- SUBJ-006: operational burden on one person (rotation of duties, duty fatigue, break-glass)

## Constraints

- Do not propose bypassing the dual interlock by editing policy from within a session.
- Keep proposals MVP-sized (Python 3.11 stdlib-only per ADR-006; no crypto additions per ADR-007 — assess honestly if out-of-band ingress breaks that).
- Output per fallback/index.md §Output Structure; findings must cite SUBJ-xxx.

## Output limits

≤ 120 lines per role review; findings ≤ 8 per role; severity low|medium|high|critical.
