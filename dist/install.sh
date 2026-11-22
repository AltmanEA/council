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
# Hard precheck: core/ and templates/ must exist (defect fix — closes issue
# where install printed 'installed successfully' with core/ absent).
# ---------------------------------------------------------------------------
if [[ ! -d "$SCRIPT_DIR/core" ]]; then
  echo "FATAL: core/ directory is missing in the distribution."
  echo "       The archive is corrupted or incomplete."
  echo "       Re-extract the archive and try again."
  exit 1
fi
if [[ ! -d "$SCRIPT_DIR/templates" ]]; then
  echo "FATAL: templates/ directory is missing in the distribution."
  echo "       The archive is corrupted or incomplete."
  echo "       Re-extract the archive and try again."
  exit 1
fi

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
    echo "         .council/tools/check_all.py, .council/tools/gen_manifest.py, .council/tools/docmeta.py"
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
# Install CORE (framework files) — all under <target>/.council/
# ---------------------------------------------------------------------------
echo ""
echo "Installing core framework files ..."

if [[ "$MODE" == "init" ]] && [[ -d "$TARGET_ABS/.council" ]]; then
  rm -rf "$TARGET_ABS/.council"
fi
mkdir -p "$TARGET_ABS/.council"

for item in "$SCRIPT_DIR/core/"* "$SCRIPT_DIR/core/".*; do
  base=$(basename "$item")
  [[ "$base" == "*" || "$base" == "." || "$base" == ".." ]] && continue
  if [[ "$MODE" == "init" || ! -e "$TARGET_ABS/.council/$base" ]]; then
    if [[ -e "$TARGET_ABS/.council/$base" ]]; then
      rm -rf "$TARGET_ABS/.council/$base"
    fi
    cp -R "$item" "$TARGET_ABS/.council/$base"
    echo "  [core] installed .council/$base"
  else
    # overlay: merge into existing directory without deleting existing files
    if [[ -d "$item" ]]; then
      cp -R "$item/"* "$TARGET_ABS/.council/$base/" 2>/dev/null || true
      for dot in "$item/".*; do
        [[ "$(basename "$dot")" == "." || "$(basename "$dot")" == ".." || "$(basename "$dot")" == "*" ]] && continue
        cp -R "$dot" "$TARGET_ABS/.council/$base/" 2>/dev/null || true
      done
    else
      cp "$item" "$TARGET_ABS/.council/$base"
    fi
    echo "  [core] merged .council/$base"
  fi
done

# AC-2 mapping: .agents/skills → .council/skills (skills moves up one level)
if [[ -d "$TARGET_ABS/.council/.agents/skills" ]]; then
  rm -rf "$TARGET_ABS/.council/skills"
  cp -R "$TARGET_ABS/.council/.agents/skills" "$TARGET_ABS/.council/skills"
  echo "  [core] mapped .council/.agents/skills → .council/skills"
fi

# ---------------------------------------------------------------------------
# Install TEMPLATES (project-specific scaffolding) — host root
# ---------------------------------------------------------------------------
echo ""
echo "Installing project templates ..."

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

for item in "$SCRIPT_DIR/templates/"*; do
  [[ "$(basename "$item")" == "*" ]] && continue
  base=$(basename "$item")
  copy_template_item "$item" "./$base"
done

# ---------------------------------------------------------------------------
# Substitute project name in templates
# ---------------------------------------------------------------------------
echo ""
echo "Personalizing templates for '$PROJECT_NAME' ..."
while IFS= read -r -d '' f; do
  if grep -q '{{PROJECT_NAME}}' "$f" 2>/dev/null; then
    sed -i "s/{{PROJECT_NAME}}/$PROJECT_NAME/g" "$f"
    echo "  Substituted in $f"
  fi
done < <(find . -maxdepth 4 -type f \( -name '*.md' -o -name '*.md.template' \) -print0 2>/dev/null || true)

# Rename .template files to their real names.
# Overlay-safe: never clobber an existing host file.
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
# AC-4: Documentation manifests
#   CORE manifest at .council/docs-manifest.yaml (always generated if PyYAML)
#   HOST manifest at root only when host has docs (existing behavior kept)
# ---------------------------------------------------------------------------
echo ""
echo "Ensuring documentation manifest ..."
if python3 -c "import yaml" 2>/dev/null; then
  if python3 "$TARGET_ABS/.council/tools/gen_manifest.py" --root "$TARGET_ABS/.council" --write >/dev/null 2>&1; then
    echo "  [manifest] generated .council/docs-manifest.yaml (core)"
  else
    echo "  WARNING: core manifest generation failed (see error above)"
  fi
