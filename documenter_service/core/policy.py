"""Policy loader for the Documenter Service MVP — mvp-data-models §2.

Location: `documenter_policy.yml`, or DOCUMENTER_POLICY_PATH (mvp-data-models
§5). Loading is FAIL-CLOSED: missing file, invalid YAML, or any of the 7
validation rules (mvp-data-models §2) raises PolicyError, and delegate()
refuses with a structured error. Exception: `preview: true` stays exempt —
preview carries no write intent and cannot be degraded by policy state
(mvp-data-models §2 closing paragraph); the diff size cap then falls back to
the documented default max_diff_bytes = 512 KiB.

yaml.unsafe_load is prohibited: policies are parsed with yaml.safe_load.
"""
from __future__ import annotations

import os

import yaml

from .errors import StructuredError
from .trust import STATIC_FLOORS

__all__ = ["PolicyError", "Policy", "load_policy", "validate_policy"]

#: Only policy schema version recognized at MVP (mvp-data-models §2 rule 1).
POLICY_VERSION = "0.2.0"

#: Defaults per mvp-data-models §2 example / policy-reference §Field Reference.
DEFAULTS = {
    "version": POLICY_VERSION,
    "active_tier": 0,
    "allowed_operations": [],
    "audit_freshness": 30,
    "approval_expiry_window": 30,
    "rescan_batch_ceiling": 50,
    "max_diff_bytes": 524288,
    "sync_latency_budget_ms": 30000,
    "lock_wait_timeout": 30,
    "operator_approval_timeout": 300,
    "notification_mode": "inline",
    "glossary_enforcement": "draft",
    "glossary_staleness_days": 30,
    "briefing_ref": None,
    "retry_backoff_base": 1,
    "retry_max_attempts": 3,
}

#: Integer fields that must be positive integers (mvp-data-models §2 rule 7).
POSITIVE_INT_FIELDS = (
    "audit_freshness",
    "approval_expiry_window",
    "rescan_batch_ceiling",
    "max_diff_bytes",
    "sync_latency_budget_ms",
    "lock_wait_timeout",
    "operator_approval_timeout",
    "glossary_staleness_days",
    "retry_backoff_base",
    "retry_max_attempts",
)

#: Float fields with documented ranges (policy-reference §Field Reference).
FLOAT_RANGES = {
    "temperature": (0.0, 2.0),
    "top_p": (0.0, 1.0),
    "frequency_penalty": (-2.0, 2.0),
}

#: Enum fields with closed accepted-value sets.
ENUM_FIELDS = {
    "glossary_enforcement": ("draft", "active"),
    "notification_mode": ("inline",),
}

_ENV_PATH = "DOCUMENTER_POLICY_PATH"
_DEFAULT_FILENAME = "documenter_policy.yml"


