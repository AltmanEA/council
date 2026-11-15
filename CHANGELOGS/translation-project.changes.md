# Changelog: Translation Project — Consumer Contract

<!-- CHANGES v0.1.0: Initial introduction of the translation-project consumer contract documents (index.md + contract.md) following ADR-014 / sess-translation-extraction. -->

## 0.1.0

- Initial specification of the Translation Project consumer-side contract: CLI invocation, exit-code semantics, report JSON schema, lock file format, and status index / sidecar schemas.
- Separates protocol-level behavior (`index.md`, Abstraction: protocol) from format-level definitions (`contract.md`, Abstraction: format), per ADR-014.
- Includes full CLI flag table, environment variables, and all 7 exit codes (0–6) with recovery procedures.
