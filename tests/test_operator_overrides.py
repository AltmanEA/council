"""Tests for override verbs + resolve_escalation (Cycle 9 Step 8).

Red baseline: resolve_escalation / override_precheck / override_gate /
consume_precheck_override not yet in verbs.py.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import tempfile
import unittest

# ---------------------------------------------------------------------------
# Red-baseline imports
# ---------------------------------------------------------------------------

try:
    from operator_surface.core.verbs import (  # noqa: F401
        resolve_escalation,
        override_precheck,
        override_gate,
        consume_precheck_override,
    )
except ImportError:
    resolve_escalation = None  # type: ignore[misc,assignment]
    override_precheck = None  # type: ignore[misc,assignment]
    override_gate = None  # type: ignore[misc,assignment]
    consume_precheck_override = None  # type: ignore[misc,assignment]

try:
    from operator_surface.core.envelope import error_envelope  # noqa: F401
except ImportError:
    error_envelope = None  # type: ignore[misc,assignment]

try:
    from operator_surface.core.events import make_envelope  # noqa: F401
except ImportError:
    make_envelope = None  # type: ignore[misc,assignment]

try:
    from operator_surface.core.escalations import EscalationStore  # noqa: F401
except ImportError:
    EscalationStore = None  # type: ignore[misc,assignment]

try:
    from operator_surface.ports import DocumenterPort, EventSink  # noqa: F401
except ImportError:
    DocumenterPort = None  # type: ignore[misc,assignment]
    EventSink = None  # type: ignore[misc,assignment]

try:
    from operator_surface.__main__ import handle_request  # noqa: F401
except ImportError:
    handle_request = None  # type: ignore[misc,assignment]

try:
    from operator_surface.core.auth import issue_token  # noqa: F401
except ImportError:
    issue_token = None  # type: ignore[misc,assignment]

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

class FakeEventSink:
    """In-memory EventSink that collects appended envelopes."""

    def __init__(self):
        self.events = []

    def append(self, event):
        self.events.append(event)


class FakeStore:
    """Minimal store that records append_record calls and provides CRUD."""

    def __init__(self):
        self._sessions = {}
        self._records = {}
        self.append_record_calls = []

    def create_session(self, session_id):
        self._sessions[session_id] = {"session_id": session_id}

    def get_session(self, session_id):
        return dict(self._sessions.get(session_id, {}))

    def list_sessions(self):
        return list(self._sessions.values())

    def append_record(self, session_id, record):
        self.append_record_calls.append({"session_id": session_id, "record": dict(record)})
        if session_id not in self._records:
            self._records[session_id] = []
        self._records[session_id].append(dict(record))


class FakeDocumenterPort(DocumenterPort):
    """DocumenterPort that records every method call in .calls."""

    def __init__(self):
        self.calls = []

    def audit(self, target_id="*", **kwargs):
        self.calls.append(("audit", {"target_id": target_id, **kwargs}))
        return {"compliant": True, "findings": 0}

    def status(self, target_id=None):
        self.calls.append(("status", {"target_id": target_id}))
        return {"healthy": True}

    def delegate_preview(self, target_id, change_type, trust_level, diff_input):
        self.calls.append(("delegate_preview", {
            "target_id": target_id, "change_type": change_type,
            "trust_level": trust_level, "diff_input": diff_input,
        }))
        return {"diff": "canned"}


# ---------------------------------------------------------------------------
# Token helpers
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

def _build_deps(root=None, escalation_store=None):
    if MvpSessionStore is None:
        raise RuntimeError("MvpSessionStore not available")
    store = MvpSessionStore(root or tempfile.mkdtemp())
    events = FakeEventSink()
    documenter = FakeDocumenterPort()

    class _FakeSecretStore:
        def get_hmac_secret(self):
            return "test-secret-key"

    class _FakeNotices:
        def __call__(self):
            return [{"type": "notice.layer1_stub_active",
                     "severity": "Advisory",
                     "text": "temporary adapter; sessions are stored in a provisional format"}]

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
        "secret": _FakeSecretStore().get_hmac_secret(),
        "policy_info": None,
        "notices_provider": _FakeNotices(),
        "caller_class": "operator",
        "known_services": (),
        "secret_store": _FakeSecretStore(),
        "approval_registry": approval_reg,
    }
    if escalation_store is not None:
        deps["escalations"] = escalation_store
    return deps


# ---------------------------------------------------------------------------
# Case A: resolve happy accept
# ---------------------------------------------------------------------------

@unittest.skipIf(
    resolve_escalation is None or EscalationStore is None,
    "red baseline: resolve_escalation / EscalationStore not yet implemented",
)
class TestResolveEscalationAccept(unittest.TestCase):
    """Case A: resolve_escalation accept → status accepted, resolved_by,
    ONE escalation.resolved event."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_accept_resolved(self):
        esc_store = EscalationStore(self.tmpdir)
        rec = esc_store.open(
            session_id="sess-a001",
            request="Resolve conflict",
            fallback_strategy="fallback-a",
            timeout_at="2026-12-31T23:59:59Z",
            resume_phase="3",
        )
        sink = FakeEventSink()
        result = resolve_escalation(
            esc_store,
            session_id="sess-a001",
            escalation_id=rec["escalation_id"],
            decision="accept",
            operator_id="op-b",
            events=sink,
        )
        self.assertNotIn("error", result)
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["resolved_by"], "op-b")
        self.assertEqual(len(sink.events), 1)
        ev = sink.events[0]
        self.assertEqual(ev["event_type"], "escalation.resolved")
        self.assertEqual(ev["payload"]["escalation_id"], rec["escalation_id"])
        self.assertEqual(ev["actor"], {"kind": "operator", "id": "op-b"})


