# Consensus Document — sess-documenter-workmode-refinement

Date: 2026-11-19
Mode: fallback (subagents sequential; operator as Moderator)
Predecessor: sess-documenter-concept-revision
Subject of review: `docs/en/documenter-service/index.md` v1.1.0-draft
Roster: Architect, Reliability & Security Specialist, Human-Centric Designer, Operations Engineer
Rounds: 1 (individual review) + 1 (discussion). Final statuses: all four `agree`.

## Decisions taken

### D-1 (SUBJ-001) — Staged work mode for complex edits

**Decision.** The concept document gains a "Complex edits" subsection under *Operating model*.
The single-commit invariant applies to the FINAL commit of a logical update, not to the number
of intermediate editing steps. Key elements (all prose-only, no new tools/state):

- **One approval turn.** The plan is agent-internal working context, never an approval object.
  The operator's `approve` binds to the **final assembled state** shown on the summary card.
  Plan↔final divergence is impossible by construction (no earlier consent exists to diverge
  from; an unapproved final state never commits). This resolves Security's CRITICAL
  "plan ≠ final content" and HCD's objection that plan-approval recreates v0 gating ceremony.
- **Invariant wording.** Intermediate states are not commits and do not violate the invariant.
- **Isolation.** Intermediate files live in a session-scoped area outside the `docs/` tree;
  `sessions/` is already gitignored, so staged work cannot be captured by `git add`. The concept
  states only the invariant ("intermediate work never touches committed state; only the assembled
  final bundle is written to controlled paths at commit time"); the concrete path
  (`sessions/<id>/staging/`) is a **SKILL.md** detail, not concept-level text (HCD: workspace
  layout is implementation detail).
- **Audit scope.** The advisory pre-commit pass runs on the assembled final bundle only, never on
  intermediate working-tree state.
- **Abort/crash.** New accepted risk #6: abandoned intermediate files persist in git-ignored
  areas; nothing is committed; the committed state is unchanged; cleanup is the operator's per the
  session workspace lifecycle (`fallback/index.md`); no recovery needed.

**Adopted wording (Operating model, new "Complex edits" subsection):**

> For complex updates spanning multiple steps, the skill may perform intermediate edits before
> assembling the final bundle. Intermediate states are not commits and do not violate the
> single-commit invariant (which applies only to the final commit). The operator's `approve`
> binds to the final assembled state on the summary card — the plan is agent-internal working
> context, never an approval object. The audit pass runs on the assembled bundle only.
> Intermediate files live in a session-scoped area outside the `docs/` tree; `sessions/` is
> gitignored by repository convention.

**Adopted wording (Accepted risks, #6):**

> 6. **Abandoned intermediate work.** If an agent is interrupted during staged work, intermediate
> files may persist in git-ignored workspace areas. Nothing is committed; the committed state is
> unchanged. Cleanup is the operator's per the session workspace lifecycle. No recovery is needed.

### D-2 (SUBJ-002) — "Deterministic actions → scripts" evolution stance

**Decision.** A short **Evolution stance** is added to *Principles* after OP-3 (placement by
consensus: "how things work" lives in Operating model, "what the system is" lives in Principles;
HCD r2 argument, adopted over Security's merged single-subsection draft). It records the
operator's direction of travel: deterministically-describable actions should eventually move
into scripts. Detailed design is explicitly deferred to a future **separate session** — today's
change adds the stance only.

Guardrails agreed by all roles:
- **Sole-writer preserved.** Scripts are dispatched by the skill under an operator-approved
  changeset; they never hold independent write authority (Security HIGH — anti-service-creep).
- **Ceiling by displacement.** `tools/` is already at the 12-file OP-2 ceiling; each promoted
  script replaces an existing one — zero net-new tools.
- **Anti-creep sentence** (attached to the stance, not a 4th Principles bullet, per HCD): the
  stance authorizes no new approval gates, tools beyond the ceiling, or state files.
- **Deferred-item tracking** in the producing session's consensus document ("Deferred Script
  Promotions" section; discovery via grep over archived consensus docs) — no state file (Ops).
- Inline gloss of "deterministic" included (HCD, accepted).

**Adopted wording (Principles, after OP-3):**

> **Evolution stance.** Deterministic actions (fully specified by inputs and rules, no judgment
> involved) should eventually be delegated to scripts under `tools/`, dispatched by the skill
> under an operator-approved changeset; scripts never hold independent write authority. Each
> promoted script must respect the OP-2 ceiling by displacement — replacing, not adding. This
> stance does not authorize new approval gates, new tools, or new state files. Deferred items are
> recorded in the producing session's consensus document; the detailed design is deferred to a
> future separate session.

## Subject outcomes

| Subject | Outcome |
|---------|---------|
| SUBJ-001 staged work mode | agreed (D-1) |
| SUBJ-002 evolution stance | agreed (D-2) |

## Role reservations (tied to subjects)

- Security: residual **semantic drift** risk (verbally discussed plan vs honestly-reported final
  card) — accepted under existing risk #1 (semantic blindness); defense is card honesty +
  named semantic approvals + revert, no new gates. [SUBJ-001]
- HCD: readability trade-off accepted against Ops' single-block consolidation; sync burden of a
  second section judged acceptable. [SUBJ-001/002]
- Ops: consensus-doc grep scaling is poor long-term; adequate for current volume, revisit if
  deferred-item count grows. [SUBJ-002]

## Operator rulings (resolved en route)

- `tools/README.md` is **exempt** from the OP-2 tooling ceiling (documentation, not executable
  tooling) — Ops ruling accepted by session; to be reflected as a clarifying parenthetical in the
  OP-2 paragraph.

## Open questions (for the operator, non-blocking)

1. Confirm the `tools/README.md` ceiling exemption as an operator ruling (session recommends it).
2. Whether the "Complex edits" subsection also mentions that the skill may present progress
   updates during long staged work (HCD open question; session default: no text, agent judgment).

## Action items

1. Apply D-1 + D-2 + risk #6 + OP-2 parenthetical to `docs/en/documenter-service/index.md`
   via the Documentation Worker skill after operator step-(5) Approve (semantic change: named
   approval required), with version bump and changelog; regenerate manifest.
2. Update `.agents/skills/documentation/SKILL.md` in the same changeset (prose-contract sync):
   staged-work dispatch details — session-scoped staging area under `sessions/<id>/staging/`
   (gitignored), audit on assembled bundle only, final-content summary card.
3. Update the RU mirror `docs/ru/documenter-service/index-RU.md` (separate translation pass,
   operator-triggered per convention).
4. Record "Deferred Script Promotions" (the SUBJ-002 detailed design) as a section of THIS
   consensus document — see below.

## Deferred Script Promotions (per D-2 tracking convention)

- Detailed design of deterministic-action → script promotion (separate session and separate
  document, per the operator's remark; scope: inventory of skill prose procedures that are fully
  deterministic, displacement map against current `tools/` inventory, SKILL.md dispatch rules).

## Critical findings downgraded

None (all Security criticals were resolved in discussion, not downgraded).

## Artifact index

- `task-brief.md`; `review-architect-r1.md`, `review-security-r1.md`, `review-hcd-r1.md`,
  `review-ops-r1.md`; `discussion-architect-r2.md`, `discussion-security-r2.md`,
  `discussion-hcd-r2.md`, `discussion-ops-r2.md`; this document.
