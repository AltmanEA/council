# Consensus Document — sess-doc-reliability-algo

Date: 2026-11-12
Mode: fallback (fallback/index.md v0.6.0), operator-as-Moderator
Rounds: 2 (individual review + one discussion round)
Roster: Architect, Reliability & Security Specialist, Human-Centric Designer, Operations Engineer
Final statuses: R2 — Architect: concerns; Security: agree; HCD: concerns; Ops: agree. No blocked-escalation.

## Decision

**Conditionally resolved — approved with mandatory conditions.** The direction "AI proposes — algorithm disposes" for mechanical documentation actions is adopted. Automation is staged; semantic judgment stays with AI/operator (SUBJ-006 endorsed by all roles).

## Subject outcomes

### SUBJ-001 — Manifest as generated artifact — **conditionally agreed**
- Formal YAML frontmatter in documents; `tools/gen_manifest.py` is the only writer of `docs-manifest.yaml`; `GENERATED — DO NOT EDIT` marker; deterministic ordering (sort by id).
- Mandatory: field-provenance table (each manifest field → frontmatter key | derived | authored exception) covering `allow_non_index_paths`, `references`, `has_translation` **before** the generator is written (Architect, high).
- Rule 6 (manifest parity) is redefined as **regenerate-and-diff** (idempotence) check (Security high + Architect medium converged).
- Shared single frontmatter parser between generator and validator; unparseable doc frontmatter = normal rule violation report; validator crash = distinct infrastructure error (Ops refinement).

### SUBJ-002 — Deterministic validator + git pre-commit hook — **agreed with corrected claims**
- Deterministic rules: line count (≤200), changelog existence, cross-reference anchors, manifest parity-via-regeneration, naming/schema. **Rules "glossary terms" and "abstraction consistency" are explicitly skill/AI-reserved** — the tool MUST NOT claim to implement "audit rules 1–6" (Architect high; false-comfort failure mode).
- Security claim corrected: hook is a **"best-effort pre-commit gate"**, never "structurally blocked" — `--no-verify` bypass is unpreventable; reliability = convention + git history as audit trail (ADR-007) + periodic `check_all` run in every documentation session's §8 compliance step (Security critical, accepted).
- Hook ships as versioned files `tools/hooks/pre-commit` + `core.hooksPath` + install script that self-checks and warns if hooksPath unset (Ops/Security converged).
- Severity-tiered: block high/critical equivalents, warn medium; internal tool errors fail loudly with remediation hint, exit non-zero (Architect + Security converged; HCD noise concern accepted as binding constraint).
- Scope: full-scan at current corpus size (~30 docs, <0.5 s measured by Ops); time-box guard added as corpus grows (HCD compromise retained as safety valve).
- Output: human text + `--json` mode shaped like future EventSink; rejection messages name rule + file (fix-command hint is nice-to-have) (HCD softened ask, Ops accepted).

### SUBJ-003 — Mechanical fields derived, not authored — **agreed with reductions**
- `Last Modified`: **dropped from authored frontmatter.** Disagreement (Architect keep-and-derive vs Ops/Security/HCD drop) resolved by Architect's pre-committed concession: Ops confirmed zero programmatic consumers (grep over `tools/`; only `Version:` is read). Derive at display time if ever needed. Field is also forgeable (GIT_COMMITTER_DATE) — Security.
- Changelog generation: `--note` mandatory, non-empty (all tiers), passed argv-only, **operator-supplied or quoted verbatim in the approval prompt**; changelog entries documented as "claimed rationale", not verified provenance.
- Version-bump classifier: **ships LAST**, behind measured escalation baseline. Default ambiguous → `minor` with explicit warning line citing §7.5 (never silent patch). Escalation presented in §6 format (2–3 options + recommendation); escalation rate >20% ⇒ classifier is wrong, redesign (HCD metric, adopted).

### SUBJ-004 — Parameterized safe-tier scripts — **agreed with preconditions**
- `bump_version.py` (patch only at first), atomic per-file temp+rename; **ordered writes: document content → changelog → manifest last**; partial-state window documented, not fully journaled at this stage (Security).
- **PRECONDITION (Security high + HCD high + Architect): AGENTS.md §5.1/§5.2/§8 amended and approved BEFORE any write-script becomes runnable.** Scripts are dispatched by the Documentation Worker skill only, post-§5.2 step-(5) Approve; scripts enforce atomicity, not authority.
- Post-run artifact: semantic summary (per-id old→new fields), never a raw 300-line regenerated manifest for the operator to read (HCD).

