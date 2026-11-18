# Tier 2 Activation — Runtime Overlay & Scope Presets (Implementation Spec)

Status: **approved implementation spec (Step 1)** — decision-aligned; replaces prior draft.
Scope: `documenter_service/` core/CLI, `tools/` helper, tests. **No `docs/`/manifest/CHANGELOGS edits** (deferred to Step 7, Documentation Worker skill + explicit operator Approve). Repo `documenter_policy.yml` remains the Tier 1 baseline and is **never rewritten** by this mechanism.

---

## 1. Overview & data flow

### Goals and invariants
- **Source of truth = runtime merge overlay.** `load_policy()` reads the base repo policy (Tier 1 baseline) plus an external activation overlay file and expands `scope` **in memory**. Activation/deactivation = overlay content/presence + `briefing_ref` file existence + Operator Ingress sentinel. No rewrite/materialization of `documenter_policy.yml`.
- **Dual interlock preserved (ADR-016):** Tier 2+ authorized only when effective policy satisfies policy conditions (`active_tier >= 2`, non-empty `allowed_operations`, non-null `briefing_ref` whose file exists) **and** sentinel `<root>/documenter/.operator_ingress_ready` exists (`check_tier2_authorized`, unchanged semantics).
- **Fail-closed:** absent overlay => base Tier 1 (valid). **Present** overlay that is unreadable/malformed/containment-violating/allowlist-XOR-narrowing-invalid or that yields an invalid merged policy => `PolicyError` (loud). No silent fallback to base for an invalid present overlay.
- **Procedural boundary (same-UID):** overlay path and `briefing_ref` must be absolute and outside workspace root; security relies on containment/allowlist + fail-closed checks, not true FS isolation.

### Base policy (repo, baseline)
- File: `policy_path(root, env)` (`DOCUMENTER_POLICY_PATH` or `<root>/documenter_policy.yml`). Must remain load-valid Tier 1 baseline, e.g. `active_tier: 1`, `allowed_operations: []`, `briefing_ref: null`, `allow_solo_approval: false`, `min_approval_delay_seconds: 300`. `load_policy()` fails closed on base read/parse/validation errors as today.

### Overlay (external, operator-controlled)
- **Path:** `DOCUMENTER_ACTIVATION_PATH` env (explicit) else default `~/.council/documenter_activation.yml` (`os.path.expanduser`). Resolved to an absolute path.
- **Containment:** resolved overlay path MUST be absolute and **outside workspace root** (`root`, abspath); a path inside (or equal to) workspace root => `PolicyError`.
- **Presence rules:**
  - **Explicit env set:** if the resolved path does not exist, or is not a file/readable => `PolicyError` (fail-closed, loud misconfiguration). If it exists but fails containment => `PolicyError`.
  - **Default (env unset):** if the default path does not exist => **absent** (no activation, return base). If it exists => treated as present and must fully pass containment/load/validation.
- **Format:** UTF-8 YAML mapping (flat). Parsed with `yaml.safe_load` only. Empty/`null` document => treat as empty mapping `{}` (then subject to XOR/validation rules below).

### Runtime load/merge flow (`load_policy`)
1. Load + `validate_policy` **base** from `policy_path` (unchanged fail-closed behavior) with `manifest_ids`. Let `base = Policy(...)`, `base_fields = base.as_dict()`.
2. Resolve/load overlay for `root, env`:
   - `overlay, overlay_path, overlay_meta = load_activation_overlay(root, env)` where overlay is `None` when absent, else a normalized overlay dict; on any present-but-invalid condition raise `PolicyError`.
3. **Absent overlay:** attach activation metadata (`overlay_present=False`, `overlay_path=None`, `scope=None`, `mode=None`, `activation_source='base'`) to `base` and return `base`.
4. **Present overlay:** compute `effective_fields = apply_activation_overlay(base_fields, overlay, root, manifest_ids=manifest_ids)` (expands scope/validates XOR & narrowing & briefing containment, merges activation keys over base while preserving base operational knobs).
5. `effective = validate_policy({"documenter_policy": effective_fields}, manifest_ids=manifest_ids)` (existing 7 rules + field/range checks apply to the merged result).
6. Set `effective.path = base.path` (canonical base policy path), and activation metadata: `overlay_present=True`, `overlay_path`, `activation_scope` (scope id or None), `activation_mode` (`'scope'|'override'`), `activation_source='overlay'`. Return `effective`.

