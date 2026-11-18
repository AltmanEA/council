"""Tests for approval module + delegate/approve verbs + transport routing (Cycle 8 Step 7).

Frozen API contract:
  - class ApprovalError(Exception): __init__(code, reason) → .code, .reason
  - def hash_diff(diff) → str  ( "sha256:" + sha256(diff.encode()).hexdigest() )
  - class ApprovalRegistry:
      register_request(request_id, diff_hash, proposer_operator_id) → dict COPY
      approve(request_id, approver_operator_id, diff) → dict COPY  (raises ApprovalError)
      get(request_id) → dict COPY | None
  - def documenter_delegate(documenter_port, approval_registry, target_id,
                            change_type, diff, operator_id, events) → dict
  - def documenter_approve(approval_registry, request_id, operator_id, diff, events) → dict

Transport (handle_request):
  - "documenter.delegate" → verbs.documenter_delegate(...)
  - "documenter.approve" → verbs.documenter_approve(...)
  - BOTH require auth first (bad/missing → AUTH.002)
  - 4 deferred tools still return CONFIG.001

Fakes:
  - FakeDocumenterPort(DocumenterPort) — delegate_preview returns canned dict
  - ListEventSink (extends EventSink ABC) — in-memory event collection
  - _FakeSecretStore (extends SecretStore ABC)

Red baseline: approval module red; verbs + envelope + architecture GREEN.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import unittest.mock as mock

# ---------------------------------------------------------------------------
# Frozen regexes
# ---------------------------------------------------------------------------

_REQUEST_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

# ---------------------------------------------------------------------------
# Import module-under-test — red baseline: ImportError → None
# ---------------------------------------------------------------------------

try:
    from operator_ingress.core.approval import (  # noqa: F401
        ApprovalError,
        ApprovalRegistry,
        hash_diff,
    )
except ImportError:
    ApprovalError = None  # type: ignore[misc,assignment]
    ApprovalRegistry = None  # type: ignore[misc,assignment]
    hash_diff = None  # type: ignore[misc,assignment]

# Verbs — may be red if approval not yet implemented
try:
    from operator_ingress.core.verbs import (  # noqa: F401
        documenter_delegate,
        documenter_approve,
    )
except ImportError:
    documenter_delegate = None  # type: ignore[misc,assignment]
    documenter_approve = None  # type: ignore[misc,assignment]

# envelope + auth helpers (pre-existing, should be green)
try:
    from operator_ingress.core.envelope import error_envelope  # noqa: F401
except ImportError:
    error_envelope = None  # type: ignore[misc,assignment]

try:
    from operator_ingress.core.events import make_envelope  # noqa: F401
except ImportError:
    make_envelope = None  # type: ignore[misc,assignment]

try:
    from operator_ingress.core.auth import issue_token  # noqa: F401
except ImportError:
    issue_token = None  # type: ignore[misc,assignment]

try:
    from operator_ingress.__main__ import handle_request  # noqa: F401
except ImportError:
    handle_request = None  # type: ignore[misc,assignment]

# Ports ABCs
try:
    from operator_ingress.ports import DocumenterPort, EventSink  # noqa: F401
except ImportError:
    DocumenterPort = None  # type: ignore[misc,assignment]
    EventSink = None  # type: ignore[misc,assignment]

# MvpSessionStore for handle_request test deps
try:
    from operator_ingress.adapters.session_store import MvpSessionStore  # noqa: F401
except ImportError:
    MvpSessionStore = None  # type: ignore[misc,assignment]


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeDocumenterPort(DocumenterPort):
    """Minimal DocumenterPort that returns canned delegate_preview results."""

    def __init__(self, preview_result=None):
        self.preview_result = preview_result or {"diff": "canned diff preview"}
        self.last_call = None

    def audit(self, target_id="*", **kwargs):
        return {"compliant": True, "findings": 0}

    def status(self, target_id=None):
        return {"healthy": True}

    def delegate_preview(self, target_id, change_type, trust_level, diff_input):
        self.last_call = {
            "target_id": target_id,
            "change_type": change_type,
            "trust_level": trust_level,
            "diff_input": diff_input,
        }
        return dict(self.preview_result)


class ListEventSink(EventSink):
    """In-memory EventSink that collects appended envelopes."""

    def __init__(self):
        self.events = []

    def append(self, event):
        self.events.append(event)


class _FakeSecretStore:
    """Returns a constant secret."""

    def __init__(self, secret="test-secret-key"):
        self.secret = secret

    def get_hmac_secret(self):
        return self.secret


# ---------------------------------------------------------------------------
# Minimal session store + notices for handle_request deps
# ---------------------------------------------------------------------------

class _FakeNoticesProvider:
    """Returns a list of notice dicts."""

    def __init__(self, notices=None):
        self.notices = notices or [
            {"type": "notice.layer1_stub_active",
             "severity": "Advisory",
             "text": "temporary adapter; sessions are stored in a provisional format"}
        ]

    def __call__(self, *a, **kw):
        return self.notices


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

_MIN_CLAIMS = {
    "alg": "HS256",
    "iss": "operator-surface",
    "sub": "op-alice",
    "exp": 9999999999,
}


def _make_token(secret="test-secret-key", sub="op-alice"):
    """Build a valid token via issue_token (when available)."""
    if issue_token is None:
        return None
    claims = dict(_MIN_CLAIMS)
    claims["sub"] = sub
    return issue_token(claims, secret)


# ---------------------------------------------------------------------------
# Build deps dict for handle_request
# ---------------------------------------------------------------------------

def _build_handle_request_deps(root=None):
    """Create a full deps dict for handle_request, including approval_registry."""
    if MvpSessionStore is None:
        raise RuntimeError("MvpSessionStore not available (red baseline)")
    store = MvpSessionStore(root or tempfile.mkdtemp())
    events = ListEventSink()
    documenter = FakeDocumenterPort()
    secret_store = _FakeSecretStore()
    notices = _FakeNoticesProvider()
    # Create a real ApprovalRegistry for deps
    if ApprovalRegistry is not None:
        approval_reg = ApprovalRegistry()
    else:
        approval_reg = None  # type: ignore[assignment]

    return {
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


# ---------------------------------------------------------------------------
# Test case 1: Happy path (delegate → approve)
# ---------------------------------------------------------------------------

@unittest.skipIf(ApprovalRegistry is None,
                 "red baseline: ApprovalRegistry not yet implemented")
class TestHappyPath(unittest.TestCase):
    """Case 1: delegate(op A) → approve(op B, SAME diff) → approved."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_full_flow_approved(self):
        port = FakeDocumenterPort({"diff": "canned diff"})
        reg = ApprovalRegistry()
        events = ListEventSink()
        operator_a = "op-alice"
        operator_b = "op-bob"
        diff = "some diff content"

        # delegate via verb
        result = documenter_delegate(
            port, reg, "target-doc-1", "edit", diff, operator_a, events,
        )
        self.assertIn("request_id", result)
        rid = result["request_id"]
        self.assertRegex(rid, _REQUEST_ID_RE.pattern)
        self.assertEqual(result["target_id"], "target-doc-1")
        self.assertEqual(result["change_type"], "edit")
        self.assertEqual(result["status"], "approval_required")
        self.assertEqual(result["diff_preview"], {"diff": "canned diff"})

        # approve via verb (different operator)
        approve_result = documenter_approve(
            reg, rid, operator_b, diff, events,
        )
        self.assertNotIn("error", approve_result)
        self.assertEqual(approve_result["status"], "approved")
        self.assertEqual(approve_result["request_id"], rid)
        self.assertEqual(
            approve_result["proposer_operator_id"], operator_a
        )
        self.assertEqual(
            approve_result["approver_operator_id"], operator_b
        )

    def test_documenter_approval_event_emitted(self):
        port = FakeDocumenterPort({"diff": "preview"})
        reg = ApprovalRegistry()
        events = ListEventSink()
        operator_a = "op-alice"
        operator_b = "op-bob"
        diff = "content"

        # delegate
        result = documenter_delegate(
            port, reg, "target", "edit", diff, operator_a, events,
        )
        rid = result["request_id"]

        # approve
        documenter_approve(reg, rid, operator_b, diff, events)

        # exactly ONE documenter.approval event
        approval_events = [
            e for e in events.events
            if e.get("event_type") == "documenter.approval"
        ]
        self.assertEqual(len(approval_events), 1)
        ev = approval_events[0]

        # event payload
        self.assertEqual(ev["actor"]["kind"], "operator")
        self.assertEqual(ev["actor"]["id"], operator_b)
        self.assertEqual(ev["session_id"], None)
        payload = ev["payload"]
        self.assertEqual(payload["request_id"], rid)
        self.assertEqual(payload["proposer_operator_id"], operator_a)
        self.assertEqual(payload["approver_operator_id"], operator_b)