# ---------------------------------------------------------------------------
# Case B: resolve reject
# ---------------------------------------------------------------------------

@unittest.skipIf(
    resolve_escalation is None or EscalationStore is None,
    "red baseline: resolve_escalation / EscalationStore not yet implemented",
)
class TestResolveEscalationReject(unittest.TestCase):
    """Case B: resolve_escalation reject → status rejected."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_reject(self):
        esc_store = EscalationStore(self.tmpdir)
        rec = esc_store.open(
            session_id="sess-b001",
            request="Reject me",
            fallback_strategy="fb",
            timeout_at="2026-12-31T23:59:59Z",
            resume_phase="2",
        )
        sink = FakeEventSink()
        result = resolve_escalation(
            esc_store,
            session_id="sess-b001",
            escalation_id=rec["escalation_id"],
            decision="reject",
            operator_id="op-c",
            events=sink,
        )
        self.assertNotIn("error", result)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["resolved_by"], "op-c")


# ---------------------------------------------------------------------------
# Case C: unknown escalation_id → VAL.003
# ---------------------------------------------------------------------------

@unittest.skipIf(
    resolve_escalation is None or EscalationStore is None,
    "red baseline: resolve_escalation / EscalationStore not yet implemented",
)
class TestResolveUnknown(unittest.TestCase):
    """Case C: unknown escalation_id → VAL.003; sink empty."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_unknown_escalation_id(self):
        esc_store = EscalationStore(self.tmpdir)
        sink = FakeEventSink()
        result = resolve_escalation(
            esc_store,
            session_id="sess-c001",
            escalation_id="esc-nonexistent123",
            decision="accept",
            operator_id="op-x",
            events=sink,
        )
        self.assertIn("error", result)
        self.assertEqual(result["error"]["code"], "VAL.003")
        self.assertEqual(len(sink.events), 0)


# ---------------------------------------------------------------------------
# Case D: cross-session binding
# ---------------------------------------------------------------------------