**Precedence:** `effective = (DEFAULTS <- base file fields) <- overlay activation fields` (via re-validate on merged fields). Overlay supplies/overrides **only**: `active_tier`, `allowed_operations` (expanded from `scope` or explicit override), `briefing_ref`, `allow_solo_approval`, `min_approval_delay_seconds`. All other policy knobs (e.g. `audit_freshness`, `approval_expiry_window`, `rescan_batch_ceiling`, `max_diff_bytes`, `sync_latency_budget_ms`, `lock_wait_timeout`, `operator_approval_timeout`, `notification_mode`, `glossary_*`, retry/LLM params, `version`) come from **base**.

**Transparency:** `Service.load_policy_safe()` (cached once per instance) and all callers (`status`, `check_tier2_authorized`, `match_operation`, `write` propose/approve/apply, CLI) continue to consume the `Policy` returned by `load_policy`; no call-site signature changes. Cached behavior unchanged (one load/warn per instance). Overlay/briefing/sentinel are read at load/check time (TOCTOU same as today; long-lived process sees changes on restart/new instance).

---

## 2. `documenter_service/core/scope_presets.py`

Deterministic registry of activation presets. Targets are **explicit manifest IDs** (auditable, no runtime manifest discovery needed for expansion). Single-operation presets (v1).

### Constants
```python
ALL_MANIFEST_IDS: list[str] = [
    "documentation-rules",
    "documenter-service",
    "documenter-service-approval-surface",
    "documenter-service-configuration-guide",
    "documenter-service-mvp-contract",
    "documenter-service-mvp-data-models",
    "documenter-service-mvp-interfaces",
    "documenter-service-policy-reference",
    "execution-runtime",
    "glossary",
    "operator-ingress",
    "planned-architecture",
    "planned-architecture-decisions",
    "planned-architecture-layer-0",
    "planned-architecture-layer-1",
    "planned-architecture-layer-2",
    "project-concept",
    "project-reference",
    "protocol-core",
    "scenario",
    "service-contract",
    "service-contract-error-management",
    "translation-project",
    "translation-project-contract",
]  # 24

RU_TRANSLATED_IDS: list[str] = [
    "documentation-rules",
    "documenter-service",
    "documenter-service-approval-surface",
    "documenter-service-configuration-guide",
    "documenter-service-policy-reference",
    "execution-runtime",
    "glossary",
    "operator-ingress",
    "planned-architecture",
    "planned-architecture-layer-0",
    "planned-architecture-layer-1",
    "planned-architecture-layer-2",
    "project-concept",
    "project-reference",
    "protocol-core",
    "scenario",
    "service-contract",
    "service-contract-error-management",
]  # 18
```

### Preset definitions (exact)
Each operation entry: `{"type": "operation", "change_type": ..., "trust_level": ..., "targets": [...], "requires_diff_preview": True}`.

| scope id | description | change_type | trust_level | targets |
|---|---|---|---|---|
| `pilot-safe-v1` | Minimal safe pilot: mechanical updates to 2 operational docs | `update` | `safe` | `["documenter-service-configuration-guide", "operator-ingress"]` |
| `docs-maint-safe` | Mechanical maintenance (metadata) across full doc corpus | `update` | `safe` | `ALL_MANIFEST_IDS` (all 24) |
| `docs-content-review` | Content/normative updates across full doc corpus (review-gated) | `update` | `review` | `ALL_MANIFEST_IDS` (all 24) |
| `ru-sync-review` | RU translation create/sync for docs that have translations (review-gated) | `create_ru` | `review` | `RU_TRANSLATED_IDS` (18) |

Registry stores a deep-copyable structure, e.g. `_PRESETS[scope_id] = {"description": str, "operations": [<entry>...]}`.

### API
```python
from __future__ import annotations
from copy import deepcopy
from typing import Any

def list_scope_ids() -> list[str]:
    """Stable sorted list of known scope ids."""

def list_scopes() -> list[dict[str, Any]]:
    """Return [{id, description, change_type, trust_level, target_count, targets}, ...]."""

def get_preset(scope_id: str) -> dict[str, Any] | None:
    """Return preset definition (copy) or None if unknown."""

def expand(scope_id: str, scope_targets: list[str] | None = None) -> list[dict[str, Any]]:
    """Expand a scope id into an allowed_operations list (deep-copied).

    - Unknown scope_id => PolicyError listing available scopes.
    - scope_targets is None => use preset targets.
    - scope_targets provided => narrowing-only:
        - must be a non-empty list of strings (else PolicyError);
        - every id must be in the preset target set, else PolicyError
          ("scope_targets widens/invalid for scope ..." listing offending ids);
        - effective targets = sorted(unique(scope_targets)) (deterministic subset).
    Returns a list with 1 operation entry compatible with validate_policy/match_operation.
    """
```
- Raises `PolicyError` (from `core.policy`) for fail-closed behavior; use local import to avoid cycles if needed. No I/O.

