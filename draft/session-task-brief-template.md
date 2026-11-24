# Session Task Brief Template

> `MODE: dev-dogfood/v2@<pin>` — ЧЕРНОВИК v2, объект обсуждения, НЕ регламент. Операционный шаблон — `../council/fallback/session-task-brief-template.md`.

---

## Purpose

Fill this template **before** launching subagents. It ensures each role receives a focused task with clear expectations, preventing verbose or off-topic output.

Copy the template below into a new file (`session-task-brief.md`) and fill every `[...]` field. Pass the completed file as context to all three subagents in Phase 2.

---

## Task Brief

### Provenance (mandatory, copied to consensus-doc header)
- **worktree-path:** [actual working directory of the session, e.g. `/home/ea/council`]
- **mode:** [operational | dev-engine | dev-dogfood]
- **engine:** [regulation this session is conducted by: `v1.0.<x>@<sha>` for operational/engine sessions; `draft@<sha>` for dogfood sessions (draft frozen Phase 1 → consensus-doc)]

### Session Goal
[One sentence: what decision or outcome do we want by the end of this session?]

### Focus Areas
[Limited list of specific aspects each role should concentrate on. E.g.: "integration point between A and B," "error handling strategy," "user authentication flow."]
- [...]
- [...]

### Questionnaire per Role

**Architect:**
- Q1: [e.g., "Will this coupling create excessive dependency?"]
- Q2: [e.g., "What will become a bottleneck in the future?"]

**Reliability & Security Specialist:**
- Q1: [e.g., "What happens if this service stops responding?"]
- Q2: [e.g., "Where could this solution leak data?"]

**Human-Centric Designer:**
- Q1: [e.g., "Will the person understand why the AI made this decision?"]
- Q2: [e.g., "Is the system overloaded with too many steps?"]

### Output Limits
- Maximum findings per role: **[5–7]**
- Maximum recommendations per role: **[3–5]**
- Maximum open questions per role: **[2–3]**
- Total output: **[~150 lines]** — shorter is acceptable; brevity encouraged.

### Expected Discussion Rounds
- Simple task: **0 rounds** → jump from review directly to consensus check
- Medium task: **1 round**
- Complex task: **up to 2 rounds** + targeted resolution if needed

---

## Scenario-driven Role Assignment (Pre-Phase 0)

Per `draft/index.md` §Pre-Phase 0 — Role Analyzer: fixed Core roles are always active. Advisory Extended roles may be recommended by the AI role analyzer before Phase 1 starts.

### Analyzer Settings

- **analyzer_enabled:** `[true | false | auto]`
  - `auto` = use complexity classification (see below).
  - `true` = force launch even for simple tasks.
  - `false` = skip; Core-only roster is used regardless of complexity.

### Task Complexity Assessment

- [ ] D1: Files ≤ 3 → YES / NO
- [ ] D2: Lines ≤ 50 → YES / NO  
- [ ] D3: Directories ≤ 2 → YES / NO
- [ ] D4: Roles ≤ 3 → YES / NO

Classification: **Simple / Moderate / Complex** (see `draft/session-complexity-threshold.md`)

### Analyzer Artifacts

When analyzer is enabled, the session workspace must contain:

- **review-analyzer.json** — machine-readable output with schema `{core_locked, self_assessed_complexity, extended_roles[], timestamp, session_id}`.
- **review-analyzer.md** — human-readable justification for each recommended extended role (one block per role, max 5–7 lines per role).

Schema validation via `tools/check_all.py` (subcommand TBD per sess-council-role-selection action item №3).

### Meta-task Exemption

For meta-tasks (analyzing procedures, dogfood gate sessions, process improvement): set `analyzer_enabled: false` unless concrete protocol-level changes are under discussion.

### Extended Role List (from analyzer or manual)

If any Extended roles are activated, list them here (used in Phase 2 subagent launches):

- `[Extended role name]: [justification, copied from analyzer or operator decision]`
- ...

---

### Subject List
- `[SUBJ-ID]: [description]`
- `[SUBJ-ID]: [description]`

### Additional Context / Constraints
[Any relevant background not covered by the subject list.]
