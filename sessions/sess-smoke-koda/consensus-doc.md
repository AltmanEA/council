# Consensus Document

Session: `sess-smoke-koda` · Profile: Koda execution profile · Roster: 4 Core roles
Rounds: 1 of max 2 (advanced — all four converged on the same defect set, second round adds no new positions)
Final statuses: Architect `concerns` · R&S `concerns` · HCD `concerns` · Ops `concerns`

## Decision

Koda execution profile is fit for use as a repeatable procedure for Phase 2–3 role launches,
**conditionally**: the launch wrapper, acceptance validator and retry loop must be implemented as
scripts before the profile can be trusted for unattended sessions.

## Rationale

- Convergent (4/4): the documented launch command lacks `timeout`; a hung role absorbs the session
  budget and blocks the batch (Architect r1, R&S 2/3, HCD 3, Ops 1).
- Convergent (4/4): the acceptance snippet has no `try/except` — `FileNotFoundError` /
  `JSONDecodeError` crash the orchestrator instead of marking the role `DEGRADED` (R&S 1, adopted by
  Architect, HCD 3, Ops 1).
- Convergent (4/4): duplicating the full role profile in `--append-system-prompt` while it is also
  in stdin wastes ~2k tokens per role and creates two potentially contradictory instruction copies
  (Ops 2, endorsed by Architect 2, HCD 1, R&S 2).
- Convergent (3/4): retry policy is declared but not implemented — no retry budget, no backoff, no
  dynamic prompt escalation (Architect 2, R&S 3, Ops 1).
- Isolated but load-bearing: `read_file`/`glob` remain in the allowlist, so the no-tools rule is a
  prompt-level soft constraint only (see Conflicts, and the security escalation below).

## Subjects with Outcomes

| Subject | Status | Notes |
|---------|--------|-------|
| SUBJ-001 acceptance & artifacts | Conditionally agreed | Strict validator accepted; elasticity sub-question unresolved (see Conflicts) |
| SUBJ-002 context isolation | Conditionally agreed | `--append-system-prompt` override confirmed working; residual risk: allowlist keeps tools reachable |
| SUBJ-003 failure handling & retries | Agreed (implementation pending) | All four agree on `timeout` + `try/except` + retry budget + backoff; none implemented yet |

## Conflicts & Disagreements

**DISAGREEMENT — SUBJ-001, acceptance elasticity for the `## Status` heading.**
HCD (finding 1, rec 2) and Ops (rec 2, r1) propose substring/elastic matching to avoid rejecting
valid reviews. R&S (rec 1, r1) opposes: a false rejection costs one attempt, a false acceptance
puts an artefact without a status into the consensus where it is indistinguishable. Architect
(finding 3, r1) sides against elasticity for safety reasons.
*Recommendation, not a resolution:* keep the gate strict but validate structure (all required
sections present and non-empty via one regex) instead of loosening the heading match. Operator
decision required.

**Convergent security escalation — SUBJ-002.** R&S (r1, finding 3) reframes the allowlist issue as
a data-leak channel, not only a turn-budget risk: with `read_file` reachable, a role can read `.env`
or files outside `sessions/<id>/` and return their content in `result`, which is persisted to
`raw-*.json` and enters the shared consensus context. Not named by any other role in Phase 2; not
refuted by anyone in r1.

## Reservations

- **Architect:** soft no-tools constraint is the principal architectural risk; on tool use the
  orchestrator should abort, not continue reading.
- **R&S:** retries must be idempotent (temp file + atomic `mv`) or concurrent attempts overwrite
  each other and destroy the audit trail; 429/rate-limit needs its own failure class; rejects
  token-length gating as padding-attackable.
- **HCD:** undocumented "extracts and embeds" step leaves the operator without a defined procedure
  for oversized subjects; unclear retry-priority when format and content fail together.
- **Ops:** concurrency cap of 4 is declared but unenforced (`&` without `xargs -P`/semaphore); no
  defined behaviour when some roles finish and others time out.

## Open Questions

1. Extract-and-embed procedure for subjects exceeding the context limit — undefined (HCD, Ops).
2. If redaction detects a secret in `result`: discard the attempt as `DEGRADED` or store a redacted
  copy? Changes auditability — operator decision (R&S).
3. On truncated generation (`stop_reason == "final"`, very short `result`): retry with "continue" or
  mark `DEGRADED` immediately? (Architect)
4. Does koda offer `--system-prompt` (full replacement) rather than `--append-system-prompt`?
  Probed: `--allowed-tools ""`/`none` are ignored, tools cannot be emptied; no full-replacement flag
  observed in `--help` (Ops).

## Action Items

| # | Action | Owner hint | Priority |
|---|--------|-----------|----------|
| 1 | Wrap every role launch in `timeout 600` | orchestrator | high |
| 2 | Replace the inline acceptance snippet with `accept.py`: `try/except` → `DEGRADED`, structural regex over required sections, `stop_reason == "final"`, `num_turns <= 2`, zero tool calls | orchestrator | high |
| 3 | Implement retry loop: max 3 attempts, exponential backoff + jitter, dynamic isolation escalation on `limit turns`, atomic attempt writes `raw-<slug>-a<N>.json` | orchestrator | high |
| 4 | De-duplicate role profile: `--append-system-prompt` carries isolation clause + 2–3 line role only; full profile stays in stdin | orchestrator | medium |
| 5 | Enforce concurrency cap via `xargs -P 4` | orchestrator | medium |
| 6 | Add redaction pass and readable-path restriction for `raw-*.json` | orchestrator | medium |
| 7 | Document the extract-and-embed step for oversized subjects | profile author | medium |
| 8 | Define behaviour for partial batch timeout (some roles finish, others killed) | profile author | medium |

## Escalation References

— None — (no `blocked-in-scope`, no `blocked-escalation` in either round)

## Downgraded Critical Findings

- Ops `SUBJ-001` claim "role may return `stop_reason == final` after 15 tool calls" — infeasible as
  stated under `--max-turns 2`; retained as the weaker, valid requirement to assert `num_turns <= 2`
  and zero tool calls in the validator.
- Format defect observed in Phase 2 artefact: Ops returned `**agreed**` (bolded, non-canonical
  value) instead of the enumerated status. Not a finding downgrade — a contract violation recorded
  here because the acceptance gate did not catch it. Action item 2 adds value validation for the
  status field.
