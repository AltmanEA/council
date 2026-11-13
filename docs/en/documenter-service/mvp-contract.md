# Documenter Service — MVP Contract

id: documenter-service-mvp-contract
Version: 0.5.0-draft
Status: draft
Abstraction: protocol
references: [documenter-service-mvp-interfaces, documenter-service-mvp-data-models]
allow_non_index_paths: true
changelog-path: CHANGELOGS/documenter-service-mvp-contract.changes.md

---

## Purpose

Implementation contract for the Documenter Service MVP (Tier 0–1, read-only): technology stack, safety protocol, Tier 2+ reserved interfaces, and testing strategy. Interface schemas: `documenter-service/mvp-interfaces.md`. Data models and configuration: `documenter-service/mvp-data-models.md`. Architectural intent: `documenter-service/index.md`.

**MVP boundary:** the build exposes `audit()`, `delegate(preview: true)`, `documenter.status()`. The Tier 2+ surface (`delegate(preview: false)`, the approval flow, `override_gate`, the durability sequence, and Tier 3 pattern auto-apply) is specified here (§2.2, §4) and **implemented in the build, gated by the policy interlock**: activation requires `active_tier >= 2`, a non-null `briefing_ref` whose file exists, matching `allowed_operations` entries, and authenticated operator ingress (`COUNCIL_OPERATOR_ID` only; never a client parameter). With the repository policy at Tier 0–1 every non-preview call fails closed with `tier_interlock`. The **Multi-file Commit Protocol** (ordered renames across documents in one commit set) remains deferred — the write branch commits one document per invocation.

---

## 1. Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.11+ | Matches project tooling (`tools/local_translate.py`); stdlib covers MVP |
| Transport (MVP) | MCP stdio | Same invocation path as the Council tool layer; CLI wrapper shares one core with MCP so results cannot diverge. MVP build ships both: `python3 -m documenter_service` (CLI) and `python3 -m documenter_service --mcp` (newline-delimited JSON-RPC 2.0 stdio server exposing `audit`, `status`, `delegate_preview`); the server writes only JSON-RPC to stdout, events go to stderr. Registering it as a workspace MCP server remains an explicit operator decision (AGENTS.md §1.7) |
| LLM dependency | **None** | Writes (Tier 2+) go through the Layer 1 execution port; importing LLM clients in service code is prohibited |

### Dependencies

| Library | Purpose | Constraint |
|---------|---------|------------|
| `PyYAML` | Manifest and policy parsing | `safe_load` only; `yaml.unsafe_load` prohibited |
| `difflib`, `uuid`, `hashlib`, `datetime`, `json`, `secrets`, `fcntl` (stdlib) | Diff, IDs, hashes, timestamps, events, tokens, advisory lock | Stdlib only |

**Build constraint:** no native compilation dependencies. Installable from wheels only; no build toolchain on any deployment host.

**Local tooling (`tools/`):** scripts under `tools/` (manifest generator, validator, hook, bump script from sess-doc-reliability-algo) are designated **candidates** for the future pure core — they must keep I/O-thin cores per ADR-009 and ship golden fixtures under `tests/fixtures/` from day one. Dependency policy for `tools/` mirrors this contract: Python 3.11+, stdlib + PyYAML (`safe_load`) only.

### Architecture: Ports & Adapters

The core is deterministic pure functions (trust classifier, severity rules, pre-audit gate, hash comparison, diff canonization) with no I/O and no knowledge of MCP. Five ports face outward; adapters (filesystem, stdio, stdout) are the only impure layer. Tier interlocks and fail-closed behavior are then unit-testable without a filesystem.

| Port | Direction | Responsibility |
|------|-----------|----------------|
| `ManifestSource` | Read | Parse `docs-manifest.yaml`; resolve document paths |
| `AuditRegistry` | Read/Write | Append-only store; token lifecycle |
| `DiffEngine` | Compute | Diff generation, normalization, hash — **bidirectional** (generate → verify) |
| `WorkerPort` | Execute | Documentation Worker via Layer 1 — **Tier 2+ only** |
| `EventSink` | Emit | Structured JSON to stdout; future EventEnvelope adapter |

---

## 2. Safety Protocol

### 2.1 MVP (read-only)

1. **No writes.** The MVP binary performs zero filesystem mutation outside `documenter/` registry appends.
2. **No commits.** The service never runs `git commit`. Rollback of any future change is `git restore <file>` — the property that made cryptographic tamper-evidence unnecessary (operator decision 2026-11-12).
3. **Read-before-use.** A document read for audit is hashed; if the hash changes before a dependent computation completes, the result is discarded and the scan re-run.

### 2.2 Tier 2+ (reserved; normative now, implemented later)

1. **Pre-change snapshot:** capture `git status` and `HEAD` before modifications.
2. **Advisory lock:** `fcntl.flock(LOCK_EX)` on `documenter/.delegate.lock` covering the entire changeset (target document, `index-RU.md`, changelog, `docs-manifest.yaml`). One operation-level lock replaces per-file locks and is deadlock-free by construction. If lock acquisition fails — emit `lock_conflict` with context: "Another agent holds an advisory lock on [resource]. Lock owner: [PID/IP], acquired at [timestamp]. Wait? (yes/no) — Default: no after 30s." A race control only — writers that skip the lock are caught by (3), not by the lock. Distributed cross-host locking is out of scope for MVP; deferred to Phase 2+.
3. **Apply-time verification (contract norm, conflict C2):** before rename, recompute `sha256` of the source (compare against `intent_record.per_file_sha256`) and `sha256` of the Worker output (compare against the approved `diff_hash`). Any mismatch → `hash_mismatch`, write denied. This closes the gap between "approved hash" and "written bytes".
4. **Durability sequence (normative):** `stage in target dir → fsync(file) → intent record (temp+rename+fsync) → rename → fsync(dir)`. Staging in `/tmp` is prohibited: `rename(2)` is atomic only within one filesystem.
5. **Multi-file commit:** stage all → intent record with per-file `sha256` → ordered renames → clear intent. Crash mid-sequence leaves a **detectable** partial state; cold-start reconciles automatically only when every source hash still matches, otherwise structured error + explicit re-invocation.
6. **Post-mortem capture:** a post-mortem record writer (`documenter/post_mortems/`: audit_id, findings, reason, operator, timestamp) is implemented as the durable mechanism. **Contract resolution (operator decision 2026-11-14):** §4 makes `override_gate` unavailable for `critical` findings, so the critical-override trigger in this clause is unreachable — §4 wins; the writer stands ready for future critical flows and nothing fabricates critical findings to exercise it.

