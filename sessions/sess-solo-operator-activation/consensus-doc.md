# Consensus Document — Solo-operator Tier 2+ activation of the Documenter

Session: sess-solo-operator-activation (fallback mode, 2 rounds)
Date: 2026-11-17
Moderator: human operator; secretary: primary agent
Roster: Architect, Reliability & Security, Human-Centric Designer, Operations Engineer
Inputs: task-brief.md, review-*-r1.md, review-*-r2.md (same directory)
Consensus state: **Conditionally Resolved** (all roles concerns/agree-with-reservations, no blocks; disagreements resolved in round 2)

## 1. Decision

**Adopt stance (d) with compensating controls as a BOUNDED RISK EXPERIMENT — not permanent architecture.**

Tier 2+ will be enabled for the solo operator under these constitutive terms:

1. **Safe-only launch scope.** `allowed_operations` limited to `update` at `trust_level: safe` (mechanical metadata: version fields, changelog tails), with **explicit target lists** (1–2 documents), never wildcards. Content edits and `create_ru` remain Tier 1 (preview + manual apply via Documentation Worker).
2. **No dual-ID illusion.** Stance (c) (one person, two IDs) is rejected — the string-equality approver≠proposer check would be satisfied by naming convention only, which every role identified as security theater.
3. **§4 becomes an explicit risk-acceptance clause,** amended out-of-session through the normal documentation workflow: solo operation admits that approval is procedural self-review, not independent verification. Framing: documented risk acceptance, not a security improvement.
4. **Code-before-activation gate.** No operator may touch `active_tier`/`briefing_ref`/sentinel until the activation changeset (below) is merged and green in CI.

## 2. Subjects — outcomes

| Subject | Outcome |
|---|---|
| SUBJ-001 governance stance | Conditionally agreed: stance (d), bounded experiment, §4 amended as explicit risk acceptance with review date |
| SUBJ-002 compensating controls | Agreed: `allow_solo_approval: false` fail-closed default; `min_approval_delay_seconds` (range [60, 86400], floor ≥ 300, enforced at surface layer on `approve()`); narrow explicit targets; protected-paths blocklist (`docs-manifest.yaml`, `documenter_policy.yml`) enforced at staging; surface in a separate process tree; secret via systemd drop-in / file source, never shell export |
| SUBJ-003 code vs docs | Agreed: BOTH. Code: schema fields + `validate_policy` rules; solo-mode branch in `write.py`; ApprovalRegistry JSONL persistence (`documenter/intent/approvals.jsonl`, git-tracked per ADR-008); `_precheck_override_consumed` → append-only journal; protected-paths blocklist; bias-warning banner + typed acknowledgment token in `documenter.approve`. Docs: §4 amendment, policy-reference update, briefing, new ADR. Single enforcement point for approver≠proposer: Documenter Service `write.py` (surface pre-screen may duplicate but must not diverge) |
| SUBJ-004 attack-surface delta | Concerns recorded (irreducible): prompt-injection self-approval remains dominant vector; mitigations = min-delay + item-by-item diff review + git-only reversal + reconcile; residual risks accepted by operator |
| SUBJ-005 reversibility/audit | Agreed: git-only reversal; mandatory `--reconcile` before next `delegate()` after any manual git operation; approvals journal as audit trail |
| SUBJ-006 solo duty | Concerns recorded; ramp mechanism agreed (see §4) |

## 3. Pre-activation blockers (must ship in the merged, tested activation changeset)

1. ApprovalRegistry persistence to JSONL (blocks cross-session approve; silent loss otherwise) — raised by Ops, elevated critical by Architect, confirmed by R&S/HCD.
2. `_precheck_override_consumed` persistence (same defect class; replay vector on restart).
3. Policy schema: `allow_solo_approval` (bool, fail-closed `false`) + `min_approval_delay_seconds` (int, [60, 86400], floor ≥ 300) with load-time validation rules; absent ⇒ strict mode.
4. Solo branch in `write.py`: when `allow_solo_approval: true`, self-approval is permitted ONLY for `safe`-only matched operations AND requires the typed acknowledgment token; when `false` — current hard block.
5. Protected-paths blocklist enforced during `_apply_write_changeset()` staging.
6. Bias-warning banner + acknowledgment (e.g., `CONFIRMED_SOLE_REVIEWER`) validation in the approve path (HCD tier-1).
7. Verification items per prevention norm (every high/critical finding → reproducing test):
   - gate_failure when proposer == operator_id and `allow_solo_approval: false`;
   - solo approve rejected without acknowledgment token even when solo permitted;
   - registry/override journal survive simulated process restart;
   - delegate refused when diff touches a protected path;
   - approve refused before `min_approval_delay_seconds` elapsed.