---

## 3. `documenter_service/core/activation.py`

Overlay path resolution, containment, loading/normalization, expansion, and merge into effective policy fields.

### Constants / helpers
```python
from __future__ import annotations
import os
from typing import Any

ACTIVATION_ENV = "DOCUMENTER_ACTIVATION_PATH"
DEFAULT_ACTIVATION_PATH = os.path.expanduser("~/.council/documenter_activation.yml")
OVERLAY_ALLOWLIST: frozenset[str] = frozenset({
    "active_tier", "scope", "allowed_operations", "scope_targets",
    "briefing_ref", "allow_solo_approval", "min_approval_delay_seconds",
})

def _abs_real(path: str) -> str:
    return os.path.realpath(os.path.abspath(os.path.expanduser(path)))

def _is_under(child: str, root: str) -> bool:
    child_r, root_r = _abs_real(child), _abs_real(root)
    try:
        return os.path.commonpath([child_r, root_r]) == root_r
    except ValueError:
        return False  # different drives; treat as not under

def _require_outside_workspace(path: str, root: str, *, what: str, must_be_absolute: bool = True) -> str:
    """Return absolute real-normalizable path; PolicyError if not absolute (when required)
    or if inside/equal to workspace root."""
    if must_be_absolute and not os.path.isabs(path):
        raise PolicyError(f"{what} must be an absolute path outside workspace root: {path!r}")
    if _is_under(path, root):
        raise PolicyError(f"{what} must be outside workspace root ({root!r}): {path!r}")
    return os.path.abspath(os.path.expanduser(path))
```
Containment uses `realpath` to resist symlink escape into workspace. (`PolicyError` imported from `.policy` via local import where needed to avoid circular import.)

### Path resolution
```python
def resolve_activation_path(root: str, env: dict | None = None) -> tuple[str, bool]:
    """Return (resolved_path, explicit).
    explicit=True when ACTIVATION_ENV is set.
    - explicit: value stripped; must be absolute and outside workspace root (PolicyError otherwise).
      Missing/unreadable/non-file is enforced by load step (fail-closed).
    - default: expanded DEFAULT_ACTIVATION_PATH (normally outside workspace); containment checked if file exists/present.
    """
```

### Overlay loading & normalization
```python
def load_activation_overlay(root: str, env: dict | None = None) -> tuple[dict[str, Any] | None, str | None, bool]:
    """Return (overlay_dict_or_None, overlay_path_or_None, explicit).

    - Default path absent => (None, resolved_default_path, False).
    - Explicit path absent/non-file => PolicyError.
    - Present: enforce overlay path absolute+outside workspace root; read with yaml.safe_load;
      parse/validate; return (normalized_overlay, path, explicit).
    Any present-but-invalid condition => PolicyError (fail-closed).
    """
```
Load/validate steps (in order, fail-closed with clear `PolicyError.reason`):
1. Resolve `(path, explicit)`. If explicit and not `os.path.isfile(path)`: `PolicyError(f"activation overlay not found at {path}")`.
2. If not explicit and not `os.path.isfile(path)`: return `(None, path, False)` (absent).
3. Containment: `_require_outside_workspace(path, root, what="activation overlay path", must_be_absolute=True)` (explicit must already be absolute; default is absolute).
4. Read/parse: on OSError/YAMLError => `PolicyError(f"activation overlay unreadable or invalid YAML: ...")`. Accept `None` as `{}`.
5. Must be `dict` (mapping) else `PolicyError`.
6. **Strict allowlist:** any key not in `OVERLAY_ALLOWLIST` => `PolicyError` listing unknown keys (sorted).
7. **XOR source:** exactly one of `scope` and `allowed_operations` present.
   - neither => `PolicyError("activation overlay must specify exactly one of 'scope' or 'allowed_operations'")`
   - both => `PolicyError("activation overlay must not specify both 'scope' and 'allowed_operations'")`
