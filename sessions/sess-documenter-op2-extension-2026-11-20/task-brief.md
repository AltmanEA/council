# Session Task Brief — sess-documenter-op2-extension-2026-11-20

Date: 2026-11-20
Mode: Subagent Fallback (fallback/index.md v0.6.0), sequential local role launch per operator instruction (documentation-rules §5.4: local model → max 1 concurrent subagent).
Origin: consensus `sess-context-curation-2026-11-20`, fork B (OP-2 configuration-file prohibition vs deterministic taxonomy for a context selector).

## Session Goal

Decide how the Documenter specification (v1.3.2) must change so that a new deterministic capability — task→context selection — can be admitted without violating OP-2, and define a reusable extension path for future capabilities. Produce a decision; any actual documentation edit requires a separate operator `approve` through the Documentation Worker skill.

## Problem statement (the defect to fix)

OP-2 of `docs/en/documenter-service/index.md` is a hard ceiling: **at most 12 files / ~3,100–3,600 LOC of executable documentation tooling, one operator-facing command, no daemons, no state files, no configuration files**, with "exceeding the ceiling requires explicit operator approval" and an Evolution stance requiring **displacement** ("replacing, not adding"). `AGENTS.md` §1.7 repeats the same limits.

The context-curation capability requires (a) a selector tool or an extension of an existing tool, (b) deterministic task→budget mapping rules, and (c) opt-in `--docs`/`--code` behavior. The current spec provides **no extension path** for this:

1. **No counting rules.** It is undefined what counts as a "file" and a "line" under the ceiling: only `.py`? shell scripts? hooks? `tests/`? (`tools/README.md` is explicitly excluded; `hooks/pre-commit` and `install-hooks.sh` are not classified.) Measured baseline on 2026-11-20: **10 executable files, 3,646 LOC** (8 `.py` = 3,473 LOC, 2 `.sh` = 173 LOC; hook not counted) — already at/above the stated upper band. In the originating session, an operator role mis-computed the baseline by counting a deleted `check_parity.py` and a not-yet-existing `index_code.py` as current, producing a false "within OP-2" conclusion.
2. **No definition of "configuration file".** `defaults/translation.lock` exists as pinned distribution metadata, while the deleted v0 design had `documenter_policy.yml`, activation overlays and scope presets. A narrow read-only taxonomy mapping (`defaults/taxonomy.yaml`, ~50 LOC) is functionally closer to the deleted policy machinery than to the lock file, but the spec gives no criterion to decide. "No configuration files" is therefore simultaneously over-broad and ambiguous.
3. **No admission procedure.** "Displacement" is stated but there is no process for choosing what to displace, who decides, how the new baseline is measured/recorded, or how an explicit operator exception is proposed and recorded. There is also no rule for whether a new flag on an existing tool is a "second operator-facing command" under the one-command constraint.
4. **No rule-data policy.** Determinism and auditability are demanded by security/operations roles, but the spec does not say whether deterministic rule data must live in code, may live in a narrowly scoped data file, or must be derived from existing manifest fields. This is why the originating session split into three incompatible options (hardcode / YAML with exception / manifest-derived).

This is a **spec-level gap**, not a code failure: OP-2 was written as a simplicity guard after the v0 gating machinery was deleted, but it lacks the taxonomy and admission mechanism needed to admit any new capability without an ad-hoc operator exception.

## Verified context (facts, not assumptions)

- `docs/en/documenter-service/index.md` v1.3.2: OP-1 instant in-chat approval; OP-2 ceiling quoted above; "Evolution stance … each promoted script must respect the OP-2 ceiling by displacement — replacing, not adding"; "does not authorize new approval gates, new tools, or new state files. Deferred items are recorded in the producing session's consensus document".
- `AGENTS.md` §1.5/§1.7: Documenter is a thin concept (approval loop + audit engine); no `documenter.*`/`council.*` MCP tools; prose contracts binding; fallback frozen — do not modify fallback documents.
- `tools/README.md`: current tool inventory; `check_parity.py` displaced by `check_drift.py --phase4` rules (2026-11-19); warn-only hook; EN→RU pipeline external (ADR-014).
- `docs/en/documentation-rules/index.md` §5.4: local subagent model → at most 1 concurrent subagent (queue sequentially).
- Originating artifacts: `sessions/sess-context-curation-2026-11-20/consensus-doc.md` (forks B–D unresolved), `consolidation-notes-r1.md`.
- Any change to `docs/`, `docs-manifest.yaml` or `CHANGELOGS/` goes through the Documentation Worker skill after operator `approve` (AGENTS.md §2); this council only produces a decision.

