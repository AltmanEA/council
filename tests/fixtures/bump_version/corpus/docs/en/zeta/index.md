# Zeta Document
id: zeta
title: Zeta — Broken Version Test Document
Version: 1.2.3.4
Status: draft
Abstraction: reference
changelog-path: CHANGELOGS/zeta.changes.md

## Purpose

Stage D broken fixture: malformed `Version` (four components, rejected by
`docmeta._VERSION_RE`). Lives in the main corpus because
`gen_manifest.build_entries` does not validate version format; bumping THIS
id must be refused by the `version-format` high finding in `docmeta.validate`.
