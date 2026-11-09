# Consensus Document: Documenter Scope Boundary — Non-Manifest Files

Session: sess-documenter-scope-boundary
Date: 2026-11-09
Status: agreed

---

## Decision

Documenter operates **exclusively** on manifest-tracked documentation artifacts and its own operational state (`documenter/` directory). All files outside these two namespaces — session workspace files (`sessions/<id>/`), archive outputs, and any other non-manifest artifacts — are explicitly excluded from Documenter's scope by design.

Two distinct terms replace the rejected "non-controlled files" terminology:

- **Session working files** — transient, system-managed, invisible to operator (temp).
- **Session artifacts** — persistent, git-tracked, visible in secondary pane (archive).

Cleanup of session workspace files is the operator's responsibility. No automatic cleanup is specified at MVP. Retained sessions are moved to `archive/sessions/<session-id>/` when no longer actively referenced.

## Rationale

**Architect** — A hard boundary prevents scope creep. Documenter's interfaces (`audit()`, `delegate()`) accept only `target_id` from the manifest; extending scope would require new interface parameters, new trust tiers, and new safety protocols. Separation of concerns: the session workspace is owned by the orchestration layer, not by a documentation quality service.

**Reliability & Security** — Extending Documenter into session workspace would require its safety protocol (rename, intent records, advisory locks) to leak into a shared session namespace, creating lock-ordering conflicts and potential corruption vectors. Keeping Documenter out of `sessions/<id>/` avoids cross-system atomicity problems and ensures crash-recovery remains bounded within Documenter's own state.

**Human-Centric** — Introducing a four-category file model (manifest-tracked, operational, session working, session artifacts) would create cognitive overload for operators already managing task briefs, reviews, and consensus docs. Two categories (manifest-tracked vs. not) plus the explicit operational exception is clear and actionable.

**Operations** — There is no direct conflict with Documenter's existing locks or intent mechanism because session workspace and Documenter state occupy separate namespaces. However, the boundary must be explicitly documented to prevent future engineers from assuming Documenter should "clean up after sessions" or "audit session files."

## Reservations

None. All four roles converged on the same boundary, terminology, and cleanup approach. No role registered concerns or blocked consensus.

## Changes Required

| # | File | Change | Version Bump |
|---|------|--------|-------------|
| A | `documenter-service/index.md` | Add scope boundary statement (§Purpose or §Architecture Position) | 0.16.0-draft → 0.17.0-draft (minor: structural addition) |
| B | `documenter-service/index.md` | Add intent record constraint to Safety Protocol #9b (entries must reference only manifest-tracked paths) | (included in A) |
| C | `documenter-service/configuration-guide.md` | Ensure `documenter/hashes.json`, `documenter/intent/`, `documenter/audits.json` are annotated with `operational: true` in manifest | 0.11.0-draft → 0.12.0-draft (patch: clarification only) |
| D | `fallback/index.md` | Add session workspace lifecycle section under §Session workspace convention (cleanup responsibility, retention, archive) | 0.3.0 → 0.4.0 (minor: content addition) |
| E | `glossary/index.md` | Add terms: "Session working file" and "Session artifact" in the Artifacts section | 0.9.0 → 0.10.0 (minor: new terms) |
| F | `AGENTS.md` | Update §2.4 to note that fallback session files are outside Documenter's scope | 0.8.0 → 0.8.1 (patch: clarification) |
| G | All above + `docs-manifest.yaml` | Append changelog entries; bump versions per §7.5 | Per document |

### Text to insert

**Change A** — insert at end of §Purpose paragraph in `documenter-service/index.md`:

```
Scope boundary: Documenter operates exclusively on manifest-tracked documentation artifacts and its own operational state (`documenter/` directory). Files outside these namespaces — session workspace files (`sessions/<id>/`), archive outputs, and any other non-manifest artifacts — are explicitly excluded from Documenter's scope. The `audit()` and `delegate()` interfaces accept only `target_id` values from the manifest; any invocation referencing non-manifest files is rejected with `error_category: unknown`.
```

**Change B** — insert at end of §Safety Protocol #9b in `documenter-service/index.md`:

```
Intent record entries MUST reference only manifest-tracked file paths. Any attempt to stage a non-manifest path during a changeset causes `delegate()` to reject with `error_category: unknown` and no writes proceed.
```

**Change D** — insert as a new paragraph under §Session workspace convention in `fallback/index.md` (after the existing "Exemption from runtime contract" paragraph):

```
**Session workspace lifecycle.** Per-session workspace files (task-brief.md, review-*.md, consensus-doc.md, discussion-round-N.md) are created and maintained by the operator/orchestration layer and are outside the scope of Documenter. Cleanup responsibility belongs to the operator: after a session concludes, the operator determines which files to retain (e.g., archived consensus docs) and which to delete. No automatic cleanup is specified at MVP.

Retained session directories should be moved to `archive/sessions/<session-id>/` when no longer actively referenced. If a session directory contains files but no `consensus-doc.md` (indicating an incomplete or abandoned session), the operator may remove the directory at any time.
```

**Change E** — insert into glossary §Artifacts section (after "Escalation record"):

```
**Session working file** (Рабочий файл сессии) — A transient file created during a council session for intermediate use (e.g., discussion drafts, temporary notes). Not committed to git, not managed by Documenter. Lifecycle is tied to the session; cleanup is the operator's responsibility.

**Session artifact** (Артефакт сессии) — A persistent output from a council session (e.g., review files, consensus documents, discussion transcripts). Committed to git for audit trail. Not managed by Documenter (outside manifest scope). Visible to the operator for review but not actionable through the Documenter audit/approval flow.
```

**Change F** — append to end of §2.4 in `AGENTS.md`:

```
Session workspace files produced during fallback-mode sessions (task-brief, reviews, consensus docs, discussion transcripts) reside in `sessions/<id>/` and are outside the scope of Documenter; cleanup and archival are the operator's responsibility (see `fallback/index.md`, §Session workspace convention).
```

## Open Questions

None. All roles confirmed that session workspace lifecycle is fully operator-managed at MVP and that Documenter's own operational state is a clearly bounded exception.

## Action Items

| Item | Owner | Target |
|------|-------|--------|
| Apply Change A (scope boundary in documenter-service/index.md) | Documentation Worker skill | Operator approval |
| Apply Change B (intent record constraint in documenter-service/index.md) | Documentation Worker skill | (included with A) |
| Apply Change C (manifest operational annotation for config-guide) | Documentation Worker skill + manifest update | Operator approval |
| Apply Change D (session workspace lifecycle in fallback/index.md) | Documentation Worker skill | Operator approval |
| Apply Change E (new terms in glossary/index.md) | Documentation Worker skill | Operator approval |
| Apply Change F (fallback scope note in AGENTS.md §2.4) | Documentation Worker skill | Operator approval |
| Append changelog entries for all modified documents | Documentation Worker skill | Operator approval |
| Update `docs-manifest.yaml` versions and changelog headers | Manual (primary agent) | Operator approval |

---

*Consensus reached on 2026-11-09. All four roles (Architect, Reliability & Security Specialist, Human-Centric Designer, Operations Engineer) agreed. Ready for operator approval and documentation update execution.*