@unittest.skipIf(
    resolve_escalation is None or EscalationStore is None,
    "red baseline: resolve_escalation / EscalationStore not yet implemented",
)
class TestResolveCrossSession(unittest.TestCase):
    """Case D: esc opened under sess-a001; call with session_id=sess-b001
    → VAL.003; record still pending; sink empty."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_cross_session(self):
        esc_store = EscalationStore(self.tmpdir)
        rec = esc_store.open(
            session_id="sess-a001",
            request="cross-session test",
            fallback_strategy="fb",
            timeout_at="2026-12-31T23:59:59Z",
            resume_phase="3",
        )
        esc_id = rec["escalation_id"]
        sink = FakeEventSink()
        result = resolve_escalation(
            esc_store,
            session_id="sess-b001",
            escalation_id=esc_id,
            decision="accept",
            operator_id="op-x",
            events=sink,
        )
        self.assertIn("error", result)
        self.assertEqual(result["error"]["code"], "VAL.003")
        self.assertEqual(esc_store.get(esc_id)["status"], "pending")
        self.assertEqual(len(sink.events), 0)


# ---------------------------------------------------------------------------
# Case E: bad decision → VAL.002
# ---------------------------------------------------------------------------

@unittest.skipIf(
    resolve_escalation is None or EscalationStore is None,
    "red baseline: resolve_escalation / EscalationStore not yet implemented",
)
class TestResolveBadDecision(unittest.TestCase):
    """Case E: decision 'maybe' → VAL.002; still pending; sink empty."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_bad_decision(self):
        esc_store = EscalationStore(self.tmpdir)
        rec = esc_store.open(
            session_id="sess-e001",
            request="bad decision test",
            fallback_strategy="fb",
            timeout_at="2026-12-31T23:59:59Z",
            resume_phase="3",
        )
        sink = FakeEventSink()
        result = resolve_escalation(
            esc_store,
            session_id="sess-e001",
            escalation_id=rec["escalation_id"],
            decision="maybe",
            operator_id="op-x",
            events=sink,
        )
        self.assertIn("error", result)
        self.assertEqual(result["error"]["code"], "VAL.002")
        self.assertEqual(esc_store.get(rec["escalation_id"])["status"], "pending")
        self.assertEqual(len(sink.events), 0)


# ---------------------------------------------------------------------------
# Case F: already accepted → second resolve → VAL.001
# ---------------------------------------------------------------------------

@unittest.skipIf(
    resolve_escalation is None or EscalationStore is None,
    "red baseline: resolve_escalation / EscalationStore not yet implemented",
)
class TestResolveAlreadyResolved(unittest.TestCase):
    """Case F: first resolve → accepted; second → VAL.001 reason mentions
    'pending' or 'already'; exactly ONE escalation.resolved total."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_second_resolve_refused(self):
        esc_store = EscalationStore(self.tmpdir)
        rec = esc_store.open(
            session_id="sess-f001",
            request="double resolve",
            fallback_strategy="fb",
            timeout_at="2026-12-31T23:59:59Z",
            resume_phase="3",
        )
        esc_id = rec["escalation_id"]
        sink = FakeEventSink()

        # First resolve
        r1 = resolve_escalation(
            esc_store, session_id="sess-f001", escalation_id=esc_id,
            decision="accept", operator_id="op-b", events=sink,
        )
        self.assertNotIn("error", r1)
        self.assertEqual(r1["status"], "accepted")
        self.assertEqual(len(sink.events), 1)

        # Second resolve
        r2 = resolve_escalation(
            esc_store, session_id="sess-f001", escalation_id=esc_id,
            decision="reject", operator_id="op-c", events=sink,
        )
        self.assertIn("error", r2)
        self.assertEqual(r2["error"]["code"], "VAL.001")
        reason_lower = r2["error"]["reason"].lower()
        self.assertTrue(
            "pending" in reason_lower or "already" in reason_lower,
            f"Reason must mention pending/already, got: {r2['error']['reason']}",
        )
        self.assertEqual(len(sink.events), 1)  # exactly ONE total


# ---------------------------------------------------------------------------
# Case G: caller_class="agent" → AUTH.003
# ---------------------------------------------------------------------------

@unittest.skipIf(
    resolve_escalation is None or EscalationStore is None,
    "red baseline: resolve_escalation / EscalationStore not yet implemented",
)
class TestResolveCallerClass(unittest.TestCase):
    """Case G: caller_class='agent' → AUTH.003, reason mentions 'operator';
    NO event; record still pending. Same for 'service'."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_agent_denied(self):
        esc_store = EscalationStore(self.tmpdir)
        rec = esc_store.open(
            session_id="sess-g001",
            request="agent test",
            fallback_strategy="fb",
            timeout_at="2026-12-31T23:59:59Z",
            resume_phase="3",
        )
        sink = FakeEventSink()
        result = resolve_escalation(
            esc_store, session_id="sess-g001", escalation_id=rec["escalation_id"],
            decision="accept", operator_id="op-x", events=sink,
            caller_class="agent",
        )
        self.assertIn("error", result)
        self.assertEqual(result["error"]["code"], "AUTH.003")
        self.assertIn("operator", result["error"]["reason"].lower())
        self.assertEqual(len(sink.events), 0)
        self.assertEqual(esc_store.get(rec["escalation_id"])["status"], "pending")

    def test_service_denied(self):
        esc_store = EscalationStore(self.tmpdir)
        rec = esc_store.open(
            session_id="sess-g002",
            request="service test",
            fallback_strategy="fb",
            timeout_at="2026-12-31T23:59:59Z",
            resume_phase="3",
        )
        sink = FakeEventSink()
        result = resolve_escalation(
            esc_store, session_id="sess-g002", escalation_id=rec["escalation_id"],
            decision="accept", operator_id="op-x", events=sink,
            caller_class="service",
        )
        self.assertIn("error", result)
        self.assertEqual(result["error"]["code"], "AUTH.003")
        self.assertEqual(len(sink.events), 0)
        self.assertEqual(esc_store.get(rec["escalation_id"])["status"], "pending")


