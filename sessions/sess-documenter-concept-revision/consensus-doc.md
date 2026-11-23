# Consensus Document — sess-documenter-concept-revision

Date: 2026-11-19
Mode: Subagent Fallback (fallback/index.md v0.6.0), sequential role launch per operator instruction.
Outcome: **Conditionally resolved** (operator confirmed at Phase 4; reservations recorded below).
Operator decisions at Phase 4: (1) consensus accepted with reservations; (2) post-commit audit cadence: **on demand** (not scheduled).

## Roles and final statuses

| Role | Final status |
|------|--------------|
| Architect | concerns → accepted (fast-path audit scoping required in spec) |
| Reliability & Security Specialist | concerns → agree (exit-code contract and B→A order accepted) |
| Human-Centric Designer | agree |
| Operations Engineer | agree |

## Operator Principles (normative inputs)

- **OP-1 — Instant operator approval.** A single operator may approve any documentation edit at any moment. No gating: no trust tiers, policy gates, interlocks, readiness sentinels, out-of-band approval flows, blocking pre-checks.
- **OP-2 — Maximum simplicity.** Every retained mechanism must justify its existence; default is deletion. Hard ceiling recorded below.
- **OP-3 — Commit-audit as primary error control.** Post-hoc audit of git commits plus `git revert` when necessary. Preventive blocking checks are abolished; audit never blocks.

## Subject outcomes

### SUBJ-001: Approval model — agreed

- The trust model collapses to a single concept: **the operator said yes**. Approval is a text reply in the same conversation turn; no out-of-band mechanism, no approval_id, no time windows, no diff-hash binding.
- Minimum ritual: agent presents a **summary card** (affected files, change category, line delta, mechanical/semantic flag); operator replies `approve` — for semantic changes, the approval must name its object (e.g. `approve: rewrite of §4.2`). Classification is proposed by the agent; the operator may override the flag.
- The Documentation Worker skill remains the sole write executor for `docs/`, manifest, `CHANGELOGS/`; the approval act and the write act are one atomic operator decision.
- The consent terminal, approval surface, and all Tier-gating are abolished.

### SUBJ-002: Simplicity boundaries — agreed

Deleted entirely:
- `documenter_service/` package (28 files, ~9,400 LOC) wholesale; its test suite has no salvageable assertions for the new design.
- Trust tier model (Tier 0–3), policy engine (`documenter_policy.yml`, policy-reference, activation overlay, scope presets).
- Dual interlock machinery (sentinel `documenter/.operator_ingress_ready`, `briefing_ref` enforcement).
- Approval Surface and consent tooling: `consent_terminal.py`, `consent_review.sh`, `delegate_consent.py`, `activation_helper.py`, `documenter_activation_overlay_spec.md`, `start_operator_ingress.sh`, `session_status.py`.
- Legacy runtime state in `documenter/`: `audit_registry.jsonl`, `hashes.json(+.bak)`, `intent/`, `corpus-audit/`, `.delegate.lock`, `.registry.lock`. (Provenance artifacts under `documenter/artifacts/` remain — operational, translation provenance.)
- Pre-audit gate, intent records, multi-file commit protocol, hash store/OCC, token model.

Retained (surviving set): Documentation Worker skill (sole writer); `tools/gen_manifest.py`, `check_drift.py`, `docmeta.py`, `bump_version.py`, `classify_bump.py`, `sync_translator.sh`, `translation_status.py`, `check_parity.py`, `tests_helpers.py`; rewritten `tools/check_all.py`; `hooks/pre-commit` (warn-only); `documenter/` only as minimal log scratch space.

### SUBJ-003: Error control — commit-audit + revert — agreed

- Single audit tool: **`tools/check_all.py`** (~500–800 LOC), pure read-only, **never gates** (no caller may block on it).
- Battery (4 deterministic checks): content compliance (glossary, heading translation, structure — scoped to changed files); manifest consistency (tree-wide); translation staleness EN↔RU (tree-wide); controlled-file deletion (tree-wide manifest scan).
- Exit codes 0 (clean) / 1 (findings) / 2 (critical findings) are **informational metadata for scripts, never gating**; identical structured output in all cases.
- Dual-run, same engine: (a) **pre-commit advisory** — mandatory, run by the agent before requesting approval; verdict merged into the summary card; **silent when clean** (a line appears only for findings, with one-line fix hints); (b) **post-commit authoritative** — run by the operator **on demand** (operator decision, Phase 4; e.g. before release points or whenever suspicion arises).
- Human-facing vocabulary: `⚠ findings: N` / `🚨 critical: N`; exit 0 renders no line.
- **Single-commit invariant:** every logical update is exactly one atomic commit, bundled by the skill's propose phase (tool-level, not memory-based). This is the foundation that keeps `git revert` a viable recovery. Fallback: audit warns heuristically when a logical update appears split across commits.
- Revert is the recovery path; the decision to revert is entirely operator judgment. Observability: git log + one-line append-only audit log entries; no registry, no tokens.
- Post-commit audit cadence: **on demand** (operator decision; weekly default proposed by Ops, rejected for on-demand).

