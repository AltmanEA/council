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

import fnmatch
import os
import re

import yaml

from .errors import StructuredError
from .trust import STATIC_FLOORS

__all__ = ["PolicyError", "Policy", "load_policy", "validate_policy",
           "operator_id_valid", "check_tier2_authorized", "check_tier3_authorized",
           "match_operation", "match_pattern", "policy_structured_error"]

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

#: Kebab-case pattern ID (policy-reference §Per-Operation Entries).
_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

#: Glob character validation: allowed set is [A-Za-z0-9._*/?-].
_GLOB_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._*/?-")


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

    # Per-entry validation loop (rules 4, 5, and per-entry schema).
    # Extract type-specific fields first, then validate rules.
    _seen_pattern_ids = set()
    for i, entry in enumerate(ops):
        if not isinstance(entry, dict):
            raise PolicyError(f"allowed_operations[{i}] is not a mapping")

        # Extract type (operation is default).
        etype = entry.get("type", "operation")
        if etype not in ("operation", "pattern"):
            raise PolicyError(
                f"allowed_operations[{i}] type must be 'operation' or 'pattern', "
                f"got {etype!r}")

        # Type-specific field validation (before rule 4 so pattern schema
        # errors are reported first).
        if etype == "operation":
            if "requires_diff_preview" in entry and entry["requires_diff_preview"] is not True:
                raise PolicyError(
                    f"allowed_operations[{i}] requires_diff_preview must be true "
                    f"at Tier 2+ (got {entry['requires_diff_preview']!r})")
        if etype == "pattern":
            pid = entry.get("pattern_id")
            if not isinstance(pid, str) or not _KEBAB_RE.match(pid):
                raise PolicyError(
                    f"allowed_operations[{i}] pattern_id must be a non-empty "
                    f"kebab-case string (^[a-z0-9]+(-[a-z0-9]+)*$)")
            if pid is not None and manifest_ids is not None and pid in _seen_pattern_ids:
                raise PolicyError(
                    f"allowed_operations[{i}] duplicate pattern_id {pid!r}")
            if manifest_ids is not None:
                _seen_pattern_ids.add(pid)
            pdesc = entry.get("pattern_description")
            if not isinstance(pdesc, str) or not pdesc:
                raise PolicyError(
                    f"allowed_operations[{i}] pattern_description required "
                    f"non-empty string, got {pdesc!r}")
            mc = entry.get("match_criteria")
            if not isinstance(mc, dict):
                raise PolicyError(
                    f"allowed_operations[{i}] match_criteria must be a mapping")
            if "change_type" not in mc:
                raise PolicyError(
                    f"allowed_operations[{i}] match_criteria must contain "
                    f"change_type")
            fp = mc.get("file_pattern", "")
            if isinstance(fp, str):
                for ch in fp:
                    if ch not in ("*", "?") and ch not in _GLOB_CHARS:
                        raise PolicyError(
                            f"allowed_operations[{i}] file_pattern contains "
                            f"invalid glob character {ch!r}")
            elif fp is not None:
                raise PolicyError(
                    f"allowed_operations[{i}] file_pattern must be a string or absent")

        # Rule 4: trust floor — extract change_type and trust_level.
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


# ---- Tier 2+ authorization and matching (pure, no I/O except path check) ---

#: Operator ID regex (mvp-interfaces §5).
_OPERATOR_ID_RE = re.compile(r"^op-[a-z0-9][a-z0-9-]{2,63}$")


def operator_id_valid(operator_id: str) -> bool:
    """Return True when ``operator_id`` matches ``^op-[a-z0-9][a-z0-9-]{2,63}$``."""
    return bool(_OPERATOR_ID_RE.match(operator_id))


def check_tier2_authorized(policy, root) -> None:
    """Raise StructuredError("tier_interlock", reason, next_action="preview_denied")
    when tier 2+ conditions are not met.

    Requires: policy non-None, active_tier >= 2, briefing_ref non-null,
    and briefing file exists at ``resolve(root, briefing_ref)`` (relative paths
    are joined to root; absolute paths are kept as-is).
    """
    if policy is None:
        raise StructuredError(
            "tier_interlock",
            "policy is None — cannot authorise Tier 2+ operations",
            next_action="preview_denied")
    tier = policy.get("active_tier")
    if tier is None or tier < 2:
        raise StructuredError(
            "tier_interlock",
            f"active_tier={tier} < 2 — Tier 2+ operations require active_tier >= 2",
            next_action="preview_denied")
    briefing_ref = policy.get("briefing_ref")
    if not briefing_ref:
        raise StructuredError(
            "tier_interlock",
            "briefing_ref is null — required for Tier 2+ authorization",
            next_action="preview_denied")
    path = os.path.join(root, briefing_ref) if not os.path.isabs(briefing_ref) else briefing_ref
    if not os.path.isfile(path):
        raise StructuredError(
            "tier_interlock",
            f"briefing file not found at {path} — Tier 2+ requires an archived briefing",
            next_action="preview_denied")


def check_tier3_authorized(policy, root) -> None:
    """Same as check_tier2_authorized but requires active_tier >= 3."""
    check_tier2_authorized(policy, root)
    tier = policy.get("active_tier")
    if tier is None or tier < 3:
        raise StructuredError(
            "tier_interlock",
            f"active_tier={tier} < 3 — Tier 3 operations require active_tier >= 3",
            next_action="preview_denied")


def match_operation(policy, *, change_type, target_id, path=None) -> dict | None:
    """Return the first matching operation-type entry or None.

    An operation matches when:
    - type is "operation" (or absent),
    - change_type matches the entry's change_type,
    - targets is empty (match any) or target_id is in targets,
    - trust_level satisfies the static floor (already guaranteed by validation).

    The ``path`` parameter is accepted for future use but not evaluated here.
    """
    if not policy:
        return None
    for entry in (policy.get("allowed_operations") or []):
        etype = entry.get("type", "operation")
        if etype != "operation":
            continue
        if entry.get("change_type") != change_type:
            continue
        targets = entry.get("targets") or []
        if targets and target_id not in targets:
            continue
        return entry
    return None


def _pattern_matches(rel_path: str, file_pattern: str) -> bool:
    """Match rel_path against a file_pattern, supporting ** (recursive)."""
    if "**" in file_pattern:
        # Convert glob with ** to regex: ** matches any chars including /
        # Handle **/ prefix FIRST so the * is consumed before remaining **
        regex = file_pattern
        regex = re.escape(regex)
        regex = regex.replace(r"\*\*/", "(?:.*/)?")  # **/ → optional dir prefix
        regex = regex.replace(r"\*\*", ".*")          # remaining ** → match anything
        regex = regex.replace(r"\*", "[^/]*")         # * → match anything but /
        regex = regex.replace(r"\?", "[^/]")          # ? → single char but /
        return bool(re.fullmatch(regex, rel_path))
    return fnmatch.fnmatchcase(rel_path, file_pattern)


def match_pattern(policy, *, change_type, rel_path) -> dict | None:
    """Return the first matching pattern-type entry or None.

    A pattern matches when:
    - type is "pattern",
    - change_type matches the entry's match_criteria.change_type,
    - file_pattern (empty matches any) matches rel_path via fnmatch.
    """
    if not policy:
        return None
    for entry in (policy.get("allowed_operations") or []):
        etype = entry.get("type", "operation")
        if etype != "pattern":
            continue
        mc = entry.get("match_criteria") or {}
        if mc.get("change_type") != change_type:
            continue
        fp = mc.get("file_pattern", "")
        if fp and not _pattern_matches(rel_path, fp):
            continue
        return entry
    return None