# ---------------------------------------------------------------------------
# Test case 2: Self-approval
# ---------------------------------------------------------------------------

@unittest.skipIf(
    ApprovalRegistry is None or documenter_approve is None,
    "red baseline: ApprovalRegistry/documenter_approve not yet implemented",
)
class TestSelfApproval(unittest.TestCase):
    """Case 2: delegate(op A) → approve(op A, same diff) → error VAL.001;
    record stays pending; LATER approve by op B succeeds."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_self_approval_rejected_but_record_stays_pending(self):
        port = FakeDocumenterPort()
        reg = ApprovalRegistry()
        events = ListEventSink()
        operator_a = "op-alice"
        diff = "diff content"

        # delegate
        result = documenter_delegate(
            port, reg, "target", "edit", diff, operator_a, events,
        )
        rid = result["request_id"]

        # self-approve
        result = documenter_approve(reg, rid, operator_a, diff, events)
        self.assertIn("error", result)
        self.assertEqual(result["error"]["code"], "VAL.001")
        self.assertIn("differ", result["error"]["reason"])

        # registry record still pending
        rec = reg.get(rid)
        self.assertEqual(rec["state"], "pending")

        # no documenter.approval event
        approval_events = [
            e for e in events.events
            if e.get("event_type") == "documenter.approval"
        ]
        self.assertEqual(len(approval_events), 0)

    def test_later_approve_by_different_operator_succeeds(self):
        port = FakeDocumenterPort()
        reg = ApprovalRegistry()
        events = ListEventSink()
        operator_a = "op-alice"
        operator_b = "op-bob"
        diff = "diff content"

        # delegate
        result = documenter_delegate(
            port, reg, "target", "edit", diff, operator_a, events,
        )
        rid = result["request_id"]

        # self-approve fails
        result = documenter_approve(reg, rid, operator_a, diff, events)
        self.assertIn("error", result)

        # different operator approves — succeeds
        result = documenter_approve(reg, rid, operator_b, diff, events)
        self.assertNotIn("error", result)
        self.assertEqual(result["status"], "approved")

        # exactly one event
        approval_events = [
            e for e in events.events
            if e.get("event_type") == "documenter.approval"
        ]
        self.assertEqual(len(approval_events), 1)


# ---------------------------------------------------------------------------
# Test case 3: Changed diff
# ---------------------------------------------------------------------------

@unittest.skipIf(
    ApprovalRegistry is None or documenter_approve is None,
    "red baseline: ApprovalRegistry/documenter_approve not yet implemented",
)
class TestChangedDiff(unittest.TestCase):
    """Case 3: delegate(op A, diff1) → approve(op B, diff2) → error VAL.001 +
    "invalidation"; state "invalidated"; second approve (even correct diff)
    → error VAL.001 "single-use"."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_changed_diff_invalidates(self):
        port = FakeDocumenterPort()
        reg = ApprovalRegistry()
        events = ListEventSink()
        operator_a = "op-alice"
        operator_b = "op-bob"
        diff1 = "original diff"
        diff2 = "changed diff"

        # delegate with diff1
        result = documenter_delegate(
            port, reg, "target", "edit", diff1, operator_a, events,
        )
        rid = result["request_id"]

        # approve with different diff → invalidation error
        result = documenter_approve(reg, rid, operator_b, diff2, events)
        self.assertIn("error", result)
        self.assertEqual(result["error"]["code"], "VAL.001")
        self.assertIn("invalidation", result["error"]["reason"])

        # registry state is "invalidated"
        rec = reg.get(rid)
        self.assertEqual(rec["state"], "invalidated")

    def test_second_approve_after_invalidation_is_single_use(self):
        port = FakeDocumenterPort()
        reg = ApprovalRegistry()
        events = ListEventSink()
        operator_a = "op-alice"
        operator_b = "op-bob"
        diff1 = "original diff"

        # delegate
        result = documenter_delegate(
            port, reg, "target", "edit", diff1, operator_a, events,
        )
        rid = result["request_id"]

        # invalidate with wrong diff
        documenter_approve(reg, rid, operator_b, "wrong", events)

        # now try with correct diff → still single-use error
        result = documenter_approve(reg, rid, operator_b, diff1, events)
        self.assertIn("error", result)
        self.assertEqual(result["error"]["code"], "VAL.001")
        self.assertIn("consumed", result["error"]["reason"].lower())


