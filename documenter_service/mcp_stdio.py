"""MCP stdio JSON-RPC transport for the Documenter Service MVP.

Runs as a newline-delimited JSON-RPC 2.0 server over stdio:
- stdout carries ONLY JSON-RPC messages
- stderr may carry events (from the Service's EventSink on stderr) and logs
- stdin receives one JSON object per line

Protocol methods:
    initialize           -> server capabilities
    tools/list           -> {tools: [audit, status, delegate_preview,
                                    approve, override_gate, delegate_write]}
    tools/call           -> invoke a tool, return text content

Read-only trio: audit, status, delegate_preview (readOnlyHint: true)
Tier 2+ trio: approve, override_gate, delegate_write (readOnlyHint: false)
    Tier 2+ tools are gated by policy interlock at the Service layer.
    Operator identity from environment (COUNCIL_OPERATOR_ID), not from
    client-supplied parameters (operator-surface §AuthN).

Design (mvp-contract §1 transport rationale): the MCP server constructs
the Service composition root directly (no parallel wiring). CLI and MCP
results cannot diverge -- they share the same Service methods and adapters.

Imports:
    Service and StructuredError come from __main__ (the composition root).
    serve(service, ...) -- takes an already-constructed Service so mcp_stdio
    never imports __main__, avoiding circular dependencies.
"""
from __future__ import annotations

import json
import os
import re
import sys
import traceback

from .core.errors import StructuredError

__all__ = ["serve", "TOOLS_LIST"]


# ---------------------------------------------------------------------------
# AuthN: resolve_operator_id (local copy to avoid circular import with __main__)
# ---------------------------------------------------------------------------
#: Regex for valid operator IDs (mvp-interfaces §5).
#: Duplication with __main__ is deliberate — prevents circular import.
#: Both call policy.operator_id_valid in practice (this one in-line below).
_OPERATOR_ID_RE = re.compile(r"^op-[a-z0-9][a-z0-9-]{2,63}$")


def _resolve_operator_id(environ):
    """Resolve the authenticated operator from process environment.

    AuthN decision (mvp-contract §AuthN; operator-surface §Caller Identity and
    Authorization): operator_id NEVER comes from client-supplied parameters.
    The trusted ingress is the process environment variable COUNCIL_OPERATOR_ID.

    Raises StructuredError("unknown", ...) when absent/malformed.
    The error bubbles through the tool handler and is returned as
    tool-level isError (category "unknown"), NOT a JSON-RPC error.
    """
    oid = environ.get("COUNCIL_OPERATOR_ID")
    if not oid or not _OPERATOR_ID_RE.match(oid):
        from .core.errors import StructuredError
        raise StructuredError(
            "unknown",
            "authenticated operator ingress missing: set COUNCIL_OPERATOR_ID "
            "(operator-surface §AuthN; expected "
            r"^op-[a-z0-9][a-z0-9-]{2,63}$)")
    return oid


