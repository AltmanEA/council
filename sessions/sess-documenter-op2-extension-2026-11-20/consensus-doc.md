# Consensus Document — sess-documenter-op2-extension-2026-11-20

Session: sess-documenter-op2-extension-2026-11-20
Date: 2026-11-20
Mode: Subagent Fallback (fallback/index.md v0.6.0); four local roles launched strictly sequentially (documentation-rules §5.4, local model → max 1 concurrent).
Outcome: **Resolved** — all four roles declared `agree` in the final round. No documentation file was modified by this session; every edit below requires a separate operator `approve` through the Documentation Worker skill.

## Roles and final statuses

| Role | Phase 2 | Final (Round 1) |
|---|---|---|
| Architect | concerns | agree |
| Reliability & Security Specialist | concerns | agree |
| Human-Centric Designer | concerns | agree |
| Operations Engineer | concerns (+ format anomaly) | agree |

## Decision

Amend OP-2 in `docs/en/documenter-service/index.md` with a **minimal, three-part normative extension — definitions, a frozen baseline, and an admission procedure — without changing the ceiling, adding mechanisms, or reopening v0 design**. Admit the task→context selector as a `--selector` sub-mode of the single existing operator-facing command (`check_all.py`), dispatched by the Documentation Worker skill, with at most one ≤200-LOC rule-data file admitted under net-zero accounting. Record the admission in the producing session's consensus and on an extended Approval Card. All existing OP-1/OP-3 semantics stay intact: advisory-only audit, one atomic commit, one `git revert` as recovery.

Explicitly rejected: a 3,700-LOC tolerance cap; inline heredoc rule data; a new Exception Card; new gates, daemons, state files, configuration files, MCP tools, fallback-document edits, or resurrection of v0 policy/activation machinery.

## Rationale

- **Convergent (all four):** the defect is terminological ambiguity, not an overly rigid ceiling. OP-2 already constrains what is possible; the fix is definitions plus a procedure, not a new mechanism. (SUBJ-001)
- **Convergent (all four):** publishing a frozen baseline (10 files / 3,646 LOC, all-lines) and explicit counting rules eliminates the silent-breach and miscount failure modes that produced a false "within ceiling" conclusion in the originating session. (SUBJ-002)
- **Convergent (all four):** three file categories — executable tooling (counted), rule data (≤200 LOC, listed, counted), pinned metadata (exempt) — give a deterministic answer to the taxonomy.yaml question while excluding policy-engine revival by alternate naming. (SUBJ-003)
- **Convergent (all four):** a flag on the existing single command is an argument, not a second operator-facing command; prose-contract sync in `tools/README.md` and the skill wrapper is binding. (SUBJ-005)
- **Convergent (all four):** net-zero admission (Δ LOC ≤ 0, file count within the 2 remaining slots) satisfies "displacement — replacing, not adding" without deleting a tool; the displacement record preserves OP-3's revert path. (SUBJ-004, SUBJ-006)
- **Convergent (R&S + HCD + Ops):** the Approval Card gains Baseline, Displacement, and Pending rows; capability labels on Displacement entries and named exception for any positive LOC delta keep the decision one-turn and scannable. (SUBJ-004, SUBJ-005)

## Subjects with Outcomes

| Subject | Outcome | Notes |
|---|---|---|
| SUBJ-001 Nature of defect | **Agreed** | Ambiguity, not rigidity; minimal three-paragraph fix. |
| SUBJ-002 Counting & baseline | **Agreed** | Frozen spec table: 10 files, 3,646 LOC (all lines, incl. blanks/comments). Baseline = all-lines; going-forward delta = non-blank/non-comment; ceiling test always on total-at-a-point; discrepancy = audit item. |
| SUBJ-003 Config-file definition | **Agreed** | Three categories; "configuration file" = operator-editable file read at runtime to alter tool behavior. `defaults/translation.lock` is pinned distribution metadata, not config. One ≤200-LOC `taxonomy.yaml` is rule data: listed in displacement table, counted toward ceiling, advisory hard-cap check. Prefer manifest-derived mapping if sufficient — then no taxonomy file at all. |
| SUBJ-004 Admission mechanism | **Agreed** | `check_all.py --selector` invoked by skill wrapper; no new command/daemon/state. Displacement record `[displaced → new/embedded, LOC delta, post total, authorizing session]` in the consensus + changeset. Five-step operator checklist. |
| SUBJ-005 One-command & prose sync | **Agreed** | Flag = internal sub-mode. Approval Card: Baseline / Displacement (with one-line capability label) / Pending rows; explicit published 10-line layout; any LOC delta > 0 requires named exception. `tools/README.md`, skill wrapper, AGENTS.md §1.7 synced in the same changeset. |
| SUBJ-006 OP-1/OP-3 compatibility | **Agreed** | One atomic commit, one `git revert`; audit advisory only, never gating. Pilot verification items V1–V5 below. |