8. **scope_targets:** if present, `scope` must be present else `PolicyError("scope_targets requires 'scope'")`. If present, must be a `list` of non-empty strings (light check; narrowing validated in expand) — reject non-list early.
9. **Field sanity (early, fail-closed):**
   - `active_tier` if present: reject bool; must be int in {0,1,2,3} type-wise here? final `validate_policy` enforces; but allowlist permits activation intent — accept int/bool-guard consistent with validate_policy (reject bool, non-int) to give clear errors.
   - `briefing_ref` if present and not None/empty: must be `str`, absolute, outside workspace root (`_require_outside_workspace(..., what="briefing_ref")`).
   - `allow_solo_approval` if present: must be bool.
   - `min_approval_delay_seconds` if present: must be int (not bool); range enforced by validate_policy, but early type sanity ok.
10. Return `(overlay, path, explicit)`.

> Note: `active_tier` value/range and most field ranges are ultimately enforced by `validate_policy` on merged fields; overlay loader enforces allowlist/containment/XOR/shape and briefing path rules that are overlay-specific.

### Merge / expansion
```python
def apply_activation_overlay(
    base_fields: dict[str, Any],
    overlay: dict[str, Any],
    root: str,
    manifest_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Return effective policy fields (copy) = base knobs + overlay activation.
    Preserves all base operational knobs. Raises PolicyError on invalid expansion/narrowing/containment."""
```
Behavior:
1. `effective = dict(base_fields)` (shallow copy of fields; lists/dicts like allowed_operations replaced below).
2. Determine `allowed_operations`:
   - if `"scope" in overlay`: `ops = scope_presets.expand(overlay["scope"], overlay.get("scope_targets"))`
   - else (advanced override, XOR guaranteed): `ops = overlay["allowed_operations"]`; require `isinstance(ops, list)` else `PolicyError("allowed_operations must be a list")` (deep validation by `validate_policy`).
3. `effective["allowed_operations"] = ops`
4. For `k in ("active_tier", "briefing_ref", "allow_solo_approval", "min_approval_delay_seconds")`: if `k in overlay` then `effective[k] = overlay[k]`.
5. **Post-merge containment:** if effective `briefing_ref` is a non-empty string, enforce absolute + outside workspace root (covers overlay-supplied value; baseline is null). If activation overlay is present this ensures Tier 2 briefing lives outside workspace.
6. Return `effective`.

`manifest_ids` is accepted for forward-compat/signature symmetry (targets validated by `validate_policy`); not required for preset expansion beyond what presets encode.

### Convenience
```python
def activation_summary(policy) -> dict[str, Any]:
    """Build a status/CLI-friendly summary from an effective Policy (or base policy with metadata)."""
```
(Reads `policy` attributes/fields: overlay_present/path/scope/mode/source, effective active_tier, briefing_ref, allowed_operations count, briefing_exists under root when known, etc.)

---

## 4. Integration: `policy.py`

### `Policy` metadata (additive, backward-compatible)
Extend `Policy` to carry activation metadata without breaking existing construction/usage:
- Keep `__init__(self, fields, path=None)` working as today.
- Store attributes with defaults: `self.overlay_present=False`, `self.overlay_path=None`, `self.activation_scope=None`, `self.activation_mode=None` (`'scope'|'override'|None`), `self.activation_source='base'`.
- `as_dict()` remains `dict(self._fields)` (unchanged). Metadata accessed via attributes and/or a helper.

