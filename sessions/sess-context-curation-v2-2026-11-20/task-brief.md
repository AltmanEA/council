# Session Task Brief — sess-context-curation-v2-2026-11-20

Mode: fallback (fallback/index.md v0.6.0). Phase 2 launch: **parallel** local subagents, per `fallback/index.md` §Phase 2 and explicit operator instruction for this session.

## Session Goal

Refine the context-curation decision adopted in `sessions/sess-context-curation-2026-11-20/consensus-doc.md` under a **changed understanding of what the capability is**, and confirm which parts of the v1 decision survive. Produce a recommendation only; no documentation write is authorized.

## Refined formulation (operator, 2026-11-20) — authoritative for this session

> An AI agent receives a task. It calls the Selector. The Selector is itself an AI that performs the same relevance judgment an ordinary agent would perform at the first stage of solving the task — but only the needed information enters the main agent's context.

Consequences of this formulation:

- The Selector is **semantic**, not a rule engine. It does not require an externally defined "required-context list" and does not require a task-type→document taxonomy. Relevance is an emergent result of reasoning about the task, exactly as in an ordinary agent's first exploration step.
- The Selector is a non-role **Auxiliary Agent**: no vote, no consensus participation, no write authority. A harness subagent may implement it, but it never appears as a Council participant.
- The returned bundle is a **recommended starting set, not a boundary**. The main agent retains the discovery layer (manifest / module overviews) and may fetch additional documents mid-task when the need becomes apparent. This preserves the self-correction loop that an ordinary agent has.
- Operator decisions from v1 remain binding unless this session explicitly revisits them:
  - A: fallback Phase 4 unchanged; multiple `concerns` are not an escalation.
  - B: OP-2 numeric ceiling and config-file prohibition were removed by operator-approved commit `e17e91f` (Documenter v1.4.0); complexity is judged at approval under OP-1.
  - C: `check_all.py` remains a documentation-only audit engine; session signals live in `sessions/<id>/`.
  - D: the Selector creates **no approval object**; the operator does not approve selector work. Rationale is informational visibility only; Approval Card, its 10-line contract and `tests/card_contract.py` are unchanged.
- Codebase context, if admitted, stays a parallel, read-only, per-session opt-in path with `--docs` default and `--code` opt-in; its content is untrusted data.
- No gates, daemons, state files, new approval surfaces, `council.*`/`documenter.*` MCP tools, or edits to frozen `fallback/`. Any `docs/` change requires a separate operator `approve` through the Documentation Worker skill.

## What changed from v1 (the reason for this session)

v1 assumed a **rule-based** selector (fixed `docs-read`/`docs-edit`/`code-audit` taxonomy, bounded budgets, deterministic classifier), which forced two open questions:
1. Who supplies the per-task required-context list (operator / task brief / rule engine)?
2. Where does the taxonomy live (hardcoded / YAML / manifest-derived)?

Under the refined formulation both questions lose their premise. This session must decide whether they are genuinely dissolved, and which v1 safeguards survive the switch from deterministic to semantic selection.

## Focus Areas

- SUBJ-001: Selector as semantic Auxiliary Agent — contract, inputs/outputs, boundary with the main agent and with Council roles.
- SUBJ-002: Bundle as starting set vs boundary — permanent availability of the discovery layer, self-correction loop, what the main agent is told about the bundle's status.
- SUBJ-003: Failure modes of a semantic selector — under-selection, wrong relevance, absence of an external required-context list, detectable vs silent failure; what verification still means.
- SUBJ-004: Untrusted content and prompt injection — now more relevant for an LLM selector; retrieval/evaluation separation, mandatory baseline (glossary, fallback/index.md) if any.
- SUBJ-005: Operator visibility and Documenter boundary — rationale as informational only, no approval object, unchanged card and audit contracts; relation to HCD's original trust finding.
- SUBJ-006: Codebase extension — opt-in, read-only, untrusted content, separation from the documentation path under a semantic selector.
- SUBJ-007: Validation, metrics, rollout and verification items for high/critical findings under the refined model.

## Constraints for roles

- Use only subject IDs from the canonical list.
- Do not propose new gates, daemons, state files, approval surfaces, MCP tools, or fallback modifications.
- Do not re-open operator decisions A–D unless you explicitly mark the subject and justify why the refined formulation invalidates them.
- Critical findings must name a concrete failure mode and affected SUBJ-ID.
- Output the standard fallback Role Review structure; ≤6 findings, ≤4 recommendations, ≤3 open questions, ~150 lines. Answer in English.

## Expected outcome

A consensus document stating: which v1 provisions survive unchanged, which are replaced by the semantic-selector model, which v1 safeguards are still required, and which open questions genuinely remain. Any documentation change is a separate changeset via the Documentation Worker skill after operator approval.
