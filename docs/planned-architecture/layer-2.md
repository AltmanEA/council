# Layer 2 — External Interfaces / Adapters

Version: 0.4.1
Status: draft
Last Modified: 2026-11-09
Abstraction: protocol
changelog-path: CHANGELOGS/planned-architecture.changes.md

Source: ../index.md (planned-architecture)

---

## Purpose

All external-facing interfaces between human operators and the internal layers. Layer 2 translates external requests into Layer 1 calls; it contains no protocol logic and no LLM invocation. MVP ships one transport — MCP stdio. CLI and REST remain deferred adapters over the same library functions.

## Transport (MVP: MCP stdio)

The operator surface exposes a small set of MCP tools: submit a task, inspect session status, resolve an escalation, retrieve artifacts, and invoke Documenter (`audit`, `delegate`). Each tool validates its input, authenticates the caller, and calls Layer 1. No tool calls Layer 0 directly.

## Structured Input Validation

Pydantic models at ingress gate validating before any data reaches Layer 0. Complementary, not substitutive of Layer 0 checks.

### Schema versioning (ADR-005)

EXTERNAL MAPPER — RESERVED FOR FUTURE USE. The external mapper file `schema_versions.json` and its migration chain will NOT ship at MVP. This section exists solely to document what was decided: no migration capability at MVP; the `schema_version` field in Service Contract schemas exists for future additions only. When migration is later implemented, it will support single-level (old→next) transformation steps only, requiring PR approval for any changes.

Validation rules enforced:

- `ConfigDict(extra="forbid")` — unknown fields rejected, not silently absorbed
- Deep-nesting protection (~32 levels max) to prevent pathological input crashes
- Graceful degradation — any validation error produces structured operator-friendly response, never stack trace leaked

## Error Localization (ADR-003)

Deterministic lookup table mapping error codes to localized messages. No LLM generation. Dual-output error records: technical (raw debug context) + localized (operator-facing).

### Error code taxonomy

| Prefix | Domain | Examples |
|--------|--------|----------|
| VAL. | Validation failures | schema mismatch, missing required field |
| PROT. | Protocol violations | consensus computation error, phase transition failure |
| MODEL. | LLM provider issues | rate limit, auth failure, timeout |
| IO. | Filesystem/persistence | write failure, read corruption |
| CONFIG. | Configuration errors | missing API key, invalid scenario |
| AUTH. | Authentication/authorization failures | expired credential, invalid signature, unrecognized caller, revoked credential |

Operator-configurable verbosity level: minimal (highly summarized), balanced (default), full (actionable technical details included).

Codified gate enforcement: every new error code requires PR adding both code entry and localization entry simultaneously. CI check fails if new code exists without corresponding localization.

## Operator Surface

The operator surface is an adapter, not an orchestrator. It authenticates the caller, validates the request, and calls Layer 1. Operator verbs, identity classes, escalation delivery, and the `pre_check` gate are specified in the Operator Surface & Escalation specification. Escalation is stop-and-resume: the session is durable, and the operator resolves it in a later invocation.

## Typer CLI (deferred to Phase 2)

Local-first scriptable interface. One of multiple transport adapters sharing same underlying library functions as MCP tools.

- Tab-completion, auto-generated help
- `--no-color` flag (also responds to NO_COLOR env var)
- `--output json/yaml` mode for programmatic consumption
- stdout/stderr separation: structured result on stdout, progress/warnings/errors on stderr
- Argument sanitization pass-through after Pydantic validation

## Moved to Layer 1

The following are control-plane concerns and belong to Layer 1, not Layer 2:

- Scenario matching and loading (`ScenarioLoader`).
- Quick-review SIMPLE/COMPLEX classification (deferred; the upgrade hook is reserved in the phase state machine).
- Checkpoint/resume and session persistence.

## Supporting Services

Documenter is not a Layer 2 component. It is a Supporting service invoked through this layer's operator surface; LLM-backed writes use a Layer 1 execution port. Layer 2 never invokes an LLM on Documenter's behalf. Full specification: `../documenter-service/index.md`; placement: `../index.md`.

## Cross-References

- `../index.md` — layer model and dependency rules
- `layer-0.md` — protocol enforcement interface
- `layer-1.md` — execution runtime and Layer 1 execution ports
- `../documenter-service/index.md` — Documenter specification
