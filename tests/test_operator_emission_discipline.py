"""Emission discipline: every verb path through handle_request emits ≥1 event.

Cycle 10 Step 9 — Test Author.

Contract (A): after a verb returns non-error, handle_request (at the transport
layer in __main__) emits ONE event with event_type "verb.dispatch", payload
{"method": <method>, "operator_id": <op_id>}, actor operator, session_id None.

Additionally, verbs that have their own emission (submit_task → verb.submit_task,
precheck.*) remain as-is.  The emission discipline test asserts ≥1 event per
request whose event_type starts with "verb." or "precheck."

Existing test_operator_approval "sink empty after delegate" stays green because
emission happens in __main__ (transport layer), not the verb itself.

Red baseline: handle_request currently does NOT emit any events after verbs
return — so ALL 9 paths are red.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

# ---------------------------------------------------------------------------
# Red-baseline imports
# ---------------------------------------------------------------------------

try:
    from operator_surface.__main__ import handle_request  # noqa: F401
except ImportError:
    handle_request = None  # type: ignore[misc,assignment]

try:
    from operator_surface.core.events import make_envelope  # noqa: F401
except ImportError:
    make_envelope = None  # type: ignore[misc,assignment]

try:
    from operator_surface.core.auth import issue_token  # noqa: F401
except ImportError:
    issue_token = None  # type: ignore[misc,assignment]

try:
    from operator_surface.ports import EventSink  # noqa: F401
except ImportError:
    EventSink = None  # type: ignore[misc,assignment]

try:
    from operator_surface.adapters.session_store import MvpSessionStore  # noqa: F401
except ImportError:
    MvpSessionStore = None  # type: ignore[misc,assignment]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_CLAIMS = {
    "alg": "HS256",
    "iss": "operator-surface",
    "sub": "op-alice",
    "exp": 9999999999,
}


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class ListEventSink:
    """In-memory EventSink that collects appended envelopes."""

    def __init__(self):
        self.events = []

    def append(self, event):
        self.events.append(event)


class _FakeDocumenter:
    """Minimal DocumenterPort."""

    def audit(self, target_id="*", **kwargs):
        return {"compliant": True, "findings": 0}

    def status(self, target_id=None):
        return {"healthy": True}

    def delegate_preview(self, target_id, change_type, trust_level, diff_input):
        return {"diff": "canned"}


class _FakeNoticesProvider:
    def __init__(self, notices=None):
        self.notices = notices or [
            {"type": "notice.layer1_stub_active",
             "severity": "Advisory",
             "text": "temporary adapter; sessions are stored in a provisional format"}
        ]

    def __call__(self, *a, **kw):
        return self.notices


class _FakeSecretStore:
    def get_hmac_secret(self):
        return "test-secret-key"


# ---------------------------------------------------------------------------
# Token helper
# ---------------------------------------------------------------------------

def _make_token(secret="test-secret-key", sub="op-alice"):
    if issue_token is None:
        return None
    claims = dict(_MIN_CLAIMS)
    claims["sub"] = sub
    return issue_token(claims, secret)


# ---------------------------------------------------------------------------
# Deps builder for handle_request
# ---------------------------------------------------------------------------

def _build_handle_request_deps(root=None, escalation_store=None):
    """Create a full deps dict for handle_request."""
    if MvpSessionStore is None:
        raise RuntimeError("MvpSessionStore not available")
    store = MvpSessionStore(root or tempfile.mkdtemp())
    events = ListEventSink()
    documenter = _FakeDocumenter()
    secret_store = _FakeSecretStore()
    notices = _FakeNoticesProvider()

    approval_reg = None
    try:
        from operator_surface.core.approval import ApprovalRegistry
        approval_reg = ApprovalRegistry()
    except ImportError:
        pass

    deps = {
        "store": store,
        "events": events,
        "documenter": documenter,
        "secret": secret_store.get_hmac_secret(),
        "policy_info": None,
        "notices_provider": notices,
        "caller_class": "operator",
        "known_services": (),
        "secret_store": secret_store,
        "approval_registry": approval_reg,
    }
    if escalation_store is not None:
        deps["escalations"] = escalation_store
    return deps


# ---------------------------------------------------------------------------
# Test cases — 9 verb paths
# ---------------------------------------------------------------------------

@unittest.skipIf(handle_request is None,
                 "red baseline: handle_request not yet implemented")
class TestEmissionDiscipline(unittest.TestCase):
    """Every verb path must emit ≥1 event with event_type starting
    'verb.' or 'precheck.' through handle_request + stub sink."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_request(self, method, params, rid=1):
        req = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            req["params"] = params
        return req

    def _make_auth(self, token):
        return {"auth": {"token": token}}

    def _has_verb_or_precheck_event(self, sink):
        """Return True if sink has ≥1 event with event_type starting verb. or precheck.."""
        for ev in sink.events:
            etype = ev.get("event_type", "")
            if etype.startswith("verb.") or etype.startswith("precheck."):
                return True
        return False

    # --- 1. council.submit_task ---
    def test_01_submit_task_emits(self):
        """council.submit_task → ≥1 verb./precheck. event."""
        deps = _build_handle_request_deps(self.tmpdir)
        token = _make_token(sub="op-alice")
        req = self._make_request(
            "council.submit_task",
            params={
                **self._make_auth(token),
                "task_brief": "Emission test task",
                "scenario_id": "scen-emission",
            },
        )
        handle_request(req, deps)
        self.assertTrue(
            self._has_verb_or_precheck_event(deps["events"]),
            "submit_task must emit ≥1 event starting with verb./precheck.",
        )

    # --- 2. council.status ---
    def test_02_status_emits(self):
        """council.status → ≥1 verb./precheck. event."""
        deps = _build_handle_request_deps(self.tmpdir)
        token = _make_token(sub="op-alice")
        req = self._make_request(
            "council.status",
            params=self._make_auth(token),
        )
        handle_request(req, deps)
        self.assertTrue(
            self._has_verb_or_precheck_event(deps["events"]),
            "status must emit ≥1 event starting with verb./precheck.",
        )

    # --- 3. council.list_sessions ---
    def test_03_list_sessions_emits(self):
        """council.list_sessions → ≥1 verb./precheck. event."""
        deps = _build_handle_request_deps(self.tmpdir)
        token = _make_token(sub="op-alice")
        req = self._make_request(
            "council.list_sessions",
            params=self._make_auth(token),
        )
        handle_request(req, deps)
        self.assertTrue(
            self._has_verb_or_precheck_event(deps["events"]),
            "list_sessions must emit ≥1 event starting with verb./precheck.",
        )

    # --- 4. documenter.audit ---
    def test_04_documenter_audit_emits(self):
        """documenter.audit → ≥1 verb./precheck. event."""
        deps = _build_handle_request_deps(self.tmpdir)
        token = _make_token(sub="op-alice")
        req = self._make_request(
            "documenter.audit",
            params=self._make_auth(token),
        )
        handle_request(req, deps)
        self.assertTrue(
            self._has_verb_or_precheck_event(deps["events"]),
            "documenter.audit must emit ≥1 event starting with verb./precheck.",
        )

    # --- 5. documenter.delegate ---
    def test_05_documenter_delegate_emits(self):
        """documenter.delegate → ≥1 verb./precheck. event (transport layer)."""
        deps = _build_handle_request_deps(self.tmpdir)
        token_alice = _make_token(sub="op-alice")
        req = self._make_request(
            "documenter.delegate",
            params={
                **self._make_auth(token_alice),
                "target_id": "target-emission",
                "change_type": "edit",
                "diff": "diff content",
            },
        )
        handle_request(req, deps)
        self.assertTrue(
            self._has_verb_or_precheck_event(deps["events"]),
            "documenter.delegate must emit ≥1 event starting with verb./precheck. "
            "(emission at transport layer, not verb)",
        )

    # --- 6. documenter.approve ---
    def test_06_documenter_approve_emits(self):
        """documenter.approve → ≥1 verb./precheck. event (transport layer)."""
        deps = _build_handle_request_deps(self.tmpdir)
        token_alice = _make_token(sub="op-alice")
        token_bob = _make_token(sub="op-bob")
        # First delegate to get a request_id
        req_delegate = self._make_request(
            "documenter.delegate",
            params={
                **self._make_auth(token_alice),
                "target_id": "target-emission",
                "change_type": "edit",
                "diff": "diff content",
            },
        )
        r1 = handle_request(req_delegate, deps)
        rid = r1["result"]["request_id"]
        # Now approve
        req_approve = self._make_request(
            "documenter.approve",
            params={
                **self._make_auth(token_bob),
                "request_id": rid,
                "diff": "diff content",
            },
        )
        handle_request(req_approve, deps)
        self.assertTrue(
            self._has_verb_or_precheck_event(deps["events"]),
            "documenter.approve must emit ≥1 event starting with verb./precheck. "
            "(emission at transport layer)",
        )

    # --- 7. council.resolve_escalation ---
    def test_07_resolve_escalation_emits(self):
        """council.resolve_escalation → ≥1 verb./precheck. event (transport layer)."""
        from operator_surface.core.escalations import EscalationStore
        esc_store = EscalationStore(self.tmpdir)
        rec = esc_store.open(
            session_id="sess-esc001",
            request="Emission esc test",
            fallback_strategy="fb",
            timeout_at="2026-12-31T23:59:59Z",
            resume_phase="3",
        )
        deps = _build_handle_request_deps(self.tmpdir, escalation_store=esc_store)
        token = _make_token(sub="op-alice")
        req = self._make_request(
            "council.resolve_escalation",
            params={
                **self._make_auth(token),
                "session_id": "sess-esc001",
                "escalation_id": rec["escalation_id"],
                "decision": "accept",
            },
        )
        handle_request(req, deps)
        self.assertTrue(
            self._has_verb_or_precheck_event(deps["events"]),
            "resolve_escalation must emit ≥1 event starting with verb./precheck. "
            "(emission at transport layer)",
        )

    # --- 8. council.override_precheck ---
    def test_08_override_precheck_emits(self):
        """council.override_precheck → ≥1 verb./precheck. event (transport layer)."""
        deps = _build_handle_request_deps(self.tmpdir)
        token = _make_token(sub="op-alice")
        req = self._make_request(
            "council.override_precheck",
            params={
                **self._make_auth(token),
                "session_id": "sess-over001",
                "reason": "Emergency override",
            },
        )
        handle_request(req, deps)
        self.assertTrue(
            self._has_verb_or_precheck_event(deps["events"]),
            "override_precheck must emit ≥1 event starting with verb./precheck. "
            "(emission at transport layer)",
        )

    # --- 9. documenter.override_gate ---
    def test_09_override_gate_emits(self):
        """documenter.override_gate → ≥1 verb./precheck. event (transport layer)."""
        deps = _build_handle_request_deps(self.tmpdir)
        token = _make_token(sub="op-alice")
        req = self._make_request(
            "documenter.override_gate",
            params={
                **self._make_auth(token),
                "target_id": "doc-override",
                "reason": "Emergency override gate",
            },
        )
        handle_request(req, deps)
        self.assertTrue(
            self._has_verb_or_precheck_event(deps["events"]),
            "override_gate must emit ≥1 event starting with verb./precheck. "
            "(emission at transport layer)",
        )

    # --- Verb.dispatch exact pin ---
    def test_verb_dispatch_event_type(self):
        """Each successful request must emit exactly ONE event with
        event_type == 'verb.dispatch' at the transport layer."""
        deps = _build_handle_request_deps(self.tmpdir)
        token = _make_token(sub="op-alice")
        req = self._make_request(
            "council.status",
            params=self._make_auth(token),
        )
        handle_request(req, deps)
        dispatch_events = [
            ev for ev in deps["events"].events
            if ev.get("event_type") == "verb.dispatch"
        ]
        self.assertEqual(
            len(dispatch_events), 1,
            "Exactly one verb.dispatch event must be emitted",
        )
        ev = dispatch_events[0]
        self.assertEqual(ev["actor"]["kind"], "operator")
        self.assertEqual(ev["actor"]["id"], "op-alice")
        self.assertIsNone(ev["session_id"])
        self.assertEqual(ev["payload"]["method"], "council.status")
        self.assertEqual(ev["payload"]["operator_id"], "op-alice")


if __name__ == "__main__":
    unittest.main()
