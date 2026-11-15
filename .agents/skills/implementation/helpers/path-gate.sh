#!/usr/bin/env bash
# path-gate.sh — Implementation Worker governance gate.
# Usage: path-gate.sh <worktree-dir> <whitelist-file>
# Checks every changed path in the worktree (git diff HEAD + untracked) against
# the whitelist and an unconditional deny list. Exit 0 = allowed, 1 = blocked
# (caller must stop the cycle with BLOCKED_GOVERNANCE), 2 = usage/internal error.
set -u

WORKTREE="${1:-}"; WHITELIST="${2:-}"
if [ -z "$WORKTREE" ] || [ -z "$WHITELIST" ]; then
  echo "usage: path-gate.sh <worktree-dir> <whitelist-file>" >&2; exit 2
fi
[ -d "$WORKTREE" ] || { echo "not a directory: $WORKTREE" >&2; exit 2; }
[ -f "$WHITELIST" ] || { echo "no whitelist file: $WHITELIST" >&2; exit 2; }

# Unconditional deny list — never writable by any cycle (AGENTS.md §2 Write Rule,
# §1.7 tooling separation; ADR-013 policy file).
DENY='^(docs/|fallback/|AGENTS\.md|CHANGELOGS/|defaults/|\.opencode/|documenter_policy\.yml|archive/|sessions/|\.agents/skills/documentation/|docs-manifest\.yaml)'

# Tier 2+ / ADR-013 markers scanned in changed content (protective grep).
TIER2='(write_handler|OperatorSurface|active_tier|allowed_operations|briefing_ref)'

mapfile -t CHANGED < <(git -C "$WORKTREE" diff --name-only HEAD 2>/dev/null; \
                       git -C "$WORKTREE" ls-files --others --exclude-standard 2>/dev/null)
if [ "${#CHANGED[@]}" -eq 0 ]; then
  echo "no changed files"; exit 0
fi

fail=0
for p in "${CHANGED[@]}"; do
  if [[ "$p" =~ $DENY ]]; then
    echo "BLOCKED deny-path: $p"; fail=1; continue
  fi
  allowed=0
  while IFS= read -r pat; do
    [[ -z "$pat" || "$pat" == \#* ]] && continue
    # shellcheck disable=SC2254
    case "$p" in $pat) allowed=1 ;; esac
  done < "$WHITELIST"
  if [ "$allowed" -ne 1 ]; then
    echo "BLOCKED not-whitelisted: $p"; fail=1
  fi
done

# Tier 2+ content scan on the diff itself.
if git -C "$WORKTREE" diff HEAD 2>/dev/null | grep -Eq "$TIER2"; then
  echo "BLOCKED tier2-marker in diff"; fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo "path-gate: BLOCKED_GOVERNANCE"; exit 1
fi
echo "path-gate: PASS (${#CHANGED[@]} paths)"
exit 0
