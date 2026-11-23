# Session Task Brief — sess-hive-orchestration-2026-11-22

Date: 2026-11-22
Mode: fallback (per `fallback/index.md`), operator-specified sequential subagent execution.

---

## Session Goal

Decide whether and how the Council project should migrate its subagent orchestration (currently fallback mode: operator-driven sequential named subagents, with a planned code-based Moderator) to the `opencode-hive` tool family, and define the migration decision boundary.

## Background / Candidate Landscape

The name `opencode-hive` resolves to **two distinct projects** (operator: choice to be studied within the council):

### Candidate A — `opencode-hive` plugin (npm `opencode-hive`, repo `tctinh/agent-hive`)
- OpenCode **plugin**: feature→plan→approve→execute lifecycle with MCP tools (`hive_feature_create`, `hive_plan_write`, `hive_plan_approve`, `hive_tasks_sync`, `hive_worktree_start/commit/discard`, `hive_status`, `hive_skill`).
- Roles: `hive-master` (unified) / `architect-planner` + `swarm-orchestrator` (dedicated), `forager-worker` (task workers), `scout-researcher`, `hygienic-reviewer`, `hive-helper` (recovery).
- Execution in **isolated git worktrees**; `.hive/` directory is the durable source of truth for plan/task/worktree state; compaction recovery via `worker-prompt.md` + sessions.json; prompt budgeting (maxTotalContextChars 60k).
- Config: `.hive/agent-hive.json` (per-agent models, variants, skills, customAgents from base agents).
- **Risks:** repo `tctinh/agent-hive` **archived Oct 4, 2026 (read-only)**; license **MIT with Commons Clause** (non-commercial restriction); npm forks exist (e.g. `@hung319/opencode-hive`) with unclear maintenance lineage; plugin hooks into OpenCode via `tool.execute.before` and message-transform hooks (deep behavioral intrusion).

### Candidate B — `rretsiem/opencode-hive` (GitHub template, 42 stars, MIT)
- **Not a plugin**: a configuration template of OpenCode agents — `plan` (read-only planner) and `orchestrator` (router) as primary agents; specialists (`python-pro`, `go-pro`, `ops-specialist`, `wiki-curator`, read-only reviewers) as subagents invoked via Task tool.
- Cost-tiered model routing (SUB/MID/PREMIUM placeholders), per-agent permissions (`permission.task` allow lists), rules files, custom tools (skeleton/impact/seek/check), self-maintaining project wiki (OKF v0.2).
- Installation = copy agent/tool/rule files into `~/.config/opencode/` + project `.opencode/`; manual, auditable, no runtime hooking.

### Current Council baseline (what is being replaced/augmented)
- `fallback/index.md` v0.6.0: 5-phase protocol, operator acts as Moderator, named subagents per role (Architect, Reliability & Security, Human-Centric Designer, Operations), Phase 2/3 parallel (this session: sequential by operator instruction), plain-Markdown workspace exemption (`sessions/<id>/`).
- `docs/en/documenter-service/index.md`: OP-1 (instant operator approval, in-chat), OP-2 (maximum simplicity), OP-3 (commit audit + git revert as error control). **Write Rule**: all documentation artifacts written exclusively by Documentation Worker skill after operator approve; single-commit invariant.
- Planned but unbuilt: **code-based Moderator** (`§1.5`), which is the natural slot a hive-style orchestrator could fill.

## Key tension to resolve

- Hive's worker model (workers edit + commit in worktrees) vs the Council Write Rule (single writer, operator approve first, single-commit invariant).
- OP-2 simplicity vs plugin state machinery (`.hive/`, hooks, MCP servers, config schema) — vs template approach (plain agent files, close to current fallback).
- Archived upstream + Commons Clause license (Candidate A) as supply-chain risk for a governance-critical component.
- Whether hive replaces the *planned Moderator* (scope creep beyond "orchestration of subagents") or only its Phase 2/3 dispatch mechanics.

## Focus Areas
- Fit of hive primitives (feature/plan/task/worktree/worker/review) to the 5-phase protocol and role model.
- Write Rule and OP-1/OP-2/OP-3 compatibility.
- Supply-chain, licensing and maintenance risk.
- Migration path and reversibility (OP-3).
- Fate of `fallback/` (frozen per AGENTS.md §1.5) and the Moderator roadmap.

## Questionnaire per Role

**Architect:**
- Q1: Do hive primitives (feature/plan/tasks/worktree) map onto the Council's 5 phases and role model, or do they impose a different lifecycle that conflicts with it?
- Q2: Which candidate (plugin A / template B / hybrid) fits the planned Moderator slot without coupling the whole governance stack to an external orchestrator?

**Reliability & Security Specialist:**
- Q1: What failure modes does hive introduce (stale `.hive` state, worktree drift, compaction recovery loops, worker overreach beyond task boundary), and how do they interact with OP-3 git-revert control?
- Q2: What is the supply-chain risk of an archived repo / Commons-Clause-licensed plugin sitting on the write path of documentation artifacts, including via its hooks (`tool.execute.before`, message transforms)?

**Human-Centric Designer:**
- Q1: Does hive reduce or increase the operator's cognitive load as Moderator (approval points, status surfaces, error recovery) compared to the current fallback loop?
- Q2: Is the approval model (hive_plan_approve / vscode companion vs in-chat OP-1 approve) understandable and trust-calibrated for this project's workflow?

**Operations Engineer:**
- Q1: What is the operational cost of adopting each candidate (install, config drift, upgrades from an archived upstream, fork maintenance, worktree disk/process cost, observability of `.hive` state)?
- Q2: How reversible is the migration — can we exit hive without orphaned state, and who maintains the fork if upstream is dead?

## Output Limits
- Maximum findings per role: 5–7
- Maximum recommendations per role: 3–5
- Maximum open questions per role: 2–3
- Total per role: ~150 lines, brevity encouraged.

## Expected Discussion Rounds
- 1 round (medium-complexity task), operator may call a targeted resolution round.

## Subject List
- `SUBJ-001`: Selection between candidates — plugin A (tctinh/agent-hive opencode-hive, archived) vs template B (rretsiem/opencode-hive) vs native OpenCode subagents without hive.
- `SUBJ-002`: Mapping of hive primitives (feature/plan/task/worktree/worker/reviewer) onto the 5-phase Council protocol and the role activation model.
- `SUBJ-003`: Compatibility of hive's write/commit path with the Write Rule (Documentation Worker sole writer), OP-1 approval loop and the single-commit invariant.
- `SUBJ-004`: OP-2 simplicity — runtime state machinery (`.hive/`, hooks, MCP, config schema) vs plain agent-file approach.
- `SUBJ-005`: Error control (OP-3) — hive recovery mechanisms vs `git revert` audit-and-revert model.
- `SUBJ-006`: Supply chain — archived upstream, Commons Clause license, npm fork lineage, maintenance ownership.
- `SUBJ-007`: Fate of fallback mode (frozen) and the planned code-based Moderator — does hive replace, precede, or block it.

## Additional Context / Constraints
- Fallback documents are **frozen** (AGENTS.md §1.5): migration must not require editing `fallback/` as part of this decision; changes there need an explicit operator request.
- All documentation changes from any outcome go through the Documentation Worker skill and operator approve (Write Rule); this session produces a Consensus Document only, in `sessions/sess-hive-orchestration-2026-11-22/`.
- Current harness is OpenCode with native subagent support (`subagent` tool, background children); no MCP `council.*` tools may be invoked (prohibited while Moderator unbuilt).
- The Council is a documentation/governance project, not a code-heavy product: heavy per-task worktree machinery may be oversized for its workload.