# ---------------------------------------------------------------------------
# Canonical tools list (tools/list response, returned verbatim).
# ---------------------------------------------------------------------------
TOOLS_LIST = {
    "tools": [
        {
            "name": "audit",
            "description": (
                "Read-only audit: scan documents against compliance "
                "rules using manifest and glossary data"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "target_id": {
                        "type": "string",
                        "description": (
                            "Document ID from manifest, or \"*\" "
                            "for all"
                        ),
                        "default": "*",
                    },
                    "severity_min": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": (
                            "Minimum severity to include (default low)"
                        ),
                        "default": "low",
                    },
                    "pre_check": {
                        "type": "boolean",
                        "description": (
                            "Mid-session integrity gate; returns verdict "
                            "synchronously"
                        ),
                        "default": False,
                    },
                    "scan_cursor": {
                        "type": ["string", "null"],
                        "description": (
                            "Continuation token from prior partial scan. "
                            "null = fresh full scan"
                        ),
                        "default": None,
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": True},
        },
        {
            "name": "status",
            "description": (
                "Operational status: registry health, pending scan, "
                "tier interlock"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "target_id": {
                        "type": ["string", "null"],
                        "description": (
                            "Filter to one document; null = whole corpus"
                        ),
                        "default": None,
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": True},
        },
        {
            "name": "delegate_preview",
            "description": (
                "delegate(preview: true): evaluate a diff without write "
                "intent; returns diff_text, derived trust level, and "
                "findings"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "target_id": {
                        "type": "string",
                        "description": "Document ID from manifest",
                    },
                    "change_type": {
                        "type": "string",
                        "enum": ["update", "split", "create_ru", "custom"],
                        "description": "Change type",
                    },
                    "trust_level": {
                        "type": "string",
                        "enum": ["safe", "review"],
                        "description": "Caller trust level",
                    },
                    "diff_input": {
                        "type": "string",
                        "description": (
                            "Base64-encoded UTF-8 machine-readable diff"
                        ),
                    },
                    "preview": {
                        "type": "boolean",
                        "description": "MUST be true",
                        "default": True,
                    },
                    "audit_id": {
                        "type": ["string", "null"],
                        "description": (
                            "audit_id for pre-audit gate on delegate "
                            "preview"
                        ),
                        "default": None,
                    },
                },
                "required": [
                    "target_id",
                    "change_type",
                    "trust_level",
                    "diff_input",
                ],
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": True},
        },
        {
            "name": "approve",
            "description": (
                "approve: approve a pending write proposal (Tier 2+). "
                "Operator identity from environment (COUNCIL_OPERATOR_ID), "
                "not from client parameters (operator-surface §AuthN). "
                "For a solo (self-)approval under ADR-017, pass "
                "\"acknowledge\": \"CONFIRMED_SOLE_REVIEWER\" to confirm "
                "sole-reviewer awareness; missing or wrong value → "
                "gate_failure on the solo path."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "approval_id": {
                        "type": "string",
                        "description": "Approval ID to approve",
                    },
                    "acknowledge": {
                        "type": "string",
                        "description": (
                            "Solo-operator acknowledgment token (ADR-017): "
                            "CONFIRMED_SOLE_REVIEWER"
                        ),
                    },
                },
                "required": ["approval_id"],
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": False},
        },
        {
            "name": "override_gate",
            "description": (
                "override_gate: override an audit-gate failure (Tier 2+). "
                "Binds to (target_id, diff_hash); one consumption; "
                "next_action is \"rerun_audit\"."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "target_id": {
                        "type": "string",
                        "description": "Document ID from manifest",
                    },
                    "diff_hash": {
                        "type": "string",
                        "description": "SHA-256 diff hash (sha256:<64hex>)",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for the override (≤500 chars)",
                    },
                    "audit_id": {
                        "type": ["string", "null"],
                        "description": "audit_id for governing audit record",
                        "default": None,
                    },
                },
                "required": ["target_id", "diff_hash", "reason"],
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": False},
        },
        {
            "name": "delegate_write",
            "description": (
                "delegate(preview: false): Tier 2+ write intent. "
                "Same parameters as delegate_preview but without the "
                "\"preview\" property (server always passes preview=False). "
                "Optional \"approval_id\" to apply an already-approved write."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "target_id": {
                        "type": "string",
                        "description": "Document ID from manifest",
                    },
                    "change_type": {
                        "type": "string",
                        "enum": ["update", "split", "create_ru", "custom"],
                        "description": "Change type",
                    },
                    "trust_level": {
                        "type": "string",
                        "enum": ["safe", "review"],
                        "description": "Caller trust level",
                    },
                    "diff_input": {
                        "type": "string",
                        "description": (
                            "Base64-encoded UTF-8 machine-readable diff"
                        ),
                    },
                    "audit_id": {
                        "type": ["string", "null"],
                        "description": (
                            "audit_id for pre-audit gate on delegate write"
                        ),
                        "default": None,
                    },
                    "approval_id": {
                        "type": ["string", "null"],
                        "description": (
                            "approval_id to apply (re-invocation after approve)"
                        ),
                        "default": None,
                    },
                },
                "required": [
                    "target_id",
                    "change_type",
                    "trust_level",
                    "diff_input",
                ],
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": False},
        },
    ]
}


# ---------------------------------------------------------------------------
# Internal helper: build JSON-RPC response objects.
# ---------------------------------------------------------------------------

def _make_response(request_id, result=None, error=None):
    """Return a JSON-RPC 2.0 dict."""
    resp = {"jsonrpc": "2.0"}
    if request_id is not None:
        resp["id"] = request_id
    if error is not None:
        resp["error"] = error
    if result is not None:
        resp["result"] = result
    return resp


def _error_response(request_id, code, message):
    """JSON-RPC error dict."""
    return _make_response(request_id, error={"code": code, "message": message})


# ---------------------------------------------------------------------------
# Handler: initialize
# ---------------------------------------------------------------------------

def _handle_initialize(request_id):
    """Handle initialize method."""
    result = {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "documenter", "version": "0.1.0"},
    }
    return _make_response(request_id, result=result)


# ---------------------------------------------------------------------------
# Handler: tools/list
# ---------------------------------------------------------------------------

def _handle_tools_list(request_id):
    """Handle tools/list method."""
    return _make_response(request_id, result=TOOLS_LIST)


# ---------------------------------------------------------------------------
# Handler: tools/call
# ---------------------------------------------------------------------------

# JSON-Schema definitions for each tool's input parameters (mirror
# mvp-interfaces §1-3 types, defaults).

_AUDIT_SCHEMA = {
    "target_id": {"type": "string", "default": "*"},
    "severity_min": {"type": "string", "default": "low",
                     "enum": ["low", "medium", "high", "critical"]},
    "pre_check": {"type": "boolean", "default": False},
    "scan_cursor": {"type": ["string", "null"], "default": None},
}

_STATUS_SCHEMA = {
    "target_id": {"type": ["string", "null"], "default": None},
}

_DELEGATE_PREVIEW_SCHEMA = {
    "target_id": {"type": "string"},
    "change_type": {"type": "string",
                    "enum": ["update", "split", "create_ru", "custom"]},
    "trust_level": {"type": "string", "enum": ["safe", "review"]},
    "diff_input": {"type": "string"},
    "preview": {"type": "boolean", "default": True},
    "audit_id": {"type": ["string", "null"], "default": None},
}

_APPROVE_SCHEMA = {
    "approval_id": {"type": "string"},
    "acknowledge": {"type": "string"},
}

_OVERRIDE_GATE_SCHEMA = {
    "target_id": {"type": "string"},
    "diff_hash": {"type": "string"},
    "reason": {"type": "string"},
    "audit_id": {"type": ["string", "null"], "default": None},
}

_DELEGATE_WRITE_SCHEMA = {
    "target_id": {"type": "string"},
    "change_type": {"type": "string",
                    "enum": ["update", "split", "create_ru", "custom"]},
    "trust_level": {"type": "string", "enum": ["safe", "review"]},
    "diff_input": {"type": "string"},
    "audit_id": {"type": ["string", "null"], "default": None},
    "approval_id": {"type": ["string", "null"], "default": None},
}

# Required keys per tool (from inputSchema.required).
_DELEGATE_PREVIEW_REQUIRED = [
    "target_id", "change_type", "trust_level", "diff_input",
]
_APPROVE_REQUIRED = ["approval_id"]
_OVERRIDE_GATE_REQUIRED = ["target_id", "diff_hash", "reason"]
_DELEGATE_WRITE_REQUIRED = [
    "target_id", "change_type", "trust_level", "diff_input",
]

# Mapping: tool name -> (Service method name, schema, required_keys, pre_fn).
# pre_fn(args) -> None (raises ValueError on bad enum) or returns None.
TOOL_HANDLERS = {
    "audit": ("audit", _AUDIT_SCHEMA, [], None),
    "status": ("status", _STATUS_SCHEMA, [], None),
    "delegate_preview": (
        "delegate", _DELEGATE_PREVIEW_SCHEMA,
        _DELEGATE_PREVIEW_REQUIRED,
        lambda args: None,  # enum checked by Service.delegate itself
    ),
    "approve": (
        "approve", _APPROVE_SCHEMA,
        _APPROVE_REQUIRED,
        None,  # env ingress + operator_id from _resolve_operator_id
    ),
    "override_gate": (
        "override_gate", _OVERRIDE_GATE_SCHEMA,
        _OVERRIDE_GATE_REQUIRED,
        None,
    ),
    "delegate_write": (
        "delegate", _DELEGATE_WRITE_SCHEMA,
        _DELEGATE_WRITE_REQUIRED,
        None,  # server always passes preview=False
    ),
}


# ---------------------------------------------------------------------------
# Arg-validation: JSON-Schema subset enforcement.
# ---------------------------------------------------------------------------

def _validate_args(schema: dict, args: dict) -> str | None:
    """Validate *args* against *schema* (the ``properties`` dict from an
    inputSchema).  Returns an error message string or None when valid.

    Checks performed:
      1. No keys outside ``schema`` keys → "unknown argument: <key>".
      2. Type enforcement: ``string`` → str, ``boolean`` → bool,
         ``["string","null"]`` → str|None, ``enum`` → value in list.
    """
    for key, val in args.items():
        if key not in schema:
            return f"unknown argument: {key}"
        prop = schema[key]
        prop_type = prop.get("type")
        # Enum check
        if "enum" in prop and val is not None:
            if val not in prop["enum"]:
                return f"invalid value {val!r}: must be one of {prop['enum']}"
        # Type check
        if prop_type == "string":
            if val is not None and not isinstance(val, str):
                return f"argument {key!r}: expected string, got {type(val).__name__}"
        elif prop_type == "boolean":
            if not isinstance(val, bool):
                return f"argument {key!r}: expected boolean, got {type(val).__name__}"
        elif isinstance(prop_type, list):
            # Union type: e.g. ["string", "null"]
            # "null" means None is acceptable
            if val is not None:
                valid_types = [t for t in prop_type if t != "null"]
                for t in valid_types:
                    if t == "string" and isinstance(val, str):
                        break
                else:
                    return f"argument {key!r}: expected {prop_type}, got {type(val).__name__}"
    return None


def _handle_tools_call(service, request_id, params):
    """Handle tools/call method."""
    name = params.get("name")
    args = params.get("arguments")

    # --- Validate tool name ------------------------------------------
    if name not in TOOL_HANDLERS:
        return _error_response(request_id, -32602,
                               f"unknown tool: {name}")

    method_name, schema, required_keys, pre_fn = TOOL_HANDLERS[name]

    # --- Validate arguments is an object -----------------------------
    if not isinstance(args, dict):
        return _error_response(request_id, -32602,
                               f"arguments must be an object")

    # --- Check required keys are present ----------------------------
    for key in required_keys:
        if key not in args:
            return _error_response(
                request_id, -32602,
                f"missing required argument: {key}")

    # --- Strict schema validation (type, enum, no unknown keys) ---------
    validation_error = _validate_args(schema, args)
    if validation_error:
        return _error_response(request_id, -32602, validation_error)

    # --- Build kwargs for service method ---------------------------
    kwargs = {}
    for key, val in args.items():
        if key == "pre_check":
            kwargs[key] = bool(val) if val is not None else False
        elif key == "preview" and method_name == "delegate":
            kwargs[key] = bool(val) if val is not None else True
        elif key == "acknowledge" and method_name == "approve":
            # MCP-facing name "acknowledge" maps to the service/core
            # parameter "acknowledged" (ADR-017 solo token, AI-1b).
            kwargs["acknowledged"] = val
        else:
            kwargs[key] = val

    # --- Tool-specific: resolve operator from env (authN) ----------
    if method_name in ("approve", "override_gate"):
        # AuthN: operator from env, NOT from args (operator-surface §AuthN).
        # Extra args like "operator_id" are rejected by schema validation
        # (additionalProperties: false) → -32602.
        try:
            kwargs["operator_id"] = _resolve_operator_id(
                service._env if hasattr(service, "_env") else os.environ)
        except StructuredError as exc:
            # Tool-level error: returned as isError, NOT JSON-RPC error.
            return _make_response(
                request_id,
                result={
                    "content": [{"type": "text",
                                  "text": json.dumps(exc.to_dict())}],
                    "isError": True,
                })

    # --- Tool-specific: delegate(preview=False) when absent ------------------
    if method_name == "delegate" and "preview" not in kwargs:
        # preview absent → reject tier_interlock per mvp-interfaces §2
        # ("MUST be true. false or absent → reject"): pass False and let
        # Service.delegate refuse; defaulting to true here would turn an
        # explicit write-intent probe into a silent preview.
        # delegate_write always lands here: its schema has no "preview"
        # property and strict _validate_args rejects a client-supplied one
        # (-32602), so no separate strip-branch is needed (p.24 dead-code).
        kwargs["preview"] = False

    # --- Call service method ----------------------------------------
    try:
        method = getattr(service, method_name)
        result = method(**kwargs)
    except SystemExit:
        # Should not happen in normal operation, but handle gracefully
        error_result = {
            "error_category": "unknown",
            "message": "unexpected exit",
            "next_action": "escalate",
        }
        return _make_response(
            request_id,
            result={
                "content": [{"type": "text",
                              "text": json.dumps(error_result)}],
                "isError": True,
            })
    except Exception as exc:
        # Tool-level error: JSON-RPC success, but result carries isError.
        if hasattr(exc, "to_dict"):
            error_result = exc.to_dict()
        else:
            error_result = {
                "error_category": "unknown",
                "message": str(exc),
                "next_action": "escalate",
            }
        return _make_response(
            request_id,
            result={
                "content": [{"type": "text",
                              "text": json.dumps(error_result)}],
                "isError": True,
            })

    return _make_response(
        request_id,
        result={
            "content": [{"type": "text",
                          "text": json.dumps(result, sort_keys=True,
                                             ensure_ascii=False)}],
        },
    )


# ---------------------------------------------------------------------------
# Main loop: serve()
# ---------------------------------------------------------------------------

def serve(service, stdin=None, stdout=None, stderr=None):
    """Run the MCP stdio JSON-RPC server until stdin EOF.

    Parameters
    ----------
    service : Service
        An already-constructed Service instance (composition root).
    stdin  : text stream (default: sys.stdin)
    stdout : text stream (default: sys.stdout)
    stderr : text stream (default: sys.stderr)

    Returns
    -------
    int
        0 on clean exit (stdin EOF).
    """
    if stdin is None:
        stdin = sys.stdin
    if stdout is None:
        stdout = sys.stdout
    if stderr is None:
        stderr = sys.stderr

    for line in stdin:
        line = line.strip()
        if not line:
            continue

        # --- Parse JSON line ------------------------------------------
        try:
            request = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            stdout.write(json.dumps(
                _error_response(None, -32700, "Parse error")) + "\n")
            stdout.flush()
            continue

        # --- Reject batch (array) requests ---------------------------
        if isinstance(request, list):
            stdout.write(json.dumps(
                _error_response(None, -32600,
                                "Batch requests are not supported")) + "\n")
            stdout.flush()
            continue

        # --- Extract fields ------------------------------------------
        method = request.get("method")
        request_id = request.get("id")  # None for notifications
        params = request.get("params", {})

        # --- Notifications (no "id") → no response ------------------
        if request_id is None:
            continue

        # --- Validate JSON-RPC version (non-fatal; proceed anyway) --
        version = request.get("jsonrpc")

        # --- Route to handler ----------------------------------------
        try:
            if method == "initialize":
                response = _handle_initialize(request_id)
            elif method == "tools/list":
                response = _handle_tools_list(request_id)
            elif method == "tools/call":
                if not isinstance(params, dict) or "name" not in params:
                    response = _error_response(
                        request_id, -32602, "invalid tools/call params")
                else:
                    response = _handle_tools_call(
                        service, request_id, params)
            else:
                response = _error_response(
                    request_id, -32601, f"Method not found: {method}")
        except Exception as exc:
            # Unexpected internal exception: error response + traceback
            traceback.print_exc(file=stderr)
            response = _error_response(
                request_id, -32603, "internal error")

        # --- Write response to stdout --------------------------------
        if response is not None:
            stdout.write(json.dumps(
                response, ensure_ascii=False) + "\n")
            stdout.flush()

    return 0
