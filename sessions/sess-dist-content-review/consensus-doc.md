# Consensus Document — Distribution Content Composition Review

Session: sess-dist-content-review
Date: 2026-11-22
Mode: fallback (fallback/index.md), operator as fallback Moderator, primary agent facilitating
Roles: Architect, Reliability & Security Specialist, Human-Centric Designer, Operations Engineer
Rounds: 2 (individual review + one discussion round)
Final statuses: Architect concerns / Reliability concerns / HCD agree / Operations concerns — no blocked-escalation at close.

## Context

Task: determine what the Council distribution (dist/) must contain (core/ + templates/).
Trigger: install into /home/ea/ai_tutor revealed obsolete v0.x content, build artifacts,
and council project history shipped as host scaffolding; release v0.1.0-4-gc0e27a5 built
from a dirty working tree.

## Moderator factual corrections (verified by execution, binding for the decisions)

- MF-1 (SUBJ-008): `vendor/techdoc-translator/.env.example` EXISTS in repo and dist
  (initial "missing" report was an `ls` without `-a` artifact). Non-defect.
- MF-2 (SUBJ-010): `check_all.py` rule `docs-manifest-link` hard-fails when a
  `has_translation` path (EN frontmatter) OR a body reference to `docs/ru/...`
  (e.g. documentation-rules/index.md lines 27/70) points to a missing file.
  Verified: deleting docs/ru and regenerating the manifest produced 20 HIGH findings,
  exit 2. Full shipped set passes (exit 0). Half-cut RU fails. Zero-RU is clean ONLY
  with a council docs changeset stripping has_translation AND body RU references.
- MF-3 (SUBJ-007): update.sh applies only entries of the NEW core-manifest
  (dist/update.sh lines 143–164); files present in the OLD manifest but absent from
  the new one are never iterated — shipped `__pycache__/*.pyc` can never be centrally
  removed. The `[removed]` comment (lines 152–156) describes semantics the code does
  not implement (prose↔code divergence, AGENTS.md §1.7). Ops round-1 finding stands;
  Reliability round-2 contrary claim is refuted by code.