### `load_policy` (runtime merge, transparent)
```python
def load_policy(root: str, env=None, manifest_ids=None) -> Policy:
    path = policy_path(root, env)
    if not os.path.isfile(path):
        raise PolicyError(f"policy file not found: {path}")
    try:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        raise PolicyError(f"policy file {path} unreadable or invalid YAML: {exc}") from exc
    base = validate_policy(raw, manifest_ids=manifest_ids)
    base.path = path

    # --- runtime activation overlay (transparent) ---
    from .activation import load_activation_overlay, apply_activation_overlay
    overlay, overlay_path, _explicit = load_activation_overlay(root, env)
    if overlay is None:
        base.overlay_present = False
        base.overlay_path = overlay_path if _explicit else None  # None for absent default
        base.activation_scope = None
        base.activation_mode = None
        base.activation_source = "base"
        return base

    base_fields = base.as_dict()
    effective_fields = apply_activation_overlay(base_fields, overlay, root, manifest_ids=manifest_ids)
    effective = validate_policy({"documenter_policy": effective_fields}, manifest_ids=manifest_ids)
    effective.path = path
    effective.overlay_present = True
    effective.overlay_path = overlay_path
    effective.activation_scope = overlay.get("scope")
    effective.activation_mode = "scope" if "scope" in overlay else "override"
    effective.activation_source = "overlay"
    return effective
```
- **Base-only path unchanged** when no overlay (same validation, same `Policy` fields/path semantics). Existing tests/callers unaffected.
- **No change** to `policy_path` (base resolution), `validate_policy` rules, `check_tier2_authorized`/`check_tier3_authorized`, `operator_ingress_ready`, `match_operation`/`match_pattern`, or trust/range semantics. They operate on the effective `Policy` object as before.
- **`load_policy_safe` in `__main__.py` unchanged:** it caches `(policy, err)` from `load_policy`; invalid present overlay raises `PolicyError` => cached as degraded error with one stderr warning (correct fail-closed surfacing) and delegates refused via existing paths. Audit/status proceed per existing degradation-tolerant behavior but will reflect policy load failure as today when policy invalid.
- **`DOCUMENTER_POLICY_PATH` containment:** base policy path behavior unchanged for compatibility. Containment enforced on **overlay path and effective/overlay `briefing_ref`** (and overlay is the activation carrier). (R&S recommended base-path containment as defense-in-depth — out of v1 scope except as doc note.)
- **Manifest IDs:** pass-through as today so rule 5 validates targets (including preset/override targets) against manifest when provided.

---

## 5. Integration: `status.py`

`status(registry, policy=None, *, target_id=None, root=None)` keeps existing return shape/keys and sentinel/interlock logic (`_tier_interlock_state` already evaluates the effective policy) — **additive only**.

### Add `activation` block
```python
activation = {
    "overlay_present": bool(getattr(policy, "overlay_present", False)),
    "overlay_path": getattr(policy, "overlay_path", None),
    "scope": getattr(policy, "activation_scope", None),
    "mode": getattr(policy, "activation_mode", None),          # 'scope'|'override'|None
    "source": getattr(policy, "activation_source", "base" if policy is not None else "none"),
    "briefing_ref": policy.get("briefing_ref") if policy is not None else None,
    "allowed_operations_count": len(policy.get("allowed_operations") or []) if policy is not None else 0,
    "sentinel_present": (operator_ingress_ready(root) if root else None),
    "briefing_exists": <bool or None>,  # if briefing_ref and root known: os.path.isfile(resolved); resolved relative-to-root if not abs (legacy), else as-is
}
```
- Compute `briefing_exists` defensively (resolve non-abs relative to `root` as `check_tier2_authorized` does; None if unknown). Do not raise.
- Include `"activation": activation` in the returned dict. Existing keys (`active_tier`, `registry`, `scan_status`, `tier_interlock`) unchanged.
- Rationale: answers “is activation intent loaded / what scope / why not ready?” without breaking consumers that ignore unknown keys.

---

## 6. Integration: `__main__.py` & CLI

### New mode: `--verify-activation`
- Add to mutually exclusive mode group:
  ```python
  mode.add_argument("--verify-activation", action="store_true", dest="verify_activation",
                    help="verify runtime activation overlay + effective policy and "
                         "report interlock readiness (no writes)")
  ```
- No operator-id required. Uses `Service(root)` (respects `DOCUMENTER_POLICY_PATH`/`DOCUMENTER_DATA_DIR`/`DOCUMENTER_ACTIVATION_PATH` envs).
- Behavior (reports state; read-only):
  1. Resolve overlay path/explicit via `activation.resolve_activation_path(root, env)`.
  2. Detect absence: if not explicit and default file missing => **baseline/no-overlay**.
  3. Attempt effective load: `policy, policy_err = service.load_policy_safe()` (catches fail-closed overlay/base errors). For richer detail, may also attempt `load_activation_overlay` directly in a non-caching/reporting helper, but results must be consistent with `load_policy` semantics.
  4. Compute readiness checks against effective policy and `root`: `briefing_ref` present/non-null, `briefing_exists`, `sentinel_present` (`operator_ingress_ready(root)`), `tier2_authorized` (`check_tier2_authorized` would pass? evaluate conditions without raising, or catch StructuredError), plus effective tier/ops count/scope/mode/source.
  5. **States reported:**
     - `baseline` (exit 0): no overlay applied; effective is base Tier 1.
     - `active` (exit 0): overlay present and effective policy loads valid (activation intent merged). Readiness sub-checks indicate whether interlock is fully ready (sentinel/briefing) — valid config even if not yet ready.
     - `invalid` (exit 2): overlay present but load/validation/containment/XOR/expansion fails (fail-closed) or base fails. Emit structured refusal/error info.
