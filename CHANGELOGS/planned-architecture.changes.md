<!-- CHANGES v0.17.0: retarget ADR-019/020 references to archive/documenter-service and resolve numeric §3/§4 (low audit cleanup) -->
<!-- CHANGES v0.16.0: Registered ADR-020 runtime activation overlay (external YAML, read-time merge, 4 scope presets, --verify-activation CLI, fail-closed). RU mirror synchronized in same changeset. -->
<!-- CHANGES v0.15.0: Registered ADR-019 code-level identifier cleanup (sentinel path, OPERATOR_INGRESS_SENTINEL, operator_ingress_ready); ADR-018 row corrected -->
<!-- CHANGES v0.2.5: Layer 2 tools parenthetical renamed to Operator Ingress (ADR-018) -->
<!-- CHANGES v0.5.0: Operator Surface section renamed to Operator Ingress; term and cross-reference synchronized (ADR-018) -->
<!-- CHANGES v0.5.0: Layer 2 term renamed Operator Surface to Operator Ingress in diagram and tables (ADR-018) -->
<!-- CHANGES v0.14.0: Registered ADR-018 terminology rename Operator Surface to Operator Ingress; path links updated -->
<!-- CHANGES v0.13.0: AI-2: register ADR-017 solo-operator Tier 2+ bounded experiment (sess-solo-operator-activation 2026-11-17, moderator-confirmed stance d) -->
<!-- CHANGES v0.12.1: Phase 2 (sess-operator-surface-split): ADR-013/ADR-016 where-applied extended with documenter-service/approval-surface.md -->
<!-- CHANGES v0.12.0: Register ADR-016 Tier 2+ Activation Gate Norm (sess-operator-surface-split, operator decision AI-4) -->
<!-- CHANGES v0.11.0: Register ADR-015 (Operator Surface MVP build parameters) from p3-operator-surface-impl-plan -->
<!-- CHANGES v0.10.0: ADR-012 normative-content column retargeted to documentation-rules §3.3 (AGENTS.md router split) -->
<!-- CHANGES v0.9.0: ADR-014 external translation project boundary (sess-translation-extraction) -->
<!-- CHANGES v0.8.0: Registered ADR-013: Documenter Tier 2+ dual interlock amending ADR-007, with provenance paragraph -->
<!-- CHANGES v0.7.0: Register ADR-012: post-Approve automatic RU synchronization (conditional lift of AGENTS.md §3.3 suspension) -->
<!-- CHANGES v0.2.4 (layer-0.md): Removed stray Source: line from body (compliance fix, AGENTS.md §7.2; precedent per earlier stray-metadata fixes) (sess-doc-reliability-algo Stage A). -->
<!-- CHANGES v0.2.4 (layer-1.md): Removed stray Source: line from body (compliance fix, AGENTS.md §7.2) (sess-doc-reliability-algo Stage A). -->
<!-- CHANGES v0.2.4 (layer-2.md): Removed stray Source: line from body (compliance fix, AGENTS.md §7.2) (sess-doc-reliability-algo Stage A). -->
<!-- CHANGES v0.4.3 (layer-2.md): Metadata header migrated to canonical frontmatter (sess-doc-reliability-algo Stage A): id added, Last Modified removed, has_translation/references/allow_non_index_paths migrated from manifest. -->
<!-- CHANGES v0.2.3 (layer-1.md): Metadata header migrated to canonical frontmatter (sess-doc-reliability-algo Stage A): id added, Last Modified removed, has_translation/references/allow_non_index_paths migrated from manifest. -->
<!-- CHANGES v0.2.3 (layer-0.md): Metadata header migrated to canonical frontmatter (sess-doc-reliability-algo Stage A): id added, Last Modified removed, has_translation/references/allow_non_index_paths migrated from manifest. -->
<!-- CHANGES v0.4.3 (index.md): Metadata header migrated to canonical frontmatter (sess-doc-reliability-algo Stage A): id added, Last Modified removed, has_translation/references/allow_non_index_paths migrated from manifest. -->
<!-- CHANGES v0.4.2 (index.md, layer-2.md) and v0.2.2 (layer-0.md, layer-1.md): Metadata versions aligned to manifest (parity fix, post-2cd292f review). Content unchanged. -->
<!-- CHANGES v0.1.1: Resolved readiness finding A-02 — updated Fallback mode table row in §Supporting Services to clarify exemption from SessionManifest requirements (execution-runtime §Namespace Rule). -->
<!-- CHANGES v0.4.1: Moved from root-level `planned-architecture/` to `docs/planned-architecture/` as part of documentation separation (sess-documentation-separation). Path update only, no content change. Includes all sub-documents (layer-0, layer-1, layer-2, decisions/). -->
# Changelog — Planned Architecture Documentation

<!-- CHANGES 0.1.0: initial creation of planned-architecture directory documenting complete accepted platform architecture (multi-layered A with six B-derived integrations). Four files: index (conceptual overview), layer-0/1/2 (protocol specifications), decisions/index (cross-reference to ADR rationale). -->
<!-- CHANGES 0.2.0: Added "Documenter Service" section to layer-2.md, registering Documenter as an independent Layer 2 on-demand documentation utility (audit/delegate interfaces, trust-tier model). Aligns planned-architecture with documenter-service/index.md; ScenarioLoader remains in Layer 1. -->
<!-- CHANGES 0.3.0: Variant C + D3. Layer 1 redefined as Execution Runtime (deterministic Moderator inside orchestrator/, Role Agents + Auxiliary Agents, internal module/import rules, migration path to an Orchestration Core). Layer 2 renamed External Interfaces / Adapters and reduced to transport, ingress validation, error localization, and operator surface; scenario matching, quick-review classification, and checkpoint/resume moved to Layer 1; Documenter section removed. index.md diagram and dependency rules updated; decisions/index.md now defines ADR-001–005 inline because the standalone ADR document is absent. -->
<!-- CHANGES 0.4.0: Resolved readiness finding A-04 — schema migration chain marked deferred until after MVP across all planned-architecture documents. layer-2.md §Schema versioning rewritten to EXTERNAL MAPPER — RESERVED FOR FUTURE USE status. decisions/index.md ADR-005 description updated to reflect deferred decision. Maintains consistency with service-contract which already states "No migration chain ships at MVP". -->
<!-- CHANGES 0.5.0: Layer 0/1/2 + index.md frontmatter migrated to canonical format (sess-doc-reliability-algo Stage A). Added id, removed Last Modified, aligned has_translation/references/allow_non_index_paths. No content changes. -->
<!-- CHANGES 0.6.0: Added `council-distribution` sub-document and §Distribution section in index.md. References list updated. Distribution system specification covers archive-based zero-registry propagation with core/template separation, init/overlay installer, and self-updater. -->
