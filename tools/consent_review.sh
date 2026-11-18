#!/usr/bin/env bash
# consent_review.sh — Thin bash wrapper for the consent terminal review.
# Resolves repo root from this script's location and execs the Python
# consent terminal.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
exec python3 "$ROOT/tools/consent_terminal.py" review "$@"
