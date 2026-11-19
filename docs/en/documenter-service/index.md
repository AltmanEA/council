# Documenter

id: documenter-service
Version: 1.2.1-draft
Status: draft
Abstraction: conceptual
has_translation: docs/ru/documenter-service/index-RU.md
allow_non_index_paths: true
changelog-path: CHANGELOGS/documenter-service.changes.md

---

## Migration note (v1.0.0)

This specification replaces the v0.x Documenter suite from scratch. The previous design — trust tiers, a policy engine, a dual interlock, an approval surface, a consent terminal, a pre-audit gate, a hash store, intent records — reached a dead end: the gating machinery multiplied without improving documentation quality. It was abolished on 2026-11-19 by consensus `sess-documenter-concept-revision` (operator decision) and archived under `docs/en/documenter-service/legacy/`. This document is the whole system; the legacy archive is history, not authority.

## Principles (normative)

- **OP-1 — Instant operator approval.** A single operator may approve any documentation edit at any moment. No waiting, no gating: no tiers, policy gates, interlocks, readiness sentinels, out-of-band approval flows, or blocking pre-checks. The approval act is one conversation turn: the operator answers `approve` to a proposed changeset.
- **OP-2 — Maximum simplicity.** Every retained mechanism must justify its existence; the default is deletion. Hard ceiling: at most 12 files and about 3,100–3,600 lines of documentation tooling code (executable tooling only; `tools/README.md` is documentation and does not count), one operator-facing command, no daemons, no state files, no configuration files. Exceeding the ceiling requires explicit operator approval.
- **OP-3 — Commit audit as primary error control.** Errors are controlled after the fact: commits are audited against the documentation rules, and a bad commit is reverted with git. Audit never blocks any action.
- **Evolution stance.** Deterministic actions (fully specified by inputs and rules, no judgment involved) should eventually be delegated to scripts under `tools/`, dispatched by the skill under an operator-approved changeset; scripts never hold independent write authority. Each promoted script must respect the OP-2 ceiling by displacement — replacing, not adding. This stance does not authorize new approval gates, new tools, or new state files. Deferred items are recorded in the producing session's consensus document; the detailed design is deferred to a future separate session.

## Operating model

The loop per change:

1. An agent (or the operator) proposes a changeset; the Documentation Worker skill prepares it and bundles **all files of one logical update into one commit** (the single-commit invariant — the foundation that keeps revert a viable recovery).
2. The agent runs the audit tool on the change (advisory pre-commit pass). The result is merged into the approval summary: **silent when clean**; findings appear as a short list with one-line fix hints. The audit never blocks — findings inform the operator, the operator decides.
3. The operator reviews the summary (affected files, change category, line delta, mechanical/semantic flag) and answers `approve`. A **semantic** change (substantive rewrite of meaning) must name its object: `approve: rewrite of the Safety section`. A mechanical change accepts a bare `approve`. The agent proposes the mechanical/semantic classification; the operator may override it.
4. The Documentation Worker skill writes the files (its dispatches to `tools/` keep the order: document content → changelog → manifest) and the change lands as a single atomic commit.
5. Later, on demand, the operator runs the audit over recent commits; on a bad commit the operator reverts it. The revert decision is entirely the operator's judgment.

The Documentation Worker skill (`.agents/skills/documentation/SKILL.md`) remains the sole writer of `docs/`, `docs-manifest.yaml`, and `CHANGELOGS/`. There is no Documenter service, no MCP interface, and no intermediate authority between the proposal and the operator's yes.

### Complex edits

For complex updates spanning multiple steps, the skill may perform intermediate edits before assembling the final bundle. Intermediate states are not commits and do not violate the single-commit invariant (which applies only to the final commit). The operator's `approve` binds to the final assembled state on the summary card — the plan is agent-internal working context, never an approval object. The audit pass runs on the assembled bundle only. Intermediate files live in a session-scoped area outside the `docs/` tree; `sessions/` is gitignored by repository convention.

## Error control

### Audit tool

`tools/check_all.py` is the only audit engine. It is read-only, deterministic, and never gates: no caller may block on it. It runs at two calling contexts — advisory pre-commit (mandatory, run by the agent, silent when clean) and post-commit (run by the operator **on demand**; e.g. before release points or whenever suspicion arises).

Check battery:

| Check | Scope | Detects |
|-------|-------|---------|
| Content compliance (rules 1–2, 4, 6, naming, schema per `documentation-rules` §8) | changed files | structure, changelog, cross-reference, line-count defects |
| Manifest consistency | whole tree | `docs-manifest.yaml` diverging from frontmatter truth |
| Translation staleness EN↔RU | whole tree | missing or structurally drifted RU mirrors |
| Controlled-file deletion | whole tree | deletion of manifest-tracked documents |

Exit codes are informational metadata, never gating: `0` clean, `1` findings, `2` critical findings. Human-facing rendering: clean is silent; otherwise `⚠ findings: N` or `🚨 critical: N` plus one-line fix hints, grouped and severity-sorted. `--severity` sets the minimum **reported** severity (default `low`; `--strict` ≡ report everything); internal error and bad `--rule` tokens also exit `2` but are distinguished on output (`check_all: INTERNAL ERROR` / `ERROR:`), never by the `🚨` marker. (Implementation status: the frozen contract above is shipped in `tools/check_all.py` as of the Phase 0 rewrite; the pre-commit hook and prose contracts were synchronized in the same changeset.)

### Recovery

`git revert` is the recovery path for any bad commit. Because every logical update is exactly one atomic commit, revert is always a viable single operation. If a logical update was split across commits (manual bypass), the audit warns heuristically and recovery needs manual triage.

### Accepted risks

These risks are knowingly accepted under OP-3:

1. **Semantic blindness.** Mechanical audit checks structure, not meaning; a wrong-but-well-formed edit passes audit. Defense: the operator's judgment at the approval moment (naming approvals for semantic changes).
2. **Manual commit splits.** Bypassing skill bundling degrades revert reliability; mitigated only by audit warnings.
3. **Approval fatigue.** The operator may rubber-stamp; mitigations are UX-shaped, never gates.
4. **Audit latency at scale.** Full-tree checks cost a few seconds; correctness outranks speed.
5. **RU staleness.** Translation runs when the operator triggers it; delays accumulate drift without automated enforcement.
6. **Abandoned intermediate work.** If an agent is interrupted during staged work, intermediate files may persist in git-ignored workspace areas. Nothing is committed; the committed state is unchanged. Cleanup is the operator's per the session workspace lifecycle. No recovery is needed.

## Surviving tooling

Retained: `tools/gen_manifest.py` (sole manifest writer), `tools/check_all.py` (audit engine), `tools/check_drift.py` (EN↔RU structural comparison), `tools/docmeta.py`, `tools/bump_version.py`, `tools/classify_bump.py`, `tools/translation_status.py`, `tools/sync_translator.sh`, `tools/check_parity.py`, `tools/tests_helpers.py`, the warn-only `hooks/pre-commit`. Deleted with the v0 design: the `documenter_service/` package, `documenter_policy.yml`, activation overlays, the operator-ingress readiness sentinel, consent terminals, intent records, hash stores, and audit registries.

## Legacy

`docs/en/documenter-service/legacy/` (guard: `legacy/index.md`) holds the superseded v0.x suite: primary spec (`spec-v0.md`), MVP contract/interfaces/data-models, policy reference, approval surface, configuration guide. Read them only as history of why this simplicity was chosen.
