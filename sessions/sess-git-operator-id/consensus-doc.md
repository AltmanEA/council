# Consensus Document

## Decision
Do **not** use the current git account as operator identification or authentication at the Operator Ingress entry point for AuthN/AuthZ or governance actions. The authoritative operator principal must remain the HMAC-verified token claim `sub` (`operator_id`, `^op-[a-z0-9][a-z0-9-]{2,63}$`) as in the current implementation/spec model.

## Rationale
- Convergent (all roles, `SUBJ-001..005`): “current git account” is unspecified and unstable (e.g. `git config user.name`/`user.email`, repo/global/system scope, absent in non-git/CI); workspace values `EA (Documenter) <ea@council.local>` are mutable and do not satisfy `op-*` `operator_id` format.
- Convergent critical (`SUBJ-002`, `SUBJ-003`): if git identity is used as credential, sole assertion, or authority source, local config tampering enables trivial impersonation of governance verbs (`council.resolve_escalation`, `documenter.approve`, `council.override_precheck`/gate overrides) without possession/verification of `COUNCIL_OPERATOR_SECRET` or a valid token, breaking principal binding, non-repudiation, and separation controls. Git config is mutable state, not a cryptographic credential.
- Convergent (`SUBJ-002`, `SUBJ-005`): replacing/augmenting token authority conflicts with current ingress/spec contracts (token-verified claims before routing, deny-by-default, human operator principal for governance) and would require coordinated spec/code/env/record migration while preserving fail-closed behavior and Tier 2+ dual interlocks (ADR-013/016).
- Convergent (`SUBJ-003`, `SUBJ-004`): auditability, observability, and operator trust degrade if “commit identity” is conflated with “governance authority”; git as runtime dependency creates non-determinism in multi-identity, shared-host, container, CI, and non-repo contexts.
- Conditional allowance (all roles): git identity may be considered only as optional, explicitly labeled **unverified** advisory/display/audit metadata recorded alongside the verified `operator_id` after successful authentication, never used for AuthN/AuthZ decisions and with fail-safe handling when absent/ambiguous/mismatched.

## Subjects with Outcomes
| Subject | Status | Notes |
|---------|--------|------|
| `SUBJ-001` | Conditionally Agreed | No authoritative derivation from git config. Any future metadata/mapping use requires explicit, deterministic contract (source, scope/precedence, normalization/validation, ambiguity/absence behavior). |
| `SUBJ-002` | Agreed | Git identity MUST NOT be an AuthN credential or AuthZ/authority input. HMAC token verification and claim-derived `operator_id` remain the sole principal for governance verbs. |
| `SUBJ-003` | Agreed | Using mutable git state as authority is rejected due to spoofing/tampering and weak attribution. If recorded, verified principal and unverified git metadata must be clearly distinguished. |
| `SUBJ-004` | Conditionally Agreed | No silent auto-detection as identity/authority. If exposed, present separately as unverified local context with clear warnings and recovery guidance; must not break authenticated/non-git/CI flows. |
| `SUBJ-005` | Conditionally Agreed | No implementation/spec activation in this session. Any change requires operator-approved, coordinated updates across `operator_ingress/`, specs/docs/tests and existing env contracts; Tier 2+ interlocks and operator-only activation acts unchanged. |

## Conflicts & Disagreements
— None — (All roles converged: reject git as authoritative/auth credential; allow only constrained non-authoritative metadata if explicitly designed.)

## Reservations
- **Architect:** Only acceptable if strictly non-authoritative audit metadata bound to authenticated token flow; cross-cutting contract/spec/code/test alignment required before any adoption (`SUBJ-001..005`).
- **Reliability & Security Specialist:** Any identity derivation/mapping (if ever pursued) must be fail-closed for governance, avoid collisions/ambiguity, prefer cryptographic proof/allowlisting, and be tested against shared-host/CI spoofing scenarios (`SUBJ-001..003`, `SUBJ-005`).
- **Human-Centric Designer:** Explicit labeling and separation of “Authenticated operator” vs “Local git identity (unverified, optional)” required; avoid silent fallback, wrong-identity selection, and confusion with self-approval/attribution (`SUBJ-001`, `SUBJ-003`, `SUBJ-004`).
- **Operations Engineer:** Adding git as runtime dependency/identity source risks deterministic behavior and incident response; spec/impl/env naming and identity-record migration must be reconciled if any change is made, with rollback path (`SUBJ-001..005`).

## Open Questions
- What mechanism, if any, is actually desired: unverified display/audit label only, explicit operator-configured allowlist/mapping to `operator_id`, or stronger cryptographic binding (e.g. verified signatures)? Deriving/replacing the acting principal from git config is not accepted.
- If metadata/mapping is pursued: canonical source and precedence (which field(s), repo/local/global/system), normalization/validation rules, mismatch/ambiguity handling, and required stability across machines/sessions.
- How must non-git directories, containers, CI/service automation, shared worktrees, and multi-identity or mid-session identity changes be detected, represented, and attributed without affecting authenticated governance flows?

## Action Items
- **Operator (decision):** Treat proposal as **rejected for authoritative identification** at ingress; confirm whether a follow-up, narrowly scoped proposal for *unverified advisory git metadata only* is wanted. (Priority: high)
- **Operator / Spec owners (if follow-up approved):** Define precise contract and threat model (including non-repudiation expectations) before any implementation; preserve `operator-ingress` as sole identity authority and keep Tier 2+ interlocks/activation operator-only. (Priority: medium)
- **Implementers (if follow-up approved):** Design coordinated changes to `operator_ingress/`, docs (via Documentation Worker + operator approval for `docs/`/manifest/changelog), env/registration, audit/event schema, and tests; default to no impact on AuthN/AuthZ when git unavailable/mismatched. (Priority: medium)
- **No action now:** No changes to `docs/`, `docs-manifest.yaml`, `CHANGELOGS/`, policy/sentinel, or ingress runtime in this session.

## Escalation References
— None —

## Downgraded Critical Findings
— None — (Critical findings from all roles included concrete failure modes/attack scenarios and affected subjects; no downgrades applied.)
