# Tier 2 Activation Runbook — pilot-safe-v1 (Runtime Overlay)

> **DRAFT — for operator reference.** All activation, sentinel, and MCP
> registration steps are operator actions performed **out-of-session**.
> This runbook does not perform any of those actions; it describes the
> operator's steps and verification commands.

**Runtime model:** overlay (`DOCUMENTER_ACTIVATION_PATH`) + base repo policy
(Tier 1 baseline) are merged **in memory** by `load_policy()`. The repo
policy file is never rewritten. Tier 2+ authorization requires the dual
interlock: effective policy ready **and** sentinel present.

---

## Prerequisites / Assumptions

- Repository is at the **Tier 1 baseline**: `active_tier: 1`, `allowed_operations: []`,
  `briefing_ref: null` in `documenter_policy.yml` (unchanged by this process).
- The Operator Ingress sentinel (`documenter/.operator_ingress_ready`) is **absent**
  (fail-closed default).
- The following code/tools are present and functional:
  - `python3 -m documenter_service` (Documenter Service MVP, CLI)
  - `python3 tools/activation_helper.py` (operator helper, read-only)
  - `python3 -m operator_ingress` (Operator Ingress, to be launched by operator)
- Environment: same-UID execution; containment is procedural + code fail-closed,
  not true filesystem isolation.

---

## Step 1: Prepare Outside Workspace (Operator Action)

Create the directory structure for the operator's external artifacts:

```bash
mkdir -p ~/.council/briefings
chmod 700 ~/.council
chmod 700 ~/.council/briefings
```

> These are **procedural** (same-UID) permissions — not a security boundary.
> The operator controls these directories and must keep the signed briefing
> and overlay secure.

---

## Step 2: Prepare Signed Briefing (Operator Action)

1. Review the draft briefing: `documenter/artifacts/operator-briefing-pilot-safe-v1-draft.md`.
2. Adapt, sign, and date it as the operative briefing.
3. Store the signed briefing at an **absolute path outside workspace root**, e.g.:

   ```bash
   cp /path/to/council/documenter/artifacts/operator-briefing-pilot-safe-v1-draft.md \
       ~/.council/briefings/tier2-pilot-safe-v1-YYYYMMDD.md
   ```

4. **Do not** reference this file from the workspace. Store it outside `~/.council/`
   (or another secure external location) and record the absolute path for
   `briefing_ref`.

---

## Step 3: Create Activation Overlay (Operator Action)

### Option A: Copy from example

1. Copy the example overlay:

   ```bash
   cp /path/to/council/documenter/artifacts/activation-overlay-pilot-safe-v1.example.yml \
       ~/.council/documenter_activation.yml
   ```

2. Edit the file and replace the `briefing_ref` placeholder with the **absolute
   path to the operator's signed briefing** (must be outside workspace root).

### Option B: Use helper template

```bash
python3 tools/activation_helper.py template --scope pilot-safe-v1 \
    --briefing-ref /home/ea/.council/briefings/tier2-pilot-safe-v1-YYYYMMDD.md
```

This prints valid YAML to stdout (no file writes). Copy the output to the
target overlay file at `~/.council/documenter_activation.yml` (or your custom
path).

### Option C: Non-default overlay path

If you prefer a different overlay location, set the environment variable:

```bash
export DOCUMENTER_ACTIVATION_PATH=/some/other/path/documenter_activation.yml
```

The path must be absolute and outside workspace root (checked at load time).

---

## Step 4: Verify Before Act (Read-Only)

### 4a. Check current state (should be baseline)

```bash
# Documenter Service CLI
python3 -m documenter_service --verify-activation --root .

# Or with JSON output
python3 -m documenter_service --verify-activation --root . --json

# Helper script (same checks)
python3 tools/activation_helper.py verify --root .
python3 tools/activation_helper.py verify --root . --json
```

Expected state: **baseline** (exit 0) — no overlay applied, effective is Tier 1.

### 4b. If overlay is placed, verify effective merge

After placing the overlay file and (if using a non-default path) setting
`DOCUMENTER_ACTIVATION_PATH`:

```bash
python3 -m documenter_service --verify-activation --root . --json
python3 tools/activation_helper.py verify --root . --json
```

Expected state: **active** (exit 0) — overlay merged, effective policy shows
`active_tier: 2`, expanded `allowed_operations_count`, and scope summary.

Readiness sub-checks reported:
- `sentinel_present`: `false` (expected — sentinel not yet created)
- `tier2_policy_ready`: `true` (policy from overlay)
- `briefing_exists`: `true`/`false` (depends on whether the briefing file
  actually exists at the referenced path)
- `tier2_authorized`: `false` (sentinel missing)

### 4c. Inspect effective policy details

```bash
python3 tools/activation_helper.py print-effective --root .
python3 tools/activation_helper.py print-effective --root . --json
```

