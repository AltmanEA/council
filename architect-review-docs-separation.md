# Architect Review

## Summary Position

**Agree in principle, but the proposal as stated contains several structural risks that must be addressed in the execution plan.** The separation of project documents from implementation files is architecturally sound and reduces coupling, but the path convention system and cross-reference model need stronger design to survive the move without cascading changes.

---

## Key Findings

### [high] Cross-references rely on fragile relative paths that will break on directory move

Multiple documents use `../` relative paths to reference other documents:

- `fallback/index.md` line 12: references `../protocol-core/index.md`
- `fallback/index.md` line 138: references `../protocol-core/index.md`
- `fallback/index.md` line 144: references `../protocol-core/index.md`
- `fallback/index.md` line 167: references `../protocol-core/index.md`, `../glossary/index.md`
- `planned-architecture/layer-0.md` line 9: `Source: ../index.md`
- `planned-architecture/layer-1.md` line 9: `Source: ../index.md`
- `planned-architecture/layer-2.md` line 9: `Source: ../index.md`
- `planned-architecture/layer-2.md` line 78: references `../documenter-service/index.md`
- `planned-architecture/index.md` line 70: references `layer-0.md`, `layer-1.md`, `layer-2.md`, `decisions/index.md`

This creates **bidirectional coupling**: every move of a source document requires updating all consumer references. The canonical identifier system (§2.3 — "Documents reference others by canonical identifier") is conceptually correct but is inconsistently applied in practice.

**Risk:** If only some cross-references are converted to canonical identifiers during the move, the remaining relative paths become time bombs that will break in future directory restructuring.

### [high] Three documents already exceed the 200-line limit; the move amplifies split urgency

Per the manifest compliance notes and line counts:
- `service-contract/index.md` — **280 lines** (format abstraction, primarily schema tables)
- `protocol-core/index.md` — **205 lines** (protocol core, primarily phase procedures)
- `operator-surface/index.md` — **206 lines** (operator surface, primarily transport/verbs)

`planned-architecture/layer-0.md` (66 lines) and `layer-1.md` (86 lines) are under the limit, but they reference `protocol-core/index.md` in their source line (e.g., line 9: `Source: ../index.md`). The `Source:` field on layer-*.md files is an internal linking convention within the multi-document folder and needs resolution regardless.

`documenter-service/configuration-guide.md` at 211 lines is already flagged in the manifest compliance notes — this is a non-index file under `allow_non_index_paths: true` and is excluded from splitting scope for this session.

**Risk:** Moving documents deeper into `docs/<id>/` does not reduce line count, but the reorganization creates a natural opportunity to split. Delaying splits until after the move creates a second wave of file churn (move → split → update all cross-references again).

### [medium] Skill activation list (§Activation) must be updated as a single source of truth

The skill file (`.agents/skills/documentation/SKILL.md`, line 20) lists:

```
AGENTS.md, glossary/, project-concept/, protocol-core/, backlog/, fallback/, scenario/, project-reference/, service-contract/, execution-runtime/, operator-surface/, documenter-service/, planned-architecture/
```

After the move, this becomes:

```
AGENTS.md, docs/glossary/, docs/project-concept/, docs/protocol-core/, docs/backlog/, docs/scenario/, docs/project-reference/, docs/service-contract/, docs/execution-runtime/, docs/operator-surface/, fallback/, documenter-service/, planned-architecture/
```

But `fallback/` and `documenter-service/` are explicitly **excluded from Documenter control** per the proposal. The activation list would then need to become a **glob pattern** rather than a linear list, because:
1. New documents added under `docs/` should automatically activate the skill without updating the list.
2. Root-level implementation files must NOT activate the skill.

**Current approach:** The list must be manually updated every time a new document folder is created — but the proposal says new documents go under `docs/<id>/`. If the activation list is still a linear list, it must be updated every time, which is the same fragility the manifest solves for content operations.

**Recommendation:** Change activation from a linear path list to a directory-pattern match: "Documents within the `docs/` directory and root-level `AGENTS.md`."

### [medium] Manifest entry for root-level documents needs explicit scoping

The current manifest includes:
- `AGENTS.md` (id: `agents`, path: `AGENTS.md`)
- `fallback/index.md` (id: `fallback-mode`, path: `fallback/index.md`)
- All `documenter-service/*` entries (id: `documenter-service`, `documenter-policy-reference`, `documenter-configuration-guide`)

Per the proposal:
- `AGENTS.md` stays at root (document describes the process, not the product)
- `fallback/` and `documenter-service/` are excluded from Documenter control

**Questions:**
1. Should `AGENTS.md` remain in the manifest? It is operational rules, not a project document. If it stays, the manifest becomes a hybrid of project documents AND operational rules, weakening its "single source of truth for project documentation" purpose.
2. Should `fallback-mode` remain in the manifest? It is frozen (§1.5) and excluded from Documenter control. If it's in the manifest, the compliance checker will attempt to audit a frozen document.
3. Should `documenter-service/*` entries remain in the manifest? They are excluded from Documenter control.

**Recommendation:** Remove `AGENTS.md`, `fallback-mode`, and all `documenter-service` entries from the manifest. They are operational/implementation artifacts, not project documentation subject to Documenter governance. Their existence is a file-system fact, not a manifest entry.

### [medium] Changelog storage location is ambiguous post-move

