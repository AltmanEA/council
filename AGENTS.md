# Documentation Agent Instructions (AGENTS.md)
Version: 2.2.0
Status: active
changelog-path: CHANGELOGS/agents.changes.md

This file is the **context router** for AI agents working in this repository. It is not part of the framework itself — it governs the *documentation process* only. The normative documentation rules were relocated to `docs/en/documentation-rules/index.md` (section numbering §2–§8 preserved); this file keeps only what every agent needs: how to *read* documentation, the single write rule, and the safety guards.

---

## 1. Context for All Agents (Reading Documentation)

- The **manifest** (`docs-manifest.yaml`) is the generated index and single source of truth for documentation layout: every project document with path, title, version, status, abstraction, and RU translation path (`has_translation`). Read documentation **only via manifest paths**; do NOT scan the filesystem blindly. Frontmatter is the truth; the manifest is its printout (§2.2 in `documentation-rules`).
- English under `docs/en/<id>/` is authoritative; Russian under `docs/ru/<id>/` is derivative convenience. When documents conflict, apply the Content Precedence rules in `service-contract/index.md`.
- Read the glossary (`docs/en/glossary/index.md`) before using domain terms verbatim.

## 2. The Write Rule (All Changes Go Through the Documentation Worker)

**All changes to documentation artifacts — files under `docs/`, the manifest `docs-manifest.yaml`, and `CHANGELOGS/` — are made exclusively through the Documentation Worker skill** (`/.agents/skills/documentation/SKILL.md`, invoked via `skill("documentation")`), and only after the human operator's step (5) Approve of the proposed changeset (§5.1–§5.2 in `documentation-rules`). No exceptions — even typo fixes require explicit go-ahead after the propose step. Agents MUST NOT edit these files directly, hand-edit the manifest, or dispatch `tools/` write-scripts on their own authority; scripts provide atomicity, not authority.

The Documenter Service is *not* the write executor: it is an on-demand audit/preview supporting service (§1.7). Agents that need a documentation change load the skill instruction (the `documentation` skill) and follow its Work Request Contract.

## 3. Working on Documenter — Required Inputs

Developers of the Documenter Service, and the Documenter runtime itself, do **not** use this file as their specification. Their normative inputs live in the Documenter documentation folder:

| Input | Path | Covers |
|-------|------|--------|
| Service specification | `docs/en/documenter-service/index.md` | interfaces `audit()`/`delegate()`, trust tiers, safety protocol |
| MVP implementation contract | `docs/en/documenter-service/mvp-contract.md` | stack, ports, Tier 2+ reserved interfaces, testing |
| Interface schemas | `docs/en/documenter-service/mvp-interfaces.md` | machine-readable schemas, error categories |
| Runtime data models | `docs/en/documenter-service/mvp-data-models.md` | audit registry, token model, policy schema |
| Policy schema | `docs/en/documenter-service/policy-reference.md` | policy fields, authorization workflow |
| Configuration guide | `docs/en/documenter-service/configuration-guide.md` | hash store, intent records, RU alignment |
| Documentation rules (audit target) | `docs/en/documentation-rules/index.md` | the rules Documenter audits against |

The runtime consumes the manifest read-only via the `ManifestSource` port and never writes it.

---

## 1.5 Project Stage

The project has moved from the **Specification** phase to **Specification→MVP implementation started**: per operator decision of 2026-11-12 (ADR-011), implementation of Documenter MVP (Tier 0–1) and `tools/` is approved; the Documenter Tier 2+ write branch is implemented but **dormant behind the dual interlock**, gated exclusively by code-level checks per ADR-016: (a) policy state — `documenter_policy.yml` holds `active_tier: 1` with a null `briefing_ref`; (b) the Operator Ingress readiness sentinel `documenter/.operator_ingress_ready`, currently absent. The Operator Ingress (formerly Operator Surface; renamed per ADR-018; package executed `operator_surface/` → `operator_ingress/` and sentinel path renamed per ADR-019, both 2026-11-18) exists as code (`operator_ingress/`, p3 MVP, 2026-11-15) providing authenticated operator ingress, so the code-existence condition of ADR-013 is satisfied; Tier 2+ remains interlocked because neither code-level gate is open. Activation is an operator act out-of-session. Code implementation beyond that scope (Layer 0+) has not started. The code-based Moderator is not yet built. All Council sessions during this phase run in fallback mode until a Moderator adapter is available.

**Fallback is frozen.** `fallback/index.md` is operational and is the working mode for development. Do not modify fallback documents as part of remediation, refactoring, or consistency cleanup. Changes require an explicit operator request and a confirmed critical defect.

---

### 1.6 Documentation Separation

Documentation artifacts are divided into two categories based on their role in the project lifecycle:

**Project documents** — specifications and protocols that describe the developing project (Council framework). Stored under `docs/`, tracked by the manifest. Examples: `docs/protocol-core/`, `docs/project-concept/`, `docs/glossary/`.