## 4. Ramp and review (bounded-experiment mechanics)

- **Clean cycle** (Ops definition, event-log deterministic): one full `delegate(preview=False)` → `approve` → `apply_write` with exactly one `documenter.approval decision:approved`, zero `hash_mismatch`/`gate_failure` in the lifecycle, cold-start `reconcile` clean.
- **Widening:** after **5 consecutive clean cycles**, operator may expand by exactly ONE change_type OR one target document; re-measure 5 cycles per expansion. No broadening leaps.
- **Review date:** mandatory re-evaluation ≤ 30 days after activation (scope adequacy, residual risks, whether to continue, narrow, or revert to Tier 1).
- **Rollback:** set `active_tier: 1` (next-invocation effect); git-revert affected files; `--reconcile`.

## 5. Role reservations (verbatim essence, tied to subjects)

- R&S: one mind two hats is irreducible; controls produce evidence, not separation; acceptable only as bounded experiment; secret rotation deferred (Phase 2); HMAC demoted critical→medium given separate-terminal clarification, residual = env-var dumpability (mitigate: systemd drop-in).
- Architect: safe-only scope may prove too restrictive — upgrade path within 30 days essential; alias resolution deferred; reconcile Branch-1 orphan tmp cleanup is Phase 2; `rollback_reason` field recommended.
- HCD: min-delay alone doesn't counter confirmation bias (acknowledgment token is the stopgap, risk of becoming mechanical); counter-proposes default 900s vs consensus 300s (operator decision); structured diff annotations post-activation.
- Ops: activation conditional on §3 shipping tested; `operator_approval_timeout` likely needs 600s for solo cadence; approvals.jsonl git-tracked (ADR-008).

## 6. Open questions (operator decisions)

- OQ-1: default `min_approval_delay_seconds` — **RESOLVED by Moderator 2026-11-17: 300** (Architect/Ops position; floor 300 agreed; HCD's 900s noted as reservation — operator may raise per-document later).
- OQ-2: first activation target document + which 1–2 changelog/metadata scopes. **RESOLVED by Moderator 2026-11-17: variant A+B** — pilot targets `documenter-service-configuration-guide` and `operator-surface/index.md` (safe-only: version fields + changelog tails); rationale: both change naturally during AI-1/AI-2, so 5 clean cycles accrue without artificial edits.
- OQ-3: timeline for any second principal — converts exception back to norm (none foreseeable).
- Moderator verdict: **Conditionally Resolved CONFIRMED** (2026-11-17).

## 7. Escalations resolved en route

- Architect information-gap (schema expansion legality) — closed by operator clarification (out-of-session changeset permitted).
- R&S risk-threshold-breach — converted to concerns in r2 after clarifications + package; residual recorded as irreducible.
- Ops risk-threshold-breach — converted; residual accepted under §3/§4 conditions.

## 8. Findings downgraded for invalid justification

None. All critical findings carried concrete failure modes; severities were adjusted only through evidence (clarification 3 demoted R&S HMAC finding from critical to medium).

## 9. Action items

- AI-1 [code, TDD via implementation skill]: activation changeset §3 items 1–7, aligned with §2 SUBJ-003 canonical schema (naming: `min_approval_delay_seconds`).
- AI-2 [docs via Documentation Worker, post-Approve]: `mvp-contract.md` §4 risk-acceptance amendment; `policy-reference.md` new fields + solo authorization notes; briefing regeneration from `documenter/artifacts/operator-briefing-20261117.draft.md`; new ADR-017 (solo-operator Tier 2+ bounded experiment) in `planned-architecture/decisions/index.md`.
- AI-3 [operator]: decide OQ-1/OQ-2; after AI-1+AI-2 merge and green CI, execute out-of-session activation acts (policy edit with narrowed ops, briefing archive, surface launch, sentinel, MCP registration decision).
- AI-4 [operator, +30d]: scheduled review per §4.
- AI-5 [deferred, Phase 2]: secret rotation, alias resolution, structured diff annotations, reconcile Branch-1 cleanup.

---
*Produced in fallback mode per `fallback/index.md` Phases 1–5. This document is an implementation-file artifact under `sessions/` (outside Documenter scope); the normative changes it mandates flow through AI-1/AI-2.*
