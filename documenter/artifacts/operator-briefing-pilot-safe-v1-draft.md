# DRAFT — Operator Briefing: pilot-safe-v1 Activation (Runtime Overlay)

> **This is a repo-draft artifact for reference.** The operator should store the
> signed/operative briefing **outside the workspace** (e.g. in a private directory
> such as `~/.council/briefings/`) and point `briefing_ref` in the activation
> overlay to that external file. This file must **not** be referenced as the
> operative `briefing_ref` — it is a draft template only.

**Document type:** Tier 2+ activation briefing (bounded pilot)
**Preset scope:** `pilot-safe-v1`
**Date:** 2026-11-18
**Status:** DRAFT — for operator review, signature, and placement outside workspace

---

## 1. Purpose

Authorize a **minimal, safe Tier 2+ activation** for the solo operator using a
**runtime merge overlay** (external to the workspace) and the **pilot-safe-v1**
scope preset. This briefing defines the scope, constraints, and expectations for
the pilot experiment.

## 2. Scope and What "update@safe" Means

### Preset definition

| Field | Value |
|---|---|
| `scope` id | `pilot-safe-v1` |
| Description | Minimal safe pilot: mechanical updates to 2 operational docs |
| `change_type` | `update` |
| `trust_level` | `safe` |
| `requires_diff_preview` | `true` (always) |
| Targets (2) | `documenter-service-configuration-guide`, `operator-ingress` |

### Scope of authority

- **change_type = `update`** only. `split`, `create_ru`, `custom` remain
  review-floor operations and are **not delegated**.
- **trust_level = `safe`** means mechanical, safe-to-derive changes (e.g. version
  field bumps, changelog tails, metadata). Content/normative edits and Russian
  translation creation remain at Tier 1 (preview + manual apply via Documentation
  Worker).
- **Explicit targets** (2 documents). Wildcard (`targets: []`) is **not used**.
- Every write targets exactly one document per invocation (`target_ids` length 1);
  multi-file commits are reserved.
- **`requires_diff_preview: true`** — a diff preview must be reviewed before any
  write proposal is accepted.

## 3. Policy / Overlay Model

### Runtime merge — no repo policy rewrite

- The repo policy file (`documenter_policy.yml`) **remains the Tier 1 baseline**
  (`active_tier: 1`, `allowed_operations: []`, `briefing_ref: null`) at all times.
  This mechanism **never writes** the repo policy file.
- Tier 2+ intent is expressed via an **external activation overlay** YAML file,
  loaded by `load_policy()` at runtime and merged **in memory**.
- Overlay path: default `~/.council/documenter_activation.yml` (set via
  `DOCUMENTER_ACTIVATION_PATH` env var for non-default locations).
- The overlay must pass **strict allowlist** validation (only 7 keys permitted),
  **XOR** (exactly one of `scope` or `allowed_operations`), **narrowing-only**
  (`scope_targets`), and **containment** rules.

### Containment (procedural boundary — same UID)

- Overlay path and `briefing_ref` must be **absolute paths outside workspace root**.
  Containment uses `realpath` to resist symlink escape. Not true filesystem
  isolation — relies on fail-closed code checks.
- An overlay pointing inside the workspace root, or a relative path, is rejected
  with a `PolicyError` (fail-closed).

### No manual `allowed_operations` here

The `pilot-safe-v1` preset expands into the `allowed_operations` list automatically.
Do not manually specify `allowed_operations` when using `scope`.

## 4. Interlock Conditions

Per ADR-013 dual interlock, Tier 2+ operations are authorized only when **both**
conditions hold:

| Level | Condition | Checked by |
|---|---|---|
| Policy | `active_tier >= 2`, non-empty `allowed_operations`, non-null `briefing_ref` whose file exists | `check_tier2_authorized()` |
| Sentinel | `<root>/documenter/.operator_ingress_ready` exists | `operator_ingress_ready()` |

**Verification:** `python3 -m documenter_service --verify-activation --root .`
or `python3 tools/activation_helper.py verify --root .` report states:
- `baseline` (exit 0): no overlay applied, effective is Tier 1.
- `active` (exit 0): overlay merged valid, readiness sub-checks shown.
- `invalid` (exit 2): overlay present but load/validation/containment/XOR failed.

## 5. Operator Responsibilities

The operator must perform the following **out-of-session** acts:

