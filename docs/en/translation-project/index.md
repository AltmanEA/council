# Translation Project — Consumer Contract

id: translation-project
Version: 0.1.0
Status: draft
Abstraction: protocol
changelog-path: CHANGELOGS/translation-project.changes.md
references:
  - planned-architecture-decisions
  - glossary

---

## Purpose

This document specifies the consumer-side contract for Council's interaction with the external Translation Project (`techdoc-translator`, per ADR-014). The Translation Project is a standalone repository that generates EN→RU candidate translations via a CLI interface with exit-code semantics and `.env` configuration. Council knows the Translation Project only through the contract defined here and the lock file (`defaults/translation.lock`). The dependency direction is one-way: Council pins the engine version; the engine project knows nothing about Council. The Translation Project writes no Council files directly — all writes go through the Documentation Worker skill (write authority remains with Council). Provenance artifacts (sidecar, STATUS.md, run reports) are git-tracked operational files under `documenter/artifacts/translation/`, outside the manifest scope.

---

## Invocation

The Translation Project CLI is invoked via a wrapper script (`translate.sh`) whose path is read from the lock file:

```
<local_path>/translate.sh \
  --input-en <path-to-en.md> \
  --output-ru <path-to-temp-ru.md> \
  --glossary <path-to-glossary.md> \
  --report <path-to-report.json> \
  --skip-pattern <regex> \
  [--allow-cloud] \
  --contract-version <N>
```

- `--input-en` / `--output-ru` / `--report` are file paths; the Translation Project performs no Council-specific format interpretation.
- `--glossary` points to the Council glossary file (or a subset); the Translation Project parses it as a generic markdown glossary (see §Glossary format in `contract.md`).
- `--skip-pattern` is a regex; the caller (Council layer) prepares the appropriate patterns to preserve Council frontmatter and other metadata lines. The Translation Project itself does not know Council metadata formats.
- `--allow-cloud` enables the cloud backend branch; requires per-run operator consent per ADR-012.
- `--contract-version` triggers a version handshake against the lock file; on mismatch, exit code 5.

---

## Procedure

The Documentation Worker skill executes the following sequence for translation:

1. **Pre-translate:** compute SHA-256 of the EN source; write an intent record with `tx_id`, `target_id`, EN path, and `before_hash`.
2. **Generate candidate:** invoke the Translation Project CLI with `--output-ru` pointing to a temp path in the target document's directory. Wait for process completion.
3. **Verify exit:** check exit code 0 in the report JSON. Any non-zero exit → fail-closed (RU not written). Check report schema against the spec in `contract.md`.
4. **Phase 4 write-gates:** run all gates defined in the Documentation Worker skill (translation completeness, line parity, EN-identity scan, glossary compliance). `fail > 0` in the report triggers rejection.
5. **Drift check:** run `tools/check_drift.py` to verify structural invariants (line parity, heading hierarchy, table row count, code fences, list markers, metadata fingerprint, Cyrillic-ratio English leakage).
6. **TOCTOU EN re-hash:** re-read the EN source and compute SHA-256; compare with the pre-translate hash. Mismatch → `hash_mismatch`, reject.
7. **Write RU:** write candidate to a temp file in the target directory, then `rename` to `index-RU.md` — the commit point.
8. **Post-write:** compute SHA-256 of the written RU file; update hash store; emit audit event.
9. **Provenance:** derive sidecar (`documenter/artifacts/translation/<target_id>.json`) and `STATUS.md` from the saved report. Rebuild deterministically using `tools/translation_status.py` (planned) from `runs/` data.

---

## Status Semantics

Each translated document carries a status in the generated Status Index (`documenter/artifacts/translation/STATUS.md`):

- **verified** — all Phase 4 write-gates passed, check_drift clean, TOCTOU hash matched, sidecar written. Only achievable when every gate passes.
- **unverified** — a Phase 4 gate did not complete, the backend failed, or the sidecar could not be derived from a stored run report.
- **drift** — the EN source changed after translation, or the glossary delta invalidated the previous translation's verified status.
- **error-N** — the Translation Project exited with code N (1–6). Each code has a documented meaning in the contract.

Status derivation: the Status Index is rebuilt deterministically from the append-only `runs/` reports (`runs.jsonl`). Sidecar files are also regenerated from runs — they are derived, not authoritative. The RU `index-RU.md` file itself is the authoritative source of truth; sidecar and STATUS.md are audit artifacts.

---

## Failure Policy

- **Any exit ≠ 0** → fail-closed. The RU file is never written. The report JSON is still saved (for audit). The status becomes `error-N`.
- **Cloud branch:** only invoked when both `--allow-cloud` is set AND the operator gives per-run explicit consent per ADR-012. Cloud configuration lives in the Translation Project's `.env` file; Council has no knowledge of it.
- **Incomplete translation (exit 4):** the report contains `fail > 0`. Treated as `unverified` — no write. Retry after addressing the cause.
- **Contract mismatch (exit 5):** the lock file version does not match `--contract-version`. The lock must be updated by the operator before retry.

---

## Cross-References

- **ADR-012** (Post-Approve auto-sync): cloud fallback requires per-run operator consent.
- **ADR-013** (Dual interlock): Documenter integration deferred; only the Documentation Worker skill invokes the Translation Project during transition.
- **ADR-014** (External Translation Project boundary): defines the project separation and one-way dependency.
- **AGENTS.md** §1.6–§1.7: tooling separation; this contract is the consumer-side norm.
- **SKILL.md**: Phase 4 write-gates and translation execution procedure.
- **Glossary terms:** `Translation Project`, `Translation Project Artifact`, `Status Index`, `Translation Contract`.

---

## Versioning

The `contract_version` field in the run report indicates the CLI contract version that was verified. If the current CLI's contract version differs from what the report was produced under, the contract may have evolved (backward-compatible flag additions). A mismatch between the lock file's `contract_version` and the `--contract-version` CLI argument triggers exit 5. The report's `contract_version` is also recorded in the sidecar and used for drift detection on contract evolution.
