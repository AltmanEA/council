#!/usr/bin/env bash
# tools/install-hooks.sh — point git at the versioned hooks directory.
# Stage B, plan sess-doc-reliability-algo.
#
# Sets `git config core.hooksPath tools/hooks` (repository-local config only)
# so the versioned hook tools/hooks/pre-commit runs on every commit in THIS
# clone. Nothing is copied into .git/hooks. Each developer runs this once
# per clone (git config is not shared by cloning).
#
# Usage: bash tools/install-hooks.sh   (from anywhere inside the repo)
set -u

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "ERROR: not inside a git repository (git rev-parse --show-toplevel failed)" >&2
  echo "remediation: cd into the council repository and re-run: bash tools/install-hooks.sh" >&2
  exit 1
}

cd "$ROOT" || exit 1

if [ ! -f tools/hooks/pre-commit ]; then
  echo "ERROR: tools/hooks/pre-commit not found under ${ROOT}" >&2
  echo "remediation: restore the versioned hooks directory (git checkout tools/hooks) and re-run" >&2
  exit 1
fi

git config core.hooksPath tools/hooks

# SELF-CHECK: the config must read back exactly what we set.
ACTUAL="$(git config --local --get core.hooksPath 2>/dev/null || true)"
if [ "$ACTUAL" != "tools/hooks" ]; then
  echo "ERROR: self-check failed — core.hooksPath reads '${ACTUAL:-<unset>}', expected 'tools/hooks'" >&2
  echo "remediation: check for a conflicting system/global core.hooksPath (git config --show-origin --get core.hooksPath) and re-run: bash tools/install-hooks.sh" >&2
  exit 1
fi

echo "OK: core.hooksPath = tools/hooks (self-check passed)"

if [ -f tools/hooks/block-mode.flag ]; then
  echo "Hook mode: BLOCK (high-severity findings reject commits)"
else
  echo "Hook mode: WARN-ONLY (soak) — findings are printed, commits always pass"
  echo "To flip to block mode after a clean soak (~10 clean documentation commits): touch tools/hooks/block-mode.flag"
fi
