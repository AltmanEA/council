# Session Task Brief — sess-selector-impl-plan-2026-11-20

Mode: Subagent Fallback (fallback/index.md v0.6.0), **sequential local subagents only** (local model → max 1 concurrent agent). No `council.*` / `documenter.*` MCP tools. This session reviews a plan only: no edits to `docs/`, `docs-manifest.yaml`, `CHANGELOGS/`, `fallback/`, `AGENTS.md`, `.opencode/`, or any repository file. Subagents return their review as their final response; the primary agent owns all artifacts.

## Session Goal

Reach consensus on the **interim implementation plan for Selector** (skill + subagent) derived from `docs/en/selector/index.md` v0.1.0 (draft/conceptual), including packaging, invocation, provenance, budgets, verification, and governance gates.

## Plan under review (condensed)

Basis: `docs/en/selector/index.md` v0.1.0 + `sessions/sess-selector-spec-2026-11-20/consensus-doc.md`. Only the interim form is in scope; the final module/service and the `selector.query` event are out of scope (compatibility notes only). Operator decisions already taken: stable caller interface = skill (`skill("selector")` / `@selector`); subagent = role prompt inside the skill, invoked via built-in `general`, **no `.opencode/` edits**; audit = response block + `sessions/<id>/selector-<n>.md`; verification = contract `unittest` tests + smoke scenarios.

Artifacts to create (implementation files per `AGENTS.md` §1.6, outside Documenter):
- `.agents/skills/selector/SKILL.md` — contract, activation, subagent invocation protocol, budget, read-only invariants.
- `.agents/skills/selector/roles/selector.md` — role prompt for built-in `general`.
- `.agents/skills/selector/contract/output.schema.json` — machine-readable provenance/gap block for tests.
- `.agents/skills/selector/fixtures/` — mini manifest, docs, code for smoke scenarios.
- `tests/test_selector_contract.py`, `tests/test_selector_smoke.py` — structure, statuses, budget, no-write assertions.

Steps:
1. Freeze contract profile: input = free-form request + soft hints (`overview|targeted|deep`, docs/code, identifiers); output = `summary → facts+references → gaps`; provenance = manifest `id/path/title/version/status` + section/quote, code = path + line/symbol; budget default ≤4K tokens / ≤20 files, tunable; graceful stop with covered/omitted report.
2. Discovery: docs strictly manifest-first (`docs-manifest.yaml`), EN authoritative, `draft`/`archive` marked and never presented as current authority; code = targeted path/symbol/pattern search, default excludes `.git/`, `vendor/`, `sessions/` unless in scope; boundary breach → gap/warning with `searched_sources`; never fabricate.
3. Invocation protocol: skill receives request → builds role prompt → calls built-in `general` → validates response against schema → returns to caller. Stateless, no cross-call cache, no Council authority claims, no `explore` substitution.
4. Auditability: every fact carries a reference; incomplete result → structured `{gap_type, searched_sources, suggestion}`; fallback additionally writes `sessions/<id>/selector-<n>.md` (request intent, consulted sources, outcome, limits).
5. Verification: `unittest` with reversed-TDD baseline (per implementation skill), mandatory provenance, `draft`/`archive` marking, budget compliance, no filesystem writes; smoke scenarios: docs query, code query, archive query, not-found, budget-hit; re-run in main working tree after merge.
6. Pilot: one real fallback query + artifact review; metrics from `sess-context-selector-reframe` (bundle stability, operator correction rate, context savings) are **observational, never gates**.
7. Governance: implementation skill's default whitelist covers only `tools/`, `documenter_service/`, `tests/` — extending it to `.agents/skills/selector/` requires explicit operator decision. `.opencode/`, `fallback/`, `docs/` untouched. Changing the spec document's `draft` status requires a separate operator `approve` through the Documentation Worker.

Known tension: `sessions/sess-context-selector-reframe-2026-11-20/consensus-doc.md` adopted a different framing — index-only LLM relevance judge, "recommended starting set, not a boundary", `discover()` helper, N=20/30-day pilot, prompt-injection tests. The spec document defines a broader facts+references IR utility. SUBJ-008 asks how the two relate.

## Subject List

- `SUBJ-001`: Scope — interim only; final module/service and event schema out of scope.
- `SUBJ-002`: Packaging — skill + role prompt under `.agents/skills/selector/`, invoked via built-in `general`; no `.opencode/` edits.
- `SUBJ-003`: Invocation — `skill("selector")` / `@selector` as the stable caller-facing contract; subagent internal.
- `SUBJ-004`: Provenance and audit — per-fact references, gap block, fallback `selector-<n>.md` artifact.
- `SUBJ-005`: Discovery, safety, budgets — manifest-first, archive/draft marking, code excludes, ≤4K/≤20 tunable, graceful stop, stateless/read-only.
- `SUBJ-006`: Verification — contract tests + smoke scenarios, reversed-TDD, main-tree re-run, observational pilot metrics.
- `SUBJ-007`: Governance — whitelist extension for `.agents/skills/selector/`, no Documenter-scope writes, separate approve for status change.
- `SUBJ-008`: Relation to `sess-context-selector-reframe-2026-11-20` (index-only starting-set design, `discover()`, injection tests, pilot metrics) — layering or conflict.

## Questionnaire per Role

**Architect:**
- Q1: Is the skill + role-prompt packaging coherent, and does invoking built-in `general` with a prompt preserve a stable contract without editing `.opencode/`?
- Q2: Does the discovery→validate→return flow keep docs and code strategies extensible, and is the interim/final boundary clean?
- Q3: How should SUBJ-008 be resolved without breaking the authoritative spec document?

**Reliability & Security Specialist:**
- Q1: Where can the read-only/stateless guarantee fail (subagent tool access, fixtures, session artifacts), and what concrete failure mode should tests reproduce?
- Q2: Are archive/draft marking, gap reporting, and budget stop sufficient to prevent false confidence or scope over-reach?
- Q3: Are injection tests from the reframe session still applicable, and does the new design reintroduce the content-as-instruction risk?

**Human-Centric Designer:**
- Q1: Does `summary → facts+references → gaps` with per-fact provenance give a calling agent enough trust signal without context bloat?
- Q2: Are soft hints and graceful budget stop understandable and predictable for the caller?
- Q3: Does the separate `selector-<n>.md` audit artifact add useful inspectability or just friction?

**Operations Engineer:**
- Q1: Are the budget defaults, excludes, and pilot metrics operable, and is "observational, never gates" the right stance?
- Q2: Is the whitelist/governance path executable given the implementation skill's current pre-gate and path gate?
- Q3: What is the minimal verification set that gives confidence before any wider rollout?

## Output Limits

- Maximum findings per role: **7**
- Maximum recommendations per role: **5**
- Maximum open questions per role: **3**
- Total output per role: **~150 lines** — shorter is acceptable.

## Expected Discussion Rounds

Medium task: **1 round** (plus a targeted resolution round only if `blocked-in-scope` occurs).

## Additional Context / Constraints

- Answer in **English**; reference subject IDs (`SUBJ-001` … `SUBJ-008`) exactly.
- Use the standard fallback Role Review structure: Summary Position / Key Findings / Recommendations / Open Questions / Status / Escalation Reason.
- Critical findings require a concrete failure mode and affected subject ID.
- Read-only: you may read repository files for grounding, but must not create, modify, or delete any file. Return the review as your final response.
