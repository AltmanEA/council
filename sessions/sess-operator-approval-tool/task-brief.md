# Session Task Brief — Operator Approval Tool

Session id: `sess-operator-approval-tool`
Date: 2026-11-18
Mode: fallback (`fallback/index.md` v0.6.0), local subagent model, strictly sequential launches (AGENTS/documentation-rules §5.4: local model → max 1 concurrent).

## Session Goal

Design (as a consensus document with an implementation-ready specification) a small standalone operator-side tool — a "consent terminal" — that the operator runs in a separate terminal to review and approve agent-proposed actions with a single keypress or short input, maximizing operator simplicity without reducing reliability.

## Problem Statement (current pain)

The current approval chain requires the human operator to manually compose and type parameterized commands across several flows:

1. **Documentation writes** (`documentation-rules` §5.1–5.2): the operator must give explicit step-(5) Approve for every changeset; today this is conversational, but in the pilot the operator was asked to type scripts with parameters.
2. **Tier 2+ Documenter approval** (`documenter-service/mvp-contract.md` §4, `approval-surface.md`): `documenter.approve(approval_id, operator_id, acknowledge)` must be a separate out-of-band invocation; the solo path (ADR-017) additionally requires the typed acknowledgment token `CONFIRMED_SOLE_REVIEWER` and `min_approval_delay_seconds` wait.
3. **Tier 2 activation flow** (`tools/activation_helper.py`, `tools/start_operator_ingress.sh`, overlay files, sentinel): multi-step, parameter-heavy shell usage.

Pilot run evidence: operator had to type scripts with parameters — high friction, error-prone (typos in ids/tokens), no consolidated view of *what* is being approved.

## Candidate design direction (to be examined, not assumed)

A local, out-of-band consent terminal, e.g. `python3 tools/approve.py` (or `tools/consent_terminal.py`), launched by the agent in a *separate terminal* (out-of-band relative to the agent session):

- Agent creates a **pending approval request** record (single JSON file under `documenter/` or a `pending/` spool) containing: human-readable summary, target id(s), diff file path + diff hash, proposed change, expiry deadline, proposer id, solo/mode flags.
- The tool watches the spool, renders the pending item(s) **verbatim from the record** (no LLM paraphrase, per `approval-surface.md` presentation rule), and asks for one of: single keypress (Y/N), or short typed input (e.g. a short code, or `CONFIRMED_SOLE_REVIEWER` where ADR-017 requires it — possibly as `y` + auto-supplying the typed token *only after* an explicit second confirmation step, if the consensus deems this preserves the 'typed acknowledgment' intent).
- On approve/deny the tool writes a signed-or-at least authenticated decision record (operator id from `~/.council` credentials as in `start_operator_ingress.sh`), consumed once by the agent's flow via the existing canonical contract paths (approval token, single-use, expiry, diff-hash binding, TOCTOU re-check of the diff before acting).
- Reused existing mechanics: approval token semantics (`mvp-contract.md` §4 — canonical), `documenter/approval` event schema, `approval_expiry_window`, `min_approval_delay_seconds`, ADR-017 solo constraints, registry single-use/expiry checks (`documenter_service/core/registry.py`).

## Non-negotiable reliability constraints (from controlling docs)

- **Step-(5) Approve by human** before any doc write (AGENTS.md §2, documentation-rules §5.1) — the tool must be a faithful carrier of that human act, not a bypass.
- **Out-of-band separate invocation** from the proposal; `operator_id` from authenticated ingress only; approver ≠ proposer except ADR-017 solo exception.
- **Single-use tokens, diff-hash binding, expiry window, changed-diff invalidation** (§4 canonical).
- **No LLM paraphrase of the diff** in the approval presentation (`approval-surface.md`).
- **Tier interlock unchanged**: the tool must never write `documenter_policy.yml` or create the readiness sentinel; activation remains an operator act out-of-session.
- **Stdlib-only, local-first** (ADR-006/007 style constraints); same-UID threat model honesty (see SECURITY note in `start_operator_ingress.sh` — convenience separation, not true isolation).
- The tool is an **implementation file** (repo root / `tools/`), outside Documenter scope (§1.6); prose-contract synchronization rule applies when it lands.

