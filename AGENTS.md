# Documentation Agent Instructions (AGENTS.md)
Version: 3.0.0
Status: active
changelog-path: CHANGELOGS/agents.changes.md

This file is the **context router** for AI agents working in this repository. It is not part of the framework itself — it governs the *documentation process* only. The normative documentation rules were relocated to `docs/en/documentation-rules/index.md` (section numbering §2–§8 preserved); this file keeps only what every agent needs: how to *read* documentation, the single write rule, and the safety guards.

---

## 1. Context for All Agents (Reading Documentation)

- The **manifest** (`docs-manifest.yaml`) is the generated index and single source of truth for documentation layout: every project document with path, title, version, status, abstraction, and RU translation path (`has_translation`). Read documentation **only via manifest paths**; do NOT scan the filesystem blindly. Frontmatter is the truth; the manifest is its printout (§2.2 in `documentation-rules`).
- English under `docs/en/<id>/` is authoritative; Russian under `docs/ru/<id>/` is derivative convenience. When documents conflict, apply the Content Authority and Precedence rules in `documentation-rules` §2.7.
- Read the glossary (`docs/en/glossary/index.md`) before using domain terms verbatim.

## 2. The Write Rule (All Changes Go Through the Documentation Worker)

**All changes to documentation artifacts — files under `docs/`, the manifest `docs-manifest.yaml`, and `CHANGELOGS/` — are made exclusively through the Documentation Worker skill** (`/.agents/skills/documentation/SKILL.md`, invoked via `skill("documentation")`), and only after the human operator's step (5) Approve of the proposed changeset (§5.1–§5.2 in `documentation-rules`). No exceptions — even typo fixes require explicit go-ahead after the propose step. Agents MUST NOT edit these files directly, hand-edit the manifest, or dispatch `tools/` write-scripts on their own authority; scripts provide atomicity, not authority.

**The approval carrier is in-chat (OP-1, per sess-documenter-concept-revision 2026-11-19).** Step (5) Approve is the operator's text reply in the same conversation turn — there is no out-of-band consent tool, no approval queue, no gating service. The agent presents a summary card (affected files, change category, line delta, mechanical/semantic classification) with the advisory audit verdict merged in (silent when clean); the operator replies `approve`, and for a **semantic** change must name its object (e.g. `approve: rewrite of the Safety section`). After approval the primary agent lands each logical update as exactly one atomic commit (single-commit invariant); the Documentation Worker assembles the bundle but never commits on its own; errors are recovered by `git revert` after audit, not prevented by gates. The authoritative specification is `docs/en/documenter-service/index.md`.

## 3. Working on Documenter — Required Inputs

Documenter is a thin concept, not a service: an approval loop plus one read-only audit engine. Its normative inputs:

| Input | Path | Covers |
|-------|------|--------|
| Documenter specification | `docs/en/documenter-service/index.md` | OP-1/OP-2/OP-3 principles, operating loop, audit contract, accepted risks, tool inventory |
| Documentation rules (audit target) | `docs/en/documentation-rules/index.md` | the rules `tools/check_all.py` audits against |

The superseded v0.x suite (service, tiers, policy engine, approval surface, MVP contracts) is archived under `docs/en/archive/documenter-service/` — history only, not authority.

---

## 1.5 Project Stage

The Documenter design was reconstructed from scratch on 2026-11-19 (consensus `sess-documenter-concept-revision`, operator decision) under three operator principles: **OP-1** instant operator approval without gating, **OP-2** maximum simplicity, **OP-3** commit audit plus revert as primary error control. The previous machinery — trust tiers, `documenter_policy.yml`, the dual interlock and readiness sentinel, the Operator Ingress service, the consent terminal, the approval surface, the `documenter_service/` package — was deleted (Commits B/A of the revision). The surviving system is: the Documentation Worker skill (sole writer), the deterministic tools under `tools/`, and the read-only audit engine `tools/check_all.py` (exit codes 0/1/2 are informational, never gating; run advisory pre-commit by the agent, post-commit by the operator on demand). `documenter/` holds only translation provenance artifacts.

The code-based Moderator is not yet built. All Council sessions run in fallback mode until a Moderator adapter is available.

