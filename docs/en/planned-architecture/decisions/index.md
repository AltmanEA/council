# Decisions Index

id: planned-architecture-decisions
Version: 0.9.0
Status: draft
Abstraction: reference
changelog-path: CHANGELOGS/planned-architecture.changes.md

Source: ../index.md (planned-architecture)

---

## Overview

This is the central registry of binding architectural decisions. ADR identifiers are assigned here and nowhere else; any document introducing a new decision MUST first register it in this table (the identifiers are globally unique across the project).

ADR-001–005 originate from a multi-role consilium, accepted by consensus of three roles: Architect, Reliability & Security Specialist, Human-Centric Designer. The standalone ADR document referenced by earlier versions is no longer part of the documentation set.

ADR-006–009 originate from `sess-documenter-contract` (2026-11-12); their normative content lives in `../../documenter-service/mvp-contract.md` §5. ADR-010 originates from `sess-doc-reliability-algo` (2026-11-12); its normative content lives in `documenter-service/configuration-guide.md` §Hash Store. ADR-011 originates from `sess-doc-reliability-algo` (2026-11-12), operator decision; its normative context lives in `AGENTS.md` §1.5. ADR-012 originates from `sess-translate-automation` (2026-11-14), operator decisions; its normative content lives in `AGENTS.md` §3.3 and the Documentation Worker skill. ADR-013 originates from the prose-synchronization session of 2026-11-14 (operator decisions C-1/E2); it amends ADR-007; its normative content lives in `AGENTS.md` §1.5/§1.7 and `documenter-service/mvp-contract.md` §4. ADR-014 originates from `sess-translation-extraction` (2026-11-15), operator decisions; its normative content lives in `AGENTS.md` §1.6–§1.7 and `docs/en/translation-project/`.

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
| ADR-010 | `documenter/hashes.json` as rebuildable cache; git history as primary audit trail; `tools/` exempt from hash-store updates | `documenter-service/configuration-guide.md` |
| ADR-011 | Start of Documenter MVP (Tier 0–1) and tools/ implementation; fallback remains session mode | `AGENTS.md` §1.5 |
| ADR-012 | Post-Approve automatic RU synchronization: conditional lift of §3.3 suspension; write only via Documentation Worker after Phase 4 write-gates; per-document opt-out; per-run cloud consent | `AGENTS.md` §3.3, `/.agents/skills/documentation/SKILL.md` |
| ADR-013 | Documenter Tier 2+ dual interlock (amends ADR-007): write branch implemented but dormant behind a policy gate; ADR-007 "no writes" holds for the registered surface (MCP unregistered); Tier 2+ not activatable until the Operator Surface exists as code providing authenticated ingress — the specification alone is not sufficient; editing `documenter_policy.yml` is an activation act reserved to the operator out-of-session | `AGENTS.md` §1.5/§1.7, `documenter-service/mvp-contract.md` §4 |
| ADR-014 | External Translation Project boundary: the EN→RU translation engine lives in the standalone repository techdoc-translator (CLI contract v1, exit-code API, .env configuration); Council retains only the adapter path (Documentation Worker skill), the verification layer (`check_drift.py`, metadata fingerprint), write authority (Documentation Worker only), RU documents and provenance artifacts; dependency direction is one-way (Council pins the engine via `defaults/translation.lock`); the engine project knows nothing about Council; Documenter integration deferred | `AGENTS.md` §1.6–§1.7, `docs/en/translation-project/`, `/.agents/skills/documentation/SKILL.md` |

D3 (Documenter as a Supporting service) is recorded in `../index.md` and `../../documenter-service/index.md`.
