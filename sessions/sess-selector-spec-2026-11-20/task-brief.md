# Session Task Brief

## Session Goal
Produce a consensus-backed draft specification for **Selector** — a service/utility module (non-participant in Council, analogous in role to Documenter) that other agents invoke to locate and gather relevant information from project documentation and the codebase, returning only necessary facts with references so the calling agent’s context is not burdened by exploratory file reads.

## Focus Areas
- Purpose, scope, and non-goals (including clear independence from the built-in OpenCode `explore` subagent).
- Invocation and deployment model across contexts: current fallback sessions, future Council runtime (Moderator/Execution Runtime), and current coding/development tasks. Interim form (skill + subagent) vs final target (separate module, Documenter-like). Compatibility/transition path.
- Discovery and reading strategy: AGENTS.md/manifest-first routing for docs, codebase search behavior, read-only guarantees, boundaries/permissions, and how strategy may diverge later for docs vs code.
- Input contract: free-form caller request and any optional context/hints.
- Output contract: relevant facts with references for possible clarification, returned in free form; how to ensure usefulness, traceability, and context reduction (what to include/exclude, handling ambiguity/not-found/partial results).
- Operational behavior and failure modes: uncertainty reporting, limits, determinism/reproducibility expectations, and interaction with existing tools/workflows.

## Questionnaire per Role

**Architect:**
- Q1: What module boundaries, interfaces, and integration points should Selector have now (interim skill+subagent) and in the final runtime/module form to stay independent of `explore` and analogous to Documenter without becoming a Council participant?
- Q2: How should the discovery/reading flow be structured (AGENTS.md → manifest/docs routing and codebase search) so it is extensible to separate doc/code rules later while preserving clear responsibilities?
- Q3: What is the minimal contract (request → facts+references response) that enables composition by other agents across fallback, runtime, and coding contexts?

**Reliability & Security Specialist:**
- Q1: What failure modes, misuse risks, or boundary violations must the spec guard against (e.g., over-broad reads, leaking unintended content, stale/misleading references, non-deterministic or incomplete gathering)?
- Q2: How should Selector behave when information is missing, ambiguous, access is constrained, or sources conflict, to avoid false confidence in the caller?
- Q3: What read-only and scope constraints are necessary to make Selector safe as a shared utility across contexts?

**Human-Centric Designer:**
- Q1: How should free-form facts+references be presented so a calling agent (and ultimately the operator) can quickly understand, trust, and follow up without re-reading raw sources?
- Q2: What makes a caller’s free-form request sufficient, and how should Selector communicate gaps or needed clarification without creating friction?
- Q3: How can the output balance brevity/context reduction with enough provenance and context to prevent misinterpretation?

**Operations Engineer:**
- Q1: What operational characteristics must be specified for Selector to work reliably in fallback, future runtime, and day-to-day coding (invocation cost/latency expectations, size/effort limits, repeatability, observability of what was consulted)?
- Q2: How should interim (skill+subagent) and final (separate module) forms be operated and transitioned without disrupting existing workflows?
- Q3: What practical constraints or conventions (caching/limits not assumed unless specified, workspace/context handling, logging/auditability of references) should the spec include?

## Output Limits
- Maximum findings per role: **7**
- Maximum recommendations per role: **5**
- Maximum open questions per role: **3**
- Total output per role: **~150 lines** — shorter is acceptable; brevity encouraged.

## Expected Discussion Rounds
- Medium task: **1 round** (plus a targeted resolution round only if `blocked-in-scope` occurs).

## Subject List
- `SUBJ-001`: Purpose, scope, and non-goals — Selector as a non-Council service/utility for locating/gathering info in docs and codebase to reduce caller context; independence from built-in OpenCode `explore`.
- `SUBJ-002`: Invocation and deployment contexts — support for current fallback, future Council runtime, and current coding tasks; interim form (skill+subagent, for development) and final target (separate module like Documenter), with transition expectations.
- `SUBJ-003`: Discovery and reading strategy — AGENTS.md-driven start, manifest-routed doc access, codebase search, read-only operation, and extensibility toward separate rules for docs vs code.
- `SUBJ-004`: Input contract — free-form request from calling agent (and any minimal accompanying context) sufficient to drive retrieval.
- `SUBJ-005`: Output contract — relevant facts with references for possible clarification in free form; requirements for relevance, traceability/provenance, concision, and handling of uncertainty/not-found/conflicts.
- `SUBJ-006`: Operational behavior, limits, and failure handling — reliability, safety boundaries, reporting of gaps/ambiguity, and expectations that keep the module usable across environments.

## Additional Context / Constraints
- Operator decisions (2026-11-20): outcome must include session artifacts and, after consensus and explicit operator approve, preparation of a formal specification document under `docs/en/...` via the Documentation Worker skill (no direct writes to `docs/`, `docs-manifest.yaml`, or `CHANGELOGS/` without that approval flow). Search scope is documentation and codebase (read-only). Input is a free-form request; output is relevant facts with references for possible clarification in free form. Selector must be independent of the built-in OpenCode `explore` agent. Standard base roles participate.
- Context: AGENTS.md routes doc reads through `docs-manifest.yaml`; English docs under `docs/en/` are authoritative. Documenter is a thin concept (approval loop + read-only audit), sole writer flow applies to doc artifacts. Fallback sessions are outside the runtime JSON contract and produce Markdown artifacts in `sessions/<id>/`.
- Spec should be practical for interim implementation (skill+subagent) yet forward-compatible with a final separate module. Avoid inventing runtime/MCP details not required; mark future-runtime specifics as design targets where appropriate.
