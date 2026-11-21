#!/usr/bin/env bash
set -euo pipefail
# build.sh — assemble a distributable council-dist archive from the current checkout.
# Usage: bash dist/build.sh [VERSION]
#   VERSION defaults to "git describe --tags --always" or "dev".
# Output: dist/out/council-dist-<VERSION>.tar.gz

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION="${1:-$(git -C "$ROOT_DIR" describe --tags --always 2>/dev/null || echo 'dev')}"
OUT_DIR="$SCRIPT_DIR/out"
DIST_NAME="council-dist"
ARCHIVE="$DIST_NAME-$VERSION.tar.gz"

echo "Building Council distribution $VERSION ..."

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR/$DIST_NAME"

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

# Default configs
copy_core "defaults"

# Normative documentation (read-only reference for host projects)
copy_core "docs/en/documentation-rules"
copy_core "docs/en/documenter-service"
copy_core "docs/en/translation-project"
copy_core "docs/en/protocol-core"
copy_core "docs/en/glossary"

# Fallback-mode procedure
copy_core "fallback"

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

copy_template "docs/en/project-concept"
copy_template "docs/en/execution-runtime"
copy_template "docs/en/operator-ingress"
copy_template "docs/en/planned-architecture"
copy_template "docs/en/project-reference"
copy_template "docs/en/scenario"
copy_template "docs/en/selector"
copy_template "docs/en/service-contract"
copy_template "docs/en/archive"
copy_template "CHANGELOGS"

# AGENTS.md is special: it contains project-specific context.  Ship as template.
if [[ -f "$ROOT_DIR/AGENTS.md" ]]; then
  cp "$ROOT_DIR/AGENTS.md" "$OUT_DIR/$DIST_NAME/templates/AGENTS.md.template"
  echo "  [template] AGENTS.md → AGENTS.md.template"
fi

# ---------------------------------------------------------------------------
# Installer & updater scripts
# ---------------------------------------------------------------------------
cp "$SCRIPT_DIR/install.sh" "$OUT_DIR/$DIST_NAME/install.sh"
cp "$SCRIPT_DIR/update.sh"  "$OUT_DIR/$DIST_NAME/update.sh"
chmod +x "$OUT_DIR/$DIST_NAME/install.sh"
chmod +x "$OUT_DIR/$DIST_NAME/update.sh"
echo "  [meta] install.sh, update.sh"

# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------
echo "$VERSION" > "$OUT_DIR/$DIST_NAME/version.txt"
echo "$VERSION" > "$OUT_DIR/$DIST_NAME/core/version.txt"

# Core manifest: list of every file under core/ relative to core/
cd "$OUT_DIR/$DIST_NAME/core"
find . -type f | sed 's|^\./||' > "../core-manifest.txt"
cd "$ROOT_DIR"
echo "  [meta] core-manifest.txt ($(wc -l < "$OUT_DIR/$DIST_NAME/core-manifest.txt") files)"

# ---------------------------------------------------------------------------
# Package
# ---------------------------------------------------------------------------
cd "$OUT_DIR"
tar czf "$ARCHIVE" "$DIST_NAME"

echo ""
echo "Built: $OUT_DIR/$ARCHIVE"
echo "Size:  $(du -h "$OUT_DIR/$ARCHIVE" | cut -f1)"
echo ""
echo "Install (new project):"
echo "  tar xzf $ARCHIVE"
echo "  cd $DIST_NAME"
echo "  bash install.sh --target ../my-project --mode init --project-name my-project"
echo ""
echo "Overlay (existing project):"
echo "  bash install.sh --target /path/to/existing --mode overlay --project-name existing"