# ---------------------------------------------------------------------------
# Test case 4: Unknown request_id
# ---------------------------------------------------------------------------

@unittest.skipIf(
    ApprovalRegistry is None or documenter_approve is None,
    "red baseline: ApprovalRegistry/documenter_approve not yet implemented",
)
class TestUnknownRequestId(unittest.TestCase):
    """Case 4: approve with unknown request_id → error code VAL.003
    (reason mentions unknown request_id); no event."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_unknown_request_id_error(self):
        reg = ApprovalRegistry()
        events = ListEventSink()
        fake_rid = "00000000-0000-4000-8000-000000000000"

        result = documenter_approve(
            reg, fake_rid, "op-alice", "some diff", events,
        )
        self.assertIn("error", result)
        self.assertEqual(result["error"]["code"], "VAL.003")
        self.assertIn("unknown", result["error"]["reason"].lower())
        # no event emitted
        self.assertEqual(len(events.events), 0)


# ---------------------------------------------------------------------------
# Test case 5: Double approve (single-use)
# ---------------------------------------------------------------------------

@unittest.skipIf(
    ApprovalRegistry is None or documenter_approve is None,
    "red baseline: ApprovalRegistry/documenter_approve not yet implemented",
)
class TestDoubleApprove(unittest.TestCase):
    """Case 5: delegate(op A) → approve(op B) ok → approve(op C) → error
    VAL.001 single-use; exactly ONE documenter.approval event total."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_second_approve_is_single_use(self):
        port = FakeDocumenterPort()
        reg = ApprovalRegistry()
        events = ListEventSink()
        operator_a = "op-alice"
        operator_b = "op-bob"
        operator_c = "op-charlie"
        diff = "diff content"

        # delegate
        result = documenter_delegate(
            port, reg, "target", "edit", diff, operator_a, events,
        )
        rid = result["request_id"]

        # first approve (B) succeeds
        result1 = documenter_approve(reg, rid, operator_b, diff, events)
        self.assertNotIn("error", result1)
        self.assertEqual(result1["status"], "approved")

        # second approve (C) fails — single-use
        result2 = documenter_approve(reg, rid, operator_c, diff, events)
        self.assertIn("error", result2)
        self.assertEqual(result2["error"]["code"], "VAL.001")
        self.assertIn("consumed", result2["error"]["reason"].lower())

        # exactly one approval event
        approval_events = [
            e for e in events.events
            if e.get("event_type") == "documenter.approval"
        ]
        self.assertEqual(len(approval_events), 1)