## Conflicts & Disagreements

All Round-1 conflicts were resolved by role convergence; none reached Phase 4 as an opposite final stance:

1. **Host of selector logic** — Architect/Ops: `check_all.py` flag; R&S: skill dispatch only, no new CLI entry point. **Resolution:** flag on the existing single command, invoked by skill wrapper; not a new command.
2. **Rule-data location** — standalone taxonomy.yaml (Architect) vs inline heredoc (Ops) vs ≤200-LOC listed rule data (R&S). **Resolution:** one ≤200-LOC listed, counted, net-zero taxonomy.yaml; heredoc rejected as non-auditable/fragile.
3. **Counting method** — non-blank/non-comment (Architect P2) vs publish 3,646 as-is (Ops/R&S). **Resolution:** baseline frozen at 3,646 all-lines; going-forward method explicit and separate; only total-at-a-point tested against ceiling.
4. **Displacement target** — no tool identified for deletion. **Resolution:** net-zero delta counts as displacement; no deletion required.
5. **LOC tolerance** — 3,700 hard cap (HCD) vs stated 3,600 ceiling (others). **Resolution:** cap rejected; 3,600 stands; positive delta → named OP-1 exception.

## Reservations

- **Architect:** Baseline row must not be silently altered between admissions; `check_all.py` preferred host over `gen_manifest.py` (open question); audit-count discrepancies need a named resolver.
- **R&S:** baseline must be a frozen spec-embedded table, not a soft prose statement; dual-counting relationship stated explicitly; 200-LOC rule-data limit hard-enforced by advisory check; check engine must report raw total and cleaned count; 200-LOC cap is a hard cap, not best-effort.
- **HCD:** Displacement row must carry capability-level labels, not bare file paths; "any LOC delta > 0 → named exception" threshold must be part of the card format; the new 10-line card layout must be published explicitly, stating which rows were merged/dropped; suggest soft limit of max 2 Pending items. Conflict D (inclusion_rationale on the card) remains deferred to the originating session.
- **Ops:** information gap considered closed by the published baseline table; pilot must verify the displacement claim and remaining functionality of any compressed tool; if embedded rule data later exceeds 200 LOC, handle via a separate changeset/session, not silent growth.

## Open Questions

1. **Net-zero scope (operator clarification needed):** "net-zero" is used for both LOC and file delta. A standalone 11th file (10 → 11) remains within the 12-file ceiling but is not file-net-zero. Recommended reading: Δ LOC ≤ 0 against the published baseline, file count ≤ 12; strict file-net-zero would force inline heredoc (rejected by three roles). No role took a stance — operator decides at approval.
2. Whether the advisory LOC/file-count assertion in `check_all.py` needs separate operator authorization given the originating session's rejected Conflict C (session summaries / `~/.opencode/session-log.jsonl`, not adopted). The proposed check is tooling-metric-only, not session data.
3. Who authors the Displacement capability label — auto-derived from tool docs or operator-supplied at approval time.
4. Whether the pilot's "3 documents" are fixed or chosen per task; success criterion for "selector output usable".
5. Fate of a rule-data mapping requiring >200 LOC: second changeset with further displacement, or deferral.
6. Pending-item soft limit (if adopted): max 2 per card, and who enforces it — operator or skill wrapper.
7. Conflict D (inclusion_rationale vs fixed 10-line card) — out of scope here; remains with sess-context-curation-2026-11-20.

## Action Items