- **Exit codes:** `0` for `baseline` or `active` (valid, report-only); `2` for `invalid` (structured refusal via `_print_json` of a StructuredError-shaped object or dedicated payload consistent with existing refusal style); `3` reserved for unexpected internal error (existing handler).
- **Output:** honors `--json` (one JSON object, last/only stdout line) else human-readable. Suggested JSON shape (additive, stable keys):
  ```json
  {
    "mode": "verify-activation",
    "state": "baseline|active|invalid",
    "ok": true|false,
    "overlay": {"present": false, "path": "...", "explicit": false, "scope": null, "mode": null},
    "effective": {"active_tier": 1, "allowed_operations_count": 0, "briefing_ref": null,
                  "briefing_exists": null, "allow_solo_approval": false,
                  "min_approval_delay_seconds": 300, "source": "base"},
    "interlock": {"sentinel_present": false, "tier2_policy_ready": false, "tier2_authorized": false, "reason": "..."},
    "errors": []
  }
  ```
  Human output prints labeled lines and readiness checklist (PASS/FAIL) and, for active, the expanded scope summary (id, op count/type/targets summary) without dumping excessive noise.
- Place handler in `main()` with others (e.g. after `--status` branch or as its own `if args.verify_activation:`). Compatible with existing flags (`--root`, `--json`).

### Existing modes
- Unchanged. `Service`/`load_policy` runtime merge makes `--status`, `--delegate-*`, `--approve`, `--override-gate`, `--reconcile` operate on effective policy transparently. `--status` output gains additive `activation` field in JSON (human printer may optionally mention activation/source/scope; if changed, keep concise and backward-tolerant).

---

## 7. Operator helper script (`tools/...`)

**File:** `tools/activation_helper.py` (Python 3.11+, stdlib + PyYAML only), executable bit optional; invoked as `python3 tools/activation_helper.py ...` from repo root. Reuses `documenter_service.core` (activation, policy, scope_presets, status/interlock helpers) by adding repo root to `sys.path` like other tools; **must not** import or modify `documenter_policy.yml` writing logic.

### Interface
```
usage: activation_helper.py [--root ROOT] [--json] <command> [options]

commands:
  verify                Verify effective activation (same checks as --verify-activation) and print diagnostics
  print-effective       Print effective policy/activation summary (expanded ops summary)
  template              Print an example overlay YAML to stdout (no file writes)
  deactivate-hints      Print safe deactivation steps (no file/sentinel changes)
```
Options:
- `--root ROOT` (default: repo root, consistent with other tools)
- `--json` (machine-readable output where applicable)
- `template` options: `--scope {pilot-safe-v1,docs-maint-safe,docs-content-review,ru-sync-review}` (default `pilot-safe-v1`), `--briefing-ref PATH` (placeholder absolute path shown), `--active-tier 2` (default 2), `--solo` / `--no-solo` (default no-solo example), `--min-delay N` (default 300 when solo shown)

### Operations (all read-only w.r.t. repo/protected state)
- **verify / print-effective:** load effective policy via `load_policy`/service logic, report overlay path/containment, scope/mode, expanded ops summary (id/type/trust/target count + list for small sets), briefing_ref existence, sentinel presence, interlock readiness, base-vs-effective source. Exit 0 on valid baseline/active, 2 on invalid.
- **template:** emit a minimal, valid overlay example to **stdout only** (flat allowlist keys, selected `scope`, absolute `briefing_ref` placeholder outside workspace, optional solo fields). **Does not create** `~/.council/...` or any file.
- **deactivate-hints:** print instructions: remove/neutralize external overlay file (`DOCUMENTER_ACTIVATION_PATH`/default), stop Operator Ingress and remove sentinel `<root>/documenter/.operator_ingress_ready` (operator action), confirm with `--verify-activation`/`--status` returning Tier 1 locked. No mutations performed.

### Guarantees
- **Does NOT write `documenter_policy.yml`.** **Does not create files outside workspace** and **does not create/remove the sentinel** (those are operator actions). No `--apply` that mutates activation state; it may only print commands/hints.

