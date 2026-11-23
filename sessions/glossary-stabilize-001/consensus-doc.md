# Consensus Document: Glossary Stabilization

## Decision
The glossary is **not yet promoted** to `active` status. Three `concerns` from all roles have been consolidated into actionable corrections. The operator should apply these corrections (mostly mechanical) and re-evaluate for `active` promotion once completed.

## Rationale
- **Consensus on concerns**: All three roles agree the glossary is substantially correct but has issues preventing `active` status.
- **No disagreements**: No roles took opposing stances on any subject.
- **No blocks**: No `blocked-in-scope` or `blocked-escalation` declarations.
- **Most urgent**: The Assessment Criteria section leaked into the artifact and must be removed (Architect, critical).

## Subjects with Outcomes

| Subject | Status | Notes |
|---------|--------|-------|
| SUBJ-001: Status transition from draft to active | Conditionally Agreed | Not yet — requires corrections first (see below) |
| SUBJ-002: Structural integrity and cross-references | Conditionally Agreed | Missing cross-references, overloaded Technical Concepts |
| SUBJ-003: Term completeness and accuracy | Conditionally Agreed | Severity tiers need differentiation; line limit exceeded |

## Conflicts & Disagreements
— None —

## Reservations

**Architect (concerns):**
- Assessment Criteria section must be purged (critical)
- Implementation-specific terms (Operational, Dormant) belong outside protocol glossary (high)
- Auxiliary Agent vs Subagent boundary needs clarification (medium)
- `Escalation Reason` entry is circular — delete or rewrite (low)

**Reliability & Security Specialist (concerns):**
- Severity tiers lack differentiating criteria between medium/high/critical (medium)
- Risk Threshold Breach must explicitly tie to Severity enum (medium)

**Human-Centric Designer (concerns):**
- Technical Concepts mixes implementation details with protocol concepts (high)
- Missing cross-references between related terms (medium)
- 201 lines exceeds 200-line convention (medium)
- Missing quick-reference appendix (low)

## Open Questions
1. Should the glossary be scope-limited to protocol-core concepts only, or is it intended as a project-wide glossary? (Architect)
2. Is "Primary agent" a permanent framework role or a temporary fallback-mode concept? (Human-Centric Designer)
3. Is the Severity tier differentiation gap acceptable as a known limitation since Protocol-Core provides full semantics? (Reliability & Security Specialist)

## Action Items
1. **Remove `## Assessment Criteria` section entirely** (Architect, critical)
2. **Add severity tier differentiators** — one line each for low, medium, high, critical (Reliability & Security, high priority)
3. **Clarify Risk Threshold Breach** to explicitly tie to Severity = critical (Reliability & Security)
4. **Fix formatting** of "Session working file" and "Session artifact" entries to match `**Term** definition.` pattern (Architect)
5. **Delete or rewrite `Escalation Reason`** entry — either reference the three enumerated reasons or remove (Architect)
6. **Separate Documenter-internal terms** from core framework terms into a distinct "Tooling & Services" subsection, clearly marked as developer-facing (Human-Centric Designer)
7. **Add cross-references** between related terms using markdown anchor links (Human-Centric Designer)
8. **Replace implementation-specific language** in definitions with protocol-level descriptions (Human-Centric Designer)
9. **Consider adding a quick-reference table** for core protocol values (phases, stances, severities, role tiers) (Human-Centric Designer)
10. **Address line limit**: either streamline the above or prepare for a future split (Human-Centric Designer, medium)

## Escalation References
— None —

## Downgraded Critical Findings
— None —