**Fallback is frozen.** `fallback/index.md` is operational and is the working mode for development. Do not modify fallback documents as part of remediation, refactoring, or consistency cleanup. Changes require an explicit operator request and a confirmed critical defect.

---

### 1.6 Documentation Separation

Documentation artifacts are divided into two categories based on their role in the project lifecycle:

**Project documents** — specifications and protocols that describe the developing project (Council framework). Stored under `docs/`, tracked by the manifest. Examples: `docs/protocol-core/`, `docs/project-concept/`, `docs/glossary/`.

**Implementation files** — files for the current temporary operation of the Council system. Stored at repository root, excluded from Documenter control. Examples: `AGENTS.md`, `fallback/`, `documenter-service/`, `.agents/skills/documentation/`, `CHANGELOGS/`, `.opencode/`, `defaults/`, `archive/`, `tests/`, `tools/`, `consensus-non-controlled-files.md`, `notes.md`. External repositories owned by the project (e.g. the Translation Project `techdoc-translator`, ADR-014) are likewise implementation artifacts outside Documenter scope; their pinned checkout is recorded in a lock file under `defaults/`, and their internal documentation is governed by their own repository rules.

This separation is documented in the consensus document from session `sess-documentation-separation` (2026-11-09). The manifest (`docs-manifest.yaml`) tracks only project documents under `docs/`. Implementation files are explicitly excluded from Documenter scope.

### 1.7 Tooling Separation

**Operational (available now):**
- Documentation Worker skill (`/.agents/skills/documentation/SKILL.md`) — write and audit operations on documentation artifacts per `documentation-rules` rules; the sole write executor (see §2 Write Rule). The agent runs `tools/check_all.py` as the advisory pre-commit audit (mandatory, silent when clean, never blocking); the operator runs it post-commit on demand and reverts bad commits.

- Translation Project CLI (`techdoc-translator`, external repository) — the EN→RU translation engine, extracted from `tools/` per ADR-014. Operational via its CLI contract (`docs/en/translation-project/`, exit codes 0–6, pinned by `defaults/translation.lock`). The engine knows nothing about Council; the Documentation Worker skill supplies glossary and skip-patterns and owns verification and writes. Council-side translation test suite rebuild is deferred to a dedicated session; provenance artifacts live in `documenter/artifacts/translation/` (operational, git-tracked, never manifest).

- Deterministic tools (`tools/`): `check_all.py` (audit engine), `gen_manifest.py` (sole manifest writer), `check_drift.py`, `docmeta.py`, `bump_version.py`, `classify_bump.py`, `translation_status.py`, `sync_translator.sh`, `check_parity.py`. There is no fixed numeric ceiling on tooling; the operator judges complexity at approval time under OP-1.

**Under development (not yet operational):**
- Code-based Moderator — automated Council session execution. Not yet built (see §1.5); all sessions run in fallback mode.

Prohibition: Do not invoke any `council.*` or equivalent MCP tools while the Moderator is under development. There are no `documenter.*` tools any more — the Documenter service was deleted in the 2026-11-19 reconstruction; do not recreate it (OP-2).

**Prose-contract synchronization.** Behavioral contracts for tools (documented in prose, e.g. the Documentation Worker skill's wrapper contract and `tools/README.md`) are binding: whenever a tool's behavior changes, its prose contracts MUST be reviewed and updated in the same changeset. A prose contract diverging from implementation is a documentation defect (root cause: heading-translation contract breach, sess-translate-automation 2026-11-14; norm ratified sess-prevention-measures 2026-11-14).

---

## Cross-References

- `docs/en/documentation-rules/index.md` — normative documentation rules (§2 organization/manifest, §3 language policy, §4 glossary, §5 workflow and approval, §6 ambiguity, §7 file conventions, §8 compliance)
- `docs-manifest.yaml` — generated index, read-only entry point for all agents
- `.agents/skills/documentation/SKILL.md` — Documentation Worker skill (sole write executor)
- `docs/en/documenter-service/index.md` — Documenter specification (OP-1/OP-2/OP-3, operating loop, audit contract)
- `fallback/index.md` — fallback-mode Council procedure