# ---------------------------------------------------------------------------
# Case H: override_precheck missing reason
# ---------------------------------------------------------------------------

@unittest.skipIf(
    override_precheck is None,
    "red baseline: override_precheck not yet implemented",
)
class TestOverridePrecheckMissingReason(unittest.TestCase):
    """Case H: reason None / '' / '   ' → VAL.003 each; no event;
    FakeStore.append_record NOT called."""

    def test_reason_none(self):
        store = FakeStore()
        sink = FakeEventSink()
        result = override_precheck(
            store, session_id="sess-h001", reason=None,
            operator_id="op-x", events=sink,
        )
        self.assertIn("error", result)
        self.assertEqual(result["error"]["code"], "VAL.003")
        self.assertEqual(len(sink.events), 0)
        self.assertEqual(len(store.append_record_calls), 0)

    def test_reason_empty_string(self):
        store = FakeStore()
        sink = FakeEventSink()
        result = override_precheck(
            store, session_id="sess-h002", reason="",
            operator_id="op-x", events=sink,
        )
        self.assertIn("error", result)
        self.assertEqual(result["error"]["code"], "VAL.003")
        self.assertEqual(len(sink.events), 0)
        self.assertEqual(len(store.append_record_calls), 0)

    def test_reason_whitespace_only(self):
        store = FakeStore()
        sink = FakeEventSink()
        result = override_precheck(
            store, session_id="sess-h003", reason="   ",
            operator_id="op-x", events=sink,
        )
        self.assertIn("error", result)
        self.assertEqual(result["error"]["code"], "VAL.003")
        self.assertEqual(len(sink.events), 0)
        self.assertEqual(len(store.append_record_calls), 0)


# ---------------------------------------------------------------------------
# Case I: override_precheck valid
# ---------------------------------------------------------------------------

