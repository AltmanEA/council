# Session Task Brief Template
Version: 0.1.0
Status: draft
Last Modified: 2026-11-04
Abstraction: reference
<!-- Changelog: CHANGELOGS/session-task-brief-template.changes.md -->

---

## Purpose

Fill this template **before** launching subagents. It ensures each role receives a focused task with clear expectations, preventing verbose or off-topic output.

Copy the template below into a new file (`session-task-brief.md`) and fill every `[...]` field. Pass the completed file as context to all three subagents in Phase 2.

---

## Task Brief

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

### Subject List
- `[SUBJ-ID]: [description]`
- `[SUBJ-ID]: [description]`

### Additional Context / Constraints
[Any relevant background not covered by the subject list.]
