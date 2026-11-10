# Changelog — ru-restructure

## v0.1.0 (2026-11-10)

<!-- CHANGES v0.1.0: RU files restructure — migrated all 14 Russian translation files from co-located `docs/<id>/index-RU.md` to mirrored `docs/ru/<id>/index-RU.md` structure. English originals moved to `docs/en/<id>/index.md`. Manifest `has_translation` changed from bare filename to full relative path. Added `docs/ru/index.md` cross-reference TOC. Updated AGENTS.md §2.1, §2.2, §3.2, §3.3, §4.1, §7.1. Updated SKILL.md path resolution to use manifest for RU file location. Schema change documented in manifest header comment (v0.2). Based on ru-restructure consensus (sess-ru-restructure). -->

- Migrated 14 RU files: `docs/<id>/index-RU.md` → `docs/ru/<id>/index-RU.md`
- Moved EN originals: `docs/<id>/index.md` → `docs/en/<id>/index.md`
- Preserved nested structure: `planned-architecture/decisions/` mirrored
- Updated manifest: all `path` values from `docs/` → `docs/en/`; all `has_translation` from bare filename → `docs/ru/<id>/...`
- Added manifest header comment documenting schema change v0.2
- Version bumps: all documents +1 patch
- Created `docs/ru/index.md` as human-facing TOC
- Updated AGENTS.md: §2.1 (layout), §2.2 (manifest paths), §3.2/§3.3 (RU paths), §4.1 (glossary path), §7.1 (naming)
- Updated SKILL.md: all file path references updated, RU resolution now manifest-driven
