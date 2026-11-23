# Session Task Brief — Documenter Workflow Integration Readiness

Session ID: sess-documenter-workflow-readiness
Date: 2026-11-15
Mode: fallback (per `fallback/index.md` v0.6.0)

## Session Goal

Decide whether the current Documenter version (Tier 0–1 CLI operational, Tier 2+ dormant behind ADR-013 dual interlock, MCP server unregistered) can be admitted into the working process, and if so: in exactly which role, with which invocation surface, and under which constraints.

## Facts (verified before session start)

- `python3 -m documenter_service --status` → registry healthy, active_tier=1, tier_2_plus_locked=true (reason: policy gate, first interlock level ADR-013).
- `python3 -m documenter_service --reconcile` → 0 leftover intent records, needs_attention=false.
- `python3 -m documenter_service --audit --json` → runs, complete coverage 23/23 docs, returns real findings (mostly low-severity rule-4 ambiguous cross-ref anchors).
- Test suite: 655 passed in 10s (`tests/`).
- `documenter_policy.yml`: active_tier=1, allowed_operations=[], briefing_ref=null (all Tier 0–1 load rules satisfied).
- AGENTS.md §1.7: Tier 0–1 CLI "may be used in read-only/preview mode where the operator has sanctioned it". MCP server NOT registered; agents MUST NOT register it or invoke `documenter.*` MCP tools. Editing `documenter_policy.yml` is an activation act reserved to the operator out-of-session.
- ADR-013: Tier 2+ write branch implemented but not activatable until Operator Surface exists **as code**; specification alone insufficient.
- Documentation Worker skill is the sole write executor (AGENTS.md §2 Write Rule); the skill's audit mode currently dispatches `tools/check_all.py` directly, not Documenter's `audit()`.
- `documenter-service/index.md` status note: "Implemented — Tier 0–1 operational; MCP server not registered (operator decision); Tier 2+ dormant".
- Note in `notes.md` (open, unprocessed): "Ввести понятие временные документы для Документатора" (introduce concept of temporary documents for Documenter).

## Focus Areas

- In which workflow positions Documenter Tier 0–1 (CLI, read-only/preview) may legitimately sit WITHOUT conflicting with the Write Rule, the skill's existing `check_all.py` audit path, or ADR-013.
- Division of labor: `tools/check_all.py` vs Documenter `audit()` — duplication? delegation? which is canonical for pre-commit, pre-session, pre-changeset checks?
- Whether/when the Operator Surface (unblocking Tier 2+) belongs in the near roadmap vs. staying deferred.
- What operator sanction/record is required to make CLI usage a standing part of the workflow (as opposed to ad-hoc).

## Questionnaire per Role

**Architect:**
- Q1: Does inserting Documenter CLI into the workflow create a second audit authority alongside `tools/check_all.py` and the Documentation Worker skill? Where is the canonical enforcement point?
- Q2: What is the cleanest integration seam (pre-session gate? changeset pre-propose check? periodic health?) given the ports/adapters design?

**Reliability & Security Specialist:**
- Q1: Failure modes: stale hash store, false-negative audit (coverage claims), registry corruption — what do they silently permit downstream?
- Q2: Does read-only/preview CLI use carry any path to write or to interlock bypass (e.g., --delegate-preview misuse, env-var operator spoofing)? Is ADR-013 interlock intact under the proposed usage?

**Human-Centric Designer:**
- Q1: Will agents and the operator reliably understand what Tier 0–1 usage means and does not authorize (esp. that a clean audit ≠ write permission)?
- Q2: Is `--status`/`--audit` output actionable enough to be used in-session without misinterpretation?

**Operations Engineer:**
- Q1: Runtime cost and determinism: audit of 23 docs runs fast; what happens at 100+ docs (rescan_batch_ceiling=50, freshness window 30 min)?
- Q2: What standing cadence (per-commit? per-session? on demand?) is sustainable without new operational burden? What observability exists (registry health, override counter)?

## Output Limits

- Maximum findings per role: 5–7
- Maximum recommendations per role: 3–5
- Maximum open questions per role: 2–3
- Total output: ~150 lines per role, shorter is acceptable.

## Expected Discussion Rounds

1 round (medium task).

## Subject List

- SUBJ-001: Admission of Documenter Tier 0–1 CLI into the standing workflow (yes/no + conditions).
- SUBJ-002: Division of labor between Documenter `audit()` and `tools/check_all.py` (canonical audit authority per workflow position).
- SUBJ-003: Operator sanction mechanism for standing CLI usage (what must be recorded, where; does it need a doc write via the Documentation Worker?).
- SUBJ-004: Operator Surface / Tier 2+ roadmap positioning (defer vs schedule; does any current pain justify acceleration?).
- SUBJ-005: Guardrail preservation — the usage pattern must not erode ADR-013, the Write Rule, or the MCP non-registration guard.

## Additional Context / Constraints

- Repository rules: AGENTS.md §1.7 (prohibition on `documenter.*` MCP tools; CLI read-only/preview allowed "where the operator has sanctioned it"), §2 Write Rule; ADR-013.
- The decision itself may produce doc/config changes; those are out of scope here — this session produces only a Consensus Document with recommendations.
- Do not propose MCP registration as part of this decision; registration is an explicit separate operator decision.