# ---------------------------------------------------------------------------
# Test case 6: Delegate verb contract
# ---------------------------------------------------------------------------

@unittest.skipIf(
    ApprovalRegistry is None or documenter_delegate is None,
    "red baseline: ApprovalRegistry/documenter_delegate not yet implemented",
)
class TestDelegateVerbContract(unittest.TestCase):
    """Case 6: fake port returns canned preview; result carries request_id
    matching UUID4 regex + diff_preview == canned; registry.get(request_id)
    state "pending" with diff_hash == hash_diff(diff); events sink EMPTY."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_delegate_returns_uuid4_request_id(self):
        port = FakeDocumenterPort({"diff": "preview"})
        reg = ApprovalRegistry()
        events = ListEventSink()

        result = documenter_delegate(
            port, reg, "target-xyz", "edit", "diff", "op-alice", events,
        )
        self.assertRegex(result["request_id"], _REQUEST_ID_RE.pattern)

    def test_delegate_passes_correct_port_args(self):
        """Port delegate_preview receives (target_id, change_type, trust_level, diff_input)."""
        port = FakeDocumenterPort({"diff": "preview"})
        reg = ApprovalRegistry()
        events = ListEventSink()

        documenter_delegate(
            port, reg, "my-target", "update", "diff content", "op-alice", events,
        )
        self.assertEqual(port.last_call["target_id"], "my-target")
        self.assertEqual(port.last_call["change_type"], "update")
        self.assertEqual(port.last_call["trust_level"], "operator")
        self.assertEqual(port.last_call["diff_input"], "diff content")

    def test_delegate_stores_pending_in_registry(self):
        port = FakeDocumenterPort()
        reg = ApprovalRegistry()
        events = ListEventSink()
        diff = "diff content"

        result = documenter_delegate(
            port, reg, "target", "edit", diff, "op-alice", events,
        )
        rid = result["request_id"]

        rec = reg.get(rid)
        self.assertEqual(rec["state"], "pending")
        self.assertEqual(rec["proposer_operator_id"], "op-alice")
        self.assertEqual(rec["diff_hash"], hash_diff(diff))

    def test_delegate_events_sink_empty(self):
        """Delegate verb emits NO surface events (Tier 0-1 pass-through)."""
        port = FakeDocumenterPort()
        reg = ApprovalRegistry()
        events = ListEventSink()

        documenter_delegate(
            port, reg, "target", "edit", "diff", "op-alice", events,
        )
        self.assertEqual(len(events.events), 0)


# ---------------------------------------------------------------------------
# Test case 7: hash_diff determinism
# ---------------------------------------------------------------------------

@unittest.skipIf(hash_diff is None,
                 "red baseline: hash_diff not yet implemented")
class TestHashDiff(unittest.TestCase):
    """Case 7: hash_diff determinism + 'sha256:' prefix; same input same hash,
    different input differs."""

    def test_sha256_prefix(self):
        result = hash_diff("x")
        self.assertTrue(result.startswith("sha256:"))

    def test_same_input_same_hash(self):
        h1 = hash_diff("same input")
        h2 = hash_diff("same input")
        self.assertEqual(h1, h2)

    def test_different_input_different_hash(self):
        h1 = hash_diff("input a")
        h2 = hash_diff("input b")
        self.assertNotEqual(h1, h2)

    def test_expected_value(self):
        """hash_diff("x") must equal 'sha256:' + actual SHA-256 hexdigest of b'x'."""
        expected = "sha256:" + hashlib.sha256(b"x").hexdigest()
        self.assertEqual(hash_diff("x"), expected)


# ---------------------------------------------------------------------------
# Test case 8: ApprovalRegistry.get defensive copy
# ---------------------------------------------------------------------------

@unittest.skipIf(ApprovalRegistry is None,
                 "red baseline: ApprovalRegistry not yet implemented")
class TestRegistryGetDefensiveCopy(unittest.TestCase):
    """Case 8: mutating returned record must not change registry state."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_mutation_does_not_change_registry(self):
        reg = ApprovalRegistry()
        rid = "00000000-0000-4000-8000-000000000001"
        reg.register_request(rid, "sha256:abc123", "op-alice")

        rec = reg.get(rid)
        rec["state"] = "hacked"
        rec["proposer_operator_id"] = "op-hacker"
        rec["diff_hash"] = "hacked-hash"

        still = reg.get(rid)
        self.assertEqual(still["state"], "pending")
        self.assertEqual(still["proposer_operator_id"], "op-alice")
        self.assertEqual(still["diff_hash"], "sha256:abc123")