Shows activation source, scope, expanded operations, and effective fields.

### 4d. Handle invalid state (exit 2)

If `--verify-activation` reports **invalid**:
- Check the `errors` array in JSON output or the human-readable error lines.
- Common causes: unknown keys, XOR violation, containment failure,
  invalid YAML, briefing_ref not absolute/outside workspace.
- Fix the overlay file and re-verify.

---

## Step 5: Activate Interlock (Operator Actions)

### 5a. Start Operator Ingress with required environment

```bash
COUNCIL_OPERATOR_SECRET="<your-secret>" \
COUNCIL_OPERATOR_ID="op-alice" \
COUNCIL_STATE_ROOT=/home/ea/council \
python3 -m operator_ingress
```

> **Never** put `COUNCIL_OPERATOR_SECRET` in config files, shell history, or
> unencrypted files. Use systemd drop-in, vault, or direct env injection.

### 5b. Confirm sentinel creation

When the Operator Ingress starts successfully, it prints `READY` to stdout
and creates the sentinel:

```bash
# Check sentinel exists
test -f /home/ea/council/documenter/.operator_ingress_ready && echo "sentinel present"
```

### 5c. Confirm full interlock readiness

```bash
python3 -m documenter_service --verify-activation --root . --json
```

Expected state: **active** (exit 0) with:
- `sentinel_present: true`
- `tier2_policy_ready: true`
- `briefing_exists: true`
- `tier2_authorized: true`
- `reason: "all checks passed"`

### 5d. Verify full status

```bash
python3 -m documenter_service --status --json
```

Check that `tier_interlock.tier_2_plus_locked` is `false` and `activation`
block shows the overlay source.

### 5e. MCP registration (operator decision)

Registering the Operator Ingress (or any `documenter.*` / `council.*` MCP
tools) in the workspace configuration (`.opencode/opencode.jsonc`) is an
**operator-only decision**. This runbook does not perform registration.

---

## Step 6: Operate Within Scope

Once the interlock is fully ready, the operator may use the Documenter Service
to perform Tier 2+ write operations within the `pilot-safe-v1` scope:

### Delegate flow

1. **Audit first** (or ensure a fresh `audit_id` is available):

   ```bash
   python3 -m documenter_service --audit --target "*" --pre-check --json
   ```

2. **Delegate preview** (review the diff):

   ```bash
   python3 -m documenter_service --delegate-preview \
       --target documenter-service-configuration-guide \
       --change-type update --trust-level safe \
       --diff-base64 "<base64-payload>" --json
   ```

   Review the `diff_text` output and all findings. Ensure trust level matches
   the scope (`safe`, `update`).

3. **Delegate write** (propose the write):

   ```bash
   python3 -m documenter_service --delegate-write \
       --target documenter-service-configuration-guide \
       --change-type update --trust-level safe \
       --diff-base64 "<base64-payload>" --json
   ```

   This returns an `approval_id` if approval is required.

4. **Approve** (distinct operator principal, or solo with acknowledgment token):

   ```bash
   python3 -m documenter_service --approve \
       --approval-id "<approval_id>" \
       --acknowledge "CONFIRMED_SOLE_REVIEWER" \
       --json
   ```

   > Solo mode: only works when `allow_solo_approval: true` in the overlay
   > AND the operation matches `trust_level: safe`. The `--acknowledge` token
   > is required and validated.

5. **Apply** (operator identity via `COUNCIL_OPERATOR_ID` env):

   ```bash
   COUNCIL_OPERATOR_ID="op-alice" \
   python3 -m documenter_service --delegate-write \
       --target documenter-service-configuration-guide \
       --change-type update --trust-level safe \
       --diff-base64 "<base64-payload>" \
       --approval-id "<approval_id>" \
       --json
   ```

### Scope constraints during operation

- `trust_level` must match the scope (`safe` for pilot-safe-v1).
- `change_type` must match (`update`).
- `target_id` must be one of the preset targets:
  `documenter-service-configuration-guide` or `operator-ingress`.
- Each invocation targets one document.
- Review-gated presets (content, RU sync) are not accessible under this preset.

---

## Step 7: Deactivation / Rollback

### When to deactivate

- Scheduled review date (≤ 30 days after activation) determines scope adequacy.
- Any incident or unexpected behavior warrants immediate deactivation.
- Operator decision to narrow scope, widen scope, or revert to Tier 1.

### Deactivation steps

1. **Stop the Operator Ingress process** (if running).

2. **Remove the sentinel:**

   ```bash
   rm -f /home/ea/council/documenter/.operator_ingress_ready
   ```

3. **Remove or neutralize the overlay:**

   ```bash
   # Option A: remove the overlay file
   rm ~/.council/documenter_activation.yml

   # Option B: unset DOCUMENTER_ACTIVATION_PATH
   unset DOCUMENTER_ACTIVATION_PATH

   # Option C: point to a non-existent path
   export DOCUMENTER_ACTIVATION_PATH=/nonexistent/path.yml
   ```