else
  echo "  [manifest] skipped — PyYAML not available (run pip install pyyaml)"
fi

if [[ -f "docs-manifest.yaml" ]]; then
  echo "  [manifest] docs-manifest.yaml already exists — kept host version"
elif python3 -c "import yaml" 2>/dev/null; then
  if python3 .council/tools/gen_manifest.py --root "$TARGET_ABS" --write >/dev/null 2>&1; then
    echo "  [manifest] generated host docs-manifest.yaml"
  else
    echo "  WARNING: host manifest generation failed (see error above)"
  fi
fi

# ---------------------------------------------------------------------------
# AC-3: OpenCode config wiring — opencode.jsonc
#   Creates the file when absent; merges skills entry when it exists.
#   If host has an opencode.json(c) *without* a skills array, warn loudly.
# ---------------------------------------------------------------------------
echo ""
echo "Configuring OpenCode ..."

OPENCODE_PATH="$TARGET_ABS/opencode.jsonc"
OPENCODE_JSON_PATH="$TARGET_ABS/opencode.json"

if [[ -f "$OPENCODE_PATH" ]] || [[ -f "$OPENCODE_JSON_PATH" ]]; then
  TARGET_FILE=""
  if [[ -f "$OPENCODE_PATH" ]]; then
    TARGET_FILE="$OPENCODE_PATH"
  else
    TARGET_FILE="$OPENCODE_JSON_PATH"
  fi
  MERGED=$(python3 - "$TARGET_FILE" 2>/dev/null <<'PYEOF'
import sys, json, re

path = sys.argv[1]
with open(path, 'r') as f:
    text = f.read()

lines = []
for line in text.splitlines():
    stripped = ''
    in_str = False
    escape_next = False
    i = 0
    while i < len(line):
        c = line[i]
        if escape_next:
            stripped += c
            escape_next = False
            i += 1
            continue
        if c == '\\' and in_str:
            stripped += c
            escape_next = True
            i += 1
            continue
        if c == '"':
            in_str = not in_str
            stripped += c
            i += 1
            continue
        if not in_str and c == '/' and i + 1 < len(line) and line[i+1] == '/':
            break
        stripped += c
        i += 1
    lines.append(stripped)

clean_text = '\n'.join(lines)
data = json.loads(clean_text)

skills_val = './.council/skills'
skills_list = data.get('skills', [])
if isinstance(skills_list, list):
    if skills_val not in skills_list:
        skills_list.append(skills_val)
        data['skills'] = skills_list
    else:
        print(f"  [opencode] {path}: skills already contains {skills_val}")
else:
    print(f'  WARNING: {path} has no "skills" array — please add "./.council/skills" manually.')
    print(f'  To fix, edit {path} and add:')
    print(f'    "skills": ["{skills_val}", ...]')
    sys.exit(0)

data['$schema'] = data.get('$schema', 'https://opencode.ai/schema.json')
data['$comment'] = data.get('$comment', '') or 'Council-managed'

out = json.dumps(data, indent=2)
with open(path, 'w') as f:
    f.write(out + '\n')
print(f"  [opencode] merged skills into {path}")
PYEOF
)
  rc=$?
  [[ $rc -ne 0 ]] && echo "  WARNING: could not merge opencode config — create $OPENCODE_PATH manually:" && echo "    {\"\$schema\": \"...\",\"skills\": [\"./\\.council/skills\"]}"
fi

# Create opencode.jsonc if it does not exist yet
if [[ ! -f "$OPENCODE_PATH" ]]; then
  cat > "$OPENCODE_PATH" <<'JSONC'
{
  "$schema": "https://opencode.ai/schema.json",
  "$comment": "Council-managed",
  "skills": [
    "./.council/skills"
  ]
}
JSONC
  echo "  [opencode] created opencode.jsonc"
fi

# Install .opencode/agents/selector.md if not present
SRC_SELECTOR="$SCRIPT_DIR/core/.opencode/agents/selector.md"
if [[ -f "$SRC_SELECTOR" ]]; then
  mkdir -p "$TARGET_ABS/.opencode/agents"
  if [[ ! -f "$TARGET_ABS/.opencode/agents/selector.md" ]]; then
    cp "$SRC_SELECTOR" "$TARGET_ABS/.opencode/agents/selector.md"
    echo "  [selector] installed .opencode/agents/selector.md"
  else
    echo "  [selector] SKIP (exists): .opencode/agents/selector.md"
  fi
fi