# ---------------------------------------------------------------------------
# Test case 9: Transport — handle_request routing
# ---------------------------------------------------------------------------

@unittest.skipIf(
    handle_request is None or documenter_delegate is None or documenter_approve is None,
    "red baseline: handle_request/verbs not yet implemented",
)
class TestTransportRouting(unittest.TestCase):
    """Case 9: handle_request routes documenter.delegate and documenter.approve
    (auth-gated). Good token → routed. No auth → AUTH.002.
    4 deferred tools still return CONFIG.001."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_request(self, method, params=None, rid=1):
        req = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            req["params"] = params
        return req

    def _make_auth_params(self, token):
        return {"auth": {"token": token}}

    def test_delegate_routed_with_good_token(self):
        deps = _build_handle_request_deps(self.tmpdir)
        token = _make_token(secret=deps["secret"], sub="op-alice")
        diff = "diff content"
        req = self._make_request(
            "documenter.delegate",
            params={
                **self._make_auth_params(token),
                "target_id": "target-doc-1",
                "change_type": "edit",
                "diff": diff,
            },
        )
        result = handle_request(req, deps)
        self.assertIn("result", result)
        self.assertIn("request_id", result["result"])
        self.assertEqual(result["result"]["status"], "approval_required")

    def test_approve_routed_with_good_token(self):
        deps = _build_handle_request_deps(self.tmpdir)
        token_alice = _make_token(secret=deps["secret"], sub="op-alice")
        token_bob = _make_token(secret=deps["secret"], sub="op-bob")
        diff = "diff content"

        # First delegate
        req_delegate = self._make_request(
            "documenter.delegate",
            params={
                **self._make_auth_params(token_alice),
                "target_id": "target-doc-1",
                "change_type": "edit",
                "diff": diff,
            },
        )
        result = handle_request(req_delegate, deps)
        self.assertIn("result", result)
        rid = result["result"]["request_id"]

        # Then approve (different operator)
        req_approve = self._make_request(
            "documenter.approve",
            params={
                **self._make_auth_params(token_bob),
                "request_id": rid,
                "diff": diff,
            },
        )
        result = handle_request(req_approve, deps)
        self.assertIn("result", result)
        self.assertEqual(result["result"]["status"], "approved")

    def test_no_auth_returns_auth_error(self):
        deps = _build_handle_request_deps(self.tmpdir)
        req = self._make_request(
            "documenter.delegate",
            params={"target_id": "x", "change_type": "edit", "diff": "d"},
        )
        result = handle_request(req, deps)
        self.assertIn("error", result)
        self.assertNotIn("result", result)
        self.assertTrue(
            result["error"]["data"]["code"].startswith("AUTH."),
            f"Expected AUTH.* code, got {result['error']['data']['code']!r}",
        )

    def test_no_auth_verb_not_ran(self):
        """Auth failure: verb never runs → no registration in approval_registry."""
        deps = _build_handle_request_deps(self.tmpdir)
        reg = deps["approval_registry"]
        req = self._make_request(
            "documenter.delegate",
            params={"target_id": "x", "change_type": "edit", "diff": "d"},
        )
        handle_request(req, deps)
        # Verify the registry has no entries — the verb should never have run.
        # We check internal _requests dict (the registry keeps records keyed by request_id).
        self.assertEqual(len(getattr(reg, "_requests", {})), 0,
                         "approval_registry must not have been modified by a failed auth")

    def test_deferred_tools_still_return_config_001(self):
        """The 4 remaining deferred tools still return CONFIG.001 via deferred_response.
        (documenter.delegate and documenter.approve are now routed, but the other
        deferred tools like council.get_artifacts, council.resolve_escalation,
        council.override_precheck, and documenter.override_gate still do.)"""
        from operator_ingress.core.envelope import deferred_response
        if deferred_response is None:
            self.skipTest("deferred_response not yet implemented")
            return
        deferred_tools = [
            "council.get_artifacts",
            "council.resolve_escalation",
            "council.override_precheck",
            "documenter.override_gate",
        ]
        for tool in deferred_tools:
            env = deferred_response(tool)
            self.assertIn("code", env)
            self.assertTrue(env["code"].startswith("CONFIG."))
            self.assertEqual(env["code"], "CONFIG.001")


# ---------------------------------------------------------------------------
# Back-compat guard: existing envelope deferred tests must stay green
# ---------------------------------------------------------------------------

@unittest.skipIf(error_envelope is None,
                 "red baseline: envelope not yet implemented")
class TestEnvelopeBackCompat(unittest.TestCase):
    """error_envelope with reason key: tests the reason-substring assertion pattern."""

    def test_error_envelope_preserves_reason_key(self):
        env = error_envelope("VAL.001", reason="some explanation")
        self.assertIn("reason", env)
        self.assertEqual(env["reason"], "some explanation")

    def test_error_envelope_does_not_override_code(self):
        env = error_envelope("VAL.001", code="OVERRIDE")
        self.assertEqual(env["code"], "VAL.001")

    def test_error_envelope_does_not_override_message(self):
        env = error_envelope("VAL.001", message="OVERRIDE")
        self.assertNotEqual(env["message"], "OVERRIDE")

    def test_error_envelope_does_not_override_action(self):
        env = error_envelope("VAL.001", action="OVERRIDE")
        self.assertNotEqual(env["action"], "OVERRIDE")

    def test_reason_not_dropped(self):
        """The cycle-3 lesson: reason travels in 'reason' key, not 'message'."""
        env = error_envelope("VAL.001", reason="differ")
        self.assertEqual(env["reason"], "differ")
        self.assertNotEqual(env["message"], "differ")


# ---------------------------------------------------------------------------
# Architecture guard: approval.py must not import layer-1 or adapters
# ---------------------------------------------------------------------------

@unittest.skipIf(not os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "..", "operator_ingress", "core", "approval.py")),
                 "red baseline: approval.py not yet created")
class TestArchitectureGuard(unittest.TestCase):
    """approval.py must not import layer-1 or operator_ingress.adapters."""

    def test_no_adapter_imports_in_approval(self):
        import ast
        approval_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "operator_ingress", "core", "approval.py",
        )
        if not os.path.isfile(approval_path):
            self.skipTest("approval.py does not exist (red baseline)")
        with open(approval_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(
                        "adapters", alias.name,
                        f"approval.py must not import {alias.name}",
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self.assertNotIn(
                        "adapters", node.module,
                        f"approval.py must not import from {node.module}",
                    )


if __name__ == "__main__":
    unittest.main()