### Example usage
```bash
python3 tools/activation_helper.py verify --root .
python3 tools/activation_helper.py template --scope pilot-safe-v1 > /tmp/pilot-overlay.yml   # operator moves to ~/.council/...
DOCUMENTER_ACTIVATION_PATH=/home/ea/.council/documenter_activation.yml \
  python3 tools/activation_helper.py print-effective --json
python3 -m documenter_service --verify-activation --root . --json
python3 tools/activation_helper.py deactivate-hints
```

---

## 8. Test plan

Add/update tests (pytest or unittest consistent with repo; existing tests use `unittest`). Prefer new focused files + minimal/no changes to existing tests (which must keep passing: no overlay env/default absent in tmp test envs).

### New: `tests/test_activation_overlay.py` (core, fast/unit-heavy)
- **Overlay absent = baseline:** default path missing and no env => `load_policy` returns base Tier 1, `overlay_present` False, no behavior change.
- **Explicit env path missing/non-file:** `PolicyError` (fail-closed).
- **Present-but-invalid => PolicyError (no fallback):** invalid YAML, unreadable file (perm), non-mapping, empty mapping treated as `{}` then XOR violation.
- **Strict allowlist:** unknown key (e.g. `audit_freshness`, `version`, typo) => `PolicyError`.
- **Containment:** overlay path inside workspace root (explicit pointing under root) => `PolicyError`; relative explicit overlay path => `PolicyError`; `briefing_ref` relative => `PolicyError`; `briefing_ref` inside workspace root => `PolicyError`; `briefing_ref` absolute outside root => accepted (file-existence checked by interlock, not loader except path form).
- **XOR:** neither scope nor allowed_operations => `PolicyError`; both => `PolicyError`; `scope_targets` without scope => `PolicyError`.
- **Unknown scope:** `PolicyError` mentioning available scopes.
- **Preset expansion correctness:** each of 4 presets yields expected `change_type`/`trust_level`/`requires_diff_preview`/`type` and exact target sets/counts (pilot 2, maint 24, content 24, ru 18 ids equal to constants).
- **Narrowing-only:** `scope_targets` subset of preset targets => narrowed sorted-unique targets; widening/foreign id => `PolicyError`; empty list => `PolicyError`; duplicates handled deterministically.
- **Advanced override:** `allowed_operations` (XOR) passes through and is validated by `validate_policy` (valid case merges to tier2; invalid case e.g. bad floor/unknown change_type/targets not in manifest when manifest_ids provided => `PolicyError`).
- **Merge semantics:** base operational knobs preserved (e.g. custom `audit_freshness`/timeouts in base unchanged); overlay sets activation keys (active_tier, briefing_ref, solo fields, ops) only; merged tier>=2 with ops+briefing_ref passes `validate_policy`.
- **Solo fields/ranges via overlay:** bool/range accepted per existing rules; bad type/range => `PolicyError` (loader and/or validate_policy).
- **`scope_presets` API:** `list_scope_ids` stable, `get_preset` copies, expand deterministic.

### New: `tests/test_activation_cli.py` (CLI + helper, subprocess/unit as appropriate)
- **`--verify-activation`:** baseline/no overlay (default absent) => exit 0, JSON/human state `baseline`; valid overlay (tier2, briefing file present outside root, sentinel absent/present cases arranged in tmp env) => exit 0 state `active` with correct readiness/checks and expanded scope summary; invalid present overlay => exit 2 structured refusal/failure state.
- **Status activation fields:** `Service(...).status()` / CLI `--status --json` includes additive `activation` block and correct `tier_interlock` under runtime-merged effective policy.
- **Helper script:** `verify`/`print-effective` reflect state; `template --scope pilot-safe-v1` prints valid YAML to stdout containing allowlist keys and scope (no files written, assert repo policy unchanged); `deactivate-hints` prints guidance; exits correct.

### Targeted integration/regression (reuse fixtures/patterns from existing tests)
- **Interlock + runtime merge:** with overlay producing valid tier2 policy but no sentinel => `check_tier2_authorized`/delegate still `tier_interlock` (sentinel); with sentinel and valid briefing file => authorized (mirror `tests/test_documenter_ingress_sentinel.py` matrix, but policy comes via overlay+base). Existing sentinel tests remain valid (construct Policy directly) — keep passing.
- **CLI tier2 flow:** adapt pattern of `tests/test_documenter_cli_tier2.py` to an overlay-driven activation case (env `DOCUMENTER_ACTIVATION_PATH` pointing to overlay outside corpus root; briefing outside root) confirming audit→delegate-write→approve/apply works with runtime merge and base stays Tier 1 file. Existing tier2 tests (policy via `DOCUMENTER_POLICY_PATH`) keep passing.
- **Solo activation:** effective overlay can enable solo fields; solo rules unchanged (`tests/test_solo_activation.py` regressions).
- **No overlay in existing environments:** confirm existing test suite areas touched by policy loading are unaffected (default path absent).

