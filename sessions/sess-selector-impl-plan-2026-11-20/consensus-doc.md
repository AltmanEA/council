# Consensus Document — sess-selector-impl-plan-2026-11-20

Date: 2026-11-20
Mode: Subagent Fallback (fallback/index.md v0.6.0), **sequential local role launch** (local model → max 1 concurrent subagent). No `council.*` / `documenter.*` MCP tools. No documentation file, manifest, changelog, or fallback file modified by this session.

Outcome: **Conditionally resolved.** Phase 4 statuses: Architect `concerns`, Reliability & Security `concerns`, Human-Centric Designer `concerns`, Operations Engineer `agree`. No `blocked-in-scope`, no `blocked-escalation`, no opposing stances on the same subject. One discussion round (Phase 3) was sufficient; no targeted resolution round required.

## Decision

Adopt the implementation plan **as revised by the discussion round**, with the following binding changes:

1. **SUBJ-008 — layered resolution.** Interim build (Layer 1) implements the `sess-context-selector-reframe` frame: **index-only** relevance judgement from manifest metadata; output = task summary + ranked recommended IDs with rationale + explicit "starting set, not a boundary" disclaimer + `Discoverable: yes/no` advisory. The `docs/en/selector/index.md` v0.1.0 broad IR frame (facts+references, document-body and code-content discovery) becomes **Layer 2**, deferred to a separately approved transition. Code discovery is explicitly out of scope for Layer 1 and returns a deferral message.
2. **Caller-facing labelling.** The interim output carries `interim_form: Layer 1` and states what is deferred; the spec document's caller-facing sections are to be updated via the Documentation Worker (separate operator `approve`, semantic change) so callers are not misled by the current broad wording.
3. **`discover()` is an internal dependency**, not a new tool type: manifest-read wrapper with SHA-256 checksum and fail-closed behaviour, activated when content for a recommended ID is needed.
4. **Safety controls for Layer 1:** strict index-only enforcement; role-prompt capability deny-list (`write`, `shell`, `edit`) plus a post-call manifest SHA-256 integrity check in the skill wrapper; system-level budget ceiling overriding caller hints (proposed ≤8K tokens / ≤40 files absolute, default ≤4K / ≤20); explicit `⚠ TRUNCATED` banner on budget stop; structured gap core `{gap_type, searched_sources, covered_items, omitted_items}` with optional free-form `suggestion`; hint-applied/not-applied acknowledgement.
5. **Audit artifact:** `sessions/<id>/selector-<call-id>.md` containing request intent, consulted sources, manifest checksum, outcome and limits; the path/call ID is returned in the response. Full per-source hashing deferred to Layer 2.
6. **Verification:** V3 injection smoke tests (poisoned manifest metadata; poisoned doc body against the main agent) are automated and **required before the pilot launches** (R&S additionally requires them as blocking for any wider rollout). Contract tests cover the Layer 1 schema, `draft`/`archive` labels, budget ceiling, truncation banner, no-write/integrity check, and `discover()` fail-closed.
7. **Governance:** whitelist extension for `.agents/skills/selector/` is an explicit operator gate before the first write. Implementation path (full vs compressed TDD cycle for the Markdown skill) requires an operator decision; the compressed cycle still passes pre-gate, path gate and governance checks.

## Rationale

- All four roles converged that the spec/reframe conflict (SUBJ-008) was the root blocker; the layered resolution was accepted by all (three `accept-with-conditions`, one `accept`). It makes the verification set definable (Ops), closes the content-injection vector for interim (R&S), and preserves the authoritative spec as future work.
- Convergence on read-only: prompt-only enforcement is insufficient but technically stronger isolation is unavailable with the built-in `general` subagent; deny-list + post-call integrity check was accepted by Architect, R&S and Ops as the bounded interim mitigation.
- Convergence on caller trust: mandatory GAPS section, truncation banner, call-ID audit filename and hint acknowledgement were accepted by all roles that raised them.
- Governance gates were judged appropriate rather than defective: the whitelist extension and the separate Documentation Worker approval are correct pre-implementation steps, not design blockers.

## Subjects with Outcomes