class PolicyError(Exception):
    """Fail-closed policy load failure. Reason is operator-visible wording."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Policy:
    """Loaded, validated policy; attribute access to normalized fields."""

    def __init__(self, fields: dict, path: str | None = None) -> None:
        self._fields = dict(fields)
        self.path = path

    def get(self, name: str):
        return self._fields.get(name, DEFAULTS.get(name))

    def as_dict(self) -> dict:
        return dict(self._fields)


def policy_path(root: str, env=None) -> str:
    """Resolve the policy file path (DOCUMENTER_POLICY_PATH or root default)."""
    environ = os.environ if env is None else env
    configured = environ.get(_ENV_PATH)
    if configured:
        return configured if os.path.isabs(configured) else os.path.join(root, configured)
    return os.path.join(root, _DEFAULT_FILENAME)


def validate_policy(raw, manifest_ids=None) -> Policy:
    """Validate a parsed policy mapping; raise PolicyError on any violation.

    The 7 fail-closed rules of mvp-data-models §2, applied in order. Only
    documenter-service/policy-reference.md defines field semantics; this
    function enforces load-time legality, nothing else.

    Rule 3 implements the validator rule cited by mvp-data-models §2 rule 3
    (policy-reference §Policy File): load fails when allowed_operations is
    NON-EMPTY while active_tier < 2 — see the inline note below for why the
    §2 table cell is read as a typo. Rule 4 validates trust_level against the
    static floor per entry; rule 5 checks entry `targets` against
    ``manifest_ids`` when the caller supplies them (MVP ships no write
    entries, so rule 5 has no live data).
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("documenter_policy"), dict):
        raise PolicyError("missing or non-mapping `documenter_policy:` top-level key")
    data = raw["documenter_policy"]

    # Rule 1: version recognized; no default substitution.
    version = data.get("version")
    if str(version) != POLICY_VERSION:
        raise PolicyError(
            f"policy version {version!r} not recognized "
            f"(only {POLICY_VERSION!r} at MVP; no default substitution)")

    # Rule 2: active_tier ∈ {0,1,2,3} — an unreadable tier MUST NOT silently
    # lower strictness (fail closed on typos like `tier: one`).
    tier = data.get("active_tier")
    if isinstance(tier, bool) or not isinstance(tier, int) or tier not in (0, 1, 2, 3):
        raise PolicyError(
            f"active_tier {tier!r} not in {{0,1,2,3}} — refusing to load "
            "(fail closed: an unreadable tier MUST NOT silently lower strictness)")

    # Rule 3 (validator rule, policy-reference §Policy File): reject load when
    # allowed_operations is NON-EMPTY while active_tier < 2. The mvp-data-models
    # §2 rule-3 table cell ("empty while active_tier < 2") is read as a typo of
    # this cited validator rule: policy-reference §Policy File additionally
    # states "At Tier 0-1, allowed_operations must remain empty", so any other
    # reading makes a legal Tier 0/1 policy unrepresentable. Contradiction
    # recorded as an open question (documenter_service/README.md).
    ops = data.get("allowed_operations", DEFAULTS["allowed_operations"])
    if not isinstance(ops, list):
        raise PolicyError("allowed_operations must be a list")
    if tier < 2 and ops:
        raise PolicyError(
            f"allowed_operations is non-empty while active_tier={tier} (< 2) — "
            "validator rule, policy-reference §Policy File (cited by "
            "mvp-data-models §2 rule 3)")
    if tier >= 2 and not ops:
        raise PolicyError(
            "active_tier >= 2 requires non-empty allowed_operations "
            "(mvp-contract §4: advancement requires a policy file with "
            "allowed_operations)")

    # Rule 4: no entry with trust_level below the static floor for its
    # change_type (authority rule); covers type: pattern entries too.
    for i, entry in enumerate(ops):
        if not isinstance(entry, dict):
            raise PolicyError(f"allowed_operations[{i}] is not a mapping")
        ctype = entry.get("change_type") or (entry.get("match_criteria") or {}).get("change_type")
        trust = entry.get("trust_level")
        if ctype is None or trust is None:
            raise PolicyError(f"allowed_operations[{i}] missing change_type/trust_level")
        floor = STATIC_FLOORS.get(ctype)
        if floor is None:
            raise PolicyError(f"allowed_operations[{i}] unknown change_type {ctype!r}")
        if trust not in ("safe", "review"):
            raise PolicyError(f"allowed_operations[{i}] unknown trust_level {trust!r}")
        if _trust_rank(trust) < _trust_rank(floor):
            raise PolicyError(
                f"allowed_operations[{i}] trust_level {trust!r} is below the "
                f"static floor {floor!r} for change_type {ctype!r} (authority rule)")

        # Rule 5: targets are manifest IDs or empty.
        targets = entry.get("targets", [])
        if not isinstance(targets, list):
            raise PolicyError(f"allowed_operations[{i}].targets must be a list")
        if manifest_ids is not None:
            unknown = [t for t in targets if t not in manifest_ids]
            if unknown:
                raise PolicyError(
                    f"allowed_operations[{i}].targets not in manifest: "
                    + ", ".join(map(repr, unknown)))

    # Rule 6: briefing_ref non-null when active_tier >= 2.
    if tier >= 2 and data.get("briefing_ref", DEFAULTS["briefing_ref"]) in (None, ""):
        raise PolicyError(
            "briefing_ref must be non-null when active_tier >= 2 "
            "(mvp-data-models §2 rule 6)")

    # Rule 7: positive ints, ranged floats, notification_mode == inline.
    fields = dict(DEFAULTS)
    fields.update(data)
    for name in POSITIVE_INT_FIELDS:
        value = fields[name]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise PolicyError(
                f"policy field {name}={value!r} must be a positive integer")
    for name, (lo, hi) in FLOAT_RANGES.items():
        if name in data:
            value = data[name]
            if not isinstance(value, (int, float)) or isinstance(value, bool) \
                    or not (lo <= float(value) <= hi):
                raise PolicyError(
                    f"policy field {name}={value!r} outside range [{lo}, {hi}]")
    for name, allowed in ENUM_FIELDS.items():
        if fields[name] not in allowed:
            raise PolicyError(
                f"policy field {name}={fields[name]!r} not in {list(allowed)}")

    return Policy(fields)


def _trust_rank(level: str) -> int:
    return {"safe": 0, "review": 1}[level]


def load_policy(root: str, env=None, manifest_ids=None) -> Policy:
    """Load and validate the policy file; fail closed on every problem.

    Missing file, unreadable, invalid YAML or a rule violation raise
    PolicyError. Callers map it to a StructuredError for delegate(); audit()
    and status() run without policy-dependent writes.
    """
    path = policy_path(root, env)
    if not os.path.isfile(path):
        raise PolicyError(f"policy file not found: {path}")
    try:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        raise PolicyError(f"policy file {path} unreadable or invalid YAML: {exc}") from exc
    policy = validate_policy(raw, manifest_ids=manifest_ids)
    policy.path = path
    return policy


def policy_structured_error(exc: PolicyError) -> StructuredError:
    """Map a fail-closed policy failure to the closed enum (gate_failure)."""
    return StructuredError("gate_failure", f"policy load failed: {exc.reason}")