## Focus Areas

- Where the trust boundary must sit so a "one keypress" is still a genuine informed human act (what must be *seen* minimum before the keypress is meaningful).
- How the tool satisfies "separate invocation / out-of-band" for Tier 2+ without breaking the canonical §4 contract; whether it *is* an Operator Ingress client, a new ingress, or a step-(5)-only device with Tier 2+ handled by existing surface later.
- Ergonomics: batch vs one-by-one, `y`/short-code/typed-token tradeoffs, delay-wait UX, failure/typo UX, timeout behavior (deny-by-default?).
- Abuse/misuse modes: auto-approve drift, agent pre-typing, keylogger/same-UID spoofing, stale spool items, hash mismatch at apply time.

## Questionnaire per Role

**Architect:**
- Q1: Which existing components (registry tokens, ingress, events) must the tool reuse vs duplicate? Where is the single canonical source for the spool record schema?
- Q2: Is the tool an Operator Ingress transport variant or a standalone device? What coupling does each choice create?

**Reliability & Security Specialist:**
- Q1: Which §4 guarantees could silently degrade when approval collapses to one keypress, and which minimal controls are non-removable (e.g. ADR-017 typed acknowledgment)?
- Q2: Enumerate concrete attack/failure modes: stale spool, TOCTOU, replay of decision records, agent-side forgery of the operator decision file, deny-vs-hang on timeout.

**Human-Centric Designer:**
- Q1: What is the minimum-diff-view that keeps a keypress informed (truncated diff? stats + pager on demand?) and how to avoid rubber-stamping?
- Q2: How should the tool handle multiple queued items, typos, and the ADR-017 delay wait without becoming the new complexity?

**Operations Engineer:**
- Q1: Lifecycle of the spool directory, crash recovery, partial writes, cleanup responsibility, interaction with `check_all`/tests.
- Q2: What does this add to the operator's operational surface (another process to run, env vars, credentials) — net simpler or just moved complexity?

## Output Limits
- Maximum findings per role: 5–7
- Maximum recommendations per role: 3–5
- Maximum open questions per role: 2–3
- Total output per role: ~120 lines

## Expected Discussion Rounds
- 1 round (medium task)

## Subject List
- `SUBJ-001`: Consent-terminal architecture — standalone tool vs Operator Ingress client vs step-(5)-only device; spool/IPC mechanism (file-based vs stdin/stdout).
- `SUBJ-002`: Mapping of the one-keypress act onto controlling contracts — step-(5) Approve, §4 approve(approval_id…), ADR-017 typed acknowledgment; what is preserved, delegated, or reinterpreted.
- `SUBJ-003`: Minimal informed-consent presentation — what must be rendered on screen (summary, diff hash, stats, verbatim diff access), no-LLM rule.
- `SUBJ-004`: Security controls that must remain: single-use, diff-hash binding + apply-time re-verification, expiry, deny-by-default timeout, credentials source, event/audit logging.
- `SUBJ-005`: Operator UX flow — keypress vs short code vs typed token; batch handling; delay-wait; typo/error UX; scope of first MVP.

## Additional Context / Constraints

- Deliverable of this session is a **design consensus** (components, contract mapping, MUST/MUST-NOT list, MVP scope), not code. Implementation would follow via the normal process.
- Existing code to reuse (read-only here): `documenter_service/core/registry.py` (approval tokens, expiry), `core/override.py`, `operator_ingress/core/approval.py`, `core/auth.py` (HMAC tokens, caller classes), `tools/start_operator_ingress.sh` (credentials from `~/.council`).
- Note tension: `mvp-contract.md` §4 says tokens are **random server-stored single-use** (C1: no HMAC for approval tokens) while Operator Ingress uses HMAC session tokens — the design must not conflate them.
- Operator is a single person (solo experiment per ADR-017 is the realistic deployment mode).
- Keep the solution minimal-stdio-Python-plausible; no new services/daemons unless strongly justified.
