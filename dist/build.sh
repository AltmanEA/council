#!/usr/bin/env bash
set -euo pipefail
# build.sh — assemble a distributable council-dist archive from the current checkout.
# Usage: bash dist/build.sh [VERSION]
#   Bare invocation requires an exact tag (git describe --tags --exact-match);
#   on an untagged commit it exits 1 with a FATAL message.  Pass VERSION
#   explicitly for non-release builds (CI, dry-run) — then no tag is required.
#   Release builds must never be dev-labeled (consensus sess-branch-version-strategy).
# Output: dist/out/council-dist-<VERSION>.tar.gz  +  dist/out/SHA256SUMS
#
# Variant-B composition: see consensus sess-dist-content-review (2026-11-22).
#
# Dirty-tree guard: build.sh refuses to build from a dirty checkout (uncommitted
# changes to tracked files under dist/, staged changes, or untracked files in
# dist/).  Override with COUNCIL_ALLOW_DIRTY=1 (prints a WARNING).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  VERSION=$(git -C "$ROOT_DIR" describe --tags --exact-match 2>/dev/null || true)
  if [[ -z "$VERSION" ]]; then
    echo "FATAL: not on a tagged commit; pass VERSION explicitly for non-release builds" >&2
    exit 1
  fi
fi
OUT_DIR="$SCRIPT_DIR/out"
DIST_NAME="council-dist"
ARCHIVE="$DIST_NAME-$VERSION.tar.gz"

echo "Building Council distribution $VERSION ..."

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR/$DIST_NAME"

# ---------------------------------------------------------------------------
# Dirty-tree guard (Variant-B: per the build spec)
# ---------------------------------------------------------------------------
if [[ "${COUNCIL_ALLOW_DIRTY:-0}" != "1" ]]; then
  DIRTY=0

  # Check uncommitted changes to tracked files under dist/
  if ! git -C "$ROOT_DIR" diff --quiet HEAD -- dist/; then
    echo "FATAL: Uncommitted changes detected in dist/. Commit them before building."
    DIRTY=1
  fi

  # Check staged changes under dist/
  if ! git -C "$ROOT_DIR" diff --cached --quiet HEAD -- dist/; then
    echo "FATAL: Staged changes detected in dist/. Commit them before building."
    DIRTY=1
  fi

  # Check untracked files inside dist/
  UNTRACKED=$(git -C "$ROOT_DIR" ls-files --others --exclude-standard dist/ 2>/dev/null || true)
  if [[ -n "$UNTRACKED" ]]; then
    echo "FATAL: Untracked files in dist/ must be committed or removed before building:"
    echo "$UNTRACKED"
    DIRTY=1
  fi

  if [[ "$DIRTY" -eq 1 ]]; then
    echo "HINT: Set COUNCIL_ALLOW_DIRTY=1 to bypass (for dry-run / CI only)."
    exit 1
  fi
else
  echo "WARNING: COUNCIL_ALLOW_DIRTY=1 — building despite dirty tree (dry-run / CI mode)."
fi

# ---------------------------------------------------------------------------
# CORE: framework files.  These are updated centrally by update.sh.
# ---------------------------------------------------------------------------
mkdir -p "$OUT_DIR/$DIST_NAME/core"

copy_core() {
  local src="$ROOT_DIR/$1"
  if [[ -e "$src" ]]; then
    local dst="$OUT_DIR/$DIST_NAME/core/$(dirname "$1")"
    mkdir -p "$dst"
    cp -R "$src" "$dst/"
    echo "  [core] $1"
  else
    echo "  [core] SKIP (not found): $1"
  fi
}

# Deterministic tools
copy_core "tools"

# Agent skill contract (OpenCode / Claude Code / etc.)
copy_core ".agents"

# Translation engine (vendored, no external registry)
copy_core "vendor"
# Developer-local translator settings are NOT part of the framework.  Shipping
# .env would leak the build machine's endpoint/model and suppress the installer's
# "cp .env.example .env" reminder on the host (RUNBOOK §7).
rm -f "$OUT_DIR/$DIST_NAME/core/vendor/techdoc-translator/.env"
echo "  [core] excluded vendor/techdoc-translator/.env"

# Model-neutral opencode agent definition.  The source repo's
# .opencode/opencode.jsonc pins a local model and is deliberately NOT shipped:
# hosts inherit their own model/provider configuration.
copy_core ".opencode/agents"

# Default configs — Variant-B: only defaults/translation.lock
mkdir -p "$OUT_DIR/$DIST_NAME/core/defaults"
if [[ -f "$ROOT_DIR/defaults/translation.lock" ]]; then
  cp "$ROOT_DIR/defaults/translation.lock" "$OUT_DIR/$DIST_NAME/core/defaults/"
  echo "  [core] defaults/translation.lock"
