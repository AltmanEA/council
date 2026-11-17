"""Operator Surface MVP entry point — stdio JSON-RPC server (Step 4+).

Rewrites the Step 0 placeholder as a full assembly root that:
  - Exposes ``handle_request(request, deps)`` at module level for tests
  - Runs a stdio loop when invoked as ``python3 -m operator_surface``
  - AuthN before verb routing; unknown → CONFIG.002; deferred → CONFIG.001
  - Emits a verb.dispatch event after every successful verb routing.
  - Creates the readiness sentinel at READY (post-READY, non-blocking).

Env:
  COUNCIL_OPERATOR_SECRET — HMAC signing secret (REQUIRED, no default)
  COUNCIL_STATE_ROOT — base directory for session state (default: repo root)
  COUNCIL_TEST_MODE=1 — test mode: use temp-root ports, no real adapters
  COUNCIL_CALLER_CLASS — auth caller class: operator | agent | service
                         (default: "operator")

build_deps(*, env, state_root) → dict  — production dependency factory
  returns {store, events, documenter, secret, policy_info, notices_provider,
           caller_class, secret_store, approval_registry, escalations}

MCP registration is an operator act — TBD in a future step.
"""
from __future__ import annotations

import json
import os
import sys
import traceback

import yaml

from .core.approval import ApprovalRegistry
from .core.auth import verify_token, AuthError
from .core.envelope import deferred_response, error_envelope
from .core.events import make_envelope
from .core.verbs import (
    submit_task,
    status,
    list_sessions,
    documenter_audit,
    documenter_delegate,
    documenter_approve,
    resolve_escalation,
    override_precheck,
    override_gate,
)


# ---------------------------------------------------------------------------
# Deferred tools (roadmap KD-1; not yet operational)
# ---------------------------------------------------------------------------

_DEFERRED_TOOLS = frozenset((
    "council.get_artifacts",
))

# Available tools for action hints (same as envelope's _DEFERRED_ACTION_TOOL).
_AVAILABLE_TOOLS = {
    "council.get_artifacts": "council.status",
}


# ---------------------------------------------------------------------------
# handle_request — in-process dispatcher (tests use this directly)
# ---------------------------------------------------------------------------

def handle_request(request: dict, deps: dict) -> dict:
    """Dispatch a JSON-RPC 2.0 request through auth + verb routing.

    Args:
        request: parsed JSON-RPC request dict with keys jsonrpc, id, method, params.
        deps: dict with keys store, events, documenter, secret, policy_info,
              notices_provider, caller_class.

    Returns:
        JSON-RPC response dict with either "result" or "error" key.
    """
    # --- AuthN before verb routing ---
    params = request.get("params")
    if params is None or not isinstance(params, dict):
        return _error_response(request.get("id"), {
            "code": "AUTH.002",
            "message": "malformed credential",
            "action": "include a valid auth token",
        })

    auth = params.get("auth")
    if auth is None or not isinstance(auth, dict):
        return _error_response(request.get("id"), {
            "code": "AUTH.002",
            "message": "malformed credential",
            "action": "include a valid auth token",
        })

    token = auth.get("token")
    if token is None or not isinstance(token, str):
        return _error_response(request.get("id"), {
            "code": "AUTH.002",
            "message": "malformed credential",
            "action": "include a valid auth token",
        })

    # Resolve caller class from deps (default: "operator").
    caller_class = deps.get("caller_class", "operator")

    # Verify token — raises AuthError on failure.
    secret = deps.get("secret", os.environ.get("COUNCIL_OPERATOR_SECRET", ""))
    known_services = deps.get("known_services", ())
    try:
        claims = verify_token(token, secret, caller_class=caller_class,
                              known_services=known_services)
    except AuthError as exc:
        return _error_response(request.get("id"), {
            "code": exc.code,
            "message": exc.message,
            "action": exc.next_action,
        })

    # Extract operator_id from claims.
    operator_id = claims.get("sub")

    # --- Method routing ---
    method = request.get("method", "")
    params_data = request.get("params", {}) or {}

    try:
        if method == "council.submit_task":
            result = submit_task(
                deps["store"],
                deps["events"],
                task_brief=params_data.get("task_brief", ""),
                scenario_id=params_data.get("scenario_id", ""),
                operator_id=operator_id,
            )

        elif method == "council.status":
            result = status(
                deps["store"],
                deps["notices_provider"],
                operator_id=operator_id,
                escalation_store=deps.get("escalations"),
            )

        elif method == "council.list_sessions":
            result = list_sessions(
                deps["store"],
                operator_id=operator_id,
            )

        elif method == "documenter.audit":
            result = documenter_audit(
                deps["documenter"],
                target_id=params_data.get("target_id", "*"),
            )

        elif method == "documenter.delegate":
            result = documenter_delegate(
                deps["documenter"],
                deps["approval_registry"],
                target_id=params_data.get("target_id", ""),
                change_type=params_data.get("change_type", ""),
                diff=params_data.get("diff", ""),
                operator_id=operator_id,
                events=deps["events"],
            )

        elif method == "documenter.approve":
            result = documenter_approve(
                deps["approval_registry"],
                request_id=params_data.get("request_id", ""),
                operator_id=operator_id,
                diff=params_data.get("diff", ""),
                events=deps["events"],
            )

        elif method == "council.resolve_escalation":
            result = resolve_escalation(
                deps.get("escalations"),
                session_id=params_data.get("session_id", ""),
                escalation_id=params_data.get("escalation_id", ""),
                decision=params_data.get("decision", ""),
                operator_id=operator_id,
                events=deps["events"],
                note=params_data.get("note"),
                caller_class=caller_class,
            )

        elif method == "council.override_precheck":
            result = override_precheck(
                deps["store"],
                session_id=params_data.get("session_id", ""),
                reason=params_data.get("reason"),
                operator_id=operator_id,
                events=deps["events"],
            )

        elif method == "documenter.override_gate":
            result = override_gate(
                deps["documenter"],
                target_id=params_data.get("target_id", ""),
                reason=params_data.get("reason"),
                operator_id=operator_id,
                events=deps["events"],
            )

        elif method in _DEFERRED_TOOLS:
            # Deferred tools → CONFIG.001 envelope.
            env = deferred_response(method)
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"data": env},
            }

        else:
            # Unknown method → CONFIG.002.
            tool_names = sorted(_DEFERRED_TOOLS | {
                "council.submit_task", "council.status",
                "council.list_sessions", "documenter.audit"})
            hint = "Available tools: " + ", ".join(tool_names[:4])
            env = error_envelope("CONFIG.002", extra=hint)
            return _error_response(request.get("id"), env)

        # --- Transport-layer emission ---
        # After a verb routes successfully (result is NOT an error dict),
        # emit exactly ONE verb.dispatch event.
        if "error" not in result:
            event = make_envelope(
                "verb.dispatch",
                session_id=None,
                actor={"kind": "operator", "id": operator_id},
                payload={"method": method, "operator_id": operator_id},
            )
            deps["events"].append(event)

        # Success response.
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": result,
        }

    except Exception:
        # Log traceback to stderr BEFORE the IO response so callers
        # can see the full stack trace.
        traceback.print_exc(file=sys.stderr)
        return _error_response(request.get("id"),
                               error_envelope("IO.999"))


