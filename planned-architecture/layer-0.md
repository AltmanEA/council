# Layer 0 — Protocol Enforcement

Version: 0.2.0
Status: draft
Last Modified: 2026-11-08
Abstraction: protocol
changelog-path: CHANGELOGS/planned-architecture.changes.md

Source: ../index.md (planned-architecture)

---

## Purpose

Deterministic enforcement of all protocol rules. Zero framework dependencies. Pure Python functions. Testable by direct import.

## Interface Contract

```python
def evaluate_consensus(role_statuses: list[dict]) -> ConsensusVerdict
def validate_subject_references(subjects: list[dict], text: str) -> list[ValidationResult]
def extract_role_status(review_text: str) -> RoleStatus | InvalidFormat
def check_justification_format(finding: dict) -> FormatValid | FormatInvalid
```

## Boundary Rules

- Only called by Layer 1 (role execution). Never directly accessed by Layer 2 (surface tools). If Layer 2 needs protocol behavior, it calls through Layer 1.
- No framework imports allowed at this layer. No LangChain, no LangGraph, no FastAPI, no SQLite dependencies.

## Invariants (ADR-001: Structural assertions + property-based tests)

All enforced via explicit `assert` statements and Hypothesis property tests. No LLM participates in safety verification.

| Invariant | Description |
|-----------|-------------|
| Core role presence | All Core-tier roles must be present (Architect, R&S Specialist, HCD Designer) on every execution path, not only before simplification applies |
| Escalation integrity | Escalation paths cannot be removed or weakened by any parameter |
| Consensus immutability | Consensus computation logic cannot be overridden by scenario configuration |
| Justification enforcement | Critical finding justification validation always runs regardless of task complexity |
| Severity blocking rule | Only medium and above can contribute to blocking a task |
| Stance structural check | Disagreement detection uses machine-readable stance fields, not textual interpretation |

## Persistence

Phase state serialized as individual JSON files in `sessions/<id>/`. No shared state between sessions. Short-lived tasks only — no ACID required. No SQLite. No pickled checkpoints. Plain JSON with sorted keys on write.
