# Error Management & Policy

Version: 0.2.0
Status: draft
Last Modified: 2026-11-09
Abstraction: format
changelog-path: CHANGELOGS/service-contract.changes.md

Source: index.md (service-contract)

---

## Error Code Registry

| Code | Meaning | Operator action |
|------|---------|-----------------|
| `VAL.001` | Schema or unknown-field violation | Fix request |
| `VAL.002` | Unknown enum value | Fix request |
| `VAL.003` | Missing required field | Fix request |
| `VAL.004` | Trust floor mismatch | Retry at or above the derived floor |
| `VAL.005` | Audit token missing, stale, or out of scope | Re-run `audit()` |
| `PROT.001` | Missing Core role | Escalate |
| `PROT.002` | Invalid role status format | Escalate |
| `PROT.003` | Consensus rule violation | Escalate |
| `PROT.004` | Invalid phase transition | Retry; escalate if persistent |
| `PROT.005` | Blocking finding present | Resolve finding, re-audit |
| `PROT.006` | Operator approval timed out | Resume or cancel |
| `PROT.007` | Pre-check integrity gate failed | Block execution; run audit or request override |
| `MODEL.001` | Provider rate limit | Retry |
| `MODEL.002` | Provider authentication failure | Fix configuration |
| `MODEL.003` | Provider timeout | Retry |
| `IO.001` | Atomic write failed | Retry |
| `IO.002` | Manifest hash chain broken | Escalate |
| `IO.003` | Session lock held | Wait, then retry |
| `IO.004` | Delegated skill failure | Inspect trace, retry |
| `CONFIG.001` | Missing API key | Fix configuration |
| `CONFIG.002` | Invalid scenario or conflicting configuration | Fix configuration |
| `AUTH.001` | Expired credential | Fix request |
| `AUTH.002` | Invalid signature / tampered token | Fix credential |
| `AUTH.003` | Unrecognized caller class | Fix MCP or integration config |
| `AUTH.004` | Revoked credential | Re-authenticate |
| `PROT.GATE.001` | Pre-check or pre-audit gate failure requiring override | Record override via `documenter.override_gate(reason, operator_id)` and re-attempt |
| `PROT.008` | Pre-check integrity gate unavailable (Documenter unreachable) | Block transition; request `council.override_precheck` |
| `IO.999` | Unhandled exception during delegate() execution | Capture post-mortem trace (§Safety Protocol #8), escalate |

Documenter mapping: `hash_mismatch` → `IO.002`; `trust_mismatch` → `VAL.004`; `audit_mismatch` → `VAL.005`; `blocking_finding` → `PROT.005`; `skill_failure` → `IO.004`; `operator_timeout` → `PROT.006`; `gate_failure` → `PROT.GATE.001`; `unknown` → `IO.999`.

## Configuration Precedence

Highest to lowest: (1) explicit MCP request value; (2) scenario file; (3) `documenter_policy.yml` for Documenter operations; (4) `defaults/policy.yaml`; (5) built-in safe defaults. No external schema-mapper file is shipped at MVP — `schema_versions.json` mentioned in prior drafts is explicitly reserved but non-runtime per ADR-005 (§Schema Versioning). A conflict between scenario and policy on a safety parameter is `CONFIG.002`, never a silent winner.

## Schema Versioning

`schema_version` is reserved and fixed at `1` for MVP. Unknown versions are rejected with `VAL.001`. No migration chain ships at MVP; the field exists so a chain can be added without changing artifact identity. Any future migration MUST preserve the downgraded-critical transparency list. The file `schema_versions.json` referenced in prior drafts is **not shipped at MVP** — it is explicitly reserved (non-runtime) for a post-MVP migration decision per ADR-005. Producers MUST NOT emit events referencing it; consumers MUST ignore it if present.

## Critical Finding Validation Process

Validation follows a strict three-phase pipeline. Each phase operates on the original text and its outputs feed into the next:

1. **Schema Acceptance.** The artifact structure is validated against the JSON schema only (required fields present, correct types, known field names). The `justification` field is NOT required at this stage regardless of severity; a missing justification does not block submission (`VAL.003` is not emitted for missing `justification`). An invalid schema blocks submission entirely (`VAL.001`).
2. **Protocol Downgrade.** If the finding has `severity = critical`, the moderator checks whether the justification passes format validation (non-empty string naming at least one concrete failure mode or attack scenario AND referencing at least one subject identifier from the task's subject list). Valid justification → severity stays `critical`. Invalid or missing justification → severity is downgraded to `high` for protocol purposes. The original finding object is preserved unchanged in the transparency record.
3. **Transparency Record.** Every critical-or-downgraded finding is logged with its original severity, effective severity (after downgrade), and validation result. This log appears in the resolution document and is visible to the operator. No modification of the original text occurs in phases 1 or 2.

### Golden Fixtures

Golden fixtures live in `tests/fixtures/contracts/golden_test_cases.yaml`. Each fixture defines a concrete payload for validation against the canonical schemas (§Artifact Schemas) and error codes (§Error Code Registry). Before Layer 0 is coded, populate the `input_payload` field with concrete JSON/YAML matching the artifact schema, and set `validation_codes` per the table below.

#### Fixture Test Matrix

| Fixture ID | Expected Outcome | validation_codes |
|-----------|------------------|------------------|
| `critical-without-justification` | Severity downgraded from `critical` to `high`; transparency record created; original text preserved | `[VAL.001]` (schema acceptance passes — justification no longer required at MVP) |
| `absent_vs_null_stance` | Distinct interpretation: absent = subject not addressed by role; null = role addressed subject but has no stance | `[VAL.003]` |
| `support_oppose_disagreement` | Disagreement detected; `ConsensusVerdict.outcome = no-consensus` | `[PROT.003]` |
| `invalid_format_status` | extraction = `invalid-format` → session enters `blocked-escalation` with `information-gap` | `[PROT.002]` |
| `missing_core_role` | Missing Core role → `blocked-escalation` with `risk-threshold-breach` | `[PROT.001]` |
| `manifest_hash_break` | Hash chain integrity check fails | `[IO.002]` |
| `documenter_error_category_mapping` | Every Documenter error_category maps deterministically to one registry code | See mapping table below |

#### Documenter Error Category → Registry Mapping (pre-populated for Layer 0)

| error_category | Registry code | Description |
|---------------|--------------|-------------|
| `hash_mismatch` | `IO.002` | Manifest hash chain broken |
| `trust_mismatch` | `VAL.004` | Trust floor mismatch |
| `audit_mismatch` | `VAL.005` | Audit token missing/expired/out-of-scope |
| `blocking_finding` | `PROT.005` | Blocking finding present |
| `skill_failure` | `IO.004` | Delegated skill failure |
| `operator_timeout` | `PROT.006` | Operator approval timed out |
| `gate_failure` | `PROT.GATE.001` | Pre-check/pre-audit gate failure requiring override |
| `unknown` | `IO.999` | Unhandled exception during delegate() execution |

Each entry must be validated by injecting the corresponding error_category into a documenter event and verifying the emitted registry code matches exactly. Duplicate mappings are prohibited.

## Content Precedence

When specifications conflict across documents, the following precedence order applies (highest to lowest):

1. Format contracts (`service-contract`) — schema fields, enumerations, error codes, event schemas.
2. Protocol/runtime specs (`protocol-core`, `execution-runtime`, `operator-surface`) — phase transitions, escalation logic, session semantics.
3. Configuration/service docs (`planned-architecture`, `documenter-service/*`) — interfaces, policies, tooling behavior.
4. Fallback and scenario docs (`fallback`, `scenario`) — operational notes tied to specific modes or scenarios.
5. Conceptual and legacy docs (`project-concept`, `project-reference`) — goals, roles, roadmap references.

## Cross-References

- `index.md` — main artifact & event schemas
- `planned-architecture/layer-0.md` — functions consuming these schemas
- `planned-architecture/layer-1.md` — producers of role artifacts
- `execution-runtime/index.md` — phase and persistence semantics
- `operator-surface/index.md` — rendering and escalation delivery
- `documenter-service/configuration-guide.md` — Documenter event payloads