## Focus areas / suggested subjects

- SUBJ-001: Is the defect ambiguity of terminology, an overly rigid ceiling, or both? What is the minimal normative fix?
- SUBJ-002: Counting rules — files, LOC, shell scripts, hooks, tests, generated data; how to publish and verify the baseline.
- SUBJ-003: Definition of "configuration file" vs pinned metadata vs rule data; criterion that excludes policy-engine revival.
- SUBJ-004: Admission mechanism for a new capability — displacement, narrow exception, or embedding into an existing tool; who decides and where it is recorded.
- SUBJ-005: One-command constraint vs new flags/tools; prose-contract synchronization (`tools/README.md`, Documentation Worker skill, AGENTS.md §1.7).
- SUBJ-006: Compatibility with OP-1/OP-3, single-commit invariant, advisory-only audit and revert; verification items for high/critical findings.

## Constraints for roles

- Do not propose new gates, daemons, state files, `council.*`/`documenter.*` MCP tools, or resurrection of v0 policy/activation machinery.
- Do not modify fallback documents (frozen; requires explicit operator request plus confirmed critical defect).
- Sequential local subagents only (one at a time).
- Output: standard fallback Role Review structure; final round statuses feed Phase 4; operator decides.

## Questionnaire per Role

**Architect:**
- Q1: Is the defect terminological ambiguity, structural rigidity of the ceiling, or both — and what is the smallest normative change that fixes it without reopening v0 design?
- Q2: How should "file", "LOC" and "configuration file" be defined so the ceiling is mechanically checkable and the taxonomy YAML question has a deterministic answer?
- Q3: What is the minimal admission path for a new capability: displace an existing tool, extend an existing tool with a flag, or an operator-approved exception — and what coupling does each create?

**Reliability & Security Specialist:**
- Q1: What concrete failure modes arise from an undefined ceiling baseline and an ambiguous "no configuration files" ban (e.g. policy-engine revival by another name, silent ceiling breach)?
- Q2: What determinism/auditability guarantees must rule data satisfy, and which of hardcode / narrow data file / manifest-derived best preserves them?
- Q3: Which findings merit `critical` with a valid justification (failure mode + subject ID), and what verification items must accompany them?

**Human-Centric Designer:**
- Q1: Can an operator understand and remember the extension rule without a new ritual, and how ambiguous is "12 files / ~3,600 LOC" in practice?
- Q2: Will an explicit operator exception become a routine rubber-stamp — and how should the exception request be presented to keep it a meaningful decision?
- Q3: Does "displacement" of an existing tool hide a capability removal from operators, and how should that be surfaced?

**Operations Engineer:**
- Q1: What is the day-to-day maintenance cost of each rule-data option under the ceiling, including the cost of measuring and republishing the baseline?
- Q2: How can the ceiling and the admission procedure be verified without creating a gate, daemon, or state file?
- Q3: What is the rollout path if the chosen interpretation later proves wrong — how does revert work at spec level?

## Output Limits

- Maximum findings per role: 6
- Maximum recommendations per role: 4
- Maximum open questions per role: 3
- Total output: ~150 lines; brevity encouraged.

## Expected Discussion Rounds

Complex task: 1 discussion round (up to 2 if new positions keep appearing).

## Subject List (canonical)

- SUBJ-001: Nature of the defect and minimal normative fix.
- SUBJ-002: Counting rules and published baseline.
- SUBJ-003: "Configuration file" definition vs pinned metadata vs rule data.
- SUBJ-004: Admission mechanism for new capability (displacement / narrowing / exception).
- SUBJ-005: One-command constraint and prose-contract synchronization.
- SUBJ-006: OP-1/OP-3 compatibility, verification items, revert path.

## Additional Context / Constraints

- Roles reference subject IDs exclusively; any new subject must be admitted by the operator before the review round.
- Each finding: `[severity] text referencing <SUBJ-ID>`, stance `support`/`oppose` where it concerns a proposed decision, and mandatory justification for `critical` (concrete failure mode + subject ID). Invalid critical justification → downgrade to high.
- Final status: `agree` / `concerns` / `blocked-in-scope` / `blocked-escalation` with escalation reason if applicable.
- This council produces a recommendation, not a license to write documentation.