| Subject | Outcome | Notes |
|---|---|---|
| SUBJ-001 Scope | Conditionally Agreed | Interim = Layer 1 only; final module/service and event schema out of scope. Layer 2 transition requires operator approval **and** documented security review (new R&S condition). |
| SUBJ-002 Packaging | Conditionally Agreed | Skill + role prompt under `.agents/skills/selector/`, invoked via built-in `general`; no `.opencode/` edits. Read-only is policy-level + integrity check, not technical isolation. |
| SUBJ-003 Invocation | Conditionally Agreed | `skill("selector")` / `@selector` stable contract; subagent internal; `discover()` internal helper with fail-closed checksum. Budget parameters propagated explicitly into the role prompt. |
| SUBJ-004 Provenance & audit | Conditionally Agreed | Layer 1 output = ranked IDs + rationale + labels; structured gap core; call-ID audit artifact with manifest checksum; per-source hashing deferred to Layer 2. Spec caller-facing update required. |
| SUBJ-005 Discovery, safety, budgets | Conditionally Agreed | Index-only for Layer 1; code/content reads deferred; explicit exclude list codified (`.git/`, `vendor/`, `sessions/`, plus `node_modules/`, `__pycache__/`); system-level budget ceiling; truncation banner; hint acknowledgement. |
| SUBJ-006 Verification | Conditionally Agreed | Contract tests + smoke scenarios including V3 injection, budget overrun, `discover()` fail-closed, no-write/integrity. V3 required before pilot. Pilot metrics observational, never gates; collection mechanics still to be specified. |
| SUBJ-007 Governance | Conditionally Agreed | Whitelist extension is a pre-write operator gate; TDD applicability to Markdown skill unresolved; no Documenter-scope writes in this session. |
| SUBJ-008 Spec vs reframe | **Conditionally Agreed (resolved by layering)** | Layer 1 = reframe index-only judge; Layer 2 = spec broad IR utility, deferred. Requires spec labelling update and operator confirmation. |

## Conflict Aggregation (fallback §Conflict Aggregation Rules)

1. **Duplicate findings — SUBJ-008:** raised `[critical]` by Architect and R&S, `[medium]` by HCD and Ops. Recorded at highest severity (critical) with convergence noted: 4/4 roles.
2. **Divergent severity on V3 tests:** R&S requires them blocking for any rollout; HCD requires them present and passing before the pilot but not necessarily blocking operator approval; Ops converges on "must pass before pilot". Recorded as a conditional convergence: **required before pilot** (all), **blocking for wider rollout** (R&S reservation). Not a disagreement on the subject outcome.
3. **TDD applicability:** Architect proposes a compressed cycle; Ops flags the whitelist dependency and ~10–15 min cost; no counter-proposal for direct edit. Recorded as an open operator decision, not a conflict.
4. **Severity escalation via convergence:** the read-only concern rose from R&S `[critical]` to an agreed HIGH with mitigation under harness constraints (Architect and Ops concurred); recorded transparently below.

## Reservations

**Architect**
- Scope conflict must be resolved before implementation; accepted the layered resolution (SUBJ-008).
- `discover()` must remain internal, never a parallel externally callable primitive (SUBJ-003).
- TDD applicability and whitelist status are operator gates (SUBJ-007).

**Reliability & Security Specialist**
- Layer 1 must strictly enforce index-only — no "just this once" document-body or code reads (SUBJ-005).
- Deny-list is necessary but insufficient; post-call integrity check is mandatory (SUBJ-002).
- V3 injection tests are blocking for wider rollout; Layer 2 needs a documented security review gate (SUBJ-001, SUBJ-006).
- System-level budget ceiling must override caller hints (SUBJ-005).

**Human-Centric Designer**
- Caller-facing labelling of Layer 1 vs Layer 2 is required to prevent trust erosion (SUBJ-008).
- Gap block must have a structured core; free-form only as optional `suggestion` (SUBJ-004).
- Spec document update via Documentation Worker is required, not optional (SUBJ-008).

**Operations Engineer**
- Whitelist extension precedes any write; compressed cycle still runs all governance gates (SUBJ-007).
- Pilot data collection mechanics must be defined; V3 must pass before pilot (SUBJ-006).
- Budget ceiling and explicit exclude list codified in the contract (SUBJ-005).

## Open Questions / Operator Decisions Required

