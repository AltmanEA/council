# Consensus Document — sess-context-curation-2026-11-20

Date: 2026-11-20
Mode: Subagent Fallback (fallback/index.md v0.6.0), sequential local role launch per operator instruction (documentation-rules §5.4: local model → max 1 concurrent subagent).
Outcome: **Resolved by operator** — all four conflicts (A–D) closed on 2026-11-20. No documentation file was modified by this session.
- **A**: keep fallback Phase 4 unchanged (option 1); the required-context question stays as Open Question 1 / Action Item 1; no protocol or glossary change.
- **B**: closed externally by operator-approved commit `e17e91f` (Documenter v1.4.0) — fixed OP-2 ceiling and config-file prohibition removed; taxonomy storage is an OP-1 approval-time judgment.
- **C**: option 1 — `check_all.py` remains a documentation-only audit engine (only `has_translation` verification tightened); session signals stay in `sessions/<id>/`.
- **D**: the selector produces **no approval object**. Rationale is informational visibility only, rendered in the same operator turn / session workspace; the Approval Card, its 10-line contract and `tests/card_contract.py` are unchanged.

## Roles and final statuses

| Role | Phase 2 | Final (Phase 3) |
|------|---------|-----------------|
| Architect | agree | agree |
| Reliability & Security Specialist | concerns | concerns (conditions on SUBJ-003/004/005) |
| Human-Centric Designer | concerns | concerns (conditions on SUBJ-001/003) |
| Operations Engineer | concerns | concerns (conditions on SUBJ-001/002/006) |

## Decision

Adopt a **documentation-first progressive-disclosure capability** implemented as a separate, thin, non-gating selector at repo root with rule-based task→context mapping, executed as a non-voting Auxiliary Agent; keep codebase context as a strictly opt-in, parallel, read-only extension; validate by a 3-document pilot before any mandatory restructuring. No new Documenter layer, service, gate, daemon, or state file is authorized.

## Rationale

- **Convergent (Architect + R&S + Ops):** the selector must be best-effort and advisory — any blocking behavior recreates the hidden-dependency failure mode for which v0 machinery was deleted. OP-2 (v1.4.0) has no numeric ceiling: complexity is judged by the operator at approval; no gates, daemons or state files are authorized.
- **Convergent (all four):** the selector is an Auxiliary Agent (non-role, non-voting, non-consensus). Harness subagents may implement it, but it never appears as a Council participant.
- **Convergent (Architect + HCD + Ops):** reuse `docs-manifest.yaml` and frontmatter as the discovery vector; do not build a parallel index. Frontmatter stays minimal and machine-generated.
- **Convergent (R&S + HCD + Ops):** under-selection must be fail-visible (warning + audit trail), with deterministic tests; selection rationale must be inspectable by the operator; retrieval must be separated from evaluation.
- **Convergent (all four):** code context, if admitted, is per-session opt-in, read-only, on-demand, and its content is untrusted data — never selector instructions.
- **Resolved conditions:** RU-overview parity exemption is accepted with tooling-verified `has_translation` and a measured cost delta; selector rationale is informational only (no second approval object), so the Approval Card contract stays untouched.

## Subjects with Outcomes

