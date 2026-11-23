# Consensus Document — Documenter Workflow Integration Readiness

Session ID: sess-documenter-workflow-readiness
Date: 2026-11-15
Mode: fallback (fallback/index.md v0.6.0)
Roles: Architect, Reliability & Security Specialist, Human-Centric Designer, Operations Engineer
Rounds: 1 individual + 1 discussion
Final statuses: Architect agree · Reliability agree · Human-Centric agree · Operations agree
Consensus state: **Resolved**

---

## Decision

**Yes — the current Documenter version (Tier 0–1 CLI) is admitted into the working process** as a **read-only advisory auxiliary**, under the conditions D1–D7 below. Tier 2+ write remains **not admitted and not activatable** (ADR-013 dual interlock, reaffirmed by code verification this session). MCP registration remains out of scope and unchanged.

### D1 — Role in the workflow (SUBJ-001)

Documenter Tier 0–1 CLI (`python3 -m documenter_service`) enters the standing workflow as an advisory, non-blocking diagnostic and health surface. It is **not** a compliance gate and **not** a write authority. The Write Rule (AGENTS.md §2) is unchanged: the Documentation Worker skill remains the sole write executor.

### D2 — Canonical audit authority per position (SUBJ-002)

| Workflow position | Canonical tool | Character |
|---|---|---|
| Before proposing a changeset (deterministic gate) | `tools/check_all.py` | blocking (exit 1 = blocking) |
| Council-session start (health) | `documenter_service --status --json` | advisory, ~68 ms |
| Pre-changeset supplementary findings | `documenter_service --audit --json` (default `--severity-min medium`) | advisory, never blocks |
| Weekly operator-run drift check | `documenter_service --audit --json` | advisory, non-blocking |

Adopted from the Operations three-layer cadence (A: per-session `--status`; B: pre-changeset `--audit`; C: weekly `--audit`). Git pre-commit hook for Documenter: **rejected** (unbounded latency, conflates code-gating with doc-quality gating).

**Citation rule:** findings must always name the producing tool; findings from `check_all.py` and Documenter `audit()` are never interchangeable as consensus evidence.

**Rule-divergence guardrail (Reliability, medium):** the two independent implementations of rules 1,2,4,6 are acceptable at Tier 0–1 only because no write path exists; before standing usage takes effect, run the one-shot cross-test (A-1 below) and record divergences in a conformance log. Shared rule module: longer-term option, not required at MVP (Architect: consolidation cost outweighs benefit at MVP scale).

### D3 — Operator sanction record (SUBJ-003)

Standing sanction is recorded **in AGENTS.md §1.7** (updated by the operator following step-5 approval), referencing this consensus document as the authority artifact. The sanction record must contain:

- operator identity and date;
- **Documenter version pin** (git SHA of the admitted code; this session: post-`23e2706` working tree);
- scope: read-only/preview CLI only (`--status`, `--audit`, `--reconcile`, `--delegate-preview`);
- revocation criteria (operator may revoke in-session by amending the §1.7 line).

Compromise note (SUBJ-003): Architect proposed an additional machine-checkable flag file under `defaults/`; HCD and Ops countered that AGENTS.md is read by every agent each session and a separate file drifts. Consensus: **text sanction in AGENTS.md is sufficient and canonical**; a flag file is optional and, if ever added, must be derivative of the §1.7 text, never authoritative alone.

### D4 — Trust-calibration caveats (SUBJ-005, HCD must-haves)

The §1.7 addition and any workflow text must state:

1. `--audit` **exits 0 regardless of severity** — exit 0 ≠ corpus-clean; the `coverage` and `severity` fields in the JSON, not the exit code, are the signal. (Should also be surfaced in the CLI output itself — backlog A-4.)
2. Audit scope is **deterministic rules 1,2,4,6 (+naming/schema) only**; rules 3 (glossary) and 5 (abstraction) are AI/skill-reserved; a zero-finding result does not imply semantic compliance.
3. A clean `--audit`/`--status` is **never** a write authorization of any kind.

