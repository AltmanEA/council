#!/usr/bin/env bash
set -euo pipefail
# update.sh — update the Council framework core files in a host project.
# This script is copied into .council/update.sh during installation.
#
# Usage:
#   cd <host-project>
#   bash .council/update.sh <path-to-council-dist-X.Y.Z.tar.gz>
#
# Behavior:
#   - Reads .council/core-manifest.txt to know which paths are "core".
#   - Reads .council/version.lock to know the current version.
#   - Backs up every core file to .council/backup-<timestamp>/ before overwriting.
#   - Only overwrites files listed in the old core-manifest.
#   - Never touches project-specific templates (docs/en/project-concept, etc.).

ARCHIVE="${1:-}"
FORCE=0

usage() {
  cat <<EOF
Usage: update.sh <path-to-council-dist-X.Y.Z.tar.gz> [--force]

  --force   Apply update even if version matches current
EOF
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=1; shift ;;
    -h|--help) usage ;;
    *) ARCHIVE="$1"; shift ;;
  esac
done

[[ -z "$ARCHIVE" ]] && { echo "ERROR: Archive path required"; usage; }
[[ -f "$ARCHIVE" ]] || { echo "ERROR: Archive not found: $ARCHIVE"; exit 1; }

# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------
if [[ ! -f ".council/version.lock" ]]; then
  echo "ERROR: This does not appear to be a Council project."
  echo "       Missing: .council/version.lock"
  exit 1
fi

if [[ ! -f ".council/core-manifest.txt" ]]; then
  echo "ERROR: Missing .council/core-manifest.txt"
  echo "       Cannot determine which files are safe to update."
  exit 1
fi

CURRENT_VERSION=$(cat .council/version.lock)
echo "Current Council version: $CURRENT_VERSION"

# ---------------------------------------------------------------------------
# Unpack new archive
# ---------------------------------------------------------------------------
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "Unpacking $ARCHIVE ..."
tar xzf "$ARCHIVE" -C "$TMPDIR"

NEW_DIR=$(find "$TMPDIR" -maxdepth 2 -type d -name "council-dist" | head -1)
if [[ -z "$NEW_DIR" ]]; then
  # Some tar layouts put files directly under a single top-level directory
  NEW_DIR=$(find "$TMPDIR" -maxdepth 1 -type d | tail -1)
fi
if [[ ! -f "$NEW_DIR/version.txt" ]]; then
  echo "ERROR: Archive does not contain a valid council-dist/version.txt"
  exit 1
fi

NEW_VERSION=$(cat "$NEW_DIR/version.txt")
echo "New Council version:   $NEW_VERSION"

if [[ "$CURRENT_VERSION" == "$NEW_VERSION" && "$FORCE" == "0" ]]; then
  echo "Already up to date. Use --force to re-apply."
  exit 0
fi

# ---------------------------------------------------------------------------
# Backup current core files
# ---------------------------------------------------------------------------
BACKUP_DIR=".council/backup-$(date +%s)"
mkdir -p "$BACKUP_DIR"
echo "Backing up current core files to $BACKUP_DIR ..."

while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  if [[ -e "$f" ]]; then
    mkdir -p "$BACKUP_DIR/$(dirname "$f")"
    cp -R "$f" "$BACKUP_DIR/$f" 2>/dev/null || true
  fi
done < .council/core-manifest.txt

# ---------------------------------------------------------------------------
# Apply update
# ---------------------------------------------------------------------------
echo "Applying update ..."

# Read the new core manifest (if present) or fall back to old one
NEW_MANIFEST="$NEW_DIR/core-manifest.txt"
MANIFEST=".council/core-manifest.txt"
if [[ -f "$NEW_MANIFEST" ]]; then
  MANIFEST="$NEW_MANIFEST"
fi

while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  src="$NEW_DIR/core/$f"
  dst="./$f"
  if [[ -e "$src" ]]; then
    mkdir -p "$(dirname "$dst")"
    cp -R "$src" "$dst"
    echo "  [updated] $f"
  else
    echo "  [removed] $f (not in new distribution)"
    rm -rf "$dst"
  fi
done < "$MANIFEST"

# ---------------------------------------------------------------------------
# Update metadata
# ---------------------------------------------------------------------------
cp "$NEW_DIR/version.txt" .council/version.lock
if [[ -f "$NEW_DIR/core-manifest.txt" ]]; then
  cp "$NEW_DIR/core-manifest.txt" .council/core-manifest.txt
fi
# Refresh updater script itself
if [[ -f "$NEW_DIR/update.sh" ]]; then
  cp "$NEW_DIR/update.sh" .council/update.sh
  chmod +x .council/update.sh
fi

echo ""
echo "========================================"
echo "Update complete"
echo "========================================"
echo "  $CURRENT_VERSION → $NEW_VERSION"
echo "  Backup: $BACKUP_DIR"
echo ""
echo "If anything breaks, restore with:"
echo "  cp -R $BACKUP_DIR/* ."
echo ""