| Subject | Outcome | Notes |
|---------|---------|-------|
| SUBJ-001 Placement | **Agreed** | Repo-root thin wrapper, NOT a new Documenter layer. OP-2 numeric ceiling and config-file prohibition removed by `e17e91f` (v1.4.0); complexity judged at approval under OP-1. Tool-scope (C) and card-contract (D) conflicts closed. |
| SUBJ-002 Progressive disclosure | **Conditionally agreed** | Overview/detail pairs; stable IDs; 200-line rule retained. Frontmatter: `abstraction`, `stable_id`, `disclosure {overview_path, related}`. RU overviews exempt from parity only if `has_translation` (already in manifest) is tooling-verified and pilot cost delta is measured. |
| SUBJ-003 Selector | **Conditionally agreed** | Auxiliary Agent; rule-based `docs-read`/`docs-edit`/`code-audit` taxonomy with bounded budgets; mandatory glossary + `fallback/index.md`; fail-visible sufficiency assertion; retrieval/evaluation split; `inclusion_rationale`. |
| SUBJ-004 Integration/OP-2 | **Agreed** | No gates, daemons, state, or new approval surface. Selector creates no approval object; Approval Card and `check_all.py` scope unchanged. Prose contracts synchronized in the same changeset if tools change. |
| SUBJ-005 Codebase extension | **Conditionally agreed** | Admitted only as parallel, read-only, per-session opt-in path (`--code`, default `--docs`), opaque content framed as untrusted; never a dependency of the docs path. |
| SUBJ-006 Validation/rollout | **Agreed, measurement deferred** | 3-doc pilot; log context-size reduction, operator correction rate, ≥2 consecutive failures → advisory warning; verification items V1–V4 below. No gate, no state file. |

## Conflicts & Disagreements

- **A — SUBJ-004, escalation rule (procedural) — RESOLVED by operator.** R&S asserted that ≥2 roles with `concerns` (or any critical+concerns) must be treated as escalation. HCD proposed a soft grouped-summary convention; Ops proposed an `ESCALATION-FLAG` annotation. Current fallback Phase 4 escalates only on `blocked-escalation` or opposing stances. **Operator decision: keep the existing rule (option 1).** No protocol change; the substantive information-gap is handled via Open Question 1 / Action Item 1.
- **B — SUBJ-001/003, OP-2 config prohibition — RESOLVED externally by operator.** Operator-approved commit `e17e91f` (Documenter v1.4.0) removed the fixed numeric ceiling, the config-file prohibition and made displacement a recommendation. Taxonomy storage (hardcode / narrow YAML / manifest-derived) is now an OP-1 approval-time judgment; the separate OP-2 extension session is no longer needed. Draft brief `sessions/sess-documenter-op2-extension-2026-11-20/task-brief-draft.md` is retained only as history.
- **C — SUBJ-004, tool-scope creep — RESOLVED by operator (option 1).** `check_all.py` stays a documentation-only audit engine: only the existing translation check is tightened with `has_translation` verification. Session summaries/ESCALATION-FLAG and operator-correction logs stay in `sessions/<id>/`; no `~/.opencode/session-log.jsonl`. No wrapper-read-count check (its threshold derived from the removed ceiling).
- **D — SUBJ-003/004, Approval Card — RESOLVED by operator.** The apparent conflict (rationale field vs fixed 10-line card contract) rested on a category error: approval authorizes documentation writes, while selection is a read-only data fetch. The selector therefore produces **no approval object**; the operator does not approve selector work. Rationale is informational: same-turn block before the card when a changeset exists, session artifact otherwise, warning in the same block on under-selection. No field, no gate, no contract change; `tests/card_contract.py` untouched. Correction of a poor bundle is an ordinary in-chat instruction, not a second approval ritual.
- **Terminology resolved:** "context-selection subagent" = harness subagent primitive implementing a non-role **Auxiliary Agent**; HCD's "never a subagent" is read as "never a Council subagent/participant".

## Reservations

- **R&S:** downgrades conditional on a deterministic under-selection test, sanitized evaluation input, and untrusted-content framing for code. Escalation claim declined by operator (Conflict A); the substantive question is Action Item 1.
- **HCD:** critical→high condition met by informational visibility in the same operator turn, without an extra click; `disclosure` flattened in display; `has_translation` shown when false.
- **Ops:** RU exemption conditional on tooling-verified `has_translation` and ≤20% cost delta; pilot must cover diverse abstraction levels; code path must default to `--docs`.

## Open Questions