### SUBJ-005 — Spec/AGENTS impact — **agreed, scope enlarged**
Required edits (all via normal §5.2 flow with Approve): AGENTS.md §2.2 (new anchor phrase: "frontmatter is the truth; the manifest is its printout"), §5.1/§5.2/§8; SKILL.md alignment obligation extended to cover tools; `documenter-service/configuration-guide.md`: declare `documenter/hashes.json` a **rebuildable cache** (`--rebuild` flag; cache-miss = rebuild-and-continue) — locks in coexistence before the real Documenter creates double-state truth (Security, no peer objection; needs ADR entry in `planned-architecture/decisions/index.md`); `mvp-contract.md`: one-line note designating `tools/` scripts as future pure-core candidates; `tools/` dependency policy: stdlib + PyYAML(`safe_load`) only, Python 3.11+ (mirrors mvp-contract).
No conflict with Documenter MVP read-only boundary: §2.1 binds the service binary; `tools/` is implementation-file territory per AGENTS.md §1.6 (Architect, info).

### SUBJ-006 — AI/human residual boundary — **agreed (all positive)**
Semantics, split points, glossary novelty, translation, reason-string authorship remain AI/operator. Rules 3/5 of the audit list are reserved to the skill explicitly.

## Reservations (on record)
- Architect: prefers keeping `Last Modified` (generator-derived, display-only) — conceded per own conditional; revisit only if a consumer appears.
- HCD: automation-bias/rubber-stamping is mitigated but not eliminated; mitigation = one approval artifact (the change plan), red/green hook signals only, spot-check of first ~10 script invocations post-rollout then stop.
- Ops: fail-closed block mode flips on only after a **soak period** (warn-only first, operator-set duration, ~1 week); fail-closed is destination, not launch configuration.

## Sequencing (final, Ops-authored, all accepted)
1. **A**: frontmatter schema + field-provenance table + `gen_manifest.py` + shared parser + golden fixtures (1–2 d)
2. **B**: validator suite + versioned hook (warn-only soak) (3–4 d) → flip to block after clean soak
3. **D**: `bump_version.py` (patch-only, ordered writes) — only after §5.1/§5.2/§8 amendments approved (2–3 d)
4. **C**: diff→bump classifier, last, gated on escalation-rate instrumentation (5–7 d)

## Open Questions (for operator) — RESOLVED 2026-11-12
1. Does the repo ever push to a remote with CI? → **Resolved:** repository is local-only with a passive GitHub mirror (no CI). Enforcement net remains: convention + periodic `check_all` run in the skill's §8 compliance step. GitHub Actions workflow running the same validator is a deferred optional enhancement, not part of this scope.
2. Soak period length for the hook before block-mode flip. → **Resolved (operator accepted recommendation):** soak in warn-only mode until the first ~10 documentation commits pass with no false positives; flip to block mode manually by the operator (not timer-based).
3. Confirmation that `Last Modified` deletion is acceptable to the operator personally. → **Resolved (operator agreed):** field dropped from authored frontmatter; derive at display time if ever needed.
4. Approve or amend the ADR for `hashes.json` = rebuildable cache. → **Resolved (operator accepted recommendation):** adopt variant B; ADR to be drafted into `planned-architecture/decisions/index.md` per registry procedure.

## Action items
- Draft change plan per §5.2 Phase 2 for: AGENTS.md edits, SKILL.md alignment, configuration-guide.md hashes-cache note, mvp-contract.md pure-core note, ADR entry — then, after Approve, execute via Documentation Worker skill.
- Implement Stage A (provenance table first, generator second).
- Add `check_all` full-suite run to the skill's §8 compliance checklist (session-level enforcement net).

## Critical findings audit
- 1 critical raised (Security, SUBJ-002 bypass claim) — justification named concrete failure modes (`--no-verify`, unversioned hooks, editable hook) + affected subject; **not downgraded**; resolution: claim wording downgraded in spec + periodic check_all net.
- No downgrades for invalid justification this session.