else
  echo "  [core] SKIP (not found): defaults/translation.lock"
fi
# defaults/policy.yaml is REMOVED per Variant-B (sess-dist-content-review)
echo "  [core] excluded defaults/policy.yaml (Variant-B: policy removed)"

# Normative documentation (read-only reference for host projects)
copy_core "docs/en/documentation-rules"
copy_core "docs/en/documenter-service"
copy_core "docs/en/translation-project"
copy_core "docs/en/protocol-core"
copy_core "docs/en/glossary"

# Archive: only docs/en/archive/index.md (guard file), not the full subtree
# Strip all other archived docs
mkdir -p "$OUT_DIR/$DIST_NAME/core/docs/en/archive"
if [[ -f "$ROOT_DIR/docs/en/archive/index.md" ]]; then
  cp "$ROOT_DIR/docs/en/archive/index.md" "$OUT_DIR/$DIST_NAME/core/docs/en/archive/"
  echo "  [core] docs/en/archive/index.md (guard only)"
else
  echo "  [core] SKIP (not found): docs/en/archive/index.md"
fi
echo "  [core] excluded docs/en/archive/ subtree (Variant-B: archive guard only)"

# Russian mirrors — REMOVED entirely per Variant-B
echo "  [core] excluded docs/ru/ (Variant-B: RU mirrors not shipped)"

# Fallback-mode procedure
copy_core "fallback"

# ---------------------------------------------------------------------------
# Seed changelogs referenced by core doc frontmatter (required for check_all.py
# to pass on fresh host).  These are minimal seed files — the real changelog
# content lives at the repository root (implementation file).
# ---------------------------------------------------------------------------
mkdir -p "$OUT_DIR/$DIST_NAME/core/CHANGELOGS"
SEED_CHANGES="<!-- CHANGES: seed --><!-- CHANGES: v0.0.0: framework seed --><!-- CHANGES: v0.0.1: initial seed -->"
for cl in documentation-rules documenter-service documenter-service-impl-guide glossary protocol-core translation-project; do
  if [[ -f "$ROOT_DIR/CHANGELOGS/${cl}.changes.md" ]]; then
    cp "$ROOT_DIR/CHANGELOGS/${cl}.changes.md" "$OUT_DIR/$DIST_NAME/core/CHANGELOGS/"
    echo "  [core] CHANGELOGS/${cl}.changes.md (seed)"
  else
    echo "<!-- CHANGES: seed -->" > "$OUT_DIR/$DIST_NAME/core/CHANGELOGS/${cl}.changes.md"
    echo "  [core] CHANGELOGS/${cl}.changes.md (seed placeholder)"
  fi
done
echo "  [core] shipped seed CHANGELOGS/ for core doc frontmatter validation"

# ---------------------------------------------------------------------------
# Bytecode exclusion: delete __pycache__ dirs and *.pyc files
# from core/ and templates/ after copying, before manifest generation
# ---------------------------------------------------------------------------
echo ""
echo "Removing bytecode artifacts ..."
find "$OUT_DIR/$DIST_NAME/core" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$OUT_DIR/$DIST_NAME/core" -type f -name "*.pyc" -delete 2>/dev/null || true
echo "  [meta] removed __pycache__ and *.pyc from core/"

# ---------------------------------------------------------------------------
# TEMPLATES: project-specific scaffolding.  Installed once, never updated.
# ---------------------------------------------------------------------------
mkdir -p "$OUT_DIR/$DIST_NAME/templates"

copy_template() {
  local src="$ROOT_DIR/$1"
  if [[ -e "$src" ]]; then
    local dst="$OUT_DIR/$DIST_NAME/templates/$(dirname "$1")"
    mkdir -p "$dst"
    cp -R "$src" "$dst/"
    echo "  [template] $1"
  else
    echo "  [template] SKIP (not found): $1"
  fi
}

# Variant-B: only docs/en/project-concept/.
# Since sess-dist-isolated-install-2026-11-22 follow-up the shipped project
# concept is a NEUTRAL stub from dist/stubs/, not council's own concept doc:
# the host project belongs to the operator, and the stub carries
# {{PROJECT_NAME}} placeholders + TODO markers the installer personalizes.
if [[ -f "$SCRIPT_DIR/stubs/docs/en/project-concept/index.md" ]]; then
  mkdir -p "$OUT_DIR/$DIST_NAME/templates/docs/en/project-concept"
  cp "$SCRIPT_DIR/stubs/docs/en/project-concept/index.md" \
    "$OUT_DIR/$DIST_NAME/templates/docs/en/project-concept/"
  echo "  [template] docs/en/project-concept (neutral stub from dist/stubs)"