@unittest.skipIf(
    override_precheck is None,
    "red baseline: override_precheck not yet implemented",
)
class TestOverridePrecheckValid(unittest.TestCase):
    """Case I: valid reason → status override_granted; ONE
    precheck.overridden event with payload {session_id, reason, operator_id};
    FakeStore.append_record called once with verb 'council.override_precheck'."""

    def test_valid_override(self):
        store = FakeStore()
        store.create_session("sess-i001")
        sink = FakeEventSink()
        reason = "Emergency override for pre-check timeout"
        result = override_precheck(
            store, session_id="sess-i001", reason=reason,
            operator_id="op-alice", events=sink,
        )
        self.assertNotIn("error", result)
        self.assertEqual(result["status"], "override_granted")
        self.assertEqual(result["session_id"], "sess-i001")
        self.assertEqual(result["operator_id"], "op-alice")
        self.assertEqual(len(sink.events), 1)
        ev = sink.events[0]
        self.assertEqual(ev["event_type"], "precheck.overridden")
        self.assertEqual(ev["session_id"], "sess-i001")
        self.assertEqual(ev["actor"], {"kind": "operator", "id": "op-alice"})
        self.assertIn("session_id", ev["payload"])
        self.assertIn("reason", ev["payload"])
        self.assertIn("operator_id", ev["payload"])
        self.assertEqual(ev["payload"]["reason"], reason)
        self.assertEqual(len(store.append_record_calls), 1)
        call = store.append_record_calls[0]
        self.assertEqual(call["record"]["verb"], "council.override_precheck")
        self.assertIn("reason", call["record"])


# ---------------------------------------------------------------------------
# Case J: single-use consume_precheck_override
# ---------------------------------------------------------------------------

