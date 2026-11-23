# Session Task Brief — Solo-Operator Simplification Redesign

Session: sess-solo-simplification (fallback mode)
Date: 2026-11-19
Mode: fallback per fallback/index.md (Moderator = human operator; secretary = primary agent)

## Axioms (INPUT DATA — NOT SUBJECT TO DISCUSSION)

- **AXIOM A (Sovereign Operator).** The system has exactly one operator. This operator has the authority to make decisions on ANY matter in the project immediately, with no waiting, no gates, no delays, no ceremony directed at the operator. Any mechanism whose purpose is to constrain, delay, double-check, authenticate-ceremonially, or protect against the operator's own decisions/rubber-stamping is invalid by premise. Roles MUST NOT argue for keeping such mechanisms; they may only flag what would be lost.
- **AXIOM B (Maximum Simplicity).** The primary design criterion for the redesign is simplicity: fewest components, fewest documents, fewest concepts, fewest configuration surfaces, least operator time-to-understand. Where two designs satisfy the remaining functional need, the simpler one wins by default.

## Session Goal

Produce a redesign proposal ("how to remake the project") that satisfies both axioms: an inventory of what to cut, merge, or rewrite; the irreducible residue that survives Axiom B and WHY; and a migration path executable under the project's own governance.

## Ground Truth: current project inventory (for audit)

- ~21 manifest documents (docs-manifest.yaml): protocol-core, documenter-service (+ mvp-contract, mvp-interfaces, mvp-data-models, configuration-guide, policy-reference, approval-surface), operator-ingress, execution-runtime, service-contract (+error-management), planned-architecture (index, layer-0/1/2, decisions ADR-001..020), documentation-rules, glossary, project-concept, project-reference, scenario, translation-project (+contract). RU translations mirrored under docs/ru/.
- Code: `documenter_service/` (Tier 0–1 operational; Tier 2+ branch DORMANT behind ADR-013/016 dual interlock), `operator_ingress/` (p3 MVP: stdio JSON-RPC verbs, pre_check gate, notices, sentinel), `tools/` (gen_manifest.py, activation_helper.py, etc.), `tests/`.
- Heavy governance machinery built around multi-party distrust / operator-absence assumptions: three caller classes (operator/agent/service) + JWT-like tokens + HMAC secret; dual interlock (policy state + readiness sentinel); trust tiers 0–3 + solo exception (ADR-017) with delay/token/bias-banner; out-of-band approval handshake (approval_id, diff-hash binding, expiry window, single-use); escalation stop-and-resume with timeouts and fallback strategies; activation overlay (ADR-020) with scope presets; protected-paths blocklist; operator_approval_timeout; 30-day review clocks; clean-cycle ramps; 5-clean-cycle widening; pre_check gate at phase boundaries; two-step delegate→approve ceremony.
- Process artifacts: sessions/ convention (task-brief, review-*, consensus-doc), archive/sessions/, CHANGELOGS/, defaults/, fallback/ (FROZEN — changes require explicit operator request; this session may PROPOSE changes but must flag them for the operator's separate decision).
- Prior related session: sessions/sess-solo-operator-fast-approval/ (fast-approval council, 2026-11-19) — its debate assumed the operator needed protection from themselves (delay, token, bias banner). Axiom A supersedes that frame: safety floor may only target AGENT-side failure (LLM error, prompt injection), never operator ceremony.

## Redesign Questions (per role)

**Architect:**
- Q1: SUBJ-001 — Audit the component/doc inventory against Axiom A: which components exist only to police or substitute for the operator (interlock, sentinel, escalation timeouts, tier ladder, dual approval, caller-class auth, activation overlay)? What is the minimal component set that still separates Layer-1 protocol execution from Layer-2 operator interface and Layer-0 audit?
- Q2: SUBJ-003 — Propose a target-state architecture: how many services, how many config files, how many protocol documents? Justify each survivor; name what to delete outright vs merge (e.g., could documenter_service+operator_ingress+tools collapse into one package? could approval-surface+mvp-contract+policy-reference+configuration-guide collapse into one?).

**Reliability & Security Specialist:**
- Q1: SUBJ-002 — Re-anchor the threat model under Axiom A: the operator is fully trusted and instant, but AGENTS (LLMs) still write content and prompt injection remains live. Which integrity controls protect the CORPUS from agent-side error and are therefore NOT operator ceremony and must survive (diff-hash binding at apply, changed-diff invalidation, critical block, protected paths, audit pre-gate, git-as-rollback, reconcile)? Justify each with a concrete failure mode; concede everything that is operator-facing friction.
- Q2: SUBJ-005 — Name the simplicity line: what capability loss would make the system unsafe to run at all (the irreducible floor); anything above it is negotiable.

**Human-Centric Designer:**
- Q1: SUBJ-003 — Cognitive simplification: which of the 21 docs / ~20 ADRs / verb table / notice catalogue / state machines can merge or die so that one human can hold the whole system in their head? Propose a target document set (names + what each contains).
- Q2: SUBJ-001 — Which remaining concepts are already unlearnable/unusable in practice by one person (dead ceremony: e.g., notices nobody reads, registries nobody queries) and are therefore complexity without benefit?

**Operations Engineer:**
- Q1: SUBJ-004 — Migration path: big-bang rewrite vs staged supersession under the project's own rules (new ADRs superseding old, documentation-worker writes, manifest regen, fallback freeze exception). Order the deletion/merge sequence so the system stays operational at every step. What happens to the dormant Tier 2+ branch, the interlock, the overlay mechanism, tests, RU translations, external translation project?
- Q2: SUBJ-005 — Define measurable simplicity criteria (acceptance metrics: doc count, concept count, config surface count, time-to-first-write, number of commands an operator must know) and target values.

## Output Limits
- Max findings per role: 5–7; recommendations: 3–5; open questions: 2–3. ≤150 lines total. Brevity encouraged.

## Expected Discussion Rounds
- 1 round.

## Subject List
- SUBJ-001: Axiom-A audit — mechanisms that police/substitute for the operator → cut list.
- SUBJ-002: Agent-side integrity floor — controls protecting the corpus from LLM error/prompt injection → keep list, re-justified.
- SUBJ-003: Simplification map — concrete merge/delete/rewrite across docs, services, config, verbs, ADRs; target-state document/component set.
- SUBJ-004: Migration path — sequencing under the project's own governance (ADRs supersede; worker-skill writes; manifest regen; fallback freeze handling); operational continuity.
- SUBJ-005: Definition of simple — acceptance metrics, target values, and the irreducible-complexity line.

## Additional Context / Constraints
- Read first: this brief; AGENTS.md (§1.5–1.7); docs-manifest.yaml; sessions/sess-solo-operator-fast-approval/discussion-round-2.md (superseded-by-axioms frame).
- Skim as needed (via manifest paths): planned-architecture index + layer docs, documenter-service/index.md, operator-ingress/index.md, policy-reference.md, mvp-contract.md, protocol-core/index.md, execution-runtime/index.md, service-contract/index.md.
- Ops role: measure reality — file counts and LOC of documenter_service/, operator_ingress/, tools/, tests/, docs/ (wc -l, find) to ground simplicity metrics.
- Deliverable is a PROPOSAL for operator approval. Agents MUST NOT edit docs/, manifest, CHANGELOGS, policy files, or fallback/; writes go through the documentation worker only after operator step-5 approval. Proposals touching fallback/ must be flagged as requiring the operator's explicit freeze-exception act.
