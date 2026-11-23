# Consensus Document — sess-term-operator-surface

Session: sess-term-operator-surface (fallback mode, default-council-session, Core tier)
Date: 2026-11-18
Verdict: **conditional** (all roles support the decision; reservations recorded)
Artifact language: technical English

---

## Decision

**D1 (SUBJ-001).** Replace the canonical term **"Operator Surface"** with **"Operator Ingress"** for the Layer 2 authenticated operator ingress component (`docs/en/operator-surface/index.md`, code `operator_surface/`).

**D2 (SUBJ-002).** Adopt **"Точка входа оператора"** as the RU derivative (glossary and RU documents).

**D3 (SUBJ-004).** The glossary entry for the new term MUST include explicit disambiguation from:
(a) **"Approval Surface"** (`documenter-service/approval-surface.md`) — a distinct Documenter Tier 2+ out-of-band approval concept, which retains its name;
(b) the **network-gateway** and **login/entry-door** readings: the glossary states the component is the Layer 2 local stdio adapter enforcing authenticated, deny-by-default ingress, not a network device and not a login screen.

**D4 (SUBJ-003).** Migration scope: a single atomic changeset covering the spec document title/paths, glossary, `docs-manifest.yaml` regeneration, and all cross-references (`planned-architecture/layer-2.md`, `approval-surface.md`, `execution-runtime`, ADR texts, `AGENTS.md` guard clauses). Code package `operator_surface/` rename is recommended but is a separate operator decision outside Documentation Worker scope.

## Rationale

- "Surface" collides structurally with "Approval Surface": same root, different semantics, same RU root "поверхность"; produces a concrete audit-log retrieval failure mode in incident investigation (all roles agreed; the driver of the rename).
- "Gateway" was rejected after a targeted resolution round: it evokes bidirectional routing / network-gateway semantics that contradict the deny-by-default permission model, and its residual ambiguity requires the same glossary mitigation as "Ingress" — so no compensating benefit.
- "Ingress" is a boundary term (one-way, authenticated front door; K8s Ingress precedent), matching the component's actual role: authenticate → validate → route to Layer 1, with no protocol logic and no LLM.
- "Точка входа" is the established Russian IT-security phrase for "entry point": avoids the opacity of the calque "операторская поверхность" and the triviality of bare "вход".

## Reservations (recorded, non-blocking)

1. **HCD — authority-signaling gap.** Neither term intrinsically signals the operator's sovereign governance authority; the term carries the security model, the spec text must carry the authority model. Mitigation: spec text states the operator exercises governance authority at the Ingress boundary.
2. **R&S — jargon load.** "Ingress"/"ингресс" may read as infrastructure jargon to less technical operators; mitigated by a plain-language glossary definition.
3. **R&S — migration window.** Any period where old and new terms coexist (AGENTS.md guards, ADRs) risks agents following stale guidance; mitigated by the atomic-changeset rule of D4.
4. **R&S — agent read-access.** Document agent read-only verbs at the Ingress as an intentional design feature, not a permission leak.

## Rejected candidates (summary)

Operator Surface (status quo — collision), Operator Gateway/шлюз (routing/network ambiguity), Console (overstates weight), Portal (blurs end-user UI), Interface (vacuous hypernym), Cockpit/Helm/рубка (EN connotations), Front Desk/Приёмная (frames operator as service consumer), Liaison (wrong relationship), Terminal (conflates component with transport), Facade (architect-only vocabulary), Concierge (no cultural grounding), Operator Ingress variants with bare "вход" (trivial reading).

## Open questions (operator decisions)

- **Renamed (2026-11-18):** code package `operator_surface/` → `operator_ingress/` — APPROVED by operator; executed as a separate implementation changeset (outside Documentation Worker scope). Sub-question raised during planning: whether code-level identifiers (`documenter/.operator_surface_ready` sentinel path, `OPERATOR_SURFACE_SENTINEL`, `COUNCIL_OPERATOR_*` env vars) are renamed too — operator to select identifier policy (see session report options).
- Cite the API-gateway pattern explicitly in the glossary to anchor mental models? (open)
- **Pending operator selection:** ADR historical-text annotation policy — four variants presented in-session (new-ADR alias note / inline parenthetical / full rewrite / deprecation alias stub). Session recommendation: new-ADR alias note + glossary redirect stub; no rewrite of archived session consensus documents (evidence of record).

## Proposed changeset (for operator approval — NOT yet applied)

Via Documentation Worker skill only, after operator step (5) Approve:
1. Rename `docs/en/operator-surface/index.md` → `docs/en/operator-ingress/index.md` (+ RU mirror); update `id`, title, frontmatter; add "formerly Operator Surface" alias note.
2. Glossary: add/replace entry "Operator Ingress" (RU: "Точка входа оператора") with D3 disambiguation text.
3. Update cross-references in: `planned-architecture/index.md`, `layer-2.md`, `execution-runtime/index.md`, `documenter-service/approval-surface.md`, `documenter-service/index.md`, scenario/protocol-core mentions, `AGENTS.md` guard clauses.
4. Regenerate `docs-manifest.yaml` via `tools/gen_manifest.py`.
5. Changelog entries per affected document.
6. (Separate, operator) code package rename; (separate, operator) tool verb names `council.*`/`documenter.*` are a stable API namespace — NOT renamed; event types and error codes unchanged.

## Action items

- Operator: approve/reject changeset; if approved, invoke Documentation Worker skill.
- Operator: decide code package rename and ADR annotation policy.

## Downgraded critical findings (transparency)

None. All critical findings carried valid justifications (Architect: Surface/Approval-Surface collision; R&S: Gateway agent-routing mental model — later downgraded by its author to medium after the targeted round, original text preserved in `review-reliability-security.md`).
