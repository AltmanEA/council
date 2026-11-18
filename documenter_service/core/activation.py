"""Activation overlay loading, validation, expansion, and merge.

Overlay path resolution, containment, loading/normalization, expansion,
and merge into effective policy fields.

Fail-closed: present-but-invalid => PolicyError (loud, no fallback).
Absent overlay => base Tier 1 unchanged.
"""
from __future__ import annotations

import os
from typing import Any

import yaml

from .policy import PolicyError  # local import — avoids cycles via lazy resolve

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACTIVATION_ENV = "DOCUMENTER_ACTIVATION_PATH"
DEFAULT_ACTIVATION_PATH = os.path.expanduser("~/.council/documenter_activation.yml")

OVERLAY_ALLOWLIST: frozenset[str] = frozenset({
    "active_tier", "scope", "allowed_operations", "scope_targets",
    "briefing_ref", "allow_solo_approval", "min_approval_delay_seconds",
})

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _abs_real(path: str) -> str:
    """Return os.path.realpath(os.path.abspath(os.path.expanduser(path)))."""
    return os.path.realpath(os.path.abspath(os.path.expanduser(path)))


def _is_under(child: str, root: str) -> bool:
    """Return True when child is inside or equal to root (realpath-resolved)."""
    child_r, root_r = _abs_real(child), _abs_real(root)
    try:
        return os.path.commonpath([child_r, root_r]) == root_r
    except ValueError:
        return False  # different drives/mount points => not under


def _require_outside_workspace(
    path: str, root: str, *, what: str, must_be_absolute: bool = True,
) -> str:
    """Return absolute real-normalizable path; raise PolicyError if not absolute
    (when required) or if inside/equal to workspace root.

    Uses realpath to resist symlink escape into workspace.
    """
    abs_path = os.path.abspath(os.path.expanduser(path))
    if must_be_absolute and not os.path.isabs(abs_path):
        raise PolicyError(f"{what} must be an absolute path outside workspace root: {abs_path!r}")
    if _is_under(abs_path, root):
        raise PolicyError(f"{what} must be outside workspace root ({root!r}): {abs_path!r}")
    return abs_path


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def resolve_activation_path(root: str, env: dict | None = None) -> tuple[str, bool]:
    """Return (resolved_path, explicit).

    explicit=True when ACTIVATION_ENV is set.
    - explicit: value stripped; must be absolute and outside workspace root
      (PolicyError otherwise). Missing/unreadable/non-file is enforced by
      load step (fail-closed).
    - default: expanded DEFAULT_ACTIVATION_PATH (normally outside workspace);
      containment checked if file exists/present.
    """
    environ = os.environ if env is None else env
    raw = environ.get(ACTIVATION_ENV)
    if raw is not None:
        # Explicit: must be absolute.
        val = raw.strip() if isinstance(raw, str) else raw
        _require_outside_workspace(val, root, what="activation overlay path (DOCUMENTER_ACTIVATION_PATH)", must_be_absolute=True)
        return val, True
    # Default.
    return DEFAULT_ACTIVATION_PATH, False


# ---------------------------------------------------------------------------
# Overlay loading & normalization
# ---------------------------------------------------------------------------


def load_activation_overlay(
    root: str, env: dict | None = None,
) -> tuple[dict[str, Any] | None, str | None, bool]:
    """Return (overlay_dict_or_None, overlay_path_or_None, explicit).

    - Default path absent => (None, resolved_default_path, False).
    - Explicit path absent/non-file => PolicyError.
    - Present: enforce overlay path absolute+outside workspace root; read
      with yaml.safe_load; parse/validate; return (normalized_overlay, path,
      explicit).
    Any present-but-invalid condition => PolicyError (fail-closed).
    """
    from .policy import PolicyError  # local import to avoid cycle

    # 1) Resolve path + explicit flag.
    path, explicit = resolve_activation_path(root, env)

    # 2) Existence: explicit must be a file; default absent => absent.
    if not os.path.isfile(path):
        if explicit:
            raise PolicyError(f"activation overlay not found at {path}")
        return (None, path, False)  # default missing => absent

    # 3) Containment: overlay path must be outside workspace root.
    _require_outside_workspace(
        path, root, what="activation overlay path", must_be_absolute=True,
    )

    # 4) Read/parse YAML.
    try:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except OSError as exc:
        raise PolicyError(
            f"activation overlay unreadable at {path}: {exc}"
        ) from exc
    except yaml.YAMLError as exc:
        raise PolicyError(
            f"activation overlay invalid YAML at {path}: {exc}"
        ) from exc

    # None doc => empty mapping.
    if doc is None:
        doc = {}

    # 5) Must be a dict.
    if not isinstance(doc, dict):
        raise PolicyError(
            f"activation overlay must be a YAML mapping (got {type(doc).__name__})"
        )

    overlay: dict[str, Any] = doc

    # 6) Strict allowlist: unknown key => fail.
    unknown_keys = set(overlay.keys()) - OVERLAY_ALLOWLIST
    if unknown_keys:
        raise PolicyError(
            f"activation overlay contains unknown key(s): "
            + ", ".join(sorted(unknown_keys)) + "; "
            f"allowed keys are: {', '.join(sorted(OVERLAY_ALLOWLIST))}"
        )

    # 7) XOR: exactly one of 'scope' / 'allowed_operations'.
    has_scope = "scope" in overlay and overlay["scope"] is not None
    has_ops = "allowed_operations" in overlay and overlay["allowed_operations"] is not None
    if has_scope and has_ops:
        raise PolicyError(
            "activation overlay must not specify both 'scope' and "
            "'allowed_operations'"
        )
    if not has_scope and not has_ops:
        raise PolicyError(
            "activation overlay must specify exactly one of 'scope' or "
            "'allowed_operations'"
        )

    # 8) scope_targets: only allowed with scope; if present must be a list.
    if "scope_targets" in overlay:
        if not has_scope:
            raise PolicyError(
                "scope_targets requires 'scope'"
            )
        st = overlay["scope_targets"]
        if not isinstance(st, list):
            raise PolicyError(
                f"scope_targets must be a list, got {type(st).__name__}"
            )

    # 9) Field sanity (early, fail-closed):
    # active_tier: if present reject bool; accept int.
    if "active_tier" in overlay:
        at = overlay["active_tier"]
        if isinstance(at, bool) or not isinstance(at, int):
            raise PolicyError(
                f"active_tier={at!r} must be an integer (got "
                f"{type(at).__name__})"
            )

    # briefing_ref: if present and not None/empty, must be str, abs, outside root.
    if "briefing_ref" in overlay:
        br = overlay["briefing_ref"]
        if br is not None and br != "":
            if not isinstance(br, str):
                raise PolicyError(
                    f"briefing_ref={br!r} must be a string or null/empty"
                )
            _require_outside_workspace(
                br, root, what="briefing_ref", must_be_absolute=True,
            )

    # allow_solo_approval: must be bool if present.
    if "allow_solo_approval" in overlay:
        asa = overlay["allow_solo_approval"]
        if not isinstance(asa, bool):
            raise PolicyError(
                f"allow_solo_approval={asa!r} must be a boolean "
                f"(got {type(asa).__name__})"
            )

    # min_approval_delay_seconds: must be int (not bool) if present.
    if "min_approval_delay_seconds" in overlay:
        mad = overlay["min_approval_delay_seconds"]
        if isinstance(mad, bool) or not isinstance(mad, int):
            raise PolicyError(
                f"min_approval_delay_seconds={mad!r} must be an integer "
                f"(got {type(mad).__name__})"
            )

    return (overlay, path, explicit)