def _error_response(request_id, envelope: dict) -> dict:
    """Build a JSON-RPC error response dict.

    Returns {"jsonrpc":"2.0","id":<id>,"error":{"data":<envelope>}}.
    """
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"data": envelope},
    }


# ---------------------------------------------------------------------------
# build_deps — production dependency factory
# ---------------------------------------------------------------------------

def build_deps(*, env: dict, state_root: str) -> dict:
    """Build production dependencies for the Operator Surface.

    Args:
        env: environment dict (copy of os.environ or test custom dict).
        state_root: base directory for session state.

    Returns:
        Dict with keys: store, events, documenter, secret, policy_info,
        notices_provider, caller_class, secret_store, approval_registry,
        escalations.

    Note:
        ``secret`` may be ``None`` when ``COUNCIL_OPERATOR_SECRET`` is
        not set in *env* — callers (e.g. ``main()``) must check before use.
    """
    # Secret — read from env, raise ValueError if missing/empty (fail-closed).
    # main() also checks os.environ directly for fail-closed behavior.
    secret_value = env.get("COUNCIL_OPERATOR_SECRET")
    if secret_value is None or secret_value == "":
        raise ValueError(
            "COUNCIL_OPERATOR_SECRET is required in env (missing or empty)"
        )

    # Caller class — read from env, default "operator".
    caller_class = env.get("COUNCIL_CALLER_CLASS", "operator")

    # Known services — comma-separated COUNCIL_KNOWN_SERVICES, empty tuple if unset.
    known_services_str = env.get("COUNCIL_KNOWN_SERVICES", "")
    known_services = tuple(
        s.strip() for s in known_services_str.split(",") if s.strip()
    ) if known_services_str else ()

    # --- Real ports ---
    from .adapters.session_store import MvpSessionStore
    from .core.events import FileEventSink

    store = MvpSessionStore(state_root)
    events = FileEventSink(state_root)

    # Escalation store — volatile in-process store (ADR-013: no disk I/O).
    from .core.escalations import EscalationStore
    escalations = EscalationStore(state_root)

    # Documenter — real Tier 0-1 adapter (lazy import inside methods).
    from .adapters.documenter_adapter import Tier01Documenter
    documenter = Tier01Documenter(state_root)

    # Policy info — read-only YAML parse of documenter_policy.yml.
    policy_info = None
    policy_path = os.path.join(state_root, "documenter_policy.yml")
    if os.path.isfile(policy_path):
        try:
            with open(policy_path, "r", encoding="utf-8") as fh:
                policy_info = yaml.safe_load(fh)
        except Exception:
            policy_info = None

    # Notices provider — pass policy_info so interlock notice is correct.
    from .core.notices import default_notices
    notices_provider = lambda: default_notices(
        policy_info=policy_info, layer1_stub=True)

    # Secret store — wraps the raw secret value.
    class _SecretStore:
        def get_hmac_secret(self):
            return secret_value

    secret_store = _SecretStore()

    # Approval registry — in-memory, volatile (Tier 0-1 pass-through).
    approval_registry = ApprovalRegistry()

    return {
        "store": store,
        "events": events,
        "documenter": documenter,
        "secret": secret_value,
        "policy_info": policy_info,
        "notices_provider": notices_provider,
        "caller_class": caller_class,
        "known_services": known_services,
        "secret_store": secret_store,
        "approval_registry": approval_registry,
        "escalations": escalations,
    }


