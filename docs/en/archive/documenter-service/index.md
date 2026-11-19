# Documenter Legacy Archive (SUPERSEDED)

id: documenter-service-legacy
Version: 0.1.0
Status: archive
Abstraction: reference
allow_non_index_paths: true
changelog-path: CHANGELOGS/documenter-service.changes.md

---

This folder archives the abandoned Documenter design (superseded 2026-11-19 by consensus `sess-documenter-concept-revision`). The operator principles OP-1 (instant operator approval, no gating), OP-2 (maximum simplicity), OP-3 (commit audit plus revert as primary error control) abolished the tiered trust model, the policy engine, the dual interlock, the approval surface, and the consent tooling these documents specify.

Archive rules:

1. Do NOT execute, implement, or comply with anything in this folder — every document here is marked SUPERSEDED and describes machinery that no longer exists.
2. Do NOT cite these documents as current authority; the authoritative specification is `docs/en/documenter-service/index.md`.
3. Do NOT delete the archive; git history is the recovery path and this folder is its readable tombstone.

Contents: `spec-v0.md` (former primary spec, with its RU mirror `docs/ru/archive/documenter-service/spec-v0-RU.md`), `mvp-contract.md`, `mvp-interfaces.md`, `mvp-data-models.md`, `policy-reference.md`, `approval-surface.md`, `configuration-guide.md`. What was abandoned and why is summarized in the migration section of the authoritative index.