# ---------------------------------------------------------------------------
# Council metadata (version.lock, core-manifest.txt, update.sh)
# ---------------------------------------------------------------------------
echo ""
echo "Installing metadata ..."
if [[ -f "$SCRIPT_DIR/version.txt" ]]; then
  cp "$SCRIPT_DIR/version.txt" "$TARGET_ABS/.council/version.lock"
  echo "  Locked version: $(cat "$TARGET_ABS/.council/version.lock")"
fi
if [[ -f "$SCRIPT_DIR/core-manifest.txt" ]]; then
  cp "$SCRIPT_DIR/core-manifest.txt" "$TARGET_ABS/.council/core-manifest.txt"
  echo "  Core manifest: $(wc -l < "$TARGET_ABS/.council/core-manifest.txt") files"
fi
if [[ -f "$SCRIPT_DIR/update.sh" ]]; then
  cp "$SCRIPT_DIR/update.sh" "$TARGET_ABS/.council/update.sh"
  chmod +x "$TARGET_ABS/.council/update.sh"
  echo "  Updater copied to .council/update.sh"
fi

# ---------------------------------------------------------------------------
# AC-7: Host .gitignore — append managed block (idempotent)
# ---------------------------------------------------------------------------
echo ""
echo "Ensuring .gitignore ..."
GITIGNORE="$TARGET_ABS/.gitignore"
if [[ ! -f "$GITIGNORE" ]]; then
  touch "$GITIGNORE"
fi
if ! grep -q "# Council framework (managed block)" "$GITIGNORE"; then
  printf '\n# Council framework (managed block)\n.council/backup-*/\n.council/**/__pycache__/\n.council/telemetry/**/*.jsonl\n**/techdoc-translator/.env\n' >> "$GITIGNORE"
  echo "  [gitignore] appended Council-managed block"
else
  echo "  [gitignore] Council-managed block already present (idempotent)"
fi

# ---------------------------------------------------------------------------
# Git hooks — use installer from host's location after install
# ---------------------------------------------------------------------------
HOOK_INSTALLER=""
for candidate in "$TARGET_ABS/tools/install-hooks.sh" "$TARGET_ABS/.council/tools/install-hooks.sh"; do
  if [[ -f "$candidate" ]]; then
    HOOK_INSTALLER="$candidate"
    break
  fi
done
if [[ -n "$HOOK_INSTALLER" ]]; then
  echo ""
  echo "Installing git hooks ..."
  bash "$HOOK_INSTALLER" 2>/dev/null || echo "  WARNING: hook installation failed"
fi

# ---------------------------------------------------------------------------
# Translation reminder
# ---------------------------------------------------------------------------
if [[ -f "$TARGET_ABS/.council/vendor/techdoc-translator/.env.example" ]]; then
  echo ""
  echo "Translation engine is included (.council/vendor/techdoc-translator/)."
  if [[ ! -f "$TARGET_ABS/.council/vendor/techdoc-translator/.env" ]]; then
    echo "  To enable EN→RU translation:"
    echo "    cd .council/vendor/techdoc-translator"
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

  cat > "$TELEMETRY_DIR/.gitignore" <<'GITEOF'
# Telemetry data — collected diagnostics (opt-in, manual export).
# See RUNBOOK.md §Telemetry for details.
*.jsonl
GITEOF

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
# AC-5: Success verification — check NEW .council/ paths
# ---------------------------------------------------------------------------
echo ""
echo "Verifying installation ..."
MISSING=()
for f in .council/tools/check_all.py .council/update.sh AGENTS.md .council/fallback/index.md .council/docs/en/documentation-rules/index.md; do
  if [[ ! -f "$f" ]]; then
    MISSING+=("$f")
  fi
done
if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "FATAL: Installation incomplete — missing required files:"
  for m in "${MISSING[@]}"; do
    echo "  - $m"
  done
  echo "       Refusing to mark installation as successful."
  exit 1
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo "Council installed successfully"
echo "========================================"
echo "  Location: $TARGET_ABS"
echo ""
echo "Where is Council?"
echo "  Documentation : .council/docs/en/"
echo "  Tools         : .council/tools/"
echo "  Skills        : .council/skills/"
echo "  Updater       : .council/update.sh"
echo ""
echo "Next steps:"
echo "  1. Review and customize docs/en/project-concept/index.md"
echo "  2. Review AGENTS.md and adjust for your project context"
echo "  3. Run: python3 .council/tools/check_all.py --help"
echo "  4. Start a fallback session per .council/fallback/index.md"
echo ""
echo "To update the framework later:"
echo "  bash .council/update.sh /path/to/council-dist-X.Y.Z.tar.gz"
echo ""