### SUBJ-004: Fate of existing artifacts — agreed

- All 7 current `docs/en/documenter-service/` files move to `docs/en/documenter-service/legacy/` with `SUPERSEDED` headers, plus a `legacy/README.md` guard telling future agents not to execute archived documents.
- New single `docs/en/documenter-service/index.md` authored from scratch (see SUBJ-005).
- `AGENTS.md` §1.5–1.7 and `tools/README.md` rewritten to remove tier/interlock/policy/sentinel machinery. AGENTS.md is an implementation file (§1.6) — edited directly, not through the Documentation Worker skill.
- Code package is deleted, not renamed-and-kept: legacy narrative lives in the migration section, code lives in git history.

### SUBJ-005: Placement and structure of new documentation — agreed

- One authoritative document: `docs/en/documenter-service/index.md` — new principles, operating model (propose → summary card → approve → write → commit → audit on demand → revert), surviving tool inventory, and a short migration section at the top describing what was abandoned and why (no separate migration-from-legacy doc; split only if the migration narrative grows beyond ~2 pages or pushes index.md past a one-sitting read).
- Readability constraint: index.md readable end-to-end in one sitting (≤ ~20 minutes).

## Decommission plan — two commits, order B→A (agreed)

Commit B first (documentation, via Documentation Worker skill), then Commit A (code), so agents' router (AGENTS.md) never points at deleted machinery in a way that breaks agent loops:

1. **Commit B (docs, via skill):** move 7 legacy doc files to `legacy/` with SUPERSEDED headers + `legacy/README.md`; write new `index.md`; update affected `CHANGELOGS/`; regenerate manifest.
2. **Commit A (implementation, direct edits):** delete `documenter_service/`, `documenter_policy.yml`, sentinel, legacy `documenter/` state, consent/activation tooling; edit `AGENTS.md` §1.5–1.7 and `tools/README.md`; add rewritten `tools/check_all.py`.

Each commit is itself a single atomic logical update (single-commit invariant applies within each commit).

## Accepted risks register (explicit, under OP-3)

1. **Semantic correctness blind spot.** Mechanical audit cannot detect wrong substance; operator judgment at the approval moment (with the mechanical/semantic flag) is the only defense.
2. **Manual-commit split.** If the operator bypasses skill bundling, revert reliability degrades; audit warns heuristically; recovery requires manual triage.
3. **Operator fatigue / rubber-stamping.** Mitigations are UX-shaped (silent-when-clean, grouped findings, severity sort, naming approvals for semantic changes), not gates; residual risk remains.
4. **Audit latency at growth.** Full-tree checks ~1–3 s at current scale; if it grows uncomfortably slow, content-compliance scoping already limits the expensive part; correctness preferred over speed.
5. **RU staleness timing.** Translation runs operator-triggered post-commit; delays accumulate staleness with no automated enforcement.

## Reservations (conditional-agreement record)

- Architect: check_all.py spec must include the fast path (content-compliance scoped to changed files) to keep pre-commit latency negligible.
- Security: manifest consistency, translation staleness, and deletion detection must remain tree-wide regardless of fast path; exit codes must be 0/1/2 (pure exit-0 rejected).
- Operations: if the migration narrative exceeds ~2 pages, split it out then; default stays one doc.

## Action items

1. Operator approves the changeset proposal (skill step 5).
2. Commit B: execute documentation changes via Documentation Worker skill (legacy move + SUPERSEDED + new index.md + changelogs + manifest).
3. Commit A: delete/rewrite implementation files (outside skill scope), including new `tools/check_all.py` per frozen spec.
4. Update `docs/ru/documenter-service/` translations for superseded/new docs per language policy (via skill; RU is derivative).

## Role-reviews index

- task-brief.md; review-architect-r1.md; review-security-r1.md; review-hcd-r1.md; review-ops-r1.md
- discussion-architect-r2.md; discussion-security-r2.md; discussion-hcd-r2.md; discussion-ops-r2.md
- No escalations; no critical findings downgraded for invalid justification.