# ---------------------------------------------------------------------------
# stdio loop — runs when invoked as ``python3 -m operator_surface``
# ---------------------------------------------------------------------------

def main() -> int:
    """Run the stdio JSON-RPC loop."""
    state_root = os.environ.get("COUNCIL_STATE_ROOT", os.getcwd())

    # Fail-closed: secret is required, no default.
    if not os.environ.get("COUNCIL_OPERATOR_SECRET"):
        sys.stderr.write(
            "operator_surface: missing required env var "
            "COUNCIL_OPERATOR_SECRET\n"
        )
        return 1

    # Test-mode toggle: must be defined before the try block so the
    # except clause on line 478 can reference it.
    test_mode = os.environ.get("COUNCIL_TEST_MODE") == "1"

    try:
        # --- Dependency setup ---
        if test_mode:
            from .adapters.session_store import MvpSessionStore
            from .core.escalations import EscalationStore

            class _FakeDocumenter:
                """Stub DocumenterPort for test mode."""
                def audit(self, target_id="*", **kw):
                    return {"compliant": True, "findings": 0}
                def status(self, target_id=None):
                    return {"healthy": True}
                def delegate_preview(self, *a, **kw):
                    return {"diff": "fake"}

            class _FakeEvents:
                """In-memory EventSink for test mode."""
                def __init__(self):
                    self.events = []
                def append(self, event):
                    self.events.append(event)

            class _FakeNoticesProvider:
                def __init__(self):
                    from .core.notices import default_notices
                    self.notices = default_notices(
                        policy_info=None, layer1_stub=True)
                def __call__(self):
                    return self.notices

            class _SecretStore:
                def get_hmac_secret(self):
                    return os.environ["COUNCIL_OPERATOR_SECRET"]

            store = MvpSessionStore(state_root)
            events = _FakeEvents()
            documenter = _FakeDocumenter()
            notices_provider = _FakeNoticesProvider()
            secret_store = _SecretStore()
            escalations = EscalationStore(state_root)
            caller_class = os.environ.get("COUNCIL_CALLER_CLASS", "operator")

            deps = {
                "store": store,
                "events": events,
                "documenter": documenter,
                "secret": secret_store.get_hmac_secret(),
                "policy_info": None,
                "notices_provider": notices_provider,
                "caller_class": caller_class,
                "escalations": escalations,
            }

        else:
            # Production wiring — use build_deps factory.
            deps = build_deps(env=os.environ, state_root=state_root)
            deps.setdefault("caller_class", "operator")

        # --- READY + sentinel + registration docs (both modes) ---
        sys.stdout.write("READY\n")
        sys.stdout.flush()



        # Create the readiness sentinel. On failure, log to stderr but
        # keep serving — the READY line already printed.
        try:
            from .core.sentinel import ensure_sentinel
            if not ensure_sentinel(state_root):
                sys.stderr.write(
                    "operator_surface: sentinel creation failed "
                    "(non-fatal)\n"
                )
        except Exception:
            sys.stderr.write(
                "operator_surface: sentinel creation failed "
                "(non-fatal)\n"
            )

        # Stdio loop: read newline-delimited JSON-RPC from stdin.
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                response = _error_response(None,
                    error_envelope("VAL.003"))
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                continue

            try:
                response = handle_request(request, deps)
            except Exception:
                if test_mode:
                    response = _error_response(request.get("id"),
                        error_envelope("IO.999"))
                else:
                    traceback.print_exc(file=sys.stderr)
                    response = _error_response(request.get("id"),
                        error_envelope("IO.999"))

            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        return 0

    except Exception:
        # Fatal: write to stderr only, never to stdout.
        sys.stderr.write("operator_surface: fatal error\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
