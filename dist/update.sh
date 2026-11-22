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
#   - Iterates over the UNION of old and new manifests:
#     * Entry in old but not in new → rm -rf from host (orphan removal, MF-3)
#     * Entry in new → copy from archive to host
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
# Integrity: verify archive checksum when SHA256SUMS is present next to it
# ---------------------------------------------------------------------------
# build.sh always produces SHA256SUMS alongside the archive.  Verification is
# automatic (no flag to remember); it is skipped with a loud warning if the
# sidecar file was not copied — see dist/RUNBOOK.md §Integrity.
CHECKSUMS="$(dirname "$ARCHIVE")/SHA256SUMS"
if [[ -f "$CHECKSUMS" ]]; then
  echo "Verifying archive checksum ..."
  if ! (cd "$(dirname "$ARCHIVE")" && sha256sum -c "SHA256SUMS" >/dev/null 2>&1); then
    echo "ERROR: Checksum verification FAILED for $ARCHIVE."
    echo "       The archive is corrupted or has been tampered with.  Refusing to update."
    echo "       Re-copy the archive and SHA256SUMS from the build machine."
    exit 1
  fi
  echo "  Checksum OK ✓"
else
  echo "WARNING: $(dirname "$ARCHIVE")/SHA256SUMS not found — integrity NOT verified."
  echo "         Expected it next to the archive (build.sh generates it automatically)."
fi

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

# PyYAML is required by the core tools shipped with the update
# (gen_manifest.py, docmeta.py, check_all.py).  Failing here beats discovering
# it post-update when the first audit run crashes.
if ! python3 -c "import yaml" 2>/dev/null; then
  echo "ERROR: PyYAML is not installed — Council core tools will not work."
  echo "       Affected after update: tools/check_all.py, tools/gen_manifest.py, tools/docmeta.py"
  echo "       Install it first:  pip install pyyaml"
  exit 1
fi

# ---------------------------------------------------------------------------
# AC-8: Preflight — reject if .council is a symlink or not a directory
# ---------------------------------------------------------------------------
if [ -e ".council" ] && [ ! -d ".council" ] || [ -L ".council" ]; then
  echo "ERROR: .council exists but is not a regular directory (symlink?). Refusing to update."
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
# Backup current core files (union of old + new manifest entries)
# ---------------------------------------------------------------------------
BACKUP_DIR=".council/backup-$(date +%s)"
mkdir -p "$BACKUP_DIR"
echo "Backing up current core files to $BACKUP_DIR ..."

# Collect UNION of old manifest and new manifest entries
OLD_MANIFEST=".council/core-manifest.txt"
NEW_MANIFEST="$NEW_DIR/core-manifest.txt"
UNION_FILE=$(mktemp)
{
  cat "$OLD_MANIFEST" 2>/dev/null || true
  if [[ -f "$NEW_MANIFEST" ]]; then
    cat "$NEW_MANIFEST"
  fi
} | sort -u > "$UNION_FILE"

while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  if [[ -e "$f" ]]; then
    # Strip .council/ prefix to avoid double-nesting in backup
    rel="${f#.council/}"
    mkdir -p "$BACKUP_DIR/$(dirname "$rel")"
    cp -R "$f" "$BACKUP_DIR/$rel" 2>/dev/null || true
  fi
done < "$UNION_FILE"

# Write restore-instructions.txt after entries so restore won't clobber it
RESTORE_CMD="cp -R $BACKUP_DIR/* .council/"
echo "$RESTORE_CMD" > "$BACKUP_DIR/restore-instructions.txt"

# ---------------------------------------------------------------------------
# Apply update — iterate UNION so that files present in old manifest but
# absent from the new one are also removed (MF-3 orphan removal).
# Manifest entries carry .council/ prefix; archive core/ uses plain layout.
# ---------------------------------------------------------------------------
echo "Applying update ..."

while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  src="$NEW_DIR/core/${f#.council/}"
  dst="$f"
  if [[ -e "$src" ]]; then
    mkdir -p "$(dirname "$dst")"
    cp -R "$src" "$dst"
    echo "  [updated] $f"
  else
    # The file is core in the old manifest but absent from the new release:
    # it will be removed.  Loud warning + restore path (backup already made
    # above).  Per operator decision core files are not hand-edited on hosts;
    # if that ever changes, keep a .council/customizations.txt checklist.
    rel="${f#.council/}"  # stripped path for backup reference
    echo "  [removed] $f  (not in new distribution)"
    if [[ -e "$dst" ]]; then
      echo "            It will be DELETED from the host."
      echo "            A copy is preserved at: ${BACKUP_DIR}/${rel}"
      echo "            Restore if needed with: cp -R ${BACKUP_DIR}/${rel} \"$dst\""
    fi
    rm -rf "$dst"
  fi
done < "$UNION_FILE"
rm -f "$UNION_FILE"

# ---------------------------------------------------------------------------
# Skills refresh: copy .agents/skills → .council/skills so opencode.jsonc
# registrations stay in sync with what the manifest installs under .agents/
# ---------------------------------------------------------------------------
if [[ -d ".council/.agents/skills" ]]; then
  rm -rf ".council/skills"
  cp -R ".council/.agents/skills" ".council/skills"
  echo "  [core] re-mapped .council/.agents/skills -> .council/skills"
fi

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
echo "$RESTORE_CMD"
echo ""
