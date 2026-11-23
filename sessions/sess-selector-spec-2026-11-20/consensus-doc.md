# Consensus Document

## Decision
Conditionally resolved: adopt a draft specification for **Selector** as a read-only, non-Council information-retrieval utility (docs + codebase) with a free-form request and facts+references output, usable in fallback/runtime/coding contexts (interim skill+subagent → final separate module), subject to the recorded reservations and open questions.

## Rationale
- **Clear utility boundary (SUBJ-001):** All roles converge that Selector is independent of the built-in OpenCode `explore` (different responsibility/layer), read-only, and not a Council participant; thin-concept, Documenter-analogous supporting utility.
- **Cross-context viability (SUBJ-002):** A versioned minimal contract and clean interim/final separation enable use in fallback, future runtime, and coding tasks without behavioral cliff or context-rule leakage.
- **Safe, traceable discovery (SUBJ-003, SUBJ-006):** Manifest-first routing for docs, scoped/targeted code search, strict read-only boundaries, and per-call budgets prevent over-reach, context bloat, and false confidence.
- **Trustworthy I/O (SUBJ-004, SUBJ-005):** Free-form input plus optional hints, combined with provenance-backed facts/references and structured gap/conflict reporting, balance flexibility, brevity, and verifiability.
- **Convergent risk controls:** Provenance/status markers, explicit handling of missing/ambiguous/conflicting/archive sources, and format repeatability/observability expectations are required across roles.

## Subjects with Outcomes
| Subject | Status | Notes |
|---------|--------|-------|
| SUBJ-001 Purpose, scope, non-goals | Conditionally Agreed | Read-only locator/summarizer (facts+refs), non-participant, independent of `explore`; Supporting Service/thin-concept direction. Reservations on boundary enforcement details. |
| SUBJ-002 Invocation & deployment contexts | Conditionally Agreed | Fallback + future runtime + coding; interim skill+subagent, final separate module. Versioned contract, transition checklist/milestone, context isolation. Reservations on events in fallback and transition trigger. |
| SUBJ-003 Discovery & reading strategy | Conditionally Agreed | Start from AGENTS.md/context; docs manifest-first, code via scoped search, dual internal strategies (extensible). Read-only. Reservations on archive handling and allow/deny scope specifics. |
| SUBJ-004 Input contract | Conditionally Agreed | Required free-form request; optional soft hints (e.g. `scope_hint` overview/targeted/deep, context hints). Reservations on validation vs exclusion/warning behavior. |
| SUBJ-005 Output contract | Conditionally Agreed | Relevant facts with references, provenance per fact (id/version/status/section or location/excerpt as feasible), summary+details, structured gaps/conflicts, budget-aware. Reservations on exact structure/field strictness and conflict presentation depth. |
| SUBJ-006 Operational behavior, limits, failure handling | Conditionally Agreed | Per-call budgets (target ≤4K tokens payload, ≤20 files read) with graceful/structured limit signaling, no writes, format repeatability, observability/audit trail (runtime event design target; fallback session logging/artifacts). Reservations on caching, determinism scope, call limits. |

## Conflicts & Disagreements
- **SUBJ-003/SUBJ-005 (Archive handling):** R&S prefers strict isolation/explicit marking and exclusion-by-default pressure for archive/historical sources; Architect/HCD prefer surfacing status/provenance and letting caller decide. Ops supports warning tags. **Severity:** medium (all). **Proposed resolution:** always include source status/provenance (active/draft/archive, manifest id/path) and warn when archive/historical; do not present as current authority; allow explicit caller intent to focus on archives. Exact default-include/exclude rule left to operator preference/spec detail.
- **SUBJ-004 (Scope-violating or over-broad requests):** R&S favors structured rejection/errors for out-of-scope targets; Ops favors silent exclusion with verifiable `searched_sources` in gaps; HCD favors calibration/warning over rejection. **Severity:** medium. **Proposed resolution:** enforce read boundaries (no out-of-scope reads), never silently over-reach; report excluded/limited scope via structured gap/warning plus `searched_sources`; use hard structured error only when request cannot be satisfied within allowed boundaries.
- **SUBJ-002/SUBJ-006 (Audit/events in fallback):** Ops/initial R&S preference for event-like audit; Architect notes fallback is outside runtime event envelope. **Severity:** low–medium. **Proposed resolution:** runtime — define `selector.query` (or equivalent) event design target; fallback/interim — record equivalent structured audit info in session artifacts/logs.