---

## 3. Testing Strategy

### 3.1 Unit tests (pure core, no filesystem)

| Test | Verifies |
|------|----------|
| `test_trust_classification` | `requested >= derived` over the full `change_type` × `trust_level` matrix; policy floor monotonicity |
| `test_policy_validation` | Every §mvp-data-models §2 rule fails closed |
| `test_canonical_diff` | Semantically equal diffs → identical `diff_hash` (CRLF, trailing space, final newline) |
| `test_pre_audit_gate` | Rules 1–5: existence, freshness, scope, blocking findings, rescan completion |
| `test_token_lifecycle` | Single-use; `(audit_id, target_id)` binding; replay → `token_replay` |
| `test_event_redaction` | No document text in payloads; unknown fields rejected (VAL.001) |
| `test_clock_injection` | Freshness/expiry windows deterministic under injected clock |

### 3.2 Integration tests

`test_registry_integrity` (chain continuity, corruption detection, checkpoint-before-truncation), `test_manifest_parity`, `test_cross_reference_resolution`, `test_corrupt_registry_status` (status reports `corrupt`; service does not go silent), `test_coverage_header` (partial scan report states write-decision impossible).

### 3.3 Golden fixtures

| Fixture | Purpose |
|---------|---------|
| `tests/fixtures/documenter/golden_audit.yaml` | Expected audit output for a frozen corpus |
| `tests/fixtures/documenter/golden_diff_canon.json` | Input diff → normalized bytes → `diff_hash` |
| `tests/fixtures/documenter/policy_valid.yaml` / `policy_invalid.yaml` | Load-time validation, including typo'd `active_tier` and missing `briefing_ref` at tier 2 |

### 3.4 Tier 2+ (deferred with the implementation)

Crash-injection via `kill -9` after **every** boundary of the durability sequence, expecting a detectable partial state each time; apply-time `hash_mismatch` scenario (external edit between propose and apply); token replay tests.

---

## 4. Tier 2+ Interfaces (implemented; policy-gated)

Implemented per the conditions above; reachable only when **all** of: policy file with non-empty `allowed_operations`, non-null `briefing_ref` to an archived operator briefing whose file exists, and authenticated out-of-band operator ingress (`COUNCIL_OPERATOR_ID` from the environment; the Operator Surface remains the intended front). The Operator Surface spec (`operator-surface/index.md` §Documenter Integration) exists as specification; single-operator deployment is **not** a valid Tier 2+ configuration — `approver ≠ proposer` cannot be satisfied by one person with two IDs.

| Interface | Key constraints |
|-----------|----------------|
| `delegate(preview: false)` | Pre-audit gate rules 1–5; returns `approval_required` + `approval_id` + `diff_hash`; applies only after §2.2 verification |
| `documenter.approve(approval_id, operator_id)` | Separate invocation from the proposal; `operator_id` from authenticated ingress only; single-use; expires after `approval_expiry_window`; changed diff invalidates it |
| `documenter.override_gate(reason, operator_id)` | Bound to one `(target_id, diff_hash)`; one consumption; emits event; unavailable for `critical` findings |
| Tier 3 pattern auto-apply | Pattern = `(target subset, canonical diff template, expiry, application limit)` — content-bound, never class-only. Promotion metric ≥90% approval computed **only over viewed diffs**; post-apply digest per batch; quarantine: first N uses of a pattern require per-item approval |

---

## 5. Resolved Conflicts & ADRs

| Conflict | Resolution (operator decisions, 2026-11-12) |
|----------|---------------------------------------------|
| C1 Token signing | No HMAC; random server-stored single-use tokens; git history as audit trail |
| C2 Apply-time verification | Contract norm for all tiers (§2.2.3); implementation belongs to Tier 2+ |
| C3 Tier 2/3 in contract | Interfaces and enums present here (§4); apply code absent from MVP build |
| C4 Event channel | Registry + stdout JSON as documented MVP carrier; envelope via `service-contract` amendment |
| C5 Hash-chain vs retention | Chain kept as corruption aid (not anti-tamper); truncation requires checkpoint record |

| ADR | Topic | Status |
|-----|-------|--------|
| ADR-006 | Python 3.11+, stdlib-only MVP, `fcntl` advisory lock | Accepted (operator) |
| ADR-007 | Threat model: no writes, git rollback, no crypto in MVP | Accepted (operator) |
| ADR-008 | `documenter/` under git; service never commits | Accepted (operator) |
| ADR-009 | Ports & Adapters; pure core, five ports | Accepted (session consensus) |

Identifiers are assigned from the central registry (`planned-architecture/decisions/index.md`); ADR-001–005 are already taken there. This document does not define ADR content — it cites the registry entries.

---

*Part of the Documenter MVP contract. Interfaces: `documenter-service/mvp-interfaces.md`. Data models: `documenter-service/mvp-data-models.md`.*