else
  copy_template "docs/en/project-concept"
  echo "  [template] WARN: stub missing, shipped council's own concept (defect)"
fi

# Templates for v0.x docs are REMOVED per Variant-B
echo "  [template] excluded docs/en/execution-runtime (Variant-B)"
echo "  [template] excluded docs/en/operator-ingress (Variant-B)"
echo "  [template] excluded docs/en/planned-architecture (Variant-B)"
echo "  [template] excluded docs/en/project-reference (Variant-B)"
echo "  [template] excluded docs/en/scenario (Variant-B)"
echo "  [template] excluded docs/en/selector (Variant-B)"
echo "  [template] excluded docs/en/service-contract (Variant-B)"
echo "  [template] excluded docs/en/archive (Variant-B: archive is core only)"
echo "  [template] excluded CHANGELOGS/ bulk (Variant-B: only project-concept.changes.md)"

# Only CHANGELOGS/project-concept.changes.md ships — the seed stub from
# dist/stubs/ (a single "initial stub" entry), not council's own history.
mkdir -p "$OUT_DIR/$DIST_NAME/templates/CHANGELOGS"
if [[ -f "$SCRIPT_DIR/stubs/CHANGELOGS/project-concept.changes.md" ]]; then
  cp "$SCRIPT_DIR/stubs/CHANGELOGS/project-concept.changes.md" "$OUT_DIR/$DIST_NAME/templates/CHANGELOGS/"
  echo "  [template] CHANGELOGS/project-concept.changes.md (seed stub)"
else
  echo "  [template] SKIP (not found): CHANGELOGS/project-concept.changes.md"
fi

# AGENTS.md is special: it contains project-specific context.  Ship as template.
if [[ -f "$ROOT_DIR/AGENTS.md" ]]; then
  cp "$ROOT_DIR/AGENTS.md" "$OUT_DIR/$DIST_NAME/templates/AGENTS.md.template"
  echo "  [template] AGENTS.md → AGENTS.md.template"
fi

# ---------------------------------------------------------------------------
# Bytecode exclusion for templates/
# ---------------------------------------------------------------------------
find "$OUT_DIR/$DIST_NAME/templates" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$OUT_DIR/$DIST_NAME/templates" -type f -name "*.pyc" -delete 2>/dev/null || true
echo "  [meta] removed __pycache__ and *.pyc from templates/"

# ---------------------------------------------------------------------------
# Installer & updater scripts
# ---------------------------------------------------------------------------
cp "$SCRIPT_DIR/install.sh" "$OUT_DIR/$DIST_NAME/install.sh"
cp "$SCRIPT_DIR/update.sh"  "$OUT_DIR/$DIST_NAME/update.sh"
chmod +x "$OUT_DIR/$DIST_NAME/install.sh"
chmod +x "$OUT_DIR/$DIST_NAME/update.sh"
echo "  [meta] install.sh, update.sh"

# Operator runbook (host-side procedure) — shipped with every archive.
if [[ -f "$SCRIPT_DIR/RUNBOOK.md" ]]; then
  cp "$SCRIPT_DIR/RUNBOOK.md" "$OUT_DIR/$DIST_NAME/RUNBOOK.md"
  echo "  [meta] RUNBOOK.md"
fi

# ---------------------------------------------------------------------------
# Host transformations on staged files (Variant-B)
# ---------------------------------------------------------------------------

# (a) Remove every line matching ^has_translation: from staged EN files
echo ""
echo "Sanitizing has_translation: lines from staged EN files ..."
for f in \
  "$OUT_DIR/$DIST_NAME/core/docs/en/documentation-rules/index.md" \
  "$OUT_DIR/$DIST_NAME/core/docs/en/documenter-service/index.md" \
  "$OUT_DIR/$DIST_NAME/core/docs/en/documenter-service/impl-guide.md" \
  "$OUT_DIR/$DIST_NAME/core/docs/en/protocol-core/index.md" \
  "$OUT_DIR/$DIST_NAME/core/docs/en/glossary/index.md" \
  "$OUT_DIR/$DIST_NAME/templates/docs/en/project-concept/index.md"; do
  if [[ -f "$f" ]]; then
    sed -i '/^has_translation:/d' "$f"
    echo "  [transform] removed has_translation: from $(basename "$(dirname "$f")")"
  fi
done