## Reservations
**Architect**
- Archive default behavior and fallback audit mechanism should be finalized by operator/spec without blocking the core contract (SUBJ-003, SUBJ-006).
- Code-search scope/excludes must stay configurable-in-principle to avoid over-opinionated defaults (SUBJ-003).

**Reliability & Security Specialist**
- Free-form input and doc+code access remain risk surfaces without explicit allow/deny boundaries, per-call budgets, and provenance/status on every fact; archive sources must never be mistaken for authority (SUBJ-001, SUBJ-003, SUBJ-004, SUBJ-005, SUBJ-006).
- Transition must not drop provenance/safety fields (schema may grow, not regress) (SUBJ-002).

**Human-Centric Designer**
- Without minimum provenance/context and clear gap/conflict signaling, outputs risk orphaned or misleading facts despite brevity goals (SUBJ-005).
- Scope hints and summary/detail structure should aid trust and predictable cognitive load, not add friction (SUBJ-004, SUBJ-005).

**Operations Engineer**
- Budget, file-read limits, and consulted-sources traceability are required to avoid context/latency blowups and to support debugging (SUBJ-005, SUBJ-006).
- Interim→final transition needs a documented checklist/milestone and compatibility guarantees; caching/call-volume policies must avoid staleness and hidden cost (SUBJ-002, SUBJ-006).

## Open Questions
- Exact default budgets and caps: hard vs soft (tokens/output size, max files, excerpt length) and behavior on limit hit across contexts (SUBJ-005, SUBJ-006).
- Archive policy: default surface-with-warning vs exclude-unless-requested; conflict presentation format when sources disagree (SUBJ-003, SUBJ-005).
- Code-search boundaries: canonical exclude/allowlist patterns and how future separate doc/code rules are configured (SUBJ-003).
- Audit/observability: fallback audit artifact format now; `selector.query` event schema/fields for future runtime (SUBJ-002, SUBJ-006).
- Transition governance: milestone/trigger, compatibility guarantees, and deprecation plan for interim skill+subagent form (SUBJ-002).
- Caching/per-session limits: prohibit persistent cross-call cache in interim? stateless indexing allowed? per-session call ceilings for coding tasks (SUBJ-006).

## Action Items
- **Prepare formal spec (this session, post-approve):** draft `docs/en/selector/index.md` (new project document) defining purpose, boundaries, contexts, discovery/read rules, input/output contract, limits/failure handling, and transition notes; propose manifest/changelog updates — execute only after explicit operator approve via Documentation Worker skill. (All roles, priority: high)
- **Define normative defaults:** finalize budget numbers, archive behavior, and scope-validation/gap signaling policy in the spec. (Operator + Architect/R&S, priority: high)
- **Interim implementation path:** specify skill+subagent packaging and prompt contract independent of `explore`, with consulted-sources logging for fallback. (Architect/Ops, priority: medium)
- **Runtime alignment:** map Selector to future Supporting Service/module and event/audit integration when Moderator/runtime contracts are ready. (Architect/Ops, priority: medium)
- **Verification:** validate the spec draft against manifest/documentation rules during publication (frontmatter, id/path, changelog, translation handling as applicable). (Documentation Worker flow, priority: high)

## Escalation References
— None —

## Downgraded Critical Findings
— None — (R&S Phase 2 raised a critical concern on scope/boundary ambiguity (SUBJ-001/SUBJ-003); it was addressed through convergence on explicit boundaries/contract and recorded as reservations, not downgraded.)