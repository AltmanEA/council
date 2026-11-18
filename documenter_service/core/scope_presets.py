"""Scope presets for Tier 2+ runtime activation overlay.

Deterministic registry of activation presets. Targets are explicit manifest
IDs (auditable, no runtime manifest discovery needed for expansion).

mvp-data-models §2 / policy-reference — scope presets are an overlay-level
abstraction that expands into allowed_operations entries.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

# PolicyError is in policy.py; imported lazily in functions to avoid cycles.

# ---------------------------------------------------------------------------
# Manifest ID sets (authoritative copy of the English doc corpus IDs)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Preset definitions
# ---------------------------------------------------------------------------

_PRESETS: dict[str, dict[str, Any]] = {
    "pilot-safe-v1": {
        "description": "Minimal safe pilot: mechanical updates to 2 operational docs",
        "operations": [
            {
                "type": "operation",
                "change_type": "update",
                "trust_level": "safe",
                "targets": [
                    "documenter-service-configuration-guide",
                    "operator-ingress",
                ],
                "requires_diff_preview": True,
            },
        ],
    },
    "docs-maint-safe": {
        "description": "Mechanical maintenance (metadata) across full doc corpus",
        "operations": [
            {
                "type": "operation",
                "change_type": "update",
                "trust_level": "safe",
                "targets": list(ALL_MANIFEST_IDS),
                "requires_diff_preview": True,
            },
        ],
    },
    "docs-content-review": {
        "description": "Content/normative updates across full doc corpus (review-gated)",
        "operations": [
            {
                "type": "operation",
                "change_type": "update",
                "trust_level": "review",
                "targets": list(ALL_MANIFEST_IDS),
                "requires_diff_preview": True,
            },
        ],
    },
    "ru-sync-review": {
        "description": "RU translation create/sync for docs that have translations (review-gated)",
        "operations": [
            {
                "type": "operation",
                "change_type": "create_ru",
                "trust_level": "review",
                "targets": list(RU_TRANSLATED_IDS),
                "requires_diff_preview": True,
            },
        ],
    },
}


def list_scope_ids() -> list[str]:
    """Stable sorted list of known scope ids."""
    return sorted(_PRESETS.keys())


def list_scopes() -> list[dict[str, Any]]:
    """Return [{id, description, change_type, trust_level, target_count, targets}, ...]."""
    result: list[dict[str, Any]] = []
    for scope_id in sorted(_PRESETS):
        preset = _PRESETS[scope_id]
        ops = preset["operations"]
        # All ops in a preset share the same change_type/trust_level.
        first_op = ops[0]
        result.append({
            "id": scope_id,
            "description": preset["description"],
            "change_type": first_op["change_type"],
            "trust_level": first_op["trust_level"],
            "target_count": len(first_op["targets"]),
            "targets": list(first_op["targets"]),
        })
    return result


def get_preset(scope_id: str) -> dict[str, Any] | None:
    """Return preset definition (deep copy) or None if unknown."""
    preset = _PRESETS.get(scope_id)
    if preset is None:
        return None
    return deepcopy(preset)


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
    from .policy import PolicyError  # local import to avoid cycle if any

    preset = _PRESETS.get(scope_id)
    if preset is None:
        raise PolicyError(
            f"unknown scope {scope_id!r}; available scopes: "
            + ", ".join(sorted(_PRESETS.keys()))
        )

    op_template = preset["operations"][0]
    preset_target_set = set(op_template["targets"])

    if scope_targets is None:
        effective_targets = list(op_template["targets"])
    else:
        # Shape check: must be a non-empty list of strings.
        if not isinstance(scope_targets, list) or not scope_targets:
            raise PolicyError(
                f"scope_targets must be a non-empty list of strings, "
                f"got {scope_targets!r}"
            )
        for t in scope_targets:
            if not isinstance(t, str):
                raise PolicyError(
                    f"scope_targets must be a non-empty list of strings, "
                    f"got non-string element {t!r}"
                )

        # Narrowing check: every id must be in preset target set.
        provided_set = set(scope_targets)
        invalid_ids = provided_set - preset_target_set
        if invalid_ids:
            raise PolicyError(
                f"scope_targets widens/invalid for scope {scope_id!r}: "
                f"unknown ids {', '.join(sorted(invalid_ids))}; "
                f"scope_targets must be a subset of preset targets"
            )
        # Effective = sorted unique (deterministic).
        effective_targets = sorted(set(scope_targets))

    return deepcopy([
        {
            "type": "operation",
            "change_type": op_template["change_type"],
            "trust_level": op_template["trust_level"],
            "targets": effective_targets,
            "requires_diff_preview": True,
        },
    ])
