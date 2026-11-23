# Consensus Document — sess-context-selector-reframe-2026-11-20

Date: 2026-11-20
Mode: Subagent Fallback (fallback/index.md v0.6.0), sequential local role launch (documentation-rules §5.4: local model → max 1 concurrent subagent). No council.*/documenter.* MCP tools; fallback unchanged.
Outcome: **Resolved** — all four roles `agree` after one discussion round. No documentation file modified by this session.

Supersedes the rule-based/taxonomy/required-context-list design of `sess-context-curation-2026-11-20` (SUBJ-001/003 parts only); all carried-forward decisions of that session remain in force.

## Decision
Adopt the reframed capability: an **LLM-based Selector** that judges document relevance from the task description plus manifest metadata, returning a **recommended starting set** (not a boundary) with rationale. The main agent retains an on-demand `discover()` path and performs final content-level judgment. No required-context list, no task taxonomy, no new gate/tool-type/state file, no Approval Card change. Validate with a scoped pilot (N=20 sessions / 30 days) before any mandatory adoption.

## Rationale
- The Selector is a **mirror** of the main agent's first-step reasoning, not a risk amplifier (R&S): non-determinism and under-selection inherit an already-accepted risk profile.
- The real failure mode is not a wrong pick but a bundle mistaken for a boundary; therefore `discover()` with a formal call contract is a **dependency**, not an optional feature (all four).
- Index-only input is sufficient for relevance judgment and minimizes the injection surface; bodies reach only the main agent (Architect, R&S, HCD; Ops accepted).
- Trust is calibrated by visible rationale and explicit labels, not by approval: the Selector creates **no approval object** (all four; carried-forward decision D).
- Advisory pilot measurement replaces the deleted external-list assertion; no gates, no daemons.

## Subjects with Outcomes
| Subject | Outcome | Notes |
|---|---|---|
| SUBJ-001 Selector model | **Agreed** | LLM judge; input = task + manifest index; output = ordered IDs + 1–2 line rationale per doc + one-line task summary + starting-set disclaimer. One LLM call + manifest read per task (~1× overhead). No deterministic rule taxonomy. |
| SUBJ-002 Bundle semantics | **Agreed** | Bundle is a recommended starting set, explicitly labelled; `discover()` on demand. Helper with `tool="discover"` tag and formal call contract: `discover(keyword?, fields?) → ranked list`, same manifest path, SHA-256 of manifest in response envelope, fail-closed. No new tool type, gate or state. |
| SUBJ-003 Transparency | **Agreed** | Output order: task summary → per-doc rationale (10–20 words) → explicit "starting set" disclaimer → `Discoverable: yes/no` plain-text advisory. Each doc labelled `discovered`/`manual`. Operator corrects in natural language; **no new ritual, no card field, no approval object**. Manifest checksum lives in rationale text. |
| SUBJ-004 Security | **Agreed** | Selector sees only six metadata fields (id, title, abstraction, path, RU-path, description); no doc bodies. Two mandatory pilot injection tests: poisoned manifest metadata against the Selector, poisoned doc bodies against the main agent. Content-level prompt guard moves to the main agent. Code path stays opt-in and untrusted. |
| SUBJ-005 Integration | **Agreed** | Manifest + minimal frontmatter remain the only discovery layer; no parallel index. Glossary and fallback/index.md baseline inclusions retained. AGENTS.md inclusion is flagged as a behavioral-contract inclusion in the rationale. RU full content first-class. |
| SUBJ-006 Validation | **Agreed** | Primary metrics: bundle stability, operator correction rate, context savings. Missed-relevance via manual 3-field annotation (`missed_id`, `missed_reason`, `type`) in a separate panel. `bundle_relevance` and `correction_reason` are additive fields in the existing session log, not a new artifact. Pilot N=20 / 30 days; advisory only, no gate. |

## Conflicts resolved in Phase 3
1. `discover()` as new runtime primitive vs manifest-scan helper → helper + formal call contract (R&S condition accepted by Architect and Ops).
2. Checksum/marker in Approval Card vs outside → checksum and `Discoverable: yes/no` both in rationale text; Ops withdrew the card-field proposal; R&S's fixed-contract objection satisfied. CARD_FIELDS and `tests/card_contract.py` untouched.
3. Selector sees bodies vs index-only → index-only; prompt guard relocated to main agent.
4. Metrics set → top-3 primary + manual missed-relevance annotation; cost/effort trade-off accepted.
5. HCD CLI/chat command for `discover()` → withdrawn (new ritual); natural-language correction retained; UI-visible/copyable result retained.
6. Trust labels per document → `discovered`/`manual` accepted by all.

## Reservations
None blocking. Implementation-level open points: default `fields?` set for `discover()`, exact fail-closed behavior on checksum mismatch, ownership of `correction_reason`, label rendering form, correction-rate window. All are spec details, not consensus blockers.

## Verification / action items
1. **V1 (SUBJ-002 boundary):** test that the main agent can call `discover()` mid-task and fetch a document absent from the initial bundle; assert no gate/state is created and the tag `tool="discover"` is emitted.
2. **V2 (SUBJ-002 freshness):** corrupt/unreadable manifest → assert `discover()` fails closed (empty list or explicit error, never partial/cached results) and checksum mismatch is visible.
3. **V3 (SUBJ-004 injection):** (a) manifest entry with adversarial title/description — assert Selector ranks by genuine relevance, not by following injected directives; (b) doc body with hidden adversarial content — assert main-agent prompt guard prevents acting on it.
4. **V4 (SUBJ-003 no new authority):** assert the Selector output creates no approval object and the Approval Card contract remains valid and unchanged.
5. Pilot N=20 / 30 days: collect primary metrics, manual missed-relevance annotations, injection-test results; report before any mandatory rollout.
6. Any change to tool behavior → synchronize prose contracts (`tools/README.md`, Documentation Worker skill, `AGENTS.md` §1.7) in the same changeset.
7. Documentation changes (if pilot leads to them) → separate operator `approve` through the Documentation Worker skill, single atomic commit.

## Escalation references
None. No role declared `blocked-in-scope` / `blocked-escalation`; all final statuses `agree`; no opposing stances after Phase 3.

## Artifacts
`task-brief.md`, `subjects.md`, `review-<role>-p2.md`, `discussion-<role>-r1.md`, `consolidation-notes-r1.md`, `prompts/phase2-digest.md`. No documentation files modified.