# ---------------------------------------------------------------------------
# Merge / expansion
# ---------------------------------------------------------------------------


def apply_activation_overlay(
    base_fields: dict[str, Any],
    overlay: dict[str, Any],
    root: str,
    manifest_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Return effective policy fields (copy) = base knobs + overlay activation.

    Preserves all base operational knobs. Raises PolicyError on invalid
    expansion/narrowing/containment.
    """
    from .policy import PolicyError  # local import
    from . import scope_presets  # local import to avoid cycle

    # 1) Shallow copy of base fields.
    effective = dict(base_fields)

    # 2) Determine allowed_operations.
    if "scope" in overlay:
        scope_id = overlay["scope"]
        scope_tgts = overlay.get("scope_targets")
        ops = scope_presets.expand(scope_id, scope_tgts)
    else:
        # Advanced override (XOR guaranteed).
        ops_raw = overlay["allowed_operations"]
        if not isinstance(ops_raw, list):
            raise PolicyError("allowed_operations must be a list")
        ops = list(ops_raw)  # copy

    # 3) Set allowed_operations (replaces base list).
    effective["allowed_operations"] = ops

    # 4) Overlay keys override if present.
    for k in ("active_tier", "briefing_ref", "allow_solo_approval",
              "min_approval_delay_seconds"):
        if k in overlay:
            effective[k] = overlay[k]

    # 5) Post-merge containment: effective briefing_ref must be abs+outside root.
    br = effective.get("briefing_ref")
    if br and isinstance(br, str) and br.strip():
        _require_outside_workspace(
            br, root, what="effective briefing_ref", must_be_absolute=True,
        )

    return effective


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


def activation_summary(policy: Any) -> dict[str, Any]:
    """Build a status/CLI-friendly summary from an effective Policy.

    Reads policy attributes/fields: overlay_present/path/scope/mode/source,
    effective active_tier, briefing_ref, allowed_operations count,
    briefing_exists under root when known.
    """
    from .policy import operator_ingress_ready

    overlay_present = getattr(policy, "overlay_present", False)
    overlay_path = getattr(policy, "overlay_path", None)
    activation_scope = getattr(policy, "activation_scope", None)
    activation_mode = getattr(policy, "activation_mode", None)
    activation_source = getattr(policy, "activation_source", "base")

    # Effective fields from policy.
    effective_tier = policy.get("active_tier") if hasattr(policy, "get") else None
    briefing_ref = policy.get("briefing_ref") if hasattr(policy, "get") else None
    ops = policy.get("allowed_operations") if hasattr(policy, "get") else None
    ops_count = len(ops) if ops else 0

    # Resolve root from policy.path for briefing_exists and sentinel check.
    root = None
    if hasattr(policy, "path") and policy.path:
        root = os.path.dirname(policy.path)

    sentinel_present = None
    briefing_exists = None
    if root is not None:
        try:
            sentinel_present = operator_ingress_ready(root)
            if briefing_ref and isinstance(briefing_ref, str):
                br_path = (briefing_ref if os.path.isabs(briefing_ref)
                           else os.path.join(root, briefing_ref))
                briefing_exists = os.path.isfile(br_path)
            else:
                briefing_exists = False
        except Exception:
            pass  # defensive: never raise in summary

    return {
        "overlay_present": bool(overlay_present),
        "overlay_path": overlay_path,
        "scope": activation_scope,
        "mode": activation_mode,
        "source": activation_source,
        "effective_tier": effective_tier,
        "briefing_ref": briefing_ref,
        "allowed_operations_count": ops_count,
        "sentinel_present": sentinel_present,
        "briefing_exists": briefing_exists,
    }