**Implementation files** — files for the current temporary operation of the Council system. Stored at repository root, excluded from Documenter control. Examples: `AGENTS.md`, `fallback/`, `documenter-service/`, `.agents/skills/documentation/`, `CHANGELOGS/`, `.opencode/`, `defaults/`, `archive/`, `tests/`, `tools/`, `consensus-non-controlled-files.md`, `notes.md`. External repositories owned by the project (e.g. the Translation Project `techdoc-translator`, ADR-014) are likewise implementation artifacts outside Documenter scope; their pinned checkout is recorded in a lock file under `defaults/`, and their internal documentation is governed by their own repository rules.

This separation is documented in the consensus document from session `sess-documentation-separation` (2026-11-09). The manifest (`docs-manifest.yaml`) tracks only project documents under `docs/`. Implementation files are explicitly excluded from Documenter scope.

### 1.7 Tooling Separation

Tools are divided into two categories:

**Operational (available now):**
- Documentation Worker skill (`/.agents/skills/documentation/SKILL.md`) — write and audit operations on documentation artifacts per `documentation-rules` rules; the sole write executor (see §2 Write Rule).

- Translation Project CLI (`techdoc-translator`, external repository) — the EN→RU translation engine, extracted from `tools/` per ADR-014. Operational via its CLI contract (`docs/en/translation-project/`, exit codes 0–6, pinned by `defaults/translation.lock`). The engine knows nothing about Council; the Documentation Worker skill supplies glossary and skip-patterns and owns verification and writes. Council-side translation test suite rebuild is deferred to a dedicated session; provenance artifacts live in `documenter/artifacts/translation/` (operational, git-tracked, never manifest).

**Under development (not yet operational):**
- Documenter Service — automated quality auditing and delegated writes. Implementation status (glossary, §Implementation Status): Tier 0–1 surface Operational (CLI and MCP stdio implemented, `documenter_service/` package, covered by tests); the MCP server is **not registered** in the workspace configuration — registration is an explicit operator decision. The Tier 2+ write branch is Dormant behind the dual interlock, gated exclusively by the code-level checks of ADR-016 (policy state plus the readiness sentinel `documenter/.operator_ingress_ready`); both currently deny activation. Agents MUST NOT invoke unregistered `documenter.*` MCP tools, MUST NOT register the MCP server, and MUST NOT edit `documenter_policy.yml` — changing `active_tier`, `allowed_operations`, or `briefing_ref` is an activation act reserved to the operator out-of-session. The Tier 0–1 CLI (`python3 -m documenter_service`) may be used in read-only/preview mode where the operator has sanctioned it.
- Operator Ingress (formerly Operator Surface; renamed per ADR-018) — implementation complete at p3 MVP (`operator_ingress/`, ADR-015/ADR-016): JSON-RPC stdio verbs, pre_check gate, notices, readiness sentinel; creation of the sentinel on successful start is the code-level Tier 2+ condition. The surface is **not registered** in the workspace configuration and the sentinel is not created — runtime state is interlocked. Registration and activation are operator decisions out-of-session (`operator_ingress/REGISTRATION.md`). The code package rename `operator_surface/` → `operator_ingress/` was executed 2026-11-18 as the ADR-018 implementation act, and code-level identifier cleanup (sentinel path `documenter/.operator_ingress_ready`, `OPERATOR_INGRESS_SENTINEL`, `operator_ingress_ready()`) was executed the same day per ADR-019 in the interlock-closed window; stable wire identifiers NOT renamed: env vars, tool verbs, event names, event wire strings ("operator-surface" issuer/actor values).
- Code-based Moderator — automated Council session execution. Not yet built (see §1.5); all sessions run in fallback mode.

Prohibition: Do not invoke any `council.*`, `documenter.*`, or equivalent MCP tools while these services are under development. Enforcement point: the OpenCode workspace configuration (`.opencode/opencode.jsonc`) currently registers no MCP servers for Council or Documenter tools — their absence is the effective guard. Violating this rule without explicit operator approval is a protocol error.

Relationship between the two: the Documentation Worker skill is the executor; Documenter Service (when operational) will act as an intermediary that calls the Documentation Worker on behalf of its caller. A single document update may involve both: Documenter evaluates trust and policy, then invokes the Documentation Worker to perform the mechanical file operations. Both must be referenced separately to avoid confusion.

**Prose-contract synchronization.** Behavioral contracts for tools (documented in prose, e.g. the Documentation Worker skill's wrapper contract and `tools/README.md`) are binding: whenever a tool's behavior changes, its prose contracts MUST be reviewed and updated in the same changeset. A prose contract diverging from implementation is a documentation defect (root cause: heading-translation contract breach, sess-translate-automation 2026-11-14; norm ratified sess-prevention-measures 2026-11-14).

---

## Cross-References

- `docs/en/documentation-rules/index.md` — normative documentation rules (§2 organization/manifest, §3 language policy, §4 glossary, §5 workflow and approval, §6 ambiguity, §7 file conventions, §8 compliance)
- `docs-manifest.yaml` — generated index, read-only entry point for all agents
- `.agents/skills/documentation/SKILL.md` — Documentation Worker skill (sole write executor)
- `docs/en/documenter-service/` — Documenter specifications (§3 above)
- `fallback/index.md` — fallback-mode Council procedure
