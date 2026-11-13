# Epsilon Document
id: epsilon
title: Epsilon — Broken Test Document
Version: 0.1.0
Status: draft
changelog-path: CHANGELOGS/epsilon.changes.md

## Purpose

Stage D broken fixture: required frontmatter key `Abstraction` is missing.
Kept OUTSIDE the main corpus (it would break `gen_manifest.build_entries` for
every operation); tests copy it into the corpus temporarily to exercise the
`DocMetaError` refusal path.
