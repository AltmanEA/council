# Approval Surface — Tier 2+ Out-of-Band Approval

id: documenter-service-approval-surface
Version: 0.1.0
Status: draft
Abstraction: protocol
references: [documenter-service-mvp-contract, operator-surface]
allow_non_index_paths: true
has_translation: docs/ru/documenter-service/approval-surface-RU.md
changelog-path: CHANGELOGS/approval-surface.changes.md

---

> **AuthN/AuthZ boundary is exclusively defined in `operator-surface/index.md` §Caller Identity and Authorization.** This document does not define, extend, or restate who counts as an operator or how credentials are verified; any apparent conflict is resolved in favor of `operator-surface/index.md`.

## Scope

Defines the operator-facing Tier 2+ approval and gate-override workflow as rendered and delivered through the Operator Surface: the approval request presentation, the approval handshake, and the override recording. The normative contract for every mechanic named here — `approval_id` semantics, diff-hash binding, single-use, `approval_expiry_window`, changed-diff invalidation, approver ≠ proposer — is `documenter-service/mvp-contract.md` §4, the **canonical source**; where this document disagrees with §4, **§4 wins** (Canonical rule, sess-operator-surface-split). The `pre_check` gate is not covered here: it belongs to `operator-surface/index.md` §pre_check Gate (SUBJ-004, sess-operator-surface-split).

<!-- STATUS: implemented at Tier 0–1 behind the stdio transport (p3 MVP); the Tier 2+ write branch is DORMANT behind the ADR-013 dual interlock (policy gate + un-activated Operator Surface sentinel); MCP unregistered (operator decision, AGENTS.md §1.7). DORMANT means implemented-but-interlocked, not specification-only. -->

<span style="color:red;font-weight:bold">⚠ DORMANT (ADR-013) — MCP UNREGISTERED</span> `documenter.approve` and the Tier 2+ branch are implemented in the build and unreachable at runtime: every Tier 2+ call fails closed with `tier_interlock` until the operator advances `active_tier` with a valid `briefing_ref` (activation act reserved to the operator out-of-session).

## Approval Lifecycle (Operator Workflow)

- Tier 0–1 ships at MVP: read-only audit and diff preview. `documenter.delegate` validates `change_type`, `diff`, and `audit_id`, then returns a preview without writing.
- Tier 2+ is policy-gated (interlocked until the operator advances `active_tier` with a valid `briefing_ref`). When enabled, `documenter.delegate` returns `approval_required` with an `approval_id` and the diff hash; no write proceeds until approval.
- The operator reviews the diff item by item regardless of tier and invokes `documenter.approve` out-of-band as a separate invocation from the proposal; `operator_id` resolves from authenticated ingress only (header guard above).
- Approval presentation: the surface renders the approval request as a projection of the pending record — target, diff hash, proposer, expiry deadline — and never paraphrases the diff through an LLM.
- The `documenter.approval` event schema is defined in `documenter-service/mvp-contract.md` §4 (event ownership rule: the service emits, the surface renders).

## Override Gate (Operator Workflow)

- `documenter.override_gate(reason, operator_id)` overrides one audit-gate failure with a recorded reason and an authenticated `operator_id`; it is bound to one `(target_id, diff_hash)`, consumed once, and is unavailable for `critical` findings (`documenter-service/mvp-contract.md` §4).
- The override emits `documenter.override_gate` in the canonical envelope (schema in §4); while Tier 2+ is dormant the override records the event without invoking the Documenter write port.
- The `council.override_precheck` verb belongs to `operator-surface/index.md` and is not affected by this document.

## Interlock Notice and Degradation

- While Tier 2+ is interlocked, the surface shows the advisory notice `notice.documenter_tier2_interlock`; the notice-to-event mapping lives in `operator-surface/index.md` §Notices.
- When `documenter_service` is unimportable, `documenter.*` verbs return an honest `IO.004` envelope naming `council.status` as the fallback action; the surface still starts (degradation semantics in `operator-surface/index.md` §Security and Threat Model (MVP)).
- Sentinel presence (`documenter/.operator_surface_ready`) is a code consequence of a successful READY handshake and grants nothing: activation remains exclusively a policy-file state act (ADR-016).

## Cross-References

- `documenter-service/mvp-contract.md` §4 — canonical Tier 2+ approval contract and `documenter.approval` / `documenter.override_gate` event schemas
- `operator-surface/index.md` — transport, AuthN/AuthZ boundary, verbs registry, `pre_check` gate, notices
- `documenter-service/policy-reference.md` — policy fields and authorization workflow
- `documenter-service/index.md` — Documenter interfaces and trust tiers