# (b) Sanitize body-text docs/ru/...md references to placeholder form
#     Regex from tools/check_all.py: _LINK_DOC_PATH_RE
#     Replace concrete docs/ru/<id>/...md with docs/ru/<id>/index-RU.md placeholder
echo ""
echo "Sanitizing docs/ru/ body-text references in all staged .md files ..."
sanitize_ru_refs() {
  local f="$1"
  if [[ -f "$f" ]]; then
    # Replace concrete docs/ru/<something>.md with placeholder docs/ru/<id>/index-RU.md
    # Use [^ ] (non-space) to correctly match paths with hyphens (e.g. protocol-core/index-RU.md)
    # The placeholder uses angle brackets which the link-integrity regex cannot match
    sed -i -E 's|docs/ru/[^ ]+\.md|docs/ru/<id>/index-RU.md|g' "$f"
  fi
}

# Apply to ALL staged shipped .md files (core + templates)
find "$OUT_DIR/$DIST_NAME/core" -type f -name "*.md" -print0 | while IFS= read -r -d '' f; do
  sanitize_ru_refs "$f"
done
find "$OUT_DIR/$DIST_NAME/templates" -type f -name "*.md" -print0 | while IFS= read -r -d '' f; do
  sanitize_ru_refs "$f"
done
echo "  [transform] docs/ru/ concrete paths → docs/ru/<id>/index-RU.md placeholder"

# (c) Remove cross-reference to docs/en/service-contract/error-management.md
#     from documentation-rules/index.md (service-contract removed per Variant-B).
for f in "$OUT_DIR/$DIST_NAME/core/docs/en/documentation-rules/index.md"; do
  if [[ -f "$f" ]]; then
    sed -i '/service-contract\/error-management.md/d' "$f"
    echo "  [transform] removed service-contract cross-ref from documentation-rules"
  fi
done

# (d) Host path remap: AGENTS.md.template and the shipped SKILL.md files are
#     verbatim copies of the SOURCE-REPO layout (tools/, docs/en/<framework-id>/,
#     .agents/skills/), which does not resolve on a host where the framework is
#     isolated under .council/ (sess-dist-isolated-install-2026-11-22).  Without
#     this remap host agents conclude "tools/ and documentation-rules are
#     missing" and try to hand-write the manifest.  The script prefixes every
#     framework path with .council/, adds explicit --root flags to audit and
#     manifest commands (tool defaults would otherwise point at .council/), and
#     appends a layout note to AGENTS.md.template.  Host-owned paths
#     (root docs-manifest.yaml, host docs/en/<id>/, CHANGELOGS/, documenter/)
#     are deliberately left unprefixed.
python3 "$SCRIPT_DIR/remap_host_paths.py" \
  "$OUT_DIR/$DIST_NAME/templates/AGENTS.md.template" \
  "$OUT_DIR/$DIST_NAME/core/.agents/skills/documentation/SKILL.md" \
  "$OUT_DIR/$DIST_NAME/core/.agents/skills/selector/SKILL.md" \
  "$OUT_DIR/$DIST_NAME/core/.opencode/agents/selector.md" \
  --host-note

# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------
echo "$VERSION" > "$OUT_DIR/$DIST_NAME/version.txt"
echo "$VERSION" > "$OUT_DIR/$DIST_NAME/core/version.txt"

# Core manifest: list of every file under core/ relative to core/, with the
# .council/ host prefix baked in (AC-1, sess-dist-isolated-install-2026-11-22).
# The ARCHIVE itself keeps the plain layout under core/; only the manifest is
# prefixed.  install.sh/update.sh derive archive src paths by stripping the
# .council/ prefix from each entry.
cd "$OUT_DIR/$DIST_NAME/core"
find . -type f | sed 's|^\./|\.council/|' > "../core-manifest.txt"
cd "$ROOT_DIR"
echo "  [meta] core-manifest.txt ($(wc -l < "$OUT_DIR/$DIST_NAME/core-manifest.txt") files)"

# ---------------------------------------------------------------------------
# Package
# ---------------------------------------------------------------------------
cd "$OUT_DIR"
tar czf "$ARCHIVE" "$DIST_NAME"

# Checksum generated in the SAME step as the archive — the operator cannot
# forget it.  update.sh verifies it automatically when present next to the
# archive (see dist/RUNBOOK.md §Integrity).
sha256sum "$ARCHIVE" > "SHA256SUMS"

echo ""
echo "Built: $OUT_DIR/$ARCHIVE"
echo "Size:  $(du -h "$OUT_DIR/$ARCHIVE" | cut -f1)"
echo "SHA256: $(cut -d' ' -f1 "SHA256SUMS")"
echo ""
echo "Copy BOTH files to the host and update with:"
echo "  bash .council/update.sh $ARCHIVE"
echo ""
echo "Install (new project):"
echo "  tar xzf $ARCHIVE"
echo "  cd $DIST_NAME"
echo "  bash install.sh --target ../my-project --mode init --project-name my-project"
echo ""
echo "Overlay (existing project):"
echo "  bash install.sh --target /path/to/existing --mode overlay --project-name existing"