4. **Verify Tier 1 baseline is restored:**

   ```bash
   python3 -m documenter_service --verify-activation --root .
   # Expected: State: baseline, active_tier: 1, allowed_operations: empty

   python3 -m documenter_service --status --json
   # Check tier_interlock.tier_2_plus_locked: true
   ```

5. **Revert any applied changes:**

   ```bash
   git restore <file>
   ```

6. **Reconcile leftover intent records:**

   ```bash
   python3 -m documenter_service --reconcile --json
   ```

### Deactivation hints (reference)

```bash
python3 tools/activation_helper.py deactivate-hints
```

This prints safe deactivation steps as reference. **No mutations are performed.**

---

## Troubleshooting

### `--verify-activation` reports `invalid` (exit 2)

**Unknown keys:**

```
activation overlay contains unknown key(s): audit_freshness, version
```

**Fix:** Remove unknown keys. Only allowlist keys are permitted:
`active_tier`, `scope`, `allowed_operations`, `scope_targets`,
`briefing_ref`, `allow_solo_approval`, `min_approval_delay_seconds`.

**XOR violation:**

```
activation overlay must specify exactly one of 'scope' or 'allowed_operations'
activation overlay must not specify both 'scope' and 'allowed_operations'
```

**Fix:** Use exactly one — `scope` (for preset expansion) or `allowed_operations`
(manual override).

**Containment failure:**

```
activation overlay path must be outside workspace root: "/some/path"
briefing_ref must be an absolute path outside workspace root: "relative/path"
```

**Fix:** Use absolute paths for both overlay and briefing_ref that resolve
outside the workspace root.

**Narrowing validation failure:**

```
scope_targets widens/invalid for scope "pilot-safe-v1": unknown ids "foo"
```

**Fix:** Ensure `scope_targets` is a non-empty subset of the preset's targets.

**Briefing file missing:**

`tier2_authorized: false` with `briefing_exists: false` when briefing_ref points
to a non-existent file.

**Fix:** Ensure the signed briefing file exists at the referenced path.

### Sentinel missing (but overlay valid)

`tier2_authorized: false` with `sentinel_present: false`.

**Fix:** Start the Operator Ingress with `COUNCIL_OPERATOR_SECRET` env var set.
The sentinel is created on `READY` output.

### `--status` shows Tier 1 but overlay is placed

If `--verify-activation` still shows `baseline` after placing the overlay:

1. Check `DOCUMENTER_ACTIVATION_PATH` env var (explicit mode requires the file).
2. Verify the overlay file actually exists at the expected path.
3. Check for YAML parse errors or empty content.
4. Run `--verify-activation` and inspect errors.

---

## Guarantees and Limits

### What this mechanism guarantees

- **Runtime-merge only:** effective policy = base (Tier 1) + overlay.
  The repo file `documenter_policy.yml` is **never modified**.
- **Fail-closed:** absent overlay → Tier 1. Invalid overlay → explicit error,
  no silent fallback. Unknown keys → rejected.
- **Containment:** overlay path and briefing_ref must be absolute and outside
  workspace root (resolves symlinks via `realpath`).
- **Helper is read-only:** `activation_helper.py` does not write the repo
  policy, create files outside workspace, or create/remove the sentinel.
- **Dual interlock:** both policy readiness AND sentinel must be present
  for Tier 2+ authorization (ADR-013).

### What this mechanism does NOT do

- ~~Create the sentinel~~ (operator action, Operator Ingress)
- ~~Modify `documenter_policy.yml`~~ (stays at Tier 1 baseline)
- ~~Register MCP servers~~ (operator decision)
- ~~Activate/deactivate tier~~ (operator decision, overlay presence controls)

### Same-UID note

Containment and path separation are **procedural** (same-UID execution with
fail-closed code checks), not true filesystem isolation. All file operations
are performed by the same user. Security relies on the code's validation
layer, proper file permissions on `~/.council/`, and operator discipline.

---

## Other Scope Presets (Ramp Options)

Available presets (listed by `python3 tools/activation_helper.py template` or
`python3 -m documenter_service --verify-activation` scope summary):

| Preset | change_type | trust_level | target count | Description |
|---|---|---|---|---|
| `pilot-safe-v1` | `update` | `safe` | 2 | Minimal safe pilot (mechanical updates) |
| `docs-maint-safe` | `update` | `safe` | 24 | Mechanical maintenance across full corpus |
| `docs-content-review` | `update` | `review` | 24 | Content/normative updates (review-gated) |
| `ru-sync-review` | `create_ru` | `review` | 18 | RU translation create/sync (review-gated) |

Widening from pilot-safe-v1 to other presets follows the bounded-experiment
ramp: 5 clean cycles per expansion, with operator review.
