# Operator Briefing — Tier 2+ Delegated Authority

Status: **ARCHIVED — reviewed and signed by the operator 2026-11-17** (§5 checkboxes complete).
Prepared: 2026-11-17 (Authorization Workflow step 4, `policy-reference.md` §Authorization Workflow).
This artifact is the human-readable counterpart of `allowed_operations` in the live policy
(`documenter_policy.yml`); activation reference: `sessions/sess-solo-operator-activation/consensus-doc.md`
(ADR-017 solo-operator bounded experiment).

> **Pilot scope note (ADR-017 ramp).** Although §1 describes the full delegation envelope,
> the live policy at activation delegates only `update` at `safe` for the two pilot targets
> (`documenter-service-configuration-guide`, `operator-surface`) — consensus OQ-2 variant A+B.
> Widening (change_types or targets) requires 5 consecutive clean write cycles and happens
> one change_type or one document per expansion, under the ≤30-day mandatory review (AI-4).

## 1. Delegated documents and change types

- **Scope:** all documents listed in `docs-manifest.yaml` (24 documents under `docs/`), plus their recorded RU translations (`has_translation` paths), plus their changelog files (`CHANGELOGS/`).
- **Delegated `change_type` values:**
  - `update` at `safe` — mechanical metadata (version/changelog bumps via the approved write order document → changelog → manifest);
  - `update` at `review` — content edits already approved by the operator at step (5) of the documentation workflow;
  - `create_ru` at `review` — RU synchronization per ADR-012/ADR-014, all Phase 4 write-gates enforced.
- **Not delegated:** `split`, `custom` (no `allowed_operations` entries; `delegate()` must refuse them with `gate_failure`). Manifest hand-edits remain prohibited (the manifest is written only by `tools/gen_manifest.py`).

## 2. Maximum documents per single invocation

- **One (1) document per invocation** at the start of Tier 2+ operation, including its changelog and manifest refresh as the mechanical tail of the same document's changeset. Multi-document commit sets (Multi-file Commit Protocol) may be raised to a higher ceiling only by an amended briefing after observed operation.

## 3. Preconditions on every write

- Fresh `audit_id` within `audit_freshness` (30 min); zero open `high`/`critical` findings for the target.
- Diff reviewed item by item by the operator regardless of tier (step 6: capability ≠ reduced scrutiny).
- **Approval identity:** the norm is `approver ≠ proposer` — one person holding two `op-*` IDs is not a valid configuration (`mvp-contract.md` §4). The single permitted exception is the ADR-017 solo-operator bounded experiment: with `allow_solo_approval: true` in the policy, self-approval is allowed only for `safe`-trust matched operations (verified against the `change_type` persisted on the approval record), only with the typed acknowledgment token `CONFIRMED_SOLE_REVIEWER`, and only after `min_approval_delay_seconds` has elapsed since the proposal. Every solo approval returns a bias-warning banner and must be read item by item — solo mode removes the second reviewer, not the scrutiny.

## 4. Reversal procedure

1. **Immediate stop:** set `active_tier` back to `1` in `documenter_policy.yml` (rollback act, effective next invocation; in-flight `delegate()` completes under the accepting tier per §Safety Protocol #2).
2. **Content reversal:** revert the affected files from git (the Documenter never commits; every accepted write lands on top of a clean committed state — `git revert`/`git checkout` of the affected paths).
3. **Registry consistency:** run `python3 -m documenter_service --reconcile` after reversal; resolve any `needs_attention` entries before the next write.

## 5. Operator commitments (to be signed by the operator)

- [x] I have reviewed the candidate policy and its `allowed_operations`.
- [x] I accept the crash-recovery boundary of ADR-015 (intent metadata only, no roll-forward) — **p3 reservation SUBJ-106/107, required before activation per p2 roadmap**.
- [x] I accept the solo-operator configuration as a **bounded risk experiment** (ADR-017): `allow_solo_approval: true` is my explicit risk-acceptance act; I acknowledge that self-approval carries single-reviewer bias and that the bias-warning banner on every solo approval obliges me to re-read the diff item by item; I will conduct a mandatory review of the experiment within 30 days of activation and widen scope (change_types or targets) only after 5 consecutive clean write cycles, one change_type or one document per expansion.
- [x] The Operator Surface launch procedure (`operator_surface/REGISTRATION.md`) will be executed by me; sentinel creation and MCP registration are my acts.
