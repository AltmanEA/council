# Session Task Brief — sess-term-operator-surface

Mode: fallback (per fallback/index.md)
Scenario: default-council-session (Core tier: Architect, Reliability & Security Specialist, Human-Centric Designer)
Language of artifacts: technical English (operator chat report: Russian)

## Task

The Layer 2 component currently named **"Operator Surface"** (spec: `docs/en/operator-surface/index.md`, code: `operator_surface/`) is judged intuitively opaque as a term — in particular its Russian rendering "операторская поверхность" conveys little. The Council must choose a replacement term for this concept (EN canonical term + RU derivative), or explicitly decide to retain the current term.

## Component definition (what the term must denote)

The single authenticated ingress for the human operator into the Council runtime:

- MVP transport: MCP over stdio (JSON-RPC); CLI/REST are deferred adapters over the same functions.
- Authenticates callers (classes operator/agent/service; HMAC tokens; deny-by-default; only the human `operator` may exercise governance verbs such as resolving escalations or approving Documenter writes).
- Validates input, localizes errors; contains **no protocol logic and no LLM invocation** — a thin adapter over Layer 1.
- Hosts operator verbs (`council.*`, `documenter.*`), renders the operator status projection and the escalation view, and hosts the `pre_check` gate (synchronous Documenter audit at phase boundaries).

## Candidate terms (initial list; roles may propose new ones)

1. Operator Surface (status quo)
2. Operator Gateway
3. Operator Console
4. Operator Interface
5. Operator Portal
6. Operator Desk / Reception / Front Desk (RU: приёмная, стойка)
7. Operator Terminal
8. Operator Facade
9. Operator Cockpit / Helm (RU: рубка)
10. Concierge (RU: консьерж)
11. Operator Liaison

## Constraints

- EN under `docs/en/` is authoritative; RU is derivative. The term must be intuitive in BOTH languages (transparent RU rendering without calque-obscurity).
- Must not collide with existing concepts: **"Approval Surface"** (Tier 2+ out-of-band approval flow, `documenter-service/approval-surface.md`) is a separate concept; must not be confusable with end-user UI of the system being designed; must not blur Documenter naming.
- Should convey: human operator's entry point + authority channel + visibility (status/escalation rendering), without overstating the component's weight (it is a thin adapter, not the brain).
- Renaming has migration cost: glossary entry, spec filenames/IDs, cross-references, ADR text, notices (`notice.documenter_tier2_interlock` etc. are events, not term-bound), possibly the code package name (out of protocol scope — see SUBJ-003).
- Terminology changes follow documentation-rules via the Documentation Worker; session output is a recommendation changeset for operator approval, not an applied edit.

## Subject list (canonical)

- SUBJ-001: Canonical EN term for the Layer 2 operator ingress component.
- SUBJ-002: RU derivative form of the chosen term.
- SUBJ-003: Migration scope — which artifacts must be updated (docs, glossary, manifest references, code package, ADR wording) and whether the code package `operator_surface/` is renamed.
- SUBJ-004: Disambiguation policy vs "Approval Surface" and end-user UI terminology (how the new term coexists with them).

## Output rules (per fallback/index.md)

Each role returns one structured review: Summary Position; Key Findings (severity, subject ref, stance support/oppose where applicable, justification mandatory for critical); Recommendations; Open Questions; Status (agree / concerns / blocked-in-scope / blocked-escalation [+ reason]).