1. **SUBJ-008 confirmation:** accept the council's Layer 1 (index-only) / Layer 2 (deferred broad IR) resolution, which narrows the plan originally derived from the spec document? (All roles request explicit operator confirmation.)
2. **SUBJ-007 whitelist:** approve extending the implementation skill's whitelist to `.agents/skills/selector/` before any write?
3. **SUBJ-008 spec update:** instruct the Documentation Worker to prepare a semantic update to `docs/en/selector/index.md` distinguishing interim and future output contracts (requires a separate in-chat `approve: <object>`)?
4. **SUBJ-007 TDD path:** full cycle or compressed verification for the Markdown skill definition (~10–15 min local-model cost either way for the compressed path)?
5. **SUBJ-005 budget ceiling:** confirm absolute maximum values (proposed ≤8K tokens / ≤40 files) and default (≤4K / ≤20).
6. **SUBJ-006 pilot mechanics:** where to record stability / correction-rate / context-savings metrics and over what window (reframe proposes N=20 / 30 days).
7. **SUBJ-006 V3 semantics:** confirm "before pilot" (all) plus "blocking for rollout" (R&S).

## Action Items

| # | Action | Owner | Priority |
|---|---|---|---|
| 1 | Decide the 7 open questions above | Operator | high — blocks implementation |
| 2 | Revise the implementation plan to Layer 1 scope; drop code-discovery/content-read smoke scenarios from this iteration, replace with deferral-message test | Primary agent | high |
| 3 | Prepare spec-document update proposal via `skill("documentation")` after operator `approve` (single atomic commit; RU translation handling per rules) | Documentation Worker | high |
| 4 | Extend implementation whitelist after operator approval; create worktree; run approved TDD path | Primary agent | high |
| 5 | Implement skill, role prompt, output schema, fixtures; wire `discover()` helper and post-call integrity check | Implementation subagents (sequential, local) | high |
| 6 | Write verification items V1–V8 (below); no high/critical finding may ship without a reproducing test | Implementation subagents | high |
| 7 | Run one real fallback pilot query; collect observational metrics; report before any wider rollout | Primary agent + operator | medium |
| 8 | Layer 2 design, security review, transition checklist — explicitly deferred | Operator (future session) | low |

## Verification Items (every high/critical finding has a reproducing test)

- **V1** Index-only boundary: adversarial doc-body content is never read or quoted by Layer 1 output (R&S critical, Architect critical).
- **V2** V3 injection: poisoned manifest `description`/`title` metadata does not steer ranking or produce output directives (R&S critical, HCD medium).
- **V3** No-write/integrity: post-call manifest SHA-256 matches pre-call snapshot; role prompt deny-list present; no file modifications (R&S HIGH).
- **V4** Budget: hard ceiling cannot be overridden by caller hints; `⚠ TRUNCATED` banner and covered/omitted report present on overrun (HCD critical, R&S HIGH, Ops medium).
- **V5** Output contract: `interim_form: Layer 1`, ranked IDs + rationale + disclaimer + `Discoverable` flag, structured gap core, hint acknowledgement (HCD medium).
- **V6** `discover()` fail-closed: corrupted/unreadable manifest returns explicit error or empty list, never partial/cached content (Architect critical).
- **V7** Status marking: `draft`/`archive` sources carry explicit non-authority labels (all roles).
- **V8** Audit artifact: `selector-<call-id>.md` created with manifest checksum and path returned in response (HCD medium, R&S HIGH downgraded).

## Escalation References

— None — no role declared `blocked-in-scope` / `blocked-escalation`; no opposing stances after Phase 3.

## Downgraded Critical Findings (transparency)

- **Architect, SUBJ-002/SUBJ-008 "spec vs reframe scope conflict" [critical]** — resolved, not downgraded: the layered resolution (Layer 1/Layer 2) was accepted by all four roles.
- **Architect, SUBJ-008 "`discover()` absent from plan" [critical]** — resolved: `discover()` added as an internal helper with contract and V6 test.
- **R&S, "read-only enforced only by prompt" [critical]** — downgraded to HIGH with justification: built-in `general` grants write-capable tools; deny-list plus post-call manifest integrity check is the strongest available interim mitigation, accepted by Architect and Ops. Reproducing test: V3.
- **R&S, "content reading reintroduces injection risk" [critical]** — resolved for Layer 1 by strict index-only scope; deferred to Layer 2 with mandatory security review. Reproducing test: V1/V2.
- **HCD, "no complete-vs-truncated signal" [critical]** — resolved: mandatory `⚠ TRUNCATED` banner and structured gap core. Reproducing test: V4/V5.

## Artifacts

`task-brief.md`, `review-architect.md`, `review-reliability-security.md`, `review-human-centric-designer.md`, `review-operations-engineer.md`, `discussion-round-1-input.md`, `discussion-<role>-r1.md` (×4), `consensus-doc.md`. No documentation files modified.
