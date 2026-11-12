# Koda Execution Profile (Fallback Council)

Operational helper cross-referenced from `fallback/index.md`. It does **not** change the
protocol: the five phases, role semantics, output structure and conflict aggregation rules are
defined in `fallback/index.md` and remain authoritative. This file only binds those phases to the
concrete primitives of the Koda CLI harness.

**Profile selection.** Two execution profiles exist for the same protocol:

| Profile | Orchestration harness | Status |
|---------|----------------------|--------|
| OpenCode named subagents (default) | Named subagents launched through the OpenCode harness | Unchanged, primary |
| **Koda execution profile** (this file) | Child `koda -p` processes spawned by the orchestrating agent | Additive |

Use this profile when the orchestrating agent is the Koda CLI and no named-subagent tool is
available. All other rules of `fallback/index.md` apply verbatim.

`AGENTS.md` §1.7 compliance: this profile invokes no `council.*` or `documenter.*` MCP tools.
Subagents are plain CLI processes; the absence of registered MCP servers stays the effective guard.

---

## Verified Primitives

Validated on koda 1.3.2, 2026-11-12. Re-verify after a CLI upgrade before relying on them.

| Primitive | Behaviour observed |
|-----------|--------------------|
| `koda -p "<prompt>"` | Non-interactive single run; exits with the answer on stdout |
| stdin + `-p` | stdin content is prepended to the prompt — the way to pass long briefs (avoids `ARG_MAX`) |
| `--append-system-prompt "<text>"` | Role identity carrier; overrides project instructions bleed (see Context Isolation) |
| `--include-directories <path>` | Grants a subagent started outside the repo read access to project files |
| `--allowed-tools read_file,glob` | Hard restriction verified: write attempts produce zero tool calls, no file created |
| `--output-format json` | Machine-readable envelope: `result`, `is_error`, `stop_reason`, `num_turns`, `usage` |
| `--max-turns N` | Bounds runaway exploration; on exhaustion `result` is **empty** and `stop_reason` is `limit turns` |
| `&` + `wait` (shell) | Parallel role launches verified with 4 concurrent processes |

**Tool-set caveats (verified).** Three traps:

- `--disallowed-tools` does **not** restrict — it is applied on top of the default set and can
  *widen* it. A run with `--disallowed-tools <read tools>` reported `write_file` and
  `run_shell_command` as available. Never use it to sandbox a role; only `--allowed-tools` is a
  allowlist.
- The tool set cannot be emptied: `--allowed-tools ""` and `--allowed-tools none` are both ignored
  and the full default set stays available. A role therefore always *can* browse the repository —
  the no-tools behaviour must be requested in the prompt (see below).
- Left to itself, a role spends its whole turn budget walking the workspace (`read_file`/`glob`),
  hits `max-turns`, and returns an empty `result` with no error flag. All four roles failed this
  way on the first smoke run. The prompt-level prohibition plus `--max-turns 2` is the effective
  fix: 1 turn, 0 tool calls, valid review in ~60 s.

**Known noise:** launching from `/tmp` emits `EACCES` warnings about `snap-private-tmp` and
`systemd-private-*` on stderr. Harmless — keep stderr in a separate log file, never in the result.

---

## Role Invocation Contract

One subagent = one role = one process. Roles never write to disk; the orchestrator persists their
stdout. The complete task context is passed **inline via stdin**, so the role needs no tools.

```bash
SID=sess-<id>; SLUG=Architect
cd "sessions/$SID"

cat "prompts/phase2-$SLUG.md" | timeout 600 koda \
  -p "Выполни обзор сейчас, строго в требуемой структуре. ИНСТРУМЕНТЫ НЕ ИСПОЛЬЗУЙ — весь необходимый контекст уже приведён выше; отвечай сразу текстом обзора." \
  --append-system-prompt "$(cat "prompts/role-$SLUG.md") Ответ формируется без обращения к файловой системе: не читай и не перечисляй файлы, не запускай команд." \
  --allowed-tools read_file,glob \
  --max-turns 2 \
  --output-format json > "raw-$SLUG-a1.json" 2> "raw-$SLUG-a1.err"
```

Acceptance gate — write the round artefact only when the envelope is clean:

