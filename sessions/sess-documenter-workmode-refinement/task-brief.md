# Task Brief — sess-documenter-workmode-refinement

Date: 2026-11-19
Mode: fallback (subagents launched sequentially, operator-as-Moderator)
Predecessor: sess-documenter-concept-revision (consensus accepted 2026-11-19; produced docs/en/documenter-service/index.md v1.x)

## Task description

The operator reviewed the reconstructed Documenter concept (`docs/en/documenter-service/index.md`,
v1.1.0-draft) and raised two remarks. The session must propose HOW to resolve them, i.e.
concrete wording/design proposals for the concept document (and any derived contracts).
Final authority: operator (OP-1). This session only produces proposals + consensus doc.

### Remark 1 — staged work mode for complex edits

Current text (Operating model, step 1):

> An agent (or the operator) proposes a changeset; the Documentation Worker skill prepares it
> and bundles **all files of one logical update into one commit** (the single-commit invariant —
> the foundation that keeps revert a viable recovery).

Problem: for **complex edits** (large rewrites, multi-document refactors, translations, splits)
a single-shot changeset is unrealistic. The operator wants a mechanism that allows working
**step by step through several changes** that are then **closed by one commit** — i.e. an
incremental working/staging procedure that preserves the single-commit invariant at completion.

Design questions for the roles:
- Where do intermediate steps live while work is in progress (working area? draft files? git
  staging? a session-local candidate tree?) and what guarantees they don't leak into the
  committed state or violate the sole-writer rule?
- When is the operator's `approve` taken — once per logical update at the end, per step, or both
  (e.g. plan approved up front, final content approved at close)? Must not violate OP-1 (no
  waiting, no gating) nor multiply state machines (OP-2).
- What happens to an abandoned staged session (abort/cleanup semantics, recovery story)?
- How does the audit pre-commit pass interact with staged work (audit the assembled final state
  only, or per step)?
- How is the single-commit invariant checked/stated: the invariant is about the FINAL commit,
  not about the number of edits — should the concept text say that explicitly?
- Hard constraint: OP-2 ceiling (≤12 tool files / ~3,600 LOC, 1 operator-facing command, no
  daemons, no state/config files). Any proposal that adds persistent state or new tools must
  justify it or be rejected in favor of a prose-only convention.

### Remark 2 — deterministic-actions-to-scripts principle

Current text (Operating model, closing paragraph):

> The Documentation Worker skill (`.agents/skills/documentation/SKILL.md`) remains the sole
> writer of `docs/`, `docs-manifest.yaml`, and `CHANGELOGS/`. There is no Documenter service,
> no MCP interface, and no intermediate authority between the proposal and the operator's yes.

Problem: the operator wants to record in the CONCEPT (as a core principle/stance) the idea that
actions which can be described **deterministically** should eventually be **programmed into
scripts** — to be worked out later in a **separate session and a separate document**. Today we
only add the thought; we do NOT design the mechanism, do NOT create the separate document.

Design questions for the roles:
- Where does this belong: a new principle (OP-4?), a clause under OP-2, or a short "Direction
  of evolution" section? What wording keeps it a stance, not a mandate or a roadmap commitment?
- How to phrase the boundary: skill/AI handles judgment work, scripts handle deterministic work —
  without contradicting the sole-writer rule (scripts are dispatched BY the skill, atomicity not
  authority — already the rule in SKILL.md) and without implying re-creation of the deleted
  Documenter service (OP-2).
- How to keep it honest with OP-2: script promotion must respect the tooling ceiling.
- Should it reference that a future separate session/document will govern the detailed work?

## Subject list

- SUBJ-001: staged work mode for complex edits (multi-step work closed by a single commit;
  working-area semantics, approval timing, abort/recovery, audit interaction, invariant wording).
- SUBJ-002: "deterministic actions → scripts" stance in core concepts (placement, wording,
  guardrails vs OP-2 and sole-writer rule, deferral of detailed design to a separate session).

## Constraints

- Proposals must be consistent with OP-1/OP-2/OP-3 as written in the concept.
- This session proposes; it does not write docs/. Final changeset goes through the Documentation
  Worker skill after operator step-(5) Approve.
- Do not reopen settled consensus `sess-documenter-concept-revision` decisions (no tiers, no
  gating, no service, in-chat approval carrier, exit-code contract).
- OP-2 is the default filter: prefer prose conventions over new machinery.

## Output limits

Each role: single structured document per fallback/index.md "Output Structure" (Summary Position,
Key Findings with subjects, Recommendations, Open Questions, Status). ≤ 120 lines.
