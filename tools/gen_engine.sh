#!/usr/bin/env bash
set -euo pipefail
# gen_engine.sh — materialize the engine: extract a source subtree of a git ref.
#
# Usage: bash tools/gen_engine.sh <tag-or-ref> [target-dir] [--path DIR/]
#
# Extracts ONLY files under the source directory (default: fallback/; use
# --path draft/ for dogfood engines) from the given git ref using git plumbing
# (no working-tree reads).  Each .md file receives an ENGINE header as its
# first line.  A DIST-SOURCE manifest is written with tag, tree, commit,
# and generated timestamp.
#
# Version naming:
#   exact tag  → .engine/<tag>/
#   non-tag ref → .engine/<short-sha>/
#
# Idempotent: full rebuild each run (removes target dir first).
#
# Exit codes:
#   0  success
#   2  usage error — missing argument, unknown ref, or ref without source path

die() { echo "gen_engine: $*" >&2; exit 2; }

# --- argument validation ---------------------------------------------------
[[ $# -ge 1 ]] || die "missing argument: usage gen_engine.sh <tag-or-ref> [target-dir] [--path DIR/]"
REF="$1"
shift
SOURCE_PATH="fallback/"
TARGET_DIR=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --path)
            [[ $# -ge 2 ]] || die "--path requires an argument (e.g. draft/)"
            SOURCE_PATH="$2"
            shift 2
            ;;
        *)
            [[ -z "$TARGET_DIR" ]] || die "unexpected argument: $1"
            TARGET_DIR="$1"
            shift
            ;;
    esac
done
# Normalize: ensure trailing slash, no leading slash
SOURCE_PATH="${SOURCE_PATH#/}"
SOURCE_PATH="${SOURCE_PATH%/}/"

# Resolve repo root from the caller's working directory (cwd).
# This allows the script to work in any git repo, not only from the council repo.
ROOT_DIR=$(git -C . rev-parse --show-toplevel 2>/dev/null) || die "not inside a git repository (no --root flag)"

# --- verify ref exists -----------------------------------------------------
if ! git -C "$ROOT_DIR" rev-parse -q --verify "$REF" >/dev/null 2>&1; then
    die "unknown ref: $REF"
fi

# --- resolve commit sha for DIST-SOURCE header and DIST-SOURCE -------------
# Peel annotated tags: rev-parse "$REF" would yield the TAG-OBJECT sha for
# annotated tags (v1-stable/v1-latest are annotated), which then makes
# check_engine_sync.py report a false MISMATCH against ^{commit}.
COMMIT_SHA=$(git -C "$ROOT_DIR" rev-parse "$REF^{commit}" 2>/dev/null) || die "cannot resolve commit sha for ref: $REF"
SHORT_SHA="${COMMIT_SHA:0:7}"

# --- determine engine version and target dir -------------------------------
# Operator decision 4 (sess-branch-version-strategy): the engine directory is
# named by an immutable identifier — an exact semver-shaped tag or the short
# commit sha.  Moving/anchor aliases (v1-latest, v1-stable, v2-pre-dev) must
# never appear in the path; they are recorded in DIST-SOURCE tag= only.
if TAG=$(git -C "$ROOT_DIR" describe --tags --exact-match "$REF" 2>/dev/null); then
    case "$TAG" in
        v1-latest|v1-stable|v2-pre-dev) VERSION="$SHORT_SHA" ;;  # alias → short sha
        *) VERSION="$TAG" ;;
    esac
else
    VERSION="$SHORT_SHA"
fi

if [[ -z "$TARGET_DIR" ]]; then
    TARGET_DIR="$ROOT_DIR/.engine/$VERSION"
fi

# --- list source-path files --------------------------------------------------
FALLBACK_FILES=$(git -C "$ROOT_DIR" ls-tree -r --name-only "$REF" -- "$SOURCE_PATH" 2>/dev/null) || true

if [[ -z "$FALLBACK_FILES" ]]; then
    die "no $SOURCE_PATH files found at ref: $REF"
fi

# --- full rebuild: remove target, then regenerate --------------------------
rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR"

# --- copy each file with ENGINE header prepended ---------------------------
while IFS= read -r filepath; do
    # filepath is like "fallback/index.md" (or "draft/index.md" with --path) → strip the prefix
    relpath="${filepath#"$SOURCE_PATH"}"
    dest="$TARGET_DIR/$relpath"
    dest_dir=$(dirname "$dest")
    mkdir -p "$dest_dir"

    content=$(git -C "$ROOT_DIR" show "$REF:$filepath" 2>/dev/null) || die "failed to extract: $filepath"

    if [[ "$filepath" == *.md ]]; then
        {
            echo "ENGINE: $VERSION @ $SHORT_SHA — generated, do not edit"
            echo ""
            printf '%s\n' "$content"
        } > "$dest"
    else
        printf '%s\n' "$content" > "$dest"
    fi
done <<< "$FALLBACK_FILES"

# --- write DIST-SOURCE -----------------------------------------------------
# NOTE: rev-parse requires the BRACED suffix ^{tree}; the bare "^tree" form is
# invalid syntax and rev-parse just echoes it back (|| true masked the failure
# and left the literal string in DIST-SOURCE).
TREE_SHA=$(git -C "$ROOT_DIR" rev-parse "$REF^{tree}" 2>/dev/null) || die "cannot resolve tree sha for ref: $REF"
cat > "$TARGET_DIR/DIST-SOURCE" <<EOSOURCE
tag=$REF
tree=$TREE_SHA
commit=$COMMIT_SHA
generated=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EOSOURCE

echo "Engine built: $TARGET_DIR ($VERSION)"
