#!/usr/bin/env bash
# sync_translator.sh — Update the vendored techdoc-translator distribution.
#
# Reads the Translation Project repository path from the lock file (repo/
# local_path resolution), builds a clean distributable archive, verifies
# checksums, unpacks into vendor/techdoc-translator/, and updates the lock
# file with the new version metadata.
#
# Usage:
#   python3 tools/sync_translator.sh [path/to/techdoc-translator]
#
# If no argument is given, the script uses the repo URL from the lock file
# to locate the local checkout (cloning if absent).
#
# Safety: never modifies the Translation Project repository; only reads from it.
# The vendor/ directory is overwritten atomically (temp + rename).
#
# Exit codes: 0 success, 1 usage error, 2 build/verify failure, 3 lock error.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOCK="$PROJECT_DIR/defaults/translation.lock"
VENDOR="$PROJECT_DIR/vendor/techdoc-translator"

# ── Helpers ──────────────────────────────────────────────────────────────────

parse_lock() {
    # Read scalar fields from the lock file (naive, comment-aware).
    grep -E "^${1}:" "$LOCK" | head -1 | sed 's/^'"$1"': *//'
}

die() { echo "[error] $*" >&2; exit "${2:-1}"; }

# ── Resolve Translation Project path ─────────────────────────────────────────

TT_PATH="${1:-}"
if [ -z "$TT_PATH" ]; then
    # Try the lock file's local_path (if it exists and is a repo)
    LOCK_PATH="$(parse_lock local_path)"
    if [ -d "$LOCK_PATH/.git" ]; then
        TT_PATH="$LOCK_PATH"
    else
        # Fallback: look for a local clone in common locations
        TT_PATH="/home/ea/techdoc-translator"
        if [ ! -d "$TT_PATH/.git" ]; then
            TT_PATH="$PROJECT_DIR/_vendor/techdoc-translator"
        fi
    fi
fi

[ -d "$TT_PATH/.git" ] || die "not a git repo: $TT_PATH"

# ── Build archive ────────────────────────────────────────────────────────────

ARCHIVE="$(mktemp -d)/dist.tar.gz"
trap 'rm -rf "$(dirname "$ARCHIVE")"' EXIT

echo "[sync] building archive from $TT_PATH"
(
    cd "$TT_PATH"
    scripts/build_dist.sh --version "$(git describe --tags --always --dirty 2>/dev/null || echo unknown)"
    # Copy the built archive to our temp location
    cp dist/*.tar.gz "$ARCHIVE"
)

[ -f "$ARCHIVE" ] || die "archive not built", 2

# ── Verify archive ───────────────────────────────────────────────────────────

# Extract and verify checksums
VERIFY_DIR="$(mktemp -d)"
trap 'rm -rf "$(dirname "$ARCHIVE")" "$VERIFY_DIR"' EXIT
(
    cd "$VERIFY_DIR"
    tar -xzf "$ARCHIVE"
    ROOT="$(ls -d techdoc-translator-*/)"
    [ -n "$ROOT" ] || die "empty archive", 2
    cd "$ROOT"
    sha256sum -c SHA256SUMS || die "SHA256SUMS verification failed", 2
    bash tests/smoke.sh || die "smoke tests failed", 2
    # Print manifest for the log
    cat MANIFEST.txt
)

echo "[sync] archive verified"

# ── Unpack into vendor/ atomically ──────────────────────────────────────────

TEMP_VENDORDIR="$VENDOR.tmp.$$"
trap 'rm -rf "$TEMP_VENDORDIR" "$(dirname "$ARCHIVE")" "$VERIFY_DIR"' EXIT

(
    cd "$VERIFY_DIR"
    ROOT="$(ls -d techdoc-translator-*/)"
    rm -rf "$TEMP_VENDORDIR"
    cp -a "$ROOT" "$TEMP_VENDORDIR"
    # Ensure .env.example is present (it's part of the archive)
    [ -f "$TEMP_VENDORDIR/.env.example" ] || die ".env.example missing from archive", 2
    chmod +x "$TEMP_VENDORDIR/translate.sh" "$TEMP_VENDORDIR/tests/smoke.sh"
)

# Atomic rename (same filesystem, cross-dir)
if [ -d "$VENDOR" ]; then
    rm -rf "$VENDOR"
fi
mv "$TEMP_VENDORDIR" "$VENDOR"

# Ensure .env exists from example (if not already present)
if [ ! -f "$VENDOR/.env" ]; then
    cp "$VENDOR/.env.example" "$VENDOR/.env"
    echo "[sync] copied .env.example → .env (edit with your config)"
fi

# ── Update lock file ─────────────────────────────────────────────────────────

VERSION="$(grep '^VERSION=' "$VENDOR/MANIFEST.txt" | cut -d= -f2)"
COMMIT="$(grep '^GIT_COMMIT=' "$VENDOR/MANIFEST.txt" | cut -d= -f2)"
CONTRACT="$(grep '^CONTRACT_VERSION=' "$VENDOR/MANIFEST.txt" | cut -d= -f2)"

# Preserve existing fields, update version-related ones
sed -i "s/^tag:.*/tag: $VERSION/" "$LOCK"
sed -i "s/^commit:.*/commit: $COMMIT/" "$LOCK"
sed -i "s/^contract_version:.*/contract_version: $CONTRACT/" "$LOCK"
sed -i "s/^local_path:.*/local_path: vendor\/techdoc-translator/" "$LOCK"

echo "[sync] updated $LOCK (version=$VERSION, commit=$COMMIT, contract=$CONTRACT)"
echo "[sync] done: $VENDOR"
