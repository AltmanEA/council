# Session Task Brief — sess-context-curation-2026-11-20

Date: 2026-11-20
Mode: Subagent Fallback (fallback/index.md v0.6.0), sequential local role launch per operator instruction (documentation-rules §5.4: local subagent model → max 1 concurrent).

## Session Goal

Decide how to give AI agents access to only the part of project knowledge needed for the current task — primarily documentation, optionally the codebase — without bloating context, duplicating authority, or violating the Documenter principles OP-1/OP-2/OP-3.

## Background (verified from repository)

- Documentation: ~24 manifest-tracked documents under `docs/en/<id>/index.md` with RU mirrors; English authoritative, Russian derivative. `docs-manifest.yaml` is a generated index (sole writer `tools/gen_manifest.py`); agents must read via manifest, not blind filesystem scans. Document size limit 200 lines (documentation-rules §7.3); abstraction levels Conceptual/Protocol/Format/Reference (§7.4).
- Current context-loading pain: `AGENTS.md` (~9k chars) is injected into every agent; role reviews of large documents (e.g. Documentation Worker SKILL.md ~355 lines, protocol-core ~206 lines, glossary ~205 lines) force agents to read far more than a given task needs. Many docs mix reference tables, procedures and rationale in one file.
- Documenter (v1.3.2) is a thin concept: OP-1 instant operator approval in chat; OP-2 maximum simplicity (≤12 files / ~3,100–3,600 LOC of tooling, one operator-facing command, no daemons/state/config files); OP-3 audit-after-commit + `git revert`. Documentation Worker skill is the sole writer of `docs/`, manifest, `CHANGELOGS/`. `tools/check_all.py` is advisory-only, never gating.
- Falls back: no code-based Moderator; all Council sessions run in fallback mode (`fallback/index.md` frozen). No `council.*` or `documenter.*` MCP tools may be used. Auxiliary Agent (glossary): non-role worker, never participates in consensus, never votes, never advances a phase.
- Session artifacts live in `sessions/<id>/` (gitignored, outside Documenter scope). Changes to `docs/`, manifest or `CHANGELOGS/` require a separate operator `approve` through the Documentation Worker skill; this council session does not itself authorize any documentation write.
- Norm from sess-prevention-measures: every high/critical finding must yield a test/gate action item reproducing the named failure mode (the Documentation Worker flags delegations lacking one).

## Focus Areas

- Placement: additional Documenter layer vs separate project part vs combination; effect on OP-2 ceiling and on the single-write-authority rule.
- Documentation-side progressive disclosure: module-level overview → details on demand; stable identifiers; frontmatter as discovery metadata; relationship to manifest, glossary, 200-line limit and RU parity cost.
- Selection subagent: role vs Auxiliary Agent; task→context selection contract, inputs/outputs, budget, determinism, failure modes, and integration with fallback sessions.
- Conditional codebase extension: only if it does not degrade the documentation solution; read-only indexing/symbol maps; separation from the documentation path.
- Compatibility: no new gates, no new config/state files, no bypass of operator approval; prose-contract synchronization when tools change.
- Validation and rollout: measurable context savings, correctness checks, staged adoption, verification items for high/critical findings.

## Questionnaire per Role

**Architect:**
- Q1: Which placement (Documenter layer / separate part / combination) best preserves component boundaries and OP-2 simplicity? What becomes coupled?
- Q2: What is the minimal data model for progressive disclosure (overview vs detail, IDs, metadata) that fits the existing manifest/frontmatter truth?
- Q3: If both documentation selection and codebase selection exist, what interface keeps them from converging into one bulky subsystem?

**Reliability & Security Specialist:**
- Q1: How can a selector omit required context, return stale content, or be manipulated by untrusted text inside docs/code? Name concrete failure modes and affected subjects.
- Q2: What breaks if the selector is wrong (silent under-selection, over-selection, missing RU/glossary, archive smuggling)?
- Q3: Which failures deserve critical severity with a valid justification, and which are merely medium/high?

**Human-Centric Designer:**
- Q1: Will an operator understand and trust why a given context bundle was selected — and how to correct it — without learning a new ritual?
- Q2: What cognitive load does a new index/tier scheme add to agents and to the human reviewing approval cards?
- Q3: Does "less context" risk hiding decision-critical information and degrading outcomes?

**Operations Engineer:**
- Q1: What is the day-to-day cost of maintaining indexes/tiers/selection logic under the OP-2 ceiling, including EN↔RU and changelog churn?
- Q2: How should the capability be observed and validated (metrics, regression checks, advisory audit) without becoming a gate or daemon?
- Q3: What rollout sequence preserves the current workflow if the selector is wrong or unavailable?

## Output Limits

- Maximum findings per role: 6
- Maximum recommendations per role: 4
- Maximum open questions per role: 3
- Total output: ~150 lines; brevity encouraged.

## Expected Discussion Rounds

Complex task: 1 discussion round (up to 2 if new positions keep appearing).

## Subject List (canonical)

- SUBJ-001: Placement of the capability — Documenter layer vs separate project part vs combination.
- SUBJ-002: Documentation organization for progressive disclosure — overview/detail tiers, stable IDs, metadata-driven discovery.
- SUBJ-003: Context-selection subagent — classification, contract, inputs/outputs, failure modes, fallback behavior.
- SUBJ-004: Integration with existing protocol and tooling — manifest, skill, fallback sessions, OP-1/OP-2/OP-3, glossary/RU, advisory audit, no-gate constraint.
- SUBJ-005: Conditional codebase extension — read-only code context selection, admitted only if documentation solution is not degraded.
- SUBJ-006: Validation, metrics, rollout and verification items for high/critical findings.

## Additional Context / Constraints

- Roles reference subject IDs exclusively; any new subject must be admitted by the operator before the review round.
- Each finding: `[severity] text referencing <SUBJ-ID>`, stance `support`/`oppose` where it concerns a proposed decision, and mandatory justification for `critical` (concrete failure mode + subject ID). Invalid critical justification → downgrade to high.
- Final status: `agree` / `concerns` / `blocked-in-scope` / `blocked-escalation` with escalation reason if applicable.
- Do not propose: new approval gates, daemons, state/config files, `council.*`/`documenter.*` MCP tools, direct edits to `docs/` from this session, or resurrection of the deleted v0 Documenter machinery.
- Operator decision authority is preserved: this council produces a recommendation, not a license to write documentation.