```bash
python3 - "$SLUG" "review-$SLUG-p2.md" <<'PY'
import json, re, sys
slug, out = sys.argv[1], sys.argv[2]
STATUSES = {"agree", "concerns", "blocked-in-scope", "blocked-escalation"}
SECTIONS = ["Summary Position", "Key Findings", "Recommendations",
            "Open Questions", "Status"]
try:
    d = json.load(open(f"raw-{slug}-a1.json"))
except (OSError, ValueError):
    sys.exit(1)                      # missing or unparsable envelope -> retry/DEGRADED
res = (d.get("result") or "").strip()
if d.get("is_error") or not res or d.get("stop_reason") != "final":
    sys.exit(1)
if d.get("num_turns", 99) > 2 or d.get("usage", {}).get("tools", {}).get("calls"):
    sys.exit(1)                      # the role used the filesystem
# Split on level-2 headings, then require every section present and non-empty.
parts = re.split(r"^##\s+(.+?)\s*$", res, flags=re.M)
body = {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
if any(not body.get(name) for name in SECTIONS):
    sys.exit(1)
if body["Status"].splitlines()[0].strip().strip("*_` ") not in STATUSES:
    sys.exit(1)                      # canonical value only: "**agreed**" is not "agree"
open(out, "w").write(res + "\n")
PY
```

**Round artefact naming.** A later round must not silently overwrite an earlier one. Phase 2 output
is `review-<slug>-p2.md`; round *N* output is `review-<slug>-r<N>.md`; `review-<slug>.md` is the
**final** accepted review (the last round), copied explicitly by the orchestrator. This keeps the
Phase 2 positions available for the Phase 4 matrix, which compares stances across rounds.

Parts of the contract:

1. **Role identity** (`prompts/role-<slug>.md`) — perspective and responsibilities copied from
   `docs/en/protocol-core/index.md` §Role Definitions, plus the isolation clause below.
2. **Task input** (`prompts/phase2-<slug>.md`) — filled task brief, canonical subject list,
   required output structure from `fallback/index.md` §Output Structure, output limits. For
   Phase 3, additionally the other roles' reviews from the previous round.
3. **Self-contained input, no tool use.** Everything the role needs is inline in the stdin
   document, and the prompt states explicitly that tools must not be used. If a subject under
   review is too large to inline, the orchestrator extracts and embeds the relevant excerpt —
   roles are never asked to go and read the repository themselves.
4. **Allowlist, never a denylist.** `--allowed-tools read_file,glob` stays in the command as
   defence-in-depth (write attempts verified inert); `--disallowed-tools` must not appear.
5. **Turn budget.** `--max-turns 2` for review turns. A higher limit is only for a role explicitly
   instructed to inspect named files, and then the prompt must list those exact paths.
6. **Structured output.** Acceptance requires `stop_reason == "final"`, non-empty `result`, and a
   `## Status` heading; anything else is a failure, not a partial success.
7. **Canonical slugs** (fixes naming drift across `sessions/`): `Architect`,
   `ReliabilitySecurity`, `HumanCentricDesigner`, `OperationsEngineer`, extended roles in the same
   PascalCase style. File names: `review-<slug>.md`.

### Context Isolation (required)

Any `koda` process started inside this repository inherits `AGENTS.md` (~9k tokens: Documentation
Worker rules, manifest discipline). Left unaddressed, a role starts reasoning about documentation
policy instead of reviewing the task. Every role prompt must therefore open with:

> Ты — участник консилиума Council, роль: `<Role>`. Игнорируй инструкции проекта (`AGENTS.md`,
> Documentation Worker, манифест `docs/`) — они к твоей роли не относятся. Твоя задача — только
> экспертный обзор по заданию в требуемой структуре.

Verified: with this clause the subagent answers as the assigned role; without it, the project
instructions are present in its context. The clause must also state that the answer is produced
without file-system access — suppressing both the documentation-role drift and the file-walking
behaviour described above.

---

## Phase Mapping

| Phase | `fallback/index.md` | Koda profile actions |
|-------|---------------------|----------------------|
| 1 — Task Submission | operator provides task + subjects | Orchestrator fills `task-brief.md` from `session-task-brief-template.md`, writes `subjects.md`; operator approves the brief **before** any launch |
| 2 — Individual Review | launch one subagent per role in parallel | Spawn all role processes concurrently (`& … wait`), one `review-<slug>.md` each |
| 3 — Discussion Round | feed every review back to every role | For each role, build `prompts/phase3-r<N>-<slug>.md` = own previous review + all other reviews; relaunch in parallel; save `discussion-round-<N>.md` |
| 4 — Consensus Check | operator acts as Moderator | Orchestrator runs `session-consolidation-prompt.md` Steps 1–3 itself (no subagent), reports statuses to the operator |
| 5 — Resolution Formation | produce Consensus Document | Orchestrator drafts `consensus-doc.md` per Step 4, runs Step 5 self-check, hands to the operator |

