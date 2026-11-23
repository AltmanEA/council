# Consensus Document — sess-hive-orchestration-2026-11-22

Session: Migration of Council subagent orchestration to opencode-hive
Mode: fallback (`fallback/index.md` v0.6.0), operator-specified sequential execution
Date: 2026-11-22
Rounds: 2 (Phase 2 individual review + Phase 3 discussion); no targeted resolution round required.

## Roster and Final Statuses

| Role | R1 | R2 (final) |
|------|----|------------|
| Architect | concerns | concerns |
| Reliability & Security Specialist | blocked-escalation (unclassified) | concerns |
| Human-Centric Designer | concerns | concerns |
| Operations Engineer | blocked-escalation (risk-threshold-breach) | concerns |

**Consensus determination (Phase 4):** no `blocked-escalation` remains, no opposing stances on identical subjects. Result: **Conditionally resolved.** All reservations recorded below.

## Operator-Provided Inputs (resolved information gaps)

- Session volume: several sessions per day (materially validates operational need for Phase 2/3 automation).
- Model base: mixed local + paid API.
- Credential storage: OpenCode native credential store (`opencode auth login`); agent configs reference model IDs only — no plaintext keys in `.opencode/` files. (Closed Reliability's primary gap.)

## Decisions

### D-1. Candidate A (npm plugin `opencode-hive`, repo `tctinh/agent-hive`) — REJECTED. [agreed, SUBJ-001, SUBJ-006]
Unanimous four-role consensus. Grounds: upstream archived read-only (2026-10-04) → no security patches for a governance-critical component; MIT-with-Commons-Clause license → commercial-use prohibition and fork/redistribution constraints; deep runtime hooks (`tool.execute.before`, message transforms) placing dead-maintained code on the write path of documentation artifacts; opaque npm fork lineage. No re-entry path except via a fully Council-owned re-implementation.

### D-2. Candidate B (template `rretsiem/opencode-hive`) — APPROVED AS SCOPED PILOT, not a migration. [conditionally agreed, SUBJ-001, SUBJ-002, SUBJ-004, SUBJ-007]
Pilot scope (binding): Phase 2/3 subagent dispatch and result collection **only**. Explicitly excluded: plan-approval workflows, git worktrees, `.hive/` state, MCP servers, any involvement of the documentation write path. Phases 1, 4, 5 remain in the current in-chat model; OP-1 in-chat approval is untouched.

Pilot pre-conditions:
1. **P-1 (Ops):** git-tracked `.pilot-files` manifest under `.opencode/` listing every copied file + source hash; single rollback = `rm` per manifest + revert.
2. **P-2 (Reliability):** per-session `sha256sum` integrity audit of all pilot config files, recorded in the session workspace, verified at session end against the manifest.
3. **P-3 (HCD):** collected results must be plain Markdown, format-identical to current fallback output (`review-<role>.md` in `sessions/<id>/`).
4. **P-4 (Architect/HCD):** binding exit criterion — <30% aggregate operator-step savings → discard pilot entirely.
5. **P-5 (HCD/Ops):** measurement protocol: per-phase operator-step counts (a step = discrete conscious action or context switch; excludes passive waiting), plus qualitative trust-erosion signals (approval hesitation, post-session re-reading, workaround behavior). Exit criterion applies to the aggregate; per-phase distribution informs the Moderator design.
6. **P-6 (Ops/HCD):** one parallel manual-baseline session (same 4-role task, no automation, same measurement protocol) in the same period to avoid task-complexity confounding.

### D-3. Worker ↔ Documentation-Worker formal contract — DECLINED. [agreed, SUBJ-003, SUBJ-007]
Per Architect's round-2 counter (accepted by Reliability and Ops): enforcing write routing, approval gating, and atomic bundling inside an external orchestrator is functionally rebuilding the Moderator inside hive — the premature coupling OP-2 forbids. The contract, if ever needed, is owned by the Council's own Moderator.

### D-4. Code-based Moderator — remains a Council-owned native solution. [agreed, SUBJ-007]
Designed around the Council's own primitives (5-phase protocol, in-chat OP-1 approval, Documentation Worker sole-writer skill, `git revert` OP-3 recovery) with OpenCode's native `subagent` tool as the only integration point. The pilot's data (per-phase step distribution, trust signals) feeds the Moderator specification. Pilot success does NOT auto-commit the Council to any hive-based future.

### D-5. Fallback documents — NO CHANGES. [agreed, SUBJ-007]
`fallback/` remains frozen (AGENTS.md §1.5). The pilot runs alongside, not instead of, fallback mode; nothing in the pilot requires editing frozen documents.

## Operational Cost Baseline (pilot scope, per Ops)

- Disk: ~10–20 copied files (~50–150 KB); no worktrees, no `.hive/`.
- Processes: none beyond standard OpenCode subagent launches; no MCP servers, no background workers.
- Upgrades: manual re-copy on upstream template updates (~30 min, infrequent).
- Per-session overhead: one `sha256sum` pass (script-automatable).

## Subject Outcomes

| Subject | Outcome |
|---------|---------|
| SUBJ-001 (candidate selection) | agreed: reject A; B as scoped pilot only |
| SUBJ-002 (hive↔5-phase mapping) | conditionally agreed: hive lifecycle is orthogonal to the protocol; only Phase 2/3 dispatch is a valid borrowing |
| SUBJ-003 (Write Rule / OP-1 compatibility) | agreed: pilot must not touch write path or approval flow |
| SUBJ-004 (OP-2 simplicity) | conditionally agreed: pilot acceptable because footprint collapses to git-tracked file copies |
| SUBJ-005 (OP-3 error control) | agreed: `.hive/`-class state unacceptable; pilot state = git-tracked manifest + hash audit |
| SUBJ-006 (supply chain / license) | agreed: A rejected; B's MIT template copied under Council custody |
| SUBJ-007 (fallback fate / Moderator) | agreed: fallback frozen; Moderator remains Council-owned; pilot is an input to its design |

## Role Reservations (tied to subjects)

- **Architect:** pilot-creep is the top failure mode (extending past Phase 2/3 after apparent success) — exit criterion must be enforced as binding, not advisory (SUBJ-007). Cost-tiered model routing adds coupling without return for this workload (SUBJ-004).
- **Reliability:** hash audit detects but does not prevent drift; if pilot ever grows a non-git state footprint beyond the manifest, it must be treated as a scope breach (SUBJ-005). Worker overreach via prompt injection remains a residual risk mitigated by process discipline and read-only role configs (SUBJ-003).
- **HCD:** any deviation from plain-Markdown fallback output re-introduces cognitive cost even inside the approved scope (SUBJ-003); step-savings must not be gameable — superficial savings from re-run stale work must not count toward the 30% threshold (SUBJ-004).
- **Operations:** pilot continuation path (≥30% savings) is undefined — a separate decision point, not an automatic extension; script authorship/maintenance must be assigned before pilot start (SUBJ-001, SUBJ-007).

## Open Questions (carried forward)

1. Who authors and maintains the pilot setup/hash-audit scripts (Ops, Reliability)?
2. What is the decision point if savings ≥30% — extend, or treat pilot as purely evidential for the Moderator spec (Ops, Architect)?
3. Should the pilot use a single model (isolating the step-savings variable) instead of B's cost-tiered routing (Ops; Architect/HCD lean yes) (SUBJ-004)?
4. Moderator↔Documentation-Worker interface: how does a code-based Moderator trigger the single-writer flow while preserving OP-1 in-chat approval (all roles; Moderator design input).

## Escalations Resolved En Route

- Reliability R1 `blocked-escalation`: classified by operator as `information-gap` (mixed model base, session volume, credential storage answered in round 2); block lifted R2.
- Operations R1 `blocked-escalation` (`risk-threshold-breach`): resolved by scoped pilot proposal with binding exit criterion, cost baseline, and reversion manifest; block lifted R2.

## Transparency — Findings Downgraded for Contract Defects

- Reliability R1 declared `blocked-escalation` without the required Escalation Reason classification (fallback §Output Structure). Per protocol the classification gap was treated as an invalid-status defect; the block was reclassified `information-gap` by the operator rather than auto-honored, and the finding's substantive content was retained at original severity (justifications were valid; no severity downgrades were otherwise applied).

## Action Items

1. Operator: approve/reject D-1..D-5 (this document).
2. On approval of D-2: assign script authorship (open question 1); prepare `.pilot-files` manifest and hash-audit script; schedule the pilot session plus the parallel manual-baseline session (P-6).
3. Moderator design session: take P-5 per-phase measurement data and open question 4 as inputs.
4. No documentation-artifact changes result from this session; `docs/`, manifest, and `CHANGELOGS/` untouched (Write Rule not engaged). If D-2 approval later requires a protocol note under `docs/`, it goes through the Documentation Worker skill.

## Artifact Index

- `task-brief.md` — filled task brief (subjects SUBJ-001..SUBJ-007)
- `review-architect-r1.md`, `review-architect-r2.md`
- `review-reliability-r1.md`, `review-reliability-r2.md`
- `review-hcd-r1.md`, `review-hcd-r2.md`
- `review-ops-r1.md`, `review-ops-r2.md`
