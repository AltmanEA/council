# Layer 2 — Integration & Orchestration

Version: 0.1.0
Status: draft
Last Modified: 2026-11-07
Abstraction: protocol
changelog-path: CHANGELOGS/planned-architecture.changes.md

Source: ../index.md (planned-architecture)

---

## Purpose

All external-facing interfaces between human operators and the internal layers. Transport agnostic — MCP stdio, CLI, future OpenCode skill, REST API if demanded externally by third-party consumers.

## Structured Input Validation

Pydantic models at ingress gate validating before any data reaches Layer 0. Complementary, not substitutive of Layer 0 checks.

### Schema versioning (ADR-005)

External mapper file `schema_versions.json` handles backward compatibility with single-level migration chain. Each migration step transforms old → next version only (no multi-hop direct mappings). Sequential application. Adding/removing migrations requires PR through codified gate. Python model versions are self-contained; mapper only orchestrates transitions.

Validation rules enforced:
- `ConfigDict(extra="forbid")` — unknown fields rejected, not silently absorbed
- Deep-nesting protection (~32 levels max) to prevent pathological input crashes
- Graceful degradation — any validation error produces structured operator-friendly response, never stack trace leaked

## Quick-Review Path

Automatic SIMPLE/COMPLEX classification by task metadata. Simplification reduces operational parameters only, never protocol rules.

### Allowed simplifications

| Parameter | Full path | Simple path |
|-----------|-----------|-------------|
| max_discussion_rounds | up to 2 | 0 |
| Extended-tier roles | per justification | disabled unless task explicitly justifies |
| Discussion round count | configurable | auto-determined by complexity classifier |

### Invariant checklist (ADR-001)

Before any simplification applies, auto-verified that all critical invariants remain intact:
- All Core-tier roles active
- Consensus rules unchanged
- Escalation paths intact
- Justification format validation enforced
- Subject admission criteria unchanged
- Severity threshold rules unchanged

If any assertion fails, simplification is blocked and full-path defaults apply.

### Upgradable classification

After Phase 2 (Individual Review), if any finding warrants upgraded treatment (e.g., critical finding from a "simple" classified task), session automatically upgrades to full-path discussion rounds without operator intervention. Reason recorded in session log.

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

Operator-configurable verbosity level: minimal (highly summarized), balanced (default), full (actionable technical details included).

Codified gate enforcement: every new error code requires PR adding both code entry and localization entry simultaneously. CI check fails if new code exists without corresponding localization.

## Typer CLI (deferred to Phase 2)

Local-first scriptable interface. One of multiple transport adapters sharing same underlying library functions as MCP tools.

- Tab-completion, auto-generated help
- `--no-color` flag (also responds to NO_COLOR env var)
- `--output json/yaml` mode for programmatic consumption
- stdout/stderr separation: structured result on stdout, progress/warnings/errors on stderr
- Argument sanitization pass-through after Pydantic validation

## Checkpoint / Resume (deferred to Phase 2+, ADR-004)

Hybrid checkpoint strategy:
- Intra-phase recovery via LangGraph native checkpoint (mid-phase crash restart without re-invoking providers)
- Inter-phase checkpoints as custom JSON snapshots at phase boundaries containing only protocol state fields (phase number, active roles, cumulative findings, status declarations). No raw model outputs. Atomic rename, sorted keys, version check on restore.
- Ordering guarantee: inter-phase checkpoint written ONLY AFTER all graph nodes confirm successful completion of current phase.

Evaluate LangGraph-native checkpoint capability first at Phase 2 before building custom layer.
