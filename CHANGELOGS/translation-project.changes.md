# Changelog: Translation Project — Consumer Contract

<!-- CHANGES v0.1.0: Initial introduction of the translation-project consumer contract documents (index.md + contract.md) following ADR-014 / sess-translation-extraction. -->

## 0.2.0

- Sidecar schema: added `ai_review` field (`passed` / `failed` / `not_run`) — gate-5 AI quality review verdict (G-2, operator-approved 2026-11-23). `verified` status requires `ai_review: passed`; `not_run`/absent caps at `unverified`. Implemented in `tools/translation_status.py::compute_status` (historical reports without the field evaluate as `not_run`).
- `glossary_applied` annotated diagnostic-only (known engine defect: reports 0 even when terms were applied; authoritative counts are the gate-4 provenance line `terms`/`matched`).

## 0.1.0

- Initial specification of the Translation Project consumer-side contract: CLI invocation, exit-code semantics, report JSON schema, lock file format, and status index / sidecar schemas.
- Separates protocol-level behavior (`index.md`, Abstraction: protocol) from format-level definitions (`contract.md`, Abstraction: format), per ADR-014.
- Includes full CLI flag table, environment variables, and all 7 exit codes (0–6) with recovery procedures.