1. **Create external directories** (e.g. `~/.council/briefings/`) with
   appropriate permissions.
2. **Place a signed briefing** at an absolute path outside the workspace root
   (the operator signs/adapts this draft and stores the operative copy externally).
3. **Create the activation overlay** (from `activation-overlay-pilot-safe-v1.example.yml`
   or `python3 tools/activation_helper.py template --scope pilot-safe-v1`) at
   `DOCUMENTER_ACTIVATION_PATH` (or the default `~/.council/documenter_activation.yml`),
   with `briefing_ref` pointing to the operator's signed external briefing.
4. **Start the Operator Ingress** with required environment variables:
   `COUNCIL_OPERATOR_SECRET` (HMAC signing secret — never in files),
   `COUNCIL_OPERATOR_ID`, and `COUNCIL_STATE_ROOT` (defaults to current directory).
   On `READY`, the sentinel `documenter/.operator_ingress_ready` is created.
5. **Decide on MCP registration** and Tier activation decisions — operator-only.
6. **Operate within scope**: delegate/write through the service, review diffs,
   ensure safe-only changes.

## 6. Approval Mode

### Default: fail-closed (no solo)

- `allow_solo_approval` defaults to `false` (fail-closed). Self-approval is
  **not permitted**. A distinct operator principal must approve each write proposal.
- If the operator chooses to enable solo approval for this pilot:
  - Set `allow_solo_approval: true` in the overlay (commented-out in the example).
  - Solo approval is **only permitted for `trust_level: safe`** matched operations.
  - Requires typed acknowledgment token: `CONFIRMED_SOLE_REVIEWER` on `--approve`.
  - `min_approval_delay_seconds` must be in range [60, 86400]; default value is 300
    (operator decision per ADR-017 / consensus).
  - Review-gated presets are not solo-self-approvable by design.

## 7. Constraints

- **Minimal scope:** 2 target documents, 1 operation type (`update@safe`).
  This is intentionally narrow for the pilot.
- **One doc per invocation spirit:** multi-file changes are reserved; each
  delegate call targets a single document.
- **Diff preview required:** every write must pass through `delegate-preview`
  before `delegate-write`.
- **Verify before act:** always run `--verify-activation` before proceeding to
  delegate/write.

## 8. Ramp and Review

Following the bounded-experiment model (from solo-operator consensus):

- **Clean cycle:** one full `delegate(preview=False)` → `approve` → `apply_write`
  with exactly one `approved` decision, zero failures, clean `reconcile`.
- **Widening:** after **5 consecutive clean cycles**, operator may expand by
  exactly one change_type or one target document; re-measure 5 cycles per expansion.
- **Other presets as ramp options:** `docs-maint-safe` (mechanical, 24 targets),
  `docs-content-review` (content, 24 targets, review-gated), `ru-sync-review`
  (RU translation, 18 targets, review-gated).
- **Review date:** mandatory re-evaluation within **30 days** of activation to
  assess scope adequacy, residual risks, and whether to continue, narrow, or
  revert.

## 9. Deactivation / Rollback

1. Stop the Operator Ingress process.
2. Remove the sentinel file: `rm -f <root>/documenter/.operator_ingress_ready`.
3. Remove or neutralize the overlay file (delete or point `DOCUMENTER_ACTIVATION_PATH`
   to a non-existent path, or unset the env variable).
4. Verify Tier 1 baseline is restored: `--verify-activation` should return
   `baseline` with `active_tier: 1`, empty `allowed_operations`.
5. Revert any applied changes via `git restore <file>`.
6. Run `--reconcile` to resolve any leftover intent records.

## 10. Guarantees and Limits

- **Runtime-merge only:** effective policy is base + overlay; the repo policy file
  is never modified.
- **Fail-closed:** absent overlay → Tier 1 baseline. Invalid overlay → explicit
  `PolicyError` (loud, no silent fallback). Unknown keys → rejected.
- **Procedural boundary:** containment relies on code checks + same-UID execution,
  not true filesystem isolation.
- **Helper is read-only:** `activation_helper.py` does not write repo policy,
  create out-of-workspace files, or create/remove the sentinel.
- **No repo-policy materialization:** the overlay does not merge into or rewrite
  `documenter_policy.yml`. The repo file stays at `active_tier: 1`.

---

*End of draft. Operator: store the signed operative briefing outside the workspace
and reference it from the activation overlay. This repo draft is for review and
template purposes only.*
