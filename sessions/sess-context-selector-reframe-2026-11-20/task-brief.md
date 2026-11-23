# Session Task Brief — sess-context-selector-reframe-2026-11-20

Mode: Subagent Fallback (fallback/index.md v0.6.0), sequential local subagents only (documentation-rules §5.4: local model → max 1 concurrent agent). No council.*/documenter.* MCP tools. No edits to docs/, manifest, CHANGELOGS/ or fallback/; this session produces a recommendation only.

## Session Goal
Confirm and specify the reframed design of the context-selection capability, superseding the rule-based/taxonomy/required-context-list design of `sess-context-curation-2026-11-20`.

## Operator's revised formulation (the new understanding)
"An AI agent is given a task. It calls the Selector, which selects documents for that task. The Selector is an AI and works the way an ordinary AI agent would work at the first stage of solving the task — but only the needed information enters the main agent's context."

Consequence: the "required-context list" and the deterministic task taxonomy were artifacts of the earlier rule-based model. Under this formulation the Selector itself judges relevance; no external list is needed. The residual risk is not a wrong selection (ordinary agents also make first-step mistakes) but that a one-shot bundle is treated as a complete boundary, removing the main agent's normal discovery/fetch loop.

## Prior decisions carried forward (not up for re-litigation unless argued explicitly)
- Selector = Auxiliary Agent: non-role, non-voting, never a Council participant.
- No new Documenter layer, service, gate, daemon, state file or approval object. Approval Card, its 10-line contract and tests/card_contract.py unchanged.
- OP-2 (Documenter v1.4.0, commit e17e91f): no numeric file/LOC ceiling; complexity judged by operator at approval under OP-1.
- check_all.py remains a documentation-only audit engine; session signals live in sessions/<id>/.
- Documentation discovery via docs-manifest.yaml + minimal frontmatter; no parallel index; glossary and fallback/index.md are baseline inclusions.
- Codebase context is parallel, read-only, per-session opt-in (--docs default, --code opt-in), content treated as untrusted data.
- RU full content is first-class; RU overviews exempt from mandatory parity if has_translation is tooling-verified.
- Fallback frozen; session artifacts under sessions/<id>/; docs changes require a separate operator approve via Documentation Worker skill.
- Every high/critical finding must yield a test/gate action item reproducing the named failure mode (sess-prevention-measures).

## Focus areas / subjects
- SUBJ-001: Reframed selector model — semantic LLM judgment vs rule-based mapping; exact contract (inputs/outputs/budget/determinism expectations).
- SUBJ-002: Bundle semantics — "recommended starting set, not a boundary"; on-demand fetch; discovery layer (manifest/overviews) always available.
- SUBJ-003: Transparency and trust — rationale visibility at the operator turn; no approval object; correction via ordinary in-chat instruction.
- SUBJ-004: Security — prompt injection through untrusted doc/code content; content-vs-instruction separation; code path opt-in.
- SUBJ-005: Integration — manifest/overview discovery without parallel index; baseline inclusions; RU parity; relationship to AGENTS.md injection.
- SUBJ-006: Validation — metrics, 3-document pilot, verification items replacing the old V1 (no external reference list); no gates.

## Output requirements
Standard fallback Role Review structure (Summary Position / Key Findings / Recommendations / Open Questions / Status / Escalation Reason). ≤6 findings, ≤4 recommendations, ≤3 open questions, ~150 lines. Severity low/medium/high/critical; reference SUBJ-IDs exactly. Answer in English. Tools and files are not available — answer from the brief only.
