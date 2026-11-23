# Task Brief

### Session Goal
Determine whether and how the Operator Ingress operator identification at the entry point should use the current git account, and produce an actionable decision with risks, conditions, and implementation guidance.

### Focus Areas
- Identity source and binding: what "use current git account" means at the operator entry point (e.g. `git config user.name`/`user.email`, commit author, signed identity) and how it maps to `operator_id`/principal claims.
- Authentication and authorization: impact on AuthN/AuthZ guarantees, token/credential model, spoofing/tamper risks, and compatibility with `operator-ingress/index.md` §Caller Identity and Authorization and approval/escalation binding.
- Human/operator workflow: usability, local setup expectations, multi-identity/multi-repo cases, CI/non-interactive contexts, and auditability.
- Implementation and migration: changes required in `operator_ingress/` (auth, env/config, registration), specs/docs, backward compatibility, and rollout/activation constraints (Tier 2+ interlock remains unchanged).

### Questionnaire per Role

**Architect:**
- Q1: How should git-account-based operator identity integrate with the current ingress architecture (transport/auth boundary, `operator_id` format/claims, session/approval binding) without violating existing contract boundaries?
- Q2: What coupling, state, or migration risks arise (e.g. dependency on local git config/state, identity stability across environments), and what design options best contain them?

**Reliability & Security Specialist:**
- Q1: What failure modes and attack scenarios are introduced if operator entry-point identity is derived from the current git account (spoofing, repo-local config tampering, shared machines, CI agents), and how severe are they for governance actions?
- Q2: What controls or prerequisites are required to preserve authenticated, non-repudiable operator actions (`documenter.approve`, `council.resolve_escalation`) compared to the current token-based model?

**Human-Centric Designer:**
- Q1: Will operators clearly understand which identity is being used and why actions are attributed to it, especially when git identity differs from their expectation?
- Q2: Does relying on the git account reduce or increase cognitive/setup burden and error likelihood across common workflows (single dev, multiple identities, fresh clone, non-git contexts)?

**Operations Engineer:**
- Q1: How does this change affect deployment/registration, environment configuration, observability/auditing, and supportability of the operator ingress?
- Q2: What operational edge cases and rollout steps must be handled (missing/misconfigured git identity, containers/CI, identity rotation, compatibility with existing `COUNCIL_OPERATOR_*` setup)?

### Output Limits
- Maximum findings per role: **6**
- Maximum recommendations per role: **4**
- Maximum open questions per role: **3**
- Total output: **~150 lines** per role — shorter is acceptable; brevity encouraged.

### Expected Discussion Rounds
- Medium task: **1 round** (plus targeted resolution only if a role becomes `blocked-in-scope`)

### Subject List
- `SUBJ-001`: Definition and source of "current git account" for operator identification at ingress (e.g. `user.name`/`user.email`, mapping/normalization to `operator_id`, scope: repo/global/system, stability).
- `SUBJ-002`: Authentication and authorization model — whether git identity is used as identity assertion, credential, or display/audit attribute; implications for token/HMAC flow, AuthN/AuthZ boundary, and governance verbs.
- `SUBJ-003`: Security, integrity, and auditability of operator actions (spoofing/tampering risks, attribution/non-repudiation, failure handling when identity unavailable or ambiguous).
- `SUBJ-004`: Operator UX and operational workflow (clarity, setup, multi-identity/non-git/CI cases, observability).
- `SUBJ-005`: Implementation, compatibility, and migration/activation impact in `operator_ingress/` and related specs/docs, respecting existing interlocks and operator-only activation acts.

### Additional Context / Constraints
- Fallback-mode council session (Moderator not implemented). Code-based Tier 2+ remains **dormant behind the dual interlock** (ADR-013/ADR-016); activation is an operator act out-of-session. This session produces a decision/recommendation only — no activation or policy changes.
- Current implementation: `operator_ingress/core/auth.py` issues/verifies HMAC-SHA256 tokens; operator `sub` must match `^op-[a-z0-9][a-z0-9-]{2,63}$`; `__main__.py`/`handle_request` require auth token in JSON-RPC params and derive `operator_id` from `claims.sub`; secret from `COUNCIL_OPERATOR_SECRET`. `REGISTRATION.md` documents env vars including `COUNCIL_OPERATOR_ID`.
- Current spec: `docs/en/operator-ingress/index.md` states AuthN uses local stdio process plus `COUNCIL_OPERATOR_ID` and `COUNCIL_OPERATOR_TOKEN` from environment and that operator identity/`operator_id` authority is defined there; `service-contract` defines `operator_id` format `^op-[a-z0-9][a-z0-9-]{2,63}$`.
- Current git account in this workspace: `EA (Documenter) <ea@council.local>` (from `git config user.name/user.email`).
- Proposal under review (from operator): "use current git account for operator identification at operator entry point" (original: «использовать для идентификации оператора в точке входа оператора текущий git аккаунт»). Mechanism is not fully specified and must be analyzed.
- All changes to `docs/`, manifest, and `CHANGELOGS/` require Documentation Worker skill and operator approval after propose; this session must not modify them. `operator_ingress/` code is implementation (not under Documenter write scope) but any code change would be a separate implementation task if approved.
- Roles must reference `SUBJ-*` identifiers in findings. Critical findings require concrete failure mode/attack scenario and affected subject identifier(s).