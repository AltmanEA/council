# Session Consolidation Prompt

---

## Purpose

After Phase 3 (Discussion Round), collect all final role outputs and produce one consolidated analysis report that serves as input for Phase 4 (Consensus Check) and Phase 5 (Resolution Formation). This prompt gives you, the moderator, a step-by-step method to merge results without duplicating effort or missing conflicts.

**Constraint:** You are reading output from exactly three roles (Architect, R&S Specialist, Human-Centric Designer). Each output is a markdown document following the standard Role Review structure. Produce a single output document under 300 lines total.

---

## Step 1 — Normalize Each Output

For each role's review, extract the following into a flat table row:

| Subject ID | Severity | Stance | Key Finding (≤2 lines) | From Role |
|------------|----------|--------|------------------------|-----------|

Rules:
- One row per unique subject-reference in a finding.
- If a finding has no subject reference, give it a placeholder `[NO-SUBJ]`.
- For stance: map to `support` / `oppose` / `null` (null if the finding is neutral observation).
- Condense the finding text to ≤2 lines; drop examples and elaborations.

You should now have a normalized matrix of roughly N rows × 6 columns.

---

## Step 2 — Deduplicate Findings

Group rows by `Subject ID` (or by semantic similarity if no IDs exist):

### Identical findings
Two findings are identical if they describe the same observation about the same subject, even with different wording. **Rule:** keep only the row with highest severity. Note which other roles converged on the same point.

### Conflicting findings
Two findings conflict if:
- Same subject, opposite stances (`support` vs `oppose`)
- Same subject, both oppose but recommend different actions with equal severity

**Action:** Flag as DISAGREEMENT. Create a separate section listing conflicting pairs with both positions and their severities.

### Converging medium → high
If one role raises `medium` and another independently raises `medium` on the same aspect, note that combined weight may justify promoting to `high`. Mark as `HEURISTIC: promotion candidate`. Do NOT automatically upgrade — record it and let the operator decide in Phase 4.

### Neutral overlap
Different roles citing different aspects of the same problem: keep all as independent rows, no conflict.

---

## Step 3 — Identify Consensus Patterns

Answer these four questions:

1. **All agree?** Did every role declare status `agree`? → YES → proceed to Phase 5 (resolved).
2. **Partial concerns?** Any `concerns` statuses but NO `blocked-*`? → YES → conditionally resolved, list reservations.
3. **Any blocked?** At least one `blocked-in-scope` or `blocked-escalation`? → Record escalation details.
4. **Disagreements detected?** Opposing stances on any subject? → List them explicitly. If structured data alone cannot determine agreement between two roles on a subject, escalate as `information gap`.

Write your answers concisely: one sentence each.

---

## Step 4 — Draft the Consensus Document

Structure:

```markdown
# Consensus Document

## Decision
[One sentence: what was decided.]

## Rationale
[Bullet summary of key argument. Max 5 bullets. Include convergent findings (from multiple roles) first, then isolated observations.]

## Subjects with Outcomes
[Table: Subject | Status (Agreed / Conditionally Agreed / Blocked) | Notes]

## Conflicts & Disagreements
[List each conflict found in Step 2. Format: "SUBJ-XXX: Architect said X, Security said Y. Both severity MEDIUM."]

## Reservations
[Grouped by role. Each reservation ties to a specific subject.]

## Open Questions
[From all roles' open questions, deduplicated.]

## Action Items
[Derived from recommendations across all roles. Each item: action + responsible role hint + priority.]

## Escalation References
[If any blocked-in-scope escalated to blocked-escalation, explain why and what the escalation reason is.]

## Downgraded Critical Findings
[Transparency log: which critical findings were downgraded due to invalid justification, raised by which role.]
```

---

## Step 5 — Self-Check Before Finalizing

Before writing the final version, verify:

- [ ] Every row in the normalized matrix appears in either main body, conflicts, or downgrades section
- [ ] No finding exists twice (deduplication complete)
- [ ] Conflicting pairs are labeled explicitly
- [ ] All role statuses are reflected in the final answer to Step 3
- [ ] The document is under 300 lines (condense where needed — combine open questions, trim rationale bullets, remove empty sections entirely)
- [ ] Subject references use stable identifiers (no free-text descriptions in place of IDs)

---

## Anti-Patterns to Avoid

- **Don't** repeat full role review text in the output. Summarize, don't transcribe.
- **Don't** make judgment calls about merit of findings. Record what each role stated; flag disagreements but don't resolve them yourself (that's the operator's job in Phase 4).
- **Don't** invent subjects that no role mentioned. Only include subjects from the task's canonical list.
- **Don't** exceed 300 lines. Brevity is mandatory. If something doesn't fit, it belongs in an appendix referenced at the bottom of the document.
- **Don't** skip empty sections. Write `— None —` instead of omitting them entirely. Empty sections must remain visible so the operator knows they were considered.

---

*Aligned with fallback/index.md Phase 4–5 workflow.*
