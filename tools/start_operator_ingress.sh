#!/usr/bin/env bash
set -euo pipefail

# Start Operator Ingress for Tier 2 activation (step 4 of runtime-merge flow).
#
# Resolves COUNCIL_OPERATOR_ID / COUNCIL_OPERATOR_SECRET from the environment,
# or (if unset/empty) reads them from files in $COUNCIL_DOTDIR:
#   $COUNCIL_DOTDIR/operator_id      -> COUNCIL_OPERATOR_ID
#   $COUNCIL_DOTDIR/operator_secret  -> COUNCIL_OPERATOR_SECRET
#
# Default COUNCIL_DOTDIR: $HOME/.council (outside workspace, per activation scheme)
# Default COUNCIL_STATE_ROOT: repo root (directory above this script)
#
# SECURITY (same-UID): files in ~/.council and process environment variables are
# NOT physically inaccessible to other processes running as the same OS user
# (e.g. an agent in this workspace). Storing a secret in a file is a convenience
# tradeoff and provides only procedural separation, not true isolation. Prefer
# supplying COUNCIL_OPERATOR_SECRET via environment at launch when possible.
# This script never prints the secret value.

usage() {
  cat <<'EOF'
Usage: bash tools/start_operator_ingress.sh [--root <state-root>] [-h|--help]

Options:
  --root <path>   Override COUNCIL_STATE_ROOT (repo/state root)
  -h, --help      Show this help

Environment (inputs):
  COUNCIL_STATE_ROOT       Repo/state root (default: repo root)
  COUNCIL_DOTDIR           Dir holding id/secret files (default: $HOME/.council)
  COUNCIL_OPERATOR_ID      Operator id (else read from $COUNCIL_DOTDIR/operator_id)
  COUNCIL_OPERATOR_SECRET  Secret, required (else read from $COUNCIL_DOTDIR/operator_secret)

Optional file inputs (used only if corresponding env var is unset/empty):
  $COUNCIL_DOTDIR/operator_id      (first line/value; CR/LF stripped)
  $COUNCIL_DOTDIR/operator_secret  (first line/value; CR/LF stripped; chmod 600 recommended)
EOF
}

die() { echo "[ingress] ERROR: $*" >&2; exit 2; }

ROOT_OVERRIDE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      [[ $# -ge 2 ]] || die "--root requires a path argument"
      ROOT_OVERRIDE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1 (use --help)" ;;
  esac
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
COUNCIL_STATE_ROOT="${COUNCIL_STATE_ROOT:-${ROOT_OVERRIDE:-$REPO_ROOT}}"
COUNCIL_DOTDIR="${COUNCIL_DOTDIR:-$HOME/.council}"

read_trimmed_file() {
  # prints file content with CR/LF removed
  local f="$1"
  tr -d '\r\n' < "$f"
}

# Load operator id from file if not provided via env
if [[ -z "${COUNCIL_OPERATOR_ID:-}" ]]; then
  if [[ -f "$COUNCIL_DOTDIR/operator_id" ]]; then
    COUNCIL_OPERATOR_ID="$(read_trimmed_file "$COUNCIL_DOTDIR/operator_id")"
    echo "[ingress] COUNCIL_OPERATOR_ID loaded from $COUNCIL_DOTDIR/operator_id" >&2
  fi
fi

# Load secret from file if not provided via env
secret_source="env"
if [[ -z "${COUNCIL_OPERATOR_SECRET:-}" ]]; then
  if [[ -f "$COUNCIL_DOTDIR/operator_secret" ]]; then
    COUNCIL_OPERATOR_SECRET="$(read_trimmed_file "$COUNCIL_DOTDIR/operator_secret")"
    secret_source="file:$COUNCIL_DOTDIR/operator_secret"
    echo "[ingress] COUNCIL_OPERATOR_SECRET loaded from $COUNCIL_DOTDIR/operator_secret" >&2
  else
    secret_source="missing"
  fi
fi

[[ -n "${COUNCIL_OPERATOR_SECRET:-}" ]] || die "COUNCIL_OPERATOR_SECRET is required. Set it in env or place it in $COUNCIL_DOTDIR/operator_secret (chmod 600)."

export COUNCIL_STATE_ROOT
export COUNCIL_OPERATOR_SECRET
if [[ -n "${COUNCIL_OPERATOR_ID:-}" ]]; then
  export COUNCIL_OPERATOR_ID
fi

echo "[ingress] state_root=$COUNCIL_STATE_ROOT" >&2
echo "[ingress] dotdir=$COUNCIL_DOTDIR" >&2
if [[ -n "${COUNCIL_OPERATOR_ID:-}" ]]; then
  echo "[ingress] operator_id=$COUNCIL_OPERATOR_ID" >&2
else
  echo "[ingress] operator_id=(not set)" >&2
fi
if [[ "$secret_source" == "env" ]]; then
  echo "[ingress] secret_source=env (value not shown)" >&2
else
  echo "[ingress] secret_source=$secret_source (value not shown)" >&2
fi
echo "[ingress] starting: python3 -m operator_ingress (cwd=$COUNCIL_STATE_ROOT)" >&2
echo "[ingress] note: on READY a sentinel is created at documenter/.operator_ingress_ready; repo policy remains Tier 1 baseline (runtime merge)." >&2

cd "$COUNCIL_STATE_ROOT"
exec python3 -m operator_ingress
