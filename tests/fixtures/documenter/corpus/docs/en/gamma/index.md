# Gamma Document
id: gamma
Version: 0.2.0
Status: draft
Abstraction: conceptual
changelog-path: CHANGELOGS/gamma.changes.md
Last Modified: 2026-11-01

## Purpose

Fixture document carrying the deprecated `Last Modified` frontmatter key:
docmeta reports it as an internal `warning`, which the audit() boundary maps
to `medium` (legacy mapping, mvp-interfaces §1). Body text carries the
redaction marker UNIQUE-CORPUS-MARKER-PHRASE-zq7xk9 that must never surface
in an event payload or an audit description.
