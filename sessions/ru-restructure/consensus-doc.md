# Consensus Document — RU Files Restructure

**Session ID:** ru-restructure  
**Date:** 2026-11-10  
**Roles:** Architect (concerns, narrowed), Reliability & Security Specialist (concerns), Human-Centric Designer (concerns, shifted from agree)

---

## Decision Taken

**Adopt the mirrored dual-layout restructure.** English originals move to `docs/en/`, Russian translations to `docs/ru/`, preserving the identical folder hierarchy in both trees. The `decisions/` subdirectory under `planned-architecture/` is mirrored in full (not flattened).

This resolves the original proposal's flat `docs/ru/` approach in favor of a structural mirror that serves both AI navigation (clean English-only tree) and human navigation (clean Russian-only tree, predictable path mapping).

---

## Subjects

### SUBJ-001: File movement — 14 RU files from `docs/<folder>/` to `docs/ru/<folder>/`

- **Outcome:** **Agreed.** All three roles converge on mirrored structure. Flat `docs/ru/` rejected by all roles due to loss of path predictability and nested-subdirectory handling issues.
- **Path mapping:** Every `docs/<id>/index-RU.md` → `docs/ru/<id>/index-RU.md`. Every nested `docs/<id>/<file>-RU.md` → `docs/ru/<id>/<file>-RU.md`.
- **Reserved by:** Reliability & Security Specialist (pre-migration safety procedure not yet finalized).
- **Reserved by:** Architect (execution plan gap: migration order not yet defined).

### SUBJ-002: Manifest change — `has_translation` field semantics

- **Outcome:** **Agreed in principle, details to finalize.** All roles accept that `has_translation` will encode a path-like reference instead of filename-only. No new manifest field is required — the existing field value format changes from `index-RU.md` to `ru/<id>/index-RU.md` (or equivalent relative path).
- **Schema change documentation:** Mandatory. Must be recorded in manifest changelog with rationale.
- **External tooling risk:** No known consumers exist today, but the schema change must be documented to prevent future breakage. Escalated as documented risk, not blocker.
- **Reserved by:** Reliability & Security Specialist (bijective cardinality verification not yet in migration plan).

### SUBJ-003: Translation workflow impact (AGENTS.md §3.3)

- **Outcome:** **Conditionally agreed.** The workflow must be updated in parallel with the restructure. The "locate corresponding RU in same folder" pattern must be replaced by "look up `has_translation` path from manifest." This is a change to the Documentation Worker skill behavior.
- **Impact:** RU files become a manifest-dependent resource rather than filesystem-proximity resource. This is acceptable given the translation workflow is already suspended for this phase (AGENTS.md §3.3 phase exception).
- **Action required:** Update Documentation Worker skill to resolve RU paths via manifest instead of filesystem co-location.

---

## Role Reservations

| Role | Reservation | Blocks proceed? |
|------|-------------|-----------------|
| Architect | Migration order not specified; manifest schema convention not documented; AGENTS.md §3.3 update not planned | No — narrow concerns, moveable to agree if resolved in next round |
| Reliability & Security | Pre-migration snapshot not fully specified (needs tree dump + checksums + manifest dump); bijective verification missing; directory structure audit missing | No — four conditions listed, all actionable |
| HCD | Manifest encoding for mirrored paths unclear; need to verify IDE/filter config compatibility | No — low operational impact |

---

## Open Questions

1. **Migration order:** Should files be moved before or after the manifest is updated? Architect proposed manifest-first (snapshot first, move, then update manifest). Reliability Specialist disagrees — proposed snapshot → move → update manifest → verify. **Recommendation:** snapshot first, move files, update manifest, verify all four checks (file exists, checksum matches, manifest path resolves, bijective cardinality).
2. **Manifest field format:** `has_translation: ru/<id>/index-RU.md` (relative from manifest location) or absolute path? **Recommendation:** relative path from manifest file location (`docs-en/ru/<id>/...` — or just `ru/<id>/...` if manifest stays at repo root).
3. **TOC for `docs/ru/`**: Should `docs/ru/index.md` be created as a cross-reference index? **All roles agree: yes, but as supplementary, not primary navigation.**

---

## Action Items

1. **Update manifest:** Change all 14 `has_translation` values to relative paths under `ru/` prefix.
2. **Move files:** Execute file moves preserving directory structure mirror.
3. **Create `docs/ru/index.md`:** Lightweight TOC mapping each RU file to its English original.
4. **Update AGENTS.md §3.3:** Reflect the new translation workflow (manifest-based path lookup).
5. **Update Documentation Worker skill:** Path resolution now uses manifest, not filesystem co-location.
6. **Create `CHANGELOGS/ru-restructure.changes.md`:** Document the restructure decision and rationale.
7. **Pre-migration snapshot:** Create `archive/ru-restructure-snapshot/` with full checksums before execution.

---

## Consensus Status

**Conditionally resolved.** All three roles converge on the mirrored dual-layout approach. Remaining reservations are execution-level (not architectural) and can be resolved before final execution. The operator should approve the action items and provide go-ahead for Phase 5 (execution) after reviewing the reservations above.

**Next step:** Operator review of reservations → go/no-go on execution → Phase 5 implementation.

---

## Critical Findings (Downgraded)

None — all critical-severity findings from individual reviews were either addressed through discussion or downgraded to medium after mitigation analysis.
