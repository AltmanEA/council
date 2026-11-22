#!/usr/bin/env bash
set -euo pipefail
# install.sh — install or overlay the Council framework into a target directory.
#
# Usage:
#   bash install.sh --target <dir> [--mode init | overlay] [--project-name <name>] [--skip-deps-check] [--enable-telemetry]
#
# Modes:
#   init    — create a new directory, run git init if needed, install everything.
#   overlay — add Council into an existing project directory (skips existing files).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="init"
TARGET=""
PROJECT_NAME=""
SKIP_DEPS=0
ENABLE_TELEMETRY=0

usage() {
  cat <<EOF
Usage: install.sh --target <dir> [options]

Options:
  --target <dir>           Destination directory (required)
  --mode init | overlay    Installation mode (default: init)
  --project-name <name>    Project identifier (default: basename of target)
  --skip-deps-check        Skip Python / PyYAML / git checks
  --enable-telemetry       Create telemetry config and directories

Examples:
  bash install.sh --target ../my-project --mode init --project-name my-project
  bash install.sh --target /path/to/existing --mode overlay --project-name existing
  bash install.sh --target ../my-project --mode init --project-name my-project --enable-telemetry
EOF
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)           TARGET="$2"; shift 2 ;;
    --mode)             MODE="$2"; shift 2 ;;
    --project-name)     PROJECT_NAME="$2"; shift 2 ;;
    --skip-deps-check)  SKIP_DEPS=1; shift ;;
    --enable-telemetry) ENABLE_TELEMETRY=1; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
[[ -z "$TARGET" ]] && { echo "ERROR: --target is required"; usage; }
[[ "$MODE" != "init" && "$MODE" != "overlay" ]] && { echo "ERROR: --mode must be init or overlay"; usage; }

# Resolve project name
if [[ -z "$PROJECT_NAME" ]]; then
  PROJECT_NAME="$(basename "$(cd "$TARGET" 2>/dev/null && pwd || echo "$TARGET")" 2>/dev/null || echo "project")"
fi

echo "========================================"
echo "Council Framework Installer"
echo "========================================"
echo "  Target directory : $TARGET"
echo "  Mode             : $MODE"
echo "  Project name     : $PROJECT_NAME"
if [[ "$MODE" == "overlay" ]]; then
  echo ""
  echo "  NOTE: OVERLAY mode — existing files will NOT be overwritten."
  echo "        Files already present in the target are kept as-is."