- MF-4 (SUBJ-009): v0.1.0-4-gc0e27a5 was assembled from a dirty tree; the dirty edits
  are in dist/*.sh themselves — shipped script behavior matches no commit.
- MF-5 (installer): install.sh printed "installed successfully" with exit 0 while
  core/ and templates/ were entirely absent (observed on a real host). gen_manifest
  failure is swallowed by `>/dev/null 2>&1` (install.sh line 236).

## Decisions (subjects with outcomes)

### Agreed (unanimous or converged)

- SUBJ-001 core EN docs — AGREED. Keep as-is: documentation-rules, documenter-service
  (+impl-guide), translation-project, protocol-core, glossary.
- SUBJ-002 docs/en/archive/ — AGREED: exclude from dist (council history, not host
  scaffolding). Also exclude its RU mirror.
- SUBJ-004 v0.x specs (execution-runtime, operator-ingress, planned-architecture,
  scenario, service-contract) — AGREED: DELETE from build.sh templates list.
  Not templates (frozen obsolete on hosts forever), not core (semantically council
  project docs, no live consumer). Recovery = git history.
  Scope note (Ops): protects future hosts; existing v0.1.0 hosts keep inert copies
  in local templates/ (never read by tools, untouched by update.sh) — accepted as
  harmless, no migration action.
  Precondition (Architect/RSS/HCD): shipped remaining docs verified to carry no
  references to the removed set — safe for audits.
- SUBJ-005 CHANGELOGS/ — AGREED: drop all 26 council changelogs from templates.
  Ship only empty seeds for docs the templates actually install (with pruned
  templates = 1 seed: CHANGELOGS/project-concept.changes.md). Hosts create further
  seeds as they author docs.
- SUBJ-006 defaults/policy.yaml — AGREED: exclude (orphaned, self-declared "do not
  re-add without a live consumer"). Keep defaults/translation.lock.
- SUBJ-007 pyc hygiene — AGREED: (a) build.sh excludes __pycache__/*.pyc from core
  and from core-manifest.txt; (b) install.sh cleanup `rm -rf **/__pycache__` for
  already-dirty hosts; (c) follow-up: fix or annotate update.sh [removed] prose↔code
  divergence (MF-3).
- SUBJ-008 — CLOSED as non-defect (MF-1).
- SUBJ-009 release integrity — AGREED: mandatory pre-build guard in build.sh
  (`git diff --quiet` on dist/ + working tree clean check; refuse dirty builds).
  Ops demoted from escalation to blocking-in-scope: process fix, no design decision.
- Installer hard-fail (from HCD, endorsed by Ops, uncontested) — AGREED as part of
  the current changeset: install.sh exits 1 when core/ (or templates/) absent from
  the distribution; gen_manifest error surfaced instead of swallowed; success banner
  only after verifying key files (.council/update.sh, tools/check_all.py,
  .agents/skills/documentation/SKILL.md).

### Operator decision required (disagreement per Conflict Aggregation Rule 2)

- SUBJ-003 docs/ru/ mirrors — three viable options, roles split; recommendation
  noted per role:
  - A. Selective-5 RU mirrors (documentation-rules, glossary, protocol-core,
    documenter-service, translation-project). Ops: RECOMMENDED. RSS: acceptable.
    Cost: 5 build.sh lines; ~150 KB/host; no council docs changeset.
    Coupling risk: shipped EN docs' has_translation/body refs must stay a subset of
    the copied set — mitigation option: derive copy list from shipped EN frontmatter
    instead of hardcoding.
  - B. Zero RU — strip has_translation from shipped EN docs + remove body RU refs
    from documentation-rules (9 occurrences) + language-policy adjustment.
    Architect/HCD: prefer (OP-2, manifest honesty). Cost: full council docs
    changeset via Documentation Worker + operator approval BEFORE the dist can ship
    (MF-2); highest upfront ops cost, cleanest steady state.
  - C. Full RU keep (current behavior). Architect: acceptable only as all-or-nothing.
    Cost: 580 KB/host including RU of removed v0.x docs — requires pruning RU set to
    avoid shipping RU mirrors of EN docs that no longer ship (partial by definition;
    weakest option).
- Q1 (SUBJ-004 delete vs promote) — CLOSED in-round: converged on DELETE; recorded
  for operator confirmation only.

## Role reservations (tied to subjects)

- Architect: opposes half-measures on SUBJ-003 (ship-all or ship-none + strip); the
  current selective variants risk frontmatter↔copied-set drift (mitigation above).
- Reliability: deletion of v0.x specs contingent-firm — ship them again only if the
  v0.x architecture becomes operational again.
- HCD: installer false-success fix is release-blocking (non-negotiable position);
  accepted RU=0 trade-off for Russian-speaking onboarding given on-demand
  translation via vendored engine.
- Operations: SUBJ-009 guard must land in this release; recommends selective-5;
  vendor/ kept complete except __pycache__.

## Critical findings downgraded for justification issues

- None downgraded. (Reliability SUBJ-004 CRITICAL retained; Ops contextualized
  blast radius — new hosts only — severity not reduced.)

## Action items (after operator decision)

1. build.sh: dirty-tree guard; prune __pycache__; drop archive from copy_template;
   drop 5 v0.x specs; drop CHANGELOGS bulk (emit 1 seed); drop policy.yaml;
   RU handling per operator choice (A/B/C).
2. install.sh: hard-fail on missing core//templates; surface gen_manifest errors;
   post-install verification before success banner; __pycache__ cleanup pass.
3. update.sh: reconcile [removed] comment with implemented behavior (MF-3) or fix
   the loop to diff old−new manifest for removals.
4. Rebuild from a CLEAN tagged tree; re-run dist/test-dry-run.sh; verify fresh-host
   check_all.py exit 0; publish with SHA256SUMS.
5. If option B chosen: Documentation Worker changeset (strip has_translation +
   body refs) — proposed as separate docs changeset requiring operator Approve.
6. Existing host /home/ea/ai_tutor: after new release, `bash .council/update.sh`
   applies core fixes; leftover inert v0.x files in local templates/ may be removed
   manually.
