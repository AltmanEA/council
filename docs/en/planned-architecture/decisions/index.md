# Decisions Index

Version: 0.4.0
Status: draft
Last Modified: 2026-11-12
Abstraction: reference
changelog-path: CHANGELOGS/planned-architecture.changes.md

Source: ../index.md (planned-architecture)

---

## Overview

This is the central registry of binding architectural decisions. ADR identifiers are assigned here and nowhere else; any document introducing a new decision MUST first register it in this table (the identifiers are globally unique across the project).

ADR-001–005 originate from a multi-role consilium, accepted by consensus of three roles: Architect, Reliability & Security Specialist, Human-Centric Designer. The standalone ADR document referenced by earlier versions is no longer part of the documentation set.

ADR-006–009 originate from `sess-documenter-contract` (2026-11-12); their normative content lives in `../../documenter-service/mvp-contract.md` §5.

| ID | Decision | Where applied |
|----|----------|---------------|
| ADR-001 | Structural assertions + property-based tests; no LLM in safety verification | `layer-0.md` |
| ADR-002 | Zero silent defaults; every parameter traceable in the session manifest | `layer-1.md` |
| ADR-003 | Deterministic error localization lookup; no LLM-generated messages | `layer-2.md` |
| ADR-004 | Hybrid checkpoint/resume (deferred to Phase 2+) | Execution Runtime specification |
| ADR-005 | Schema migration chain — deferred until after MVP | `layer-2.md` |
| ADR-006 | Documenter MVP stack: Python 3.11+, stdlib-only, `fcntl` advisory lock | `documenter-service/mvp-contract.md` |
| ADR-007 | Documenter MVP threat model: no writes, git rollback, no crypto primitives | `documenter-service/mvp-contract.md` |
| ADR-008 | `documenter/` state directory is git-tracked; service never commits | `documenter-service/mvp-contract.md`, `mvp-data-models.md` |
| ADR-009 | Documenter MVP architecture: Ports & Adapters, pure core, five ports | `documenter-service/mvp-contract.md` |

D3 (Documenter as a Supporting service) is recorded in `../index.md` and `../../documenter-service/index.md`.