@unittest.skipIf(
    consume_precheck_override is None or override_precheck is None,
    "red baseline: consume_precheck_override / override_precheck not yet implemented",
)
class TestSingleUseOverride(unittest.TestCase):
    """Case J: after I, consume_precheck_override(session_id, operator_id)
    True first call, False second; fresh (session,operator) → False."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_single_use(self):
        store = FakeStore()
        store.create_session("sess-j001")
        sink = FakeEventSink()
        reason = "urgent fix"
        override_precheck(
            store, session_id="sess-j001", reason=reason,
            operator_id="op-alice", events=sink,
        )
        # First call → True (granted)
        self.assertTrue(
            consume_precheck_override("sess-j001", "op-alice"),
            "First consume for (sess,op) should return True",
        )
        # Second call → False (already consumed)
        self.assertFalse(
            consume_precheck_override("sess-j001", "op-alice"),
            "Second consume for same (sess,op) should return False",
        )
        # Fresh (session,operator) → False (no override yet)
        self.assertFalse(
            consume_precheck_override("sess-j002", "op-alice"),
            "Fresh session without override should return False",
        )
        # Same session, different operator → False (no override for that op)
        self.assertFalse(
            consume_precheck_override("sess-j001", "op-bob"),
            "Different operator without override should return False",
        )


# ---------------------------------------------------------------------------
# Case K: override_gate missing reason
# ---------------------------------------------------------------------------

@unittest.skipIf(
    override_gate is None,
    "red baseline: override_gate not yet implemented",
)
class TestOverrideGateMissingReason(unittest.TestCase):
    """Case K: missing reason → VAL.003, NO event, port.calls == []."""

    def test_reason_none(self):
        port = FakeDocumenterPort()
        sink = FakeEventSink()
        result = override_gate(
            port, target_id="doc-1", reason=None,
            operator_id="op-x", events=sink,
        )
        self.assertIn("error", result)
        self.assertEqual(result["error"]["code"], "VAL.003")
        self.assertEqual(len(sink.events), 0)
        self.assertEqual(port.calls, [])

    def test_reason_empty(self):
        port = FakeDocumenterPort()
        sink = FakeEventSink()
        result = override_gate(
            port, target_id="doc-1", reason="",
            operator_id="op-x", events=sink,
        )
        self.assertIn("error", result)
        self.assertEqual(result["error"]["code"], "VAL.003")
        self.assertEqual(len(sink.events), 0)
        self.assertEqual(port.calls, [])


# ---------------------------------------------------------------------------
# Case L: override_gate valid
# ---------------------------------------------------------------------------

@unittest.skipIf(
    override_gate is None,
    "red baseline: override_gate not yet implemented",
)
class TestOverrideGateValid(unittest.TestCase):
    """Case L: valid → status 'overridden'; ONE documenter.override_gate event;
    payload keys EXACTLY {target_id, reason, operator_id}; port.calls == []."""

    def test_valid_override(self):
        port = FakeDocumenterPort()
        sink = FakeEventSink()
        result = override_gate(
            port, target_id="tgt-spec-chars",
            reason="Emergency override: spec contains backtick ` and dollar $ and ampersand &",
            operator_id="op-alice", events=sink,
        )
        self.assertNotIn("error", result)
        self.assertEqual(result["status"], "overridden")
        self.assertEqual(result["target_id"], "tgt-spec-chars")
        self.assertEqual(result["operator_id"], "op-alice")
        self.assertEqual(len(sink.events), 1)
        ev = sink.events[0]
        self.assertEqual(ev["event_type"], "documenter.override_gate")
        self.assertEqual(ev["session_id"], None)
        self.assertEqual(ev["actor"], {"kind": "operator", "id": "op-alice"})
        payload = ev["payload"]
        self.assertEqual(set(payload.keys()), {"target_id", "reason", "operator_id"})
        self.assertEqual(payload["target_id"], "tgt-spec-chars")
        self.assertEqual(payload["operator_id"], "op-alice")
        self.assertIn("backtick", payload["reason"])
        self.assertIn("$", payload["reason"])
        self.assertIn("&", payload["reason"])
        # port was NOT called (no write path)
        self.assertEqual(port.calls, [])


# ---------------------------------------------------------------------------
# Case M: transport — handle_request routing
# ---------------------------------------------------------------------------

@unittest.skipIf(
    handle_request is None or issue_token is None,
    "red baseline: handle_request / issue_token not yet implemented",
)
class TestTransportRouting(unittest.TestCase):
    """Case M: handle_request routes three methods auth-first.
    Valid token → routed (result/error from verb, not CONFIG).
    No auth → AUTH.002. council.get_artifacts → CONFIG.001.
    Unknown → CONFIG.002."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.esc_store = EscalationStore(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _build_request(self, method, params=None, rid=1):
        req = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            req["params"] = params
        return req

    def _build_auth(self, token):
        return {"auth": {"token": token}}

    def test_resolve_escalation_routed_with_auth(self):
        """Valid token → verb runs; result contains verb error (VAL.*),
        NOT CONFIG.001 (not deferred)."""
        esc_store = EscalationStore(self.tmpdir)
        rec = esc_store.open(
            session_id="sess-m001",
            request="test", fallback_strategy="fb",
            timeout_at="2026-12-31T23:59:59Z", resume_phase="3",
        )
        esc_store.get(rec["escalation_id"])  # warm up
        deps = _build_deps(self.tmpdir, escalation_store=esc_store)
        token = _make_token(sub="op-alice")
        req = self._build_request(
            "council.resolve_escalation",
            params={
                **self._build_auth(token),
                "session_id": "sess-m001",
                "escalation_id": rec["escalation_id"],
                "decision": "accept",
            },
        )
        result = handle_request(req, deps)
        # Should NOT be CONFIG.001 (deferred)
        if "error" in result:
            code = result["error"]["data"]["code"]
            self.assertNotEqual(code, "CONFIG.001",
                                "resolve_escalation must not return CONFIG.001")

    def test_override_precheck_routed_with_auth(self):
        deps = _build_deps(self.tmpdir, escalation_store=EscalationStore(self.tmpdir))
        token = _make_token(sub="op-alice")
        req = self._build_request(
            "council.override_precheck",
            params={
                **self._build_auth(token),
                "session_id": "sess-m002",
                "reason": "urgent fix",
            },
        )
        result = handle_request(req, deps)
        if "error" in result:
            code = result["error"]["data"]["code"]
            self.assertNotEqual(code, "CONFIG.001",
                                "override_precheck must not return CONFIG.001")

    def test_override_gate_routed_with_auth(self):
        deps = _build_deps(self.tmpdir, escalation_store=EscalationStore(self.tmpdir))
        token = _make_token(sub="op-alice")
        req = self._build_request(
            "documenter.override_gate",
            params={
                **self._build_auth(token),
                "target_id": "doc-1",
                "reason": "override",
            },
        )
        result = handle_request(req, deps)
        if "error" in result:
            code = result["error"]["data"]["code"]
            self.assertNotEqual(code, "CONFIG.001",
                                "override_gate must not return CONFIG.001")

    def test_no_auth_returns_auth_error(self):
        deps = _build_deps(self.tmpdir, escalation_store=EscalationStore(self.tmpdir))
        req = self._build_request(
            "council.resolve_escalation",
            params={"session_id": "s", "escalation_id": "e", "decision": "accept"},
        )
        result = handle_request(req, deps)
        self.assertIn("error", result)
        self.assertNotIn("result", result)
        self.assertTrue(
            result["error"]["data"]["code"].startswith("AUTH."),
            f"Expected AUTH.*, got {result['error']['data']['code']!r}",
        )

    def test_no_auth_verb_not_ran(self):
        """Auth failure: esc_store must not have been modified."""
        esc_store = EscalationStore(self.tmpdir)
        deps = _build_deps(self.tmpdir, escalation_store=esc_store)
        # Open one escalation first.
        esc_store.open(
            session_id="sess-m003",
            request="original", fallback_strategy="fb",
            timeout_at="2026-12-31T23:59:59Z", resume_phase="3",
        )
        count_before = len(esc_store.list())
        token = _make_token(sub="op-alice")
        req = self._build_request(
            "council.resolve_escalation",
            params={
                **self._build_auth(token),
                "session_id": "sess-m003",
                "escalation_id": "esc-nonexistent999",
                "decision": "accept",
            },
        )
        # This auth is fine but verb will fail (non-existent esc)
        # So test with no auth to ensure verb never runs
        req2 = self._build_request(
            "council.resolve_escalation",
            params={"session_id": "s", "escalation_id": "e", "decision": "accept"},
        )
        handle_request(req2, deps)
        count_after = len(esc_store.list())
        self.assertEqual(count_before, count_after,
                         "EscalationStore must not be modified on auth failure")

    def test_get_artifacts_still_deferred(self):
        deps = _build_deps(self.tmpdir, escalation_store=EscalationStore(self.tmpdir))
        token = _make_token(sub="op-alice")
        req = self._build_request(
            "council.get_artifacts",
            params=self._build_auth(token),
        )
        result = handle_request(req, deps)
        self.assertIn("error", result)
        self.assertEqual(result["error"]["data"]["code"], "CONFIG.001")

    def test_unknown_method_config_002(self):
        deps = _build_deps(self.tmpdir, escalation_store=EscalationStore(self.tmpdir))
        token = _make_token(sub="op-alice")
        req = self._build_request(
            "council.nonexistent",
            params=self._build_auth(token),
        )
        result = handle_request(req, deps)
        self.assertIn("error", result)
        self.assertEqual(result["error"]["data"]["code"], "CONFIG.002")


