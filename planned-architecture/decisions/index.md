# Decisions Index

Version: 0.2.0
Status: draft
Last Modified: 2026-11-08
Abstraction: reference
changelog-path: CHANGELOGS/planned-architecture.changes.md

Source: ../index.md (planned-architecture)

---

## Overview

Five binding architectural decisions from a multi-role consilium, accepted by consensus of three roles: Architect, Reliability & Security Specialist, Human-Centric Designer.

The standalone ADR document referenced by earlier versions is no longer part of the documentation set. The identifiers remain stable; their current definitions are:

| ID | Decision | Where applied |
|----|----------|---------------|
| ADR-001 | Structural assertions + property-based tests; no LLM in safety verification | `layer-0.md` |
| ADR-002 | Zero silent defaults; every parameter traceable in the session manifest | `layer-1.md` |
| ADR-003 | Deterministic error localization lookup; no LLM-generated messages | `layer-2.md` |
| ADR-004 | Hybrid checkpoint/resume (deferred to Phase 2+) | Execution Runtime specification |
| ADR-005 | Single-level schema migration chain | `layer-2.md` |

D3 (Documenter as a Supporting service) is recorded in `../index.md` and `../../documenter-service/index.md`.