### Coverage notes
- Test both `DOCUMENTER_ACTIVATION_PATH` explicit and default-resolution behaviors (including default missing => absent).
- Use `tmp_path`/`tempfile` outside simulated workspace root for overlay/briefing to satisfy containment; simulate workspace `root` as a temp dir.
- Assert fail-closed messages/categories where practical (`PolicyError`/`gate_failure` mapping).

---

## 9. Risks, edge cases & doc-touchpoints

### Risks / edge cases (and chosen handling)
- **Invalid present overlay is fail-closed (loud):** intentional. Unlike a hypothetical silent-skip, a broken/misplaced overlay degrades `load_policy_safe` (one stderr warning) and causes delegate refusal / invalid state in verify — safer than silently ignoring operator intent. Operators fix or remove the overlay.
- **Explicit `DOCUMENTER_ACTIVATION_PATH` to missing file:** treated as `PolicyError` (fail-closed) to surface misconfiguration; default missing => absent.
- **Default path exists unintentionally:** would be applied (by design); path is outside workspace (`~/.council/...`) so unlikely in CI, but environments should not leave stray activation files.
- **Stronger path policy:** `briefing_ref` (effective when overlay active) must be absolute + outside workspace root (stricter than legacy relative-to-root resolution) — aligns with procedural boundary; baseline keeps `null`. Base `DOCUMENTER_POLICY_PATH` containment not enforced in v1 for compatibility.
- **Symlink/TOCTOU:** containment uses `realpath`; existence/readiness checked at load/authorization time and can race with later changes (same class of issue as today for briefing/sentinel/policy files).
- **Policy cache:** `Service` caches once per instance; overlay changes require new process/instance to take effect (consistent with current policy caching).
- **Preset/manifest drift:** presets embed explicit manifest IDs in code; if the corpus/manifest changes, presets (and tests) must be updated in code (auditable). `validate_policy` rule 5 with `manifest_ids` will still catch unknown targets when invoked with a manifest.
- **Scope/targets semantics:** `scope_targets` narrowing-only, non-empty, subset of preset targets; `allowed_operations` advanced override is XOR with `scope` and fully validated (may tighten, not below floors). No base operational knobs exposed via overlay by design.
- **Runtime merge vs policy-on-disk:** tools or humans inspecting `documenter_policy.yml` will see Tier 1 baseline; effective activation is visible via `--verify-activation`/`--status`/helper and runtime behavior. This is intentional (source-of-truth = overlay).

### Doc-touchpoints (Step 7, propose via Documentation Worker skill + Approve)
- `docs/en/documenter-service/policy-reference.md` / `-RU`: overlay mechanism (`DOCUMENTER_ACTIVATION_PATH`, default, allowlist, XOR/narrowing), `scope` presets registry/semantics, containment & fail-closed rules, activation/deactivation procedure (runtime merge, no repo-policy rewrite), examples.
- `docs/en/documenter-service/configuration-guide.md`, `index.md`, `mvp-contract.md`: activation/interlock narrative updated to include overlay path and effective-policy reporting; clarify baseline stays Tier 1.
- `docs/en/operator-ingress/index.md` (and RU) / `operator_ingress/REGISTRATION.md` as needed: sentinel/activation flow remains, note overlay-driven policy readiness.
- `docs/en/planned-architecture/decisions/index.md` (and changelog): ADR for runtime overlay activation model / preset scopes (if required by project convention) and relation to ADR-016/017.
- `docs/en/glossary/index.md` if new terms introduced (`activation overlay`, `scope preset`).
- Affected `CHANGELOGS/*`, `docs-manifest.yaml` (versions/metadata) — **only via Documentation Worker skill after explicit Approve**.

---
**Step 1 outcome:** concrete, repo-grounded spec aligned with confirmed decisions (runtime merge, strict allowlist incl. `scope`/`scope_targets`, XOR+narrowing, fail-closed present-invalid, containment, 4 presets, helper no repo-policy writes, CLI/status/test surfaces). Ready for Step 2 implementation.