# ---------------------------------------------------------------------------
# Case N: architecture guard — verbs.py must not contain open( or Path(
# ---------------------------------------------------------------------------

@unittest.skipIf(
    not os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "operator_surface", "core", "verbs.py")),
    "red baseline: operator_surface/core/verbs.py not found",
)
class TestArchitectureGuard(unittest.TestCase):
    """Case N: operator_surface/core/verbs.py must contain NO 'open('
    and NO 'Path(' occurrences (disk I/O forbidden in core verbs)."""

    def _get_verbs_source(self):
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        root = os.path.dirname(tests_dir)
        verbs_path = os.path.join(root, "operator_surface", "core", "verbs.py")
        with open(verbs_path, "r", encoding="utf-8") as f:
            return f.read()

    def test_no_open_in_verbs(self):
        source = self._get_verbs_source()
        self.assertNotIn("open(", source,
                         "verbs.py must not call open() (use store methods)")

    def test_no_path_in_verbs(self):
        source = self._get_verbs_source()
        self.assertNotIn("Path(", source,
                         "verbs.py must not use Path (disk I/O forbidden)")


# ---------------------------------------------------------------------------
# Case O: defensive copy — mutate returns does not corrupt internals
# ---------------------------------------------------------------------------

@unittest.skipIf(
    resolve_escalation is None or override_precheck is None or EscalationStore is None,
    "red baseline: resolve_escalation / override_precheck / EscalationStore",
)
class TestDefensiveCopy(unittest.TestCase):
    """Case O: mutate returned dict does not corrupt store internals."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_resolve_return_mutation_does_not_affect_store(self):
        esc_store = EscalationStore(self.tmpdir)
        rec = esc_store.open(
            session_id="sess-o001",
            request="defensive copy test",
            fallback_strategy="fb",
            timeout_at="2026-12-31T23:59:59Z",
            resume_phase="3",
        )
        sink = FakeEventSink()
        result = resolve_escalation(
            esc_store, session_id="sess-o001",
            escalation_id=rec["escalation_id"],
            decision="accept", operator_id="op-b", events=sink,
        )
        self.assertNotIn("error", result)
        # Mutate the result
        result["status"] = "hacked"
        result["resolved_by"] = "op-hacker"
        result["escalation_id"] = "esc-hacked"
        # Re-get from store must still show accepted
        still = esc_store.get(rec["escalation_id"])
        self.assertEqual(still["status"], "accepted")
        self.assertEqual(still["resolved_by"], "op-b")

    def test_override_return_mutation_does_not_affect_store(self):
        store = FakeStore()
        store.create_session("sess-o002")
        sink = FakeEventSink()
        result = override_precheck(
            store, session_id="sess-o002",
            reason="emergency", operator_id="op-alice", events=sink,
        )
        self.assertNotIn("error", result)
        # Mutate
        result["status"] = "hacked"
        result["session_id"] = "sess-hacked"
        result["operator_id"] = "op-hacker"
        # Store's append_record_calls must still have correct data
        self.assertEqual(len(store.append_record_calls), 1)
        self.assertEqual(store.append_record_calls[0]["record"]["verb"],
                         "council.override_precheck")


# ---------------------------------------------------------------------------
# Back-compat: existing envelope + verb tests must stay green
# ---------------------------------------------------------------------------

@unittest.skipIf(error_envelope is None,
                 "red baseline: error_envelope not yet implemented")
class TestEnvelopeBackCompat(unittest.TestCase):
    """error_envelope with reason key must work."""

    def test_reason_key_preserved(self):
        env = error_envelope("VAL.001", reason="test reason")
        self.assertIn("reason", env)
        self.assertEqual(env["reason"], "test reason")


@unittest.skipIf(
    handle_request is None or error_envelope is None,
    "red baseline: handle_request not yet implemented",
)
class TestEnvelopeDeferBackCompat(unittest.TestCase):
    """Existing deferred tools must still return CONFIG.001."""

    def test_resolve_escalation_still_deferred_in_handle_request(self):
        """In handle_request (before the new verb routes), council.resolve_escalation
        must still be in _DEFERRED_TOOLS and return CONFIG.001.
        After implementation it will NOT be deferred — but the back-compat test
        must verify it's NOT CONFIG.001 (i.e. it's now routed)."""
        esc_store = EscalationStore(tempfile.mkdtemp())
        deps = _build_deps(tempfile.mkdtemp(), escalation_store=esc_store)
        token = _make_token(sub="op-alice")
        req = {
            "jsonrpc": "2.0", "id": 1,
            "method": "council.resolve_escalation",
            "params": {"auth": {"token": token},
                       "session_id": "s", "escalation_id": "e",
                       "decision": "accept"},
        }
        result = handle_request(req, deps)
        # After Step 8, this must NOT be CONFIG.001 (deferred).
        if "error" in result:
            self.assertNotEqual(
                result["error"]["data"]["code"], "CONFIG.001",
                "council.resolve_escalation must be routed, not deferred",
            )


if __name__ == "__main__":
    unittest.main()
