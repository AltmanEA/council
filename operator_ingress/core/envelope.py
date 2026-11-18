"""Error envelope + localization table + deferred-tool stubs — Step 2.

Provides structured operator-facing error formatting:
  error_envelope(code, **overrides) -> dict
  CODE_TABLE lookup table
  deferred_response(tool_name) -> dict (CONFIG.001 for deferred tools)
  is_envelope(obj) -> bool
"""
from __future__ import annotations

__all__ = [
    "CODE_TABLE",
    "deferred_response",
    "error_envelope",
    "is_envelope",
]

# ---------------------------------------------------------------------------
# Code registry (MVP codes: VAL, IO, CONFIG)
# ---------------------------------------------------------------------------

CODE_TABLE: dict[str, tuple[str, str]] = {
    "VAL.001": (
        "Schema validation failed: unknown or disallowed field detected",
        "Review the schema and fix the input payload",
    ),
    "VAL.002": (
        "Unknown enum value provided for this field",
        "Review the available enum values and fix the input",
    ),
    "VAL.003": (
        "A required field is missing from the input",
        "Add the required field and retry the request",
    ),
    "VAL.004": (
        "Trust floor mismatch: input trust level is below the required floor",
        "Retry with a trust level at or above the derived floor",
    ),
    "VAL.005": (
        "Audit token is missing, stale, or out of its valid scope",
        "Run a fresh audit to obtain a new audit token",
    ),
    "IO.001": (
        "Atomic write operation failed: the target resource could not be updated",
        "Retry the write operation after the resource is available",
    ),
    "IO.002": (
        "Manifest hash chain integrity check has failed",
        "Escalate to a senior operator for forensic analysis",
    ),
    "IO.003": (
        "Session lock is held by another operation",
        "Wait for the lock to release and retry the operation",
    ),
    "IO.004": (
        "Delegated skill execution failed during operation",
        "Inspect the skill trace, retry the operation",
    ),
    "IO.999": (
        "An unhandled exception occurred during delegate() execution",
        "Capture the post-mortem trace and escalate for review",
    ),
    "CONFIG.001": (
        "An API key or credential is missing from the configuration",
        "Review the configuration and fix the missing credential",
    ),
    "CONFIG.002": (
        "Invalid scenario detected or conflicting configuration values present",
        "Review the scenario and fix the conflicting configuration",
    ),
}

# ---------------------------------------------------------------------------
# Deferred tools (roadmap KD-1; not yet operational)
# ---------------------------------------------------------------------------

_DEFERRED = (
    "council.get_artifacts",
    "council.resolve_escalation",
    "council.override_precheck",
    "documenter.delegate",
    "documenter.approve",
    "documenter.override_gate",
)

# Maps each deferred tool to an available tool name for the action hint.
_DEFERRED_ACTION_TOOL = {
    "council.get_artifacts": "council.status",
    "council.resolve_escalation": "council.status",
    "council.override_precheck": "documenter.audit",
    "documenter.delegate": "documenter.audit",
    "documenter.approve": "documenter.audit",
    "documenter.override_gate": "documenter.audit",
}

# Keys that overrides must never replace.
_CORE_KEYS = frozenset(("code", "message", "action"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def error_envelope(*args, **overrides) -> dict:
    """Create an operator-facing error envelope dict.

    Args:
        code: registry code (must be in CODE_TABLE).  May be passed
            positionally or as a keyword — positional always wins.
        **overrides: additional fields to include.  Override keys whose
            name is "secret" or "canary" are silently dropped to prevent
            accidental secret leakage into the envelope output.  Keys
            matching the core set (code/message/action) are ignored.

    Returns:
        dict with at least keys code, message, action.

    Raises:
        ValueError: if code is not in CODE_TABLE.
    """
    # Accept `code` as positional (first *arg) or keyword argument.
    code = overrides.pop("code", None)
    if args:
        code = args[0]  # positional always wins
    if code is None:
        raise TypeError("error_envelope() missing required argument: 'code'")

    if code not in CODE_TABLE:
        raise ValueError(f"Unknown code: {code}")

    msg, action_text = CODE_TABLE[code]
    result: dict = {
        "code": code,
        "message": msg,
        "action": action_text,
    }

    for k, v in overrides.items():
        if k in _CORE_KEYS:
            continue
        if k in ("secret", "canary"):
            continue
        result[k] = v

    return result


def deferred_response(tool_name, **kwargs) -> dict:
    """Return a CONFIG.001 envelope for a deferred (not-yet-implemented) tool.

    Args:
        tool_name: name of a deferred tool.
        **kwargs: forwarded to error_envelope (e.g. secret=..., dropped).

    Returns:
        CONFIG.001 envelope whose action field names an available tool.

    Raises:
        ValueError: if tool_name is not a known deferred tool.
    """
    if tool_name not in _DEFERRED:
        raise ValueError(f"Unknown or non-deferred tool: {tool_name}")

    short_name = tool_name.rsplit(".", 1)[-1]
    available_tool = _DEFERRED_ACTION_TOOL[tool_name]
    env = error_envelope("CONFIG.001", tool=tool_name, **kwargs)
    # Replace the GENERIC CONFIG.001 message with an honest per-tool message.
    env["message"] = f"The {short_name} tool is not available yet."
    # Override action to name an available tool for operator guidance.
    env["action"] = f"Use {available_tool} for now"
    return env


def is_envelope(obj: object) -> bool:
    """Return True if obj is a dict with code/message/action all str.

    Returns False when obj is not a dict, when any of the three required
    keys is missing, or when any required value is not a str.
    """
    if not isinstance(obj, dict):
        return False
    for key in ("code", "message", "action"):
        if key not in obj:
            return False
        if not isinstance(obj[key], str):
            return False
    return True