AGENTS.md §2.5 states: `CHANGELOGS/<id>.changes.md` — relative to the repository root. If the document moves to `docs/protocol-core/index.md`, should the changelog follow (i.e., `CHANGELOGS/protocol-core.changes.md` at root stays the same) or should it move to `docs/CHANGELOGS/protocol-core.changes.md`?

The proposal doesn't specify changelog location. Keeping changelogs at `CHANGELOGS/` (root) is the simpler approach, as:
1. It avoids embedding a `CHANGELOGS/` directory inside `docs/`, which adds nesting.
2. The `changelog-path:` field in each document's metadata already carries the full path to the changelog, so the relationship is explicit, not implicit.
3. Changelogs are versioned separately per document; grouping them at root is an organizational convenience, not a structural requirement.

**Recommendation:** Explicitly state that changelog files remain at `CHANGELOGS/` (repository root), referenced via the `changelog-path:` metadata field. This is consistent with §2.5's existing description.

### [low] Multi-document folders need explicit policy update

The `planned-architecture/` folder contains `index.md`, `layer-0.md`, `layer-1.md`, `layer-2.md`, and `decisions/index.md`. The proposal lists it as a project document (moved to `docs/`), and `allow_non_index_paths: true` is already set in the manifest. The `layer-*.md` files reference `Source: ../index.md` which is their parent within the folder.

This pattern is already documented in §2.1 as a "multi-document exception." Moving the entire folder to `docs/planned-architecture/` works without additional changes — the internal `../index.md` references within the folder are preserved.

**No action needed**, but the AGENTS.md §2.1 examples should be updated to show `docs/protocol-core/index.md` rather than `protocol-core/index.md`.

### [low] `Source:` metadata field on layer-*.md files

The `planned-architecture/layer-0.md`, `layer-1.md`, and `layer-2.md` files all contain:

```
Source: ../index.md (planned-architecture)
```

This is an internal linking convention within the folder, not part of the standard metadata defined in §7.2. It serves as a cross-reference anchor for readers navigating the multi-document folder. Moving the folder does not change this reference, but the convention should either be formalized in AGENTS.md or eliminated in favor of the canonical identifier system.

---

## Recommendations

1. **Eliminate all `../` relative cross-references between documents and replace with canonical identifiers.** This is the most impactful architectural improvement that should happen alongside the move. Every cross-document reference should use the form `protocol-core` (the document's manifest id), with stable anchor links to headings. The manifest already serves as the resolution table for id → path.

2. **Change skill activation from linear list to directory-pattern.** The activation condition should be: "files within the `docs/` directory, plus root-level `AGENTS.md`." This makes the activation list self-maintaining — new documents under `docs/` automatically activate the skill, and implementation files at root never do.

3. **Remove implementation artifacts from the manifest.** The manifest should track only project documents (Council framework), not operational or implementation files. Remove `AGENTS.md`, `fallback-mode`, and all `documenter-service` entries. If they must be discoverable, they should live under `AGENTS.md` §7.1's operational file enumeration rather than in the manifest.

4. **Explicitly state changelog storage location as `CHANGELOGS/` at repository root.** The `changelog-path:` metadata field in each document already carries the full path; the manifest and AGENTS.md should both confirm this as the canonical location. No need to nest changelogs under `docs/`.

5. **Address line-limit escalations (protocol-core, service-contract, operator-surface) either before or during the move.** Do a separate move → restructure → split sequence rather than move → split → move. The natural split points are:
   - `service-contract`: split schema tables from policy text (format → reference)
   - `protocol-core`: split role model from interaction protocol (conceptual → protocol)
   - `operator-surface`: split transport/auth from escalation/documenter sections (protocol → reference)

6. **Formalize or eliminate the `Source:` field on `layer-*.md` files.** Either add it to AGENTS.md §7.2 as an accepted metadata convention, or convert these to canonical identifier cross-references (e.g., `planned-architecture`).

---

## Open Questions

1. **Why keep AGENTS.md in the manifest?** It is operational rules for the documentation process, not a Council framework document. Removing it clarifies the manifest's scope but may cause confusion if the skill's compliance checks still need to reference AGENTS.md itself. Is this a manifest concern or an AGENTS.md concern?

2. **Should fallback-mode and documenter-service have separate non-manifest registration?** If they must be discoverable for audit purposes, perhaps via a `non-manifest-documents` section in AGENTS.md rather than polluting the primary manifest.

3. **What is the target version bump for the manifest after the move?** Moving every document path is a structural change (minor version bump per §7.5), but it doesn't change content. What version convention applies to manifest structural changes?

4. **Who maintains the new `docs/` directory boundary?** The manifest is the single source of truth for documents, but `docs/` is an implicit filesystem constraint. If someone creates a new document folder outside `docs/` and registers it in the manifest, the skill's activation pattern needs to handle it. Should the constraint be explicit (AGENTS.md says "all documents MUST be under `docs/`") or implicit (skill activation via `docs/` directory)?

5. **How does `consensus-non-controlled-files.md` fit?** This file at the root is not listed in the proposal's exclusion list. Is it also an implementation artifact, or does it need special handling?

---

## Status

**agree** (with the above implementation requirements).

The separation itself is architecturally correct and reduces coupling between project documentation and implementation artifacts. The concerns identified are about execution safety, not about the strategic direction. The recommended changes ensure the move is a single wave of structural change, not two waves (move → split) that amplify the risk of broken references and manifest drift.
