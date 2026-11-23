# Consensus Document: Documentation Separation

## Session
sess-documentation-separation

## Date
2026-11-09

## Status
agreed

---

## Decision

Documentation is separated into two categories:

**1. Project documents** (moved to `docs/<id>/`, under Documenter control):
- project-concept, protocol-core, planned-architecture (5 files), service-contract, execution-runtime, operator-surface, scenario, project-reference, glossary, backlog

**2. Implementation files** (stay at root, excluded from Documenter control):
- AGENTS.md, fallback/, documenter-service/, .agents/skills/documentation/, .opencode/, CHANGELOGS/, defaults/, archive/, tests/, consensus-non-controlled-files.md, notes.md, docs-manifest.yaml

## Operator Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Target directory name | `docs/` | Brief, standard, natural contrast with `fallback/` at root |
| 2 | Oversized documents (205, 280, 206 lines) | Move as-is, split later as separate task | Minimize risk in first migration; split is independent content change |
| 3 | Frozen fallback cross-references | Exception permitted: update only `../` references to `../docs/` | Structural migration, not remediation/refactoring |
| 4 | consensus-non-controlled-files.md | Stay at root | It is an operational rule, not a project specification |

## Scope of Changes

### Manifest (docs-manifest.yaml)
- All document paths updated to `docs/<id>/index.md`
- Remove entries for: AGENTS.md, fallback-mode, documenter-service, documenter-configuration-guide, documenter-policy-reference
- Keep changelog-path references pointing to root CHANGELOGS/

### AGENTS.md
- §2.1 (On-Disk Layout): update all path examples to `docs/<id>/`
- §2.2 (AI View): clarify manifest tracks only `docs/` documents
- §2.5 (Changelog Storage): confirm CHANGELOGS/ at root
- §3.3 (Translation Workflow): update paths
- §4.1 (Glossary): update path
- §5.1 (Responsibility Split): update skill reference
- §5.2 (Document Processing Flow): update manifest path
- §7.1 (Naming): update path examples
- §7.2 (Metadata): no change
- §7.3 (Size Limits): no change
- §7.5 (Versioning): no change
- §7.6 (Changelog): confirm root location
- §8 (Compliance): update path scope

### SKILL.md (.agents/skills/documentation/SKILL.md)
- §Activation: replace inline path list with `docs/` directory pattern
- §Update a Document: update all path references to `docs/`
- §Audit Compliance: update path assumptions
- §Compliance Checklist: update manifest path
- §References: update paths

### Cross-references in fallback/
- `../protocol-core/index.md` → `../docs/protocol-core/index.md` (lines 12, 138, 144, 161, 167)
- `../planned-architecture/` → `../docs/planned-architecture/` (if present)
- `../glossary/index.md` → `../docs/glossary/index.md` (if present)
- `../project-concept/index.md` → `../docs/project-concept/index.md` (if present)
- `../service-contract/index.md` → `../docs/service-contract/index.md` (if present)
- `../protocol-core/index.md` in planned-architecture layer files
- `../documenter-service/index.md` references (documenter-service stays at root, keep as-is)
- `../defaults/policy.yaml` → keep as-is (defaults stays at root)

### File moves
- Create `docs/` directory
- Move each document folder under `docs/`
- Move RU translation files with their EN counterparts
- Keep all CHANGELOGS/ files at root (they're referenced by `changelog-path:` in headers)

---

## Version Bumps

| Document | Current | New | Type |
|----------|---------|-----|------|
| AGENTS.md | 0.8.1 | 0.9.0 | Major (foundational restructure) |
| docs-manifest.yaml | header only | header 0.10.0 + session info | Patch (structural update) |
| SKILL.md | 0.4.0 | 0.5.0 | Minor (scope change) |
| docs/project-concept/index.md | 0.3.1 | 0.3.2 | Patch (path only) |
| docs/protocol-core/index.md | 0.5.3 | 0.5.4 | Patch (path only) |
| docs/planned-architecture/index.md | 0.4.0 | 0.4.1 | Patch (path only) |
| docs/planned-architecture/layer-0.md | 0.2.0 | 0.2.1 | Patch (path only) |
| docs/planned-architecture/layer-1.md | 0.2.0 | 0.2.1 | Patch (path + ref) |
| docs/planned-architecture/layer-2.md | 0.4.0 | 0.4.1 | Patch (path + ref) |
| docs/planned-architecture/decisions/index.md | 0.3.0 | 0.3.1 | Patch (path only) |
| docs/service-contract/index.md | 0.1.6 | 0.1.7 | Patch (path only) |
| docs/execution-runtime/index.md | 0.3.2 | 0.3.3 | Patch (path only) |
| docs/operator-surface/index.md | 0.1.2 | 0.1.3 | Patch (path only) |
| docs/scenario/index.md | 0.1.0 | 0.1.1 | Patch (path only) |
| docs/project-reference/index.md | 0.3.1 | 0.3.2 | Patch (path only) |
| docs/glossary/index.md | 0.10.0 | 0.10.1 | Patch (path only) |
| docs/backlog/index.md | 0.1.0 | 0.1.1 | Patch (path only) |
| fallback/index.md | 0.4.0 | 0.5.0 | Minor (cross-ref updates — frozen exception) |

---

## Reservations

- **Reliability & Security:** No automated cross-reference migration tool exists yet. The 40+ references will be updated manually. Risk of a missed reference creating a silent broken link. Mitigation: mandatory grep validation step after move.
- **Human-Centric:** `docs/` name still carries ambiguity about what's inside. New operators may not immediately understand the distinction between `docs/` and `fallback/`. Mitigation: consider adding a brief README.md in `docs/` explaining the scope.
- **Operations:** Fallback cross-reference updates require explicit exception from the frozen rule. This is approved by the operator for this specific case only.
- **Architect:** Oversized documents (205, 280, 206 lines) will be moved without splitting, carrying compliance debt. Split is deferred to a future session as a separate task.

---

## Open Questions

None. All operator decisions received.

---

## Action Items

| # | Task | Owner | Depends On |
|---|------|-------|------------|
| 1 | Create `docs/` directory | Documentation Worker | approved |
| 2 | Move all document folders to `docs/` (with RU files) | Documentation Worker | 1 |
| 3 | Update docs-manifest.yaml (paths + remove operational entries) | Documentation Worker | 2 |
| 4 | Update AGENTS.md (§2.1, §2.2, §2.5, §3.3, §4.1, §5.1, §5.2, §7.1, §7.5, §7.6, §8) | Documentation Worker | 3 |
| 5 | Update SKILL.md §Activation and all path references | Documentation Worker | 3 |
| 6 | Update fallback/ cross-references (exception to frozen rule) | Documentation Worker | 3 |
| 7 | Update cross-references in all moved documents (relative `../` → `../docs/` where applicable) | Documentation Worker | 2 |
| 8 | Append changelog entries to all affected documents | Documentation Worker | 3 |
| 9 | Post-migration validation: `grep -rn '../docs/' docs/` and `grep -rn '\.\.\/' --include='*.md' .` (excluding .git, .opencode) | Primary agent | 3 |

---

*Consensus reached on 2026-11-09. All four roles (Architect, Reliability & Security Specialist, Human-Centric Designer, Operations Engineer) agreed with operator decisions. Ready for operator approval and documentation update execution.*