### D5 — delegate_preview / diff_hash wiring (SUBJ-002)

**Deferred to Tier 2+.** At Tier 0–1 nothing consumes the hash; it becomes meaningful when the approval flow (Operator Surface) binds approval to bytes. Architect withdrew the Round 1 recommendation; no dissent.

### D6 — Operator Surface / Tier 2+ roadmap (SUBJ-004)

**No acceleration warranted.** Current pain points are all advisory-layer and resolvable without the write branch. ADR-013 interlock stands. Recorded for the eventual pre-activation checklist (Reliability):

- verify hash-store integrity; forbid `--rebuild-hashes` between pre-write audit and apply (OCC window);
- resolve `DOCUMENTER_POLICY_PATH` trust question (env redirection is neutralized at Tier 0–1 by the sentinel+policy check, but must be pinned down before Tier 2+);
- confirm rule-conformance log is clean (D2 guardrail);
- `.operator_surface_ready` sentinel: gitignored, operator-created, tied to Operator Surface code deployment.

### D7 — Backlog with trigger thresholds (non-blocking, SUBJ-001/003)

| Item | Trigger |
|---|---|
| Pagination ceiling (currently 50) | corpus > 40 docs |
| Audit-registry retention/GC (14-day sweep) | `audit_registry.jsonl` > 1 MB |
| Hash-rebuild event notification | rebuild frequency > 1/week |
| Materialize `scanned_count`/`total_count` in registry lines | next registry-writer edit |
| `--summary` single-line output flag | backlog, no trigger |

---

## Action Items (pre-admission, minimal)

- **A-1** (Reliability): one-shot cross-test `tools/check_all.py` vs `documenter_service --audit` on the current 23-doc corpus; record divergences in a conformance log (location: operator's choice, suggest `documenter/artifacts/`).
- **A-2** (operator): update AGENTS.md §1.7 with the standing-sanction paragraph per D3–D4 (operator edit; AGENTS.md is an implementation file outside Documenter scope).
- **A-3** (Documentation Worker, after operator Approve per §2 Write Rule): if the workflow-position table (D2) is to be mirrored into `docs/en/` (e.g., documentation-rules or documenter-service docs), route that change through the skill's propose→approve flow.
- **A-4** (backlog implementation): encode exit-code caveat and rules-scope note in CLI output (HCD must-have #1/#2 in output form; the textual rule in D4 already covers agent-facing behavior).
- **A-5** (operator): record the version pin SHA in the §1.7 sanction text.

## Reservations

- HCD: citation rule (D2) should also be reflected in the Documentation Worker skill's Response Contract — open placement question, not a block.
- Reliability: accepts admission knowing divergence risk is latent; A-1 is its condition of consent.
- Architect: flag-file option preserved as optional-derivative only.

## Open Questions (carried forward)

1. Sanction metadata: binary vs structured (§1.7 text currently carries the structured minimum per D3).
2. Is the MVP rule set frozen at 1,2,4,6 (limits divergence likelihood) or will rules be added to `check_all.py` before shared-module work?
3. Placement of the "cite the tool" rule: skill Response Contract vs AGENTS.md only.
4. Related unprocessed note (notes.md): "temporary documents" concept for Documenter — out of scope here, candidate for a dedicated session.

## Critical-findings transparency

No findings were downgraded for invalid justification. Verifications labeled CRITICAL/HIGH in Reliability Round 1 that described confirmed-safe properties (interlock enforcement, preview isolation, override-gate containment) were reclassified by the orchestrator as **verifications**, not defects, with the role's implicit concurrence (Round 2 summary reaffirms interlock integrity). Operations' `scanned_count=0/0` finding was corrected during collection (registry carries complete `scanned_ids`; reporting-layer-only gap).
