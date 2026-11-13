"""MCP stdio JSON-RPC transport for the Documenter Service MVP.

Runs as a newline-delimited JSON-RPC 2.0 server over stdio:
- stdout carries ONLY JSON-RPC messages
- stderr may carry events (from the Service's EventSink on stderr) and logs
- stdin receives one JSON object per line

Protocol methods:
    initialize           -> server capabilities
    tools/list           -> {tools: [audit, status, delegate_preview]}
    tools/call           -> invoke a tool, return text content

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
import sys
import traceback

__all__ = ["serve", "TOOLS_LIST"]


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
    "severity_min": {"type": "string", "default": "low"},
    "pre_check": {"type": "boolean", "default": False},
    "scan_cursor": {"type": ["string", "null"], "default": None},
}

_STATUS_SCHEMA = {
    "target_id": {"type": ["string", "null"], "default": None},
}

_DELEGATE_PREVIEW_SCHEMA = {
    "target_id": {"type": "string"},
    "change_type": {"type": "string"},
    "trust_level": {"type": "string"},
    "diff_input": {"type": "string"},
    "preview": {"type": "boolean", "default": True},
    "audit_id": {"type": ["string", "null"], "default": None},
}

# Required keys per tool (from inputSchema.required).
_DELEGATE_PREVIEW_REQUIRED = [
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
}


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

    # --- Build kwargs for service method ---------------------------
    kwargs = {}
    for key, val in args.items():
        if key == "pre_check":
            kwargs[key] = bool(val) if val is not None else False
        elif key == "preview" and method_name == "delegate":
            kwargs[key] = bool(val) if val is not None else True
        else:
            kwargs[key] = val
    if method_name == "delegate" and "preview" not in kwargs:
        # preview absent → reject tier_interlock per mvp-interfaces §2
        # ("MUST be true. false or absent → reject"): pass False and let
        # Service.delegate refuse; defaulting to true here would turn an
        # explicit write-intent probe into a silent preview.
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