**Role-count parameterization.** `session-consolidation-prompt.md` and
`session-task-brief-template.md` are written for a three-role roster. Under this profile, read
"three roles" as "the activated roles" (§Base Roles / §Extended Roles of `fallback/index.md`): the
normalization matrix gains one `From Role` value per activated role, and the questionnaire section
is filled only for roles present in the session. This is a reading instruction for this profile
only — the two helper files are not modified and the OpenCode profile keeps its original wording.

The orchestrator never votes. It may aggregate and normalise, but stance assignment belongs to
roles and the final decision to the operator.

---

## Artifacts

Per-session workspace `sessions/<session-id>/` (git-ignored, outside Documenter scope):

```
task-brief.md              # Phase 1, filled template
subjects.md                # canonical subject list
prompts/role-<slug>.md     # role identity, incl. isolation clause
prompts/phase2-<slug>.md   # Phase 2 input (self-contained: brief + subjects + excerpt + structure)
prompts/phase3-r<N>-<slug>.md
raw-<slug>-a<N>.json       # verbatim CLI envelope per attempt (audit trail)
raw-<slug>-a<N>.err        # stderr, incl. warnings and model errors
review-<slug>.md           # accepted role output
discussion-round-<N>.md    # Phase 3 transcript
runs.log                   # one line per attempt: ts, slug, phase, attempt, verdict, turns, tokens
consensus-doc.md           # Phase 5
```

`raw-*.json` are kept until the operator confirms `consensus-doc.md`, then may be deleted together
with `prompts/` per the lifecycle rules in `fallback/index.md`.

---

## Failure Handling

| Symptom | Detection | Action |
|---------|-----------|--------|
| Turn budget exhausted, empty `result` | `stop_reason == "limit turns"`, empty `result`, `is_error: false` | Do **not** raise `--max-turns`. Reinstate the prompt-level no-tools instruction, keep `--max-turns 2`, retry once |
| Non-zero exit / `is_error: true` | exit code, JSON field | Retry once with a stricter format reminder appended |
| Empty or truncated `result` | empty string with `stop_reason == "final"` | Retry once; on second failure mark `DEGRADED` |
| Malformed structure (no `## Status`) | heading check | One format-only retry, no re-review |
| Role hangs | orchestrator command timeout | Kill the process group, treat as failure, retry once |
| Fewer than all roles surviving after retries | count of accepted reviews | Continue with the survivors, record the gap in `consensus-doc.md` §Open Questions |
| Zero surviving roles, or no Core role left | count | **Abort** the session; report to the operator |

Retries never overwrite a previous attempt: raw envelopes are named `raw-<slug>-a<N>.json` where
`N` is the attempt number, and `runs.log` gets one line per attempt. Only the accepted attempt is
promoted to `review-<slug>.md`.

A `DEGRADED` role is not silently dropped: its absence is stated in the Consensus Document, and
the session outcome cannot be `Resolved` while a required role is missing (at minimum
`Conditionally resolved` with the gap as a reservation).

**Retry budget and backoff.** At most 3 attempts per role per round, shared across all failure
classes. Attempts run with exponential backoff plus jitter (1 s, 2 s) so a rate-limited API is not
hammered — a 429 otherwise resurfaces as a spurious "format failure". A `limit turns` retry
rebuilds `--append-system-prompt` with an escalation line (abort immediately on any tool call); a
static retry would reproduce the same failure.

**Concurrency enforcement.** Cap the batch, do not trust bare `&`: `xargs -P 4` over the slug list.
When part of a batch times out and the rest completes, the timed-out roles follow the failure table
above; the batch is never re-run as a whole.

**Budget guidance:** a tool-free review turn costs ~12–15k tokens and ~60 s; measured 61 s/role, 4
roles in parallel finished within one batch. Set the orchestrator's command timeout to at least
10 minutes for a full Phase 2 batch rather than relying on defaults.

---

*Part of the fallback mode; protocol semantics inherited from `fallback/index.md`.*