1. Who supplies the per-task required-context list — operator, task brief, or rule engine? (Defines whether under-selection is a selector or specification defect.)
2. Taxonomy storage: hardcoded rules vs narrow YAML vs manifest-derived (OP-1 approval-time judgment after Conflict B).
3. Exact format of the informational bundle block (criterion key + fallback one-line reason).
4. Exact selector output format for advisory validation (`inclusion_rationale` structured key + fallback text).
5. Baseline and target context-savings ratio for the pilot; measurement window.
6. Worst-case fallback when no task domain matches (full AGENTS.md injection vs broader set).
7. Code-index LOC ceiling and behavior on sparse codebases; size cap for injected code content.
8. Pending-edit (approved, uncommitted) vs committed version selection; missing/under-review doc at one abstraction level.
9. Does the 200-line limit apply to overview files? (Ops/HCD disagree on enforcement strictness.)

## Action Items

1. **Operator decisions on Conflicts A–D are recorded above**; remaining pre-implementation decisions: required-context ownership (Open Question 1) and taxonomy storage (Open Question 2).
2. **Docs proposal via Documentation Worker skill** (only after `approve`): new overview/detail layout for the 3 pilot docs; `disclosure`/`stable_id` frontmatter; glossary and manifest alignment; changelogs; single atomic commit (role hint: Documentation Worker + operator).
3. **Implementation (implementation files, direct edit)**: thin selector tool + taxonomy mapping, `--docs` default and opt-in `--code`, rule-based mapping with bounded budgets, mandatory glossary + fallback index, fail-visible sufficiency warning (role hint: Architect + Ops).
4. **Verification items for high/critical findings (sess-prevention-measures):**
   - **V1 (SUBJ-003 under-selection):** deterministic test that removes a mandatory doc and asserts an explicit warning + audit-trail entry, never silent degraded output.
   - **V2 (SUBJ-003/005 injection):** test with a planted instruction in a doc/code comment; assert content is treated as opaque data and cannot alter selection; verify retrieval/evaluation boundary.
   - **V3 (SUBJ-001/004 gating/creep):** test that selector failure or missing context never blocks a session and never creates an approval object; the Approval Card contract remains valid.
   - **V4 (SUBJ-002 RU parity):** pilot test that `has_translation` is tooling-verified and cost delta is measured; warning when RU full content exists without RU overview.
5. **Pilot measurement:** 3 high-impact docs across abstraction levels; log context-size reduction and operator correction rate; report before expanding (role hint: Ops + HCD).
6. **Prose-contract synchronization:** if `tools/` behavior changes, update `tools/README.md` and the Documentation Worker skill contract in the same changeset (AGENTS.md §1.7).

## Escalation References

No formal escalation was triggered: no role declared `blocked-escalation` and no opposite final stances were recorded on a subject. R&S's escalation claim (Conflict A) was reviewed and declined by the operator; the three Phase 2 critical findings were downgraded with explicit conditions (below).

## Downgraded Critical Findings

| Role | Subject | Original | Final | Condition |
|------|---------|----------|-------|-----------|
| Architect | SUBJ-001/005 | critical | high | repo-root thin wrapper, parallel opaque code flow, under-selection assertion |
| R&S | SUBJ-003/004 | critical | high | deterministic assertion test + sanitized evaluation input + mandatory inclusions |
| R&S | SUBJ-003/005 | critical | medium | system-prompt untrusted framing + content/selection separation |
| HCD | SUBJ-001/003 | critical | high | rationale visible in the same operator turn, no extra click, no new approval object |

R&S's final escalation paragraph still calls SUBJ-003/005 "critical" despite the conditional downgrades in its own revised findings — recorded as an internal inconsistency; the downgraded values above are used.

## Artifacts

- `task-brief.md`, `subjects.md`
- `review-<role>-p2.md` (Phase 2), `discussion-<role>-r1.md` and `review-<role>.md` (Phase 3 final)
- `consolidation-notes-r1.md` (Phase 4 Steps 1–3)
- No escalations; no documentation files modified.
