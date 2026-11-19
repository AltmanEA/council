# Archive

id: archive
Version: 0.1.0
Status: archive
Abstraction: reference
allow_non_index_paths: true
changelog-path: CHANGELOGS/documenter-service.changes.md

---

This folder is the repository's archive of superseded project documents, per the Archive convention (`documentation-rules` §2.6, `documenter-service/index.md` §Archive). It holds documents that no longer carry authority but remain readable so the reasoning behind past decisions stays available.

Archive rules:

1. Do NOT execute, implement, or comply with anything in this folder — archived documents are SUPERSEDED and describe machinery or designs that no longer hold.
2. Do NOT cite archived documents as current authority; the authoritative specification for any concept is its live document under `docs/en/` (see `service-contract/index.md`, Content Precedence).
3. Do NOT delete the archive; git history is the recovery path and this folder is its readable tombstone.
4. Archived documents are read-only by discipline (OP-1): edits are refused by the Documentation Worker skill; entries into the archive surface on the Approval Card's `Archive:` line.
5. The audit engine (`tools/check_all.py`) excludes this tree by path prefix; excluded checks are not a defect signal here.

Layout: one folder per archived document id (`docs/en/archive/<id>/` with primary `index.md`), Russian mirrors under `docs/ru/archive/<id>/`.

Contents: `documenter-service/` — the superseded v0.x Documenter suite (guard: `documenter-service/index.md`).