| # | Action | Role hint | Priority |
|---|---|---|---|
| A1 | Draft spec amendment to `docs/en/documenter-service/index.md` (OP-2): counting/baseline paragraph, three-category definition, admission procedure. Include the frozen 10-file / 3,646-LOC table. Route via Documentation Worker skill with Approval Card; semantic change → `approve: <named object>`. | Documentation Worker + operator | high |
| A2 | Obtain operator decision on Open Question 1 (net-zero scope) before finalizing A1 wording. | Operator | high |
| A3 | Implement selector as `check_all.py --selector`, invoked by the skill; prefer manifest-derived mapping; if a taxonomy file is needed, one ≤200-LOC listed rule-data file with net-zero LOC delta. Prose-sync `tools/README.md` and the skill wrapper in the same changeset. | Architect + Ops | high |
| A4 | Publish the extended 10-line Approval Card layout (Baseline / Displacement+capability label / Pending) and the five-step checklist; state which existing rows are merged/dropped. Record the displacement row format and positive-delta exception naming. | HCD + Documentation Worker | high |
| A5 | Add an **advisory** ceiling-count assertion to `check_all.py` (only after A2 and operator authorization): report raw total vs cleaned count, flag total > 3,600 or files > 12, flag any positive delta as exception. Never gates. | Ops + R&S | conditional |
| A6 | 3-document pilot: measure selector usability, actual LOC delta, file delta, displacement claim, and remaining functionality of any compressed tool. Failure → `git revert`; success → continuation decision. | Ops + HCD | medium |

### Verification items (sess-prevention-measures norm: every high/critical finding yields a reproducing test/action)

- **V1 (silent ceiling breach / miscount):** deterministic test re-counts the 10 baseline files and asserts the published table equals 3,646; a planted extra file or LOC must surface as an exception flag, never a silent pass. (SUBJ-002)
- **V2 (policy revival by alternate naming):** test asserts any rule-data file is ≤200 LOC, explicitly listed in the displacement table, and counted toward the ceiling; a 201-LOC or unlisted file must be flagged. (SUBJ-003)
- **V3 (unaccounted displacement):** test asserts every admission produces a displacement record with post-total and authorizing session; missing record → advisory finding. (SUBJ-004)
- **V4 (second command / gate creep):** test asserts the selector is reachable only as an argument to the single command and that its failure never blocks a session; prose contract entries match implementation. (SUBJ-005)
- **V5 (approval visibility):** card-contract test asserts the three new rows and capability labels are present and the card stays at 10 lines; missing capability label → advisory finding. (SUBJ-005)

## Escalation References

No formal escalation: no role declared `blocked-escalation`, and no opposite final stances were recorded. Ops' Phase 2 `information-gap` reason appeared with status `concerns` (format anomaly) and was withdrawn in Round 1 once the published-baseline requirement was agreed; recorded here for transparency. Open Question 1 is an operator clarification request, not an escalation of the consensus.

## Downgraded Critical Findings

| Role | Subject(s) | Original | Final | Condition / cause |
|---|---|---|---|---|
| Architect | SUBJ-002/004 | critical | high | Baseline published + displacement procedure added; deadlock failure mode removed |
| R&S | SUBJ-002/004 | critical | high | Frozen spec table + explicit counting rules enable deterministic verification |
| R&S | SUBJ-003 | critical | high | Three-category taxonomy + 200-LOC cap + listing + counting closes policy-revival path |
| HCD | SUBJ-002 | critical | high | Baseline row gives one-glance anchor; "~" ambiguity dissolved |
| HCD | SUBJ-004 | critical | high | Displacement row with capability label makes removal visible on the card |
| Ops | SUBJ-002 | critical | high | Published baseline + counting methodology close the miscount failure mode |
| Ops | SubJ-003 | critical | high | Measured-swap guardrails (cap, listing, net-zero) make taxonomy admissible |

All seven carried subject references and concrete failure modes and therefore passed format validation; their downgrades were performed by their own authors through the Round-1 convergence, not by moderator judgment. No critical finding was downgraded for invalid justification.

## Artifacts

- `task-brief.md`, `subjects.md`
- `review-<role>-p2.md` (Phase 2), `discussion-<role>-r1.md` (Phase 3 final rounds)
- `consolidation-notes-r1.md` (Phase 4 Steps 1–3)
- Origin: `sessions/sess-context-curation-2026-11-20/consensus-doc.md` (forks B–D), `consolidation-notes-r1.md`
- No documentation files modified by this session.