fi
echo ""

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------
if [[ "$SKIP_DEPS" == "0" ]]; then
  echo "Checking dependencies ..."

  if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 is required (3.11+ recommended)."
    exit 1
  fi

  PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)' 2>/dev/null || echo 0)
  PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo 0)
  if [[ "$PY_MAJOR" -lt 3 || ( "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ) ]]; then
    echo "WARNING: Python 3.11+ recommended. Found: ${PY_MAJOR}.${PY_MINOR}"
  else
    echo "  Python: ${PY_MAJOR}.${PY_MINOR} ✓"
  fi

  if ! python3 -c "import yaml" 2>/dev/null; then
    echo "WARNING: PyYAML not installed. These Council tools will NOT work until it is installed:"
    echo "         tools/check_all.py, tools/gen_manifest.py, tools/docmeta.py"
    echo "         Run: pip install pyyaml"
  else
    echo "  PyYAML: installed ✓"
  fi

  if ! command -v git &>/dev/null; then
    echo "WARNING: git not found. Git hooks will not be installed."
  else
    echo "  git: installed ✓"
  fi
fi

# ---------------------------------------------------------------------------
# Prepare target directory
# ---------------------------------------------------------------------------
mkdir -p "$TARGET"
cd "$TARGET"
TARGET_ABS="$(pwd)"

if [[ "$MODE" == "init" ]]; then
  if [[ ! -d ".git" ]]; then
    git init 2>/dev/null || echo "WARNING: git init failed (git not installed?)"
    echo "Initialized empty git repository"
  fi
else
  if [[ ! -d ".git" ]]; then
    echo "WARNING: Target is not a git repository."
    echo "         Recommend: git init && git add ."
  fi
fi

# ---------------------------------------------------------------------------
# Install CORE (framework files)
# ---------------------------------------------------------------------------
echo ""
echo "Installing core framework files ..."
if [[ -d "$SCRIPT_DIR/core" ]]; then
  for item in "$SCRIPT_DIR/core/"* "$SCRIPT_DIR/core/".*; do
    [[ "$(basename "$item")" == "*" || "$(basename "$item")" == "." || "$(basename "$item")" == ".." ]] && continue
    base=$(basename "$item")
    if [[ "$MODE" == "init" || ! -e "$base" ]]; then
      if [[ -e "$base" ]]; then
        rm -rf "$base"
      fi
      cp -R "$item" .
      echo "  [core] installed $base"
    else
      # overlay: merge into existing directory without deleting existing files
      if [[ -d "$item" ]]; then
        cp -R "$item/"* "$base/" 2>/dev/null || true
        # also copy dotfiles if any
        for dot in "$item/".*; do
          [[ "$(basename "$dot")" == "." || "$(basename "$dot")" == ".." || "$(basename "$dot")" == "*" ]] && continue
          cp -R "$dot" "$base/" 2>/dev/null || true
        done
      else
        cp "$item" "$base"
      fi
      echo "  [core] merged $base"
    fi
  done
else
  echo "  WARNING: core/ directory not found in distribution."
fi

# ---------------------------------------------------------------------------
# Install TEMPLATES (project-specific scaffolding)
# ---------------------------------------------------------------------------
echo ""
echo "Installing project templates ..."

# Recursive copy that merges into existing directories without overwriting.
copy_template_item() {
  local src="$1"
  local dst="$2"
  if [[ -f "$src" ]]; then
    if [[ ! -e "$dst" ]]; then
      mkdir -p "$(dirname "$dst")"
      cp "$src" "$dst"
      echo "  [template] installed $dst"
    else
      echo "  [template] SKIP (exists): $dst"
    fi
  elif [[ -d "$src" ]]; then
    mkdir -p "$dst"
    for sub in "$src"/*; do
      [[ "$(basename "$sub")" == "*" ]] && continue
      copy_template_item "$sub" "$dst/$(basename "$sub")"
    done
  fi
}

if [[ -d "$SCRIPT_DIR/templates" ]]; then
  for item in "$SCRIPT_DIR/templates/"*; do
    [[ "$(basename "$item")" == "*" ]] && continue
    base=$(basename "$item")
    copy_template_item "$item" "./$base"
  done
else
  echo "  WARNING: templates/ directory not found in distribution."
fi

# ---------------------------------------------------------------------------
# Substitute project name in templates
# ---------------------------------------------------------------------------
echo ""
echo "Personalizing templates for '$PROJECT_NAME' ..."
# Find all .md and .md.template files up to 4 levels deep
while IFS= read -r -d '' f; do
  if grep -q '{{PROJECT_NAME}}' "$f" 2>/dev/null; then
    sed -i "s/{{PROJECT_NAME}}/$PROJECT_NAME/g" "$f"
    echo "  Substituted in $f"
  fi
done < <(find . -maxdepth 4 -type f \( -name '*.md' -o -name '*.md.template' \) -print0 2>/dev/null || true)

# Rename .template files to their real names.
# Overlay-safe: never clobber an existing host file (e.g. a hand-written
# AGENTS.md vs. AGENTS.md.template).
while IFS= read -r -d '' f; do
  dest="${f%.template}"
  if [[ -e "$dest" ]]; then
    echo "  SKIP (exists): $dest — kept host file, removed $(basename "$f")"
    rm -f "$f"
  else
    mv "$f" "$dest"
    echo "  Renamed $f → $(basename "$dest")"
  fi
done < <(find . -maxdepth 4 -type f -name '*.template' -print0 2>/dev/null || true)

# ---------------------------------------------------------------------------
# Council metadata (for future updates)
# ---------------------------------------------------------------------------
mkdir -p .council
if [[ -f "$SCRIPT_DIR/version.txt" ]]; then
  cp "$SCRIPT_DIR/version.txt" .council/version.lock
  echo ""
  echo "  Locked version: $(cat .council/version.lock)"
fi
if [[ -f "$SCRIPT_DIR/core-manifest.txt" ]]; then
  cp "$SCRIPT_DIR/core-manifest.txt" .council/core-manifest.txt
  echo "  Core manifest: $(wc -l < .council/core-manifest.txt) files"
fi
if [[ -f "$SCRIPT_DIR/update.sh" ]]; then
  cp "$SCRIPT_DIR/update.sh" .council/update.sh
  chmod +x .council/update.sh
  echo "  Updater copied to .council/update.sh"
fi

# ---------------------------------------------------------------------------
# Git hooks
# ---------------------------------------------------------------------------
if [[ -f "tools/install-hooks.sh" ]]; then
  echo ""
  echo "Installing git hooks ..."
  bash tools/install-hooks.sh 2>/dev/null || echo "  WARNING: hook installation failed"
fi

# ---------------------------------------------------------------------------
# Translation reminder
# ---------------------------------------------------------------------------
if [[ -f "vendor/techdoc-translator/.env.example" ]]; then
  echo ""
  echo "Translation engine is included (vendor/techdoc-translator/)."
  if [[ ! -f "vendor/techdoc-translator/.env" ]]; then
    echo "  To enable EN→RU translation:"
    echo "    cd vendor/techdoc-translator"
    echo "    cp .env.example .env"
    echo "    # edit .env with your API endpoint / key"
  fi
fi

# ---------------------------------------------------------------------------
# Telemetry config (opt-in diagnostics)
# ---------------------------------------------------------------------------
if [[ "$ENABLE_TELEMETRY" == "1" ]]; then
  TELEMETRY_DIR="$TARGET_ABS/.council/telemetry"
  mkdir -p "$TELEMETRY_DIR/diagnostics"
  mkdir -p "$TELEMETRY_DIR/metrics"

  # Create telemetry.yml — only if it does not already exist (overlay-safe).
  TELEMETRY_CFG="$TARGET_ABS/.council/telemetry.yml"
  if [[ ! -f "$TELEMETRY_CFG" ]]; then
    cat > "$TELEMETRY_CFG" <<TELEOF
enabled: true
project_name: ${PROJECT_NAME}
redact_symbols: false
max_file_size_mb: 10
max_total_dir_mb: 50
retention_days: 30
collect:
TELEOF
    echo "  [telemetry] created .council/telemetry.yml"
  else
    echo "  [telemetry] telemetry.yml already exists — skipped (overlay-safe)"
  fi

  # Create .gitignore in telemetry/
  cat > "$TELEMETRY_DIR/.gitignore" <<'GITEOF'
# Telemetry data — collected diagnostics (opt-in, manual export).
# See RUNBOOK.md §Telemetry for details.
*.jsonl
GITEOF

  # Create telemetry README with checklist
  cat > "$TELEMETRY_DIR/README.md" <<'READMEEOF'
# Telemetry Directory

This directory holds opt-in diagnostics data collected by the Council framework.

## Checklist

| Item | Status |
|------|--------|
| `*.jsonl` files are listed in `.gitignore` | Not collected (safe) |
| Diagnostics are local, manual export only | Collected (manual) |
| No data leaves the host automatically | Not collected |
| Export via `--bundle` is the only path | Collected (manual) |
| `check_all.py` never initiates collection | Not collected |

## How to disable

Create the file `.council/opt-out-telemetry` to prevent any collection.

See `RUNBOOK.md` for the full Telemetry section.
READMEEOF

  echo "  [telemetry] created diagnostics/, metrics/, .gitignore, README.md"
fi

# ---------------------------------------------------------------------------
# Disclosure (always printed, per OP-2 transparency)
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo "Telemetry (opt-in diagnostics)"
echo "========================================"
echo ""
echo "  Telemetry is OFF BY DEFAULT — nothing is collected"
echo "  until you explicitly enable it with --enable-telemetry."
echo ""
echo "  When enabled, the following is collected:"
echo "    - Error records (JSONL) written to .council/telemetry/diagnostics/"
echo "    - Record count, categories, and directory size via --inspect"
echo "    - Bundled export via --bundle (gzip-tar to stdout)"
echo ""
echo "  The following is NEVER collected or transmitted:"
echo "    - Source code, environment variables, prompts"
echo "    - API keys, tokens, credentials (redacted automatically)"
echo "    - Any data is never transmitted — export is manual only"
echo ""
echo "  Opt-out: create .council/opt-out-telemetry to disable collection"
echo "           even when enabled in telemetry.yml."
echo ""
echo "  Data stays on the host. No daemon, no network, no git hooks."

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo "Council installed successfully"
echo "========================================"
echo "  Location: $TARGET_ABS"
echo ""
echo "Next steps:"
echo "  1. Review and customize docs/en/project-concept/index.md"
echo "  2. Review AGENTS.md and adjust for your project context"
echo "  3. Run: python3 tools/check_all.py --help"
echo "  4. Start a fallback session per fallback/index.md §Operational Flow"
echo ""
echo "To update the framework later:"
echo "  bash .council/update.sh /path/to/council-dist-X.Y.Z.tar.gz"
echo ""
