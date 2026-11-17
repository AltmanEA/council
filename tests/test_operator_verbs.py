"""Unit tests for operator_surface.core.verbs + __main__.handle_request (Step 4).

Frozen API:
  - operator_surface.core.verbs: submit_task, status, list_sessions, documenter_audit
  - operator_surface.__main__: handle_request(request, deps)

Uses injected fake ports; all state on tempfile roots.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import unittest

# ---------------------------------------------------------------------------
# Try to import — NameError/ImportError is the red baseline
# ---------------------------------------------------------------------------

try:
    from operator_surface.core.verbs import (  # noqa: F401
        submit_task,
        status as status_verb,
        list_sessions as list_sessions_verb,
        documenter_audit,
    )
except ImportError:
    submit_task = None
    status_verb = None
    list_sessions_verb = None
    documenter_audit = None

try:
    from operator_surface.__main__ import handle_request  # noqa: F401
except ImportError:
    handle_request = None

# Also import the helpers we need from earlier steps
try:
    from operator_surface.core.auth import issue_token  # noqa: F401
except ImportError:
    issue_token = None

try:
    from operator_surface.core.envelope import deferred_response, error_envelope  # noqa: F401
except ImportError:
    deferred_response = None
    error_envelope = None

# MvpSessionStore — needed at module level by test methods (DoD f: test classes
# named TestMvp*AsStub use it directly; anti-reversed-TDD guard).
try:
    from operator_surface.adapters.session_store import MvpSessionStore  # noqa: F401
except ImportError:
    MvpSessionStore = None  # will fail with NameError in anti-reversed-TDD

# ---------------------------------------------------------------------------
# Session-ID regex for assertions
# ---------------------------------------------------------------------------

_SESS_RE = re.compile(r"^sess-[a-z0-9]{12}$")
_EID_RE = re.compile(r"^evt-[a-z0-9][a-z0-9-]{2,63}$")

#: Minimal claims that issue_token accepts.
_MIN_CLAIMS = {
    "alg": "HS256",
    "iss": "operator-surface",
    "sub": "op-alice",
    "exp": 9999999999,
}
_EID_RE = re.compile(r"^evt-[a-z0-9][a-z0-9-]{2,63}$")

# ---------------------------------------------------------------------------
# Fake port factories
# ---------------------------------------------------------------------------

class _FakeDocumenter:
    """A minimal DocumenterPort that stores last call and returns a dict."""

    def __init__(self, return_val=None):
        self.return_val = return_val or {"compliant": True, "findings": 0}
        self.last_call = None

    def audit(self, target_id="*", **kwargs):
        self.last_call = {"target_id": target_id, **kwargs}
        return self.return_val

    def status(self, target_id=None):
        self.last_call = {"target_id": target_id}
        return {"healthy": True}

    def delegate_preview(self, target_id, change_type, trust_level, diff_input):
        self.last_call = {"target_id": target_id, "change_type": change_type}
        return {"diff": "fake"}


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


#: Minimal claims that issue_token accepts.
_MIN_CLAIMS = {
    "alg": "HS256",
    "iss": "operator-surface",
    "sub": "op-alice",
    "exp": 9999999999,
}


def _make_token(secret="test-secret-key"):
    """Build a valid token via issue_token (when available)."""
    if issue_token is None:
        return None
    claims = dict(_MIN_CLAIMS)
    return issue_token(claims, secret)


class _FakeEvents:
    """Minimal EventSink that stores appended events in memory."""

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
# Build a deps object for handle_request
# ---------------------------------------------------------------------------

class _Deps:
    """Simple namespace for deps dict in handle_request(request, deps)."""

    def __init__(self, store, events, documenter, secret, policy_info=None,
                 notices_provider=None):
        self.store = store
        self.events = events
        self.documenter = documenter
        self.secret = secret
        self.policy_info = policy_info
        self.notices_provider = notices_provider or _FakeNoticesProvider()

    def to_dict(self):
        """Convert deps object to dict (handle_request may expect dict)."""
        return {
            "store": self.store,
            "events": self.events,
            "documenter": self.documenter,
            "secret": self.secret,
            "policy_info": self.policy_info,
            "notices_provider": self.notices_provider,
        }


def _make_deps(root=None, policy_info=None):
    """Create a full deps object with temp-dir store."""
    from operator_surface.adapters.session_store import MvpSessionStore
    store = MvpSessionStore(root or tempfile.mkdtemp())
    events = _FakeEvents()
    documenter = _FakeDocumenter()
    secret = _FakeSecretStore()
    notices = _FakeNoticesProvider()
    return _Deps(store, events, documenter, secret, policy_info, notices)


# ---------------------------------------------------------------------------
# submit_task tests
# ---------------------------------------------------------------------------

class TestSubmitTaskVerb(unittest.TestCase):
    """submit_task creates session + intent, returns with identity markers."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_returns_session_id(self):
        store = MvpSessionStore(self.root)
        events = _FakeEvents()
        result = submit_task(
            store, events,
            task_brief="Test task",
            scenario_id="scen-1",
            operator_id="op-alice",
        )
        self.assertIn("session_id", result)

    def test_session_id_matches_regex(self):
        store = MvpSessionStore(self.root)
        events = _FakeEvents()
        result = submit_task(
            store, events,
            task_brief="Test task",
            scenario_id="scen-1",
            operator_id="op-alice",
        )
        self.assertRegex(result["session_id"], _SESS_RE.pattern)

    def test_status_submitted(self):
        store = MvpSessionStore(self.root)
        events = _FakeEvents()
        result = submit_task(
            store, events,
            task_brief="Test task",
            scenario_id="scen-1",
            operator_id="op-alice",
        )
        self.assertEqual(result["status"], "submitted")

    def test_operator_id_in_result(self):
        store = MvpSessionStore(self.root)
        events = _FakeEvents()
        result = submit_task(
            store, events,
            task_brief="Test task",
            scenario_id="scen-1",
            operator_id="op-alice",
        )
        self.assertEqual(result["operator_id"], "op-alice")

    def test_session_dir_created(self):
        store = MvpSessionStore(self.root)
        events = _FakeEvents()
        result = submit_task(
            store, events,
            task_brief="Test task",
            scenario_id="scen-1",
            operator_id="op-alice",
        )
        sid = result["session_id"]
        session_dir = os.path.join(self.root, "sessions", sid)
        self.assertTrue(os.path.isdir(session_dir))

    def test_session_jsonl_written(self):
        store = MvpSessionStore(self.root)
        events = _FakeEvents()
        result = submit_task(
            store, events,
            task_brief="Test task",
            scenario_id="scen-1",
            operator_id="op-alice",
        )
        sid = result["session_id"]
        path = os.path.join(self.root, "sessions", sid, "session.jsonl")
        self.assertTrue(os.path.isfile(path))

    def test_intent_jsonl_written_with_verb(self):
        store = MvpSessionStore(self.root)
        events = _FakeEvents()
        result = submit_task(
            store, events,
            task_brief="Test task",
            scenario_id="scen-1",
            operator_id="op-alice",
        )
        sid = result["session_id"]
        path = os.path.join(self.root, "sessions", sid, "intent.jsonl")
        self.assertTrue(os.path.isfile(path))
        with open(path, "r", encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh if ln.strip()]
        self.assertGreater(len(lines), 0)
        intent = json.loads(lines[0])
        self.assertEqual(intent["verb"], "council.submit_task")

    def test_intent_jsonl_has_operator_id(self):
        store = MvpSessionStore(self.root)
        events = _FakeEvents()
        result = submit_task(
            store, events,
            task_brief="Test task",
            scenario_id="scen-1",
            operator_id="op-bob",
        )
        sid = result["session_id"]
        path = os.path.join(self.root, "sessions", sid, "intent.jsonl")
        with open(path, "r", encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh if ln.strip()]
        intent = json.loads(lines[0])
        self.assertEqual(intent["operator_id"], "op-bob")

    def test_emitted_at_in_session_record(self):
        store = MvpSessionStore(self.root)
        events = _FakeEvents()
        result = submit_task(
            store, events,
            task_brief="Test task",
            scenario_id="scen-1",
            operator_id="op-alice",
        )
        sid = result["session_id"]
        path = os.path.join(self.root, "sessions", sid, "session.jsonl")
        with open(path, "r", encoding="utf-8") as fh:
            line = fh.readline().strip()
        rec = json.loads(line)
        self.assertIn("emitted_at", rec)
        self.assertTrue(rec["emitted_at"].endswith("Z"))

    def test_custom_precheck_gate_called(self):
        store = MvpSessionStore(self.root)
        events = _FakeEvents()
        gate_called = [False]
        def fake_gate(*args, **kw):
            gate_called[0] = True
            return {"verdict": "pass", "reason": "fake"}
        result = submit_task(
            store, events,
            task_brief="Test task",
            scenario_id="scen-1",
            operator_id="op-alice",
            precheck_gate=fake_gate,
        )
        self.assertTrue(gate_called[0])
        self.assertEqual(result["status"], "submitted")


class TestStatusVerb(unittest.TestCase):
    """status(store, notices_provider) returns notices + identity markers."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_returns_notices_list(self):
        store = MvpSessionStore(self.root)
        result = status_verb(
            store, notices_provider=_FakeNoticesProvider(),
        )
        self.assertIn("notices", result)
        self.assertIsInstance(result["notices"], list)

    def test_operator_id_in_result(self):
        store = MvpSessionStore(self.root)
        result = status_verb(
            store, notices_provider=_FakeNoticesProvider(),
            operator_id="op-alice",
        )
        self.assertEqual(result["operator_id"], "op-alice")

    def test_session_id_none(self):
        store = MvpSessionStore(self.root)
        result = status_verb(
            store, notices_provider=_FakeNoticesProvider(),
        )
        self.assertIsNone(result["session_id"])

    def test_notices_layer1_stub_active(self):
        from operator_surface.core.notices import default_notices
        store = MvpSessionStore(self.root)
        notices = _FakeNoticesProvider(notices=default_notices(layer1_stub=True))
        result = status_verb(
            store, notices_provider=notices,
        )
        types = [n["type"] for n in result["notices"]]
        self.assertIn("notice.layer1_stub_active", types)


class TestListSessionsVerb(unittest.TestCase):
    """list_sessions(store, ...) returns list from store, never writes."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_returns_list(self):
        store = MvpSessionStore(self.root)
        result = list_sessions_verb(store)
        self.assertIsInstance(result, dict)
        self.assertIn("sessions", result)

    def test_operator_id_in_result(self):
        store = MvpSessionStore(self.root)
        result = list_sessions_verb(
            store, operator_id="op-alice",
        )
        self.assertEqual(result["operator_id"], "op-alice")

    def test_session_id_none(self):
        store = MvpSessionStore(self.root)
        result = list_sessions_verb(store)
        self.assertIsNone(result["session_id"])

    def test_never_writes(self):
        store = MvpSessionStore(self.root)
        store.create_session("sess-aaa")
        before = set(os.listdir(os.path.join(self.root, "sessions")))
        list_sessions_verb(store)
        after = set(os.listdir(os.path.join(self.root, "sessions")))
        self.assertEqual(before, after)


class TestDocumenterAuditVerb(unittest.TestCase):
    """documenter_audit(documenter_port, target_id) → verbatim result."""

    def test_returns_documenter_result(self):
        doc = _FakeDocumenter({"compliant": True, "findings": 2})
        result = documenter_audit(doc, target_id="test-target")
        self.assertEqual(result, {"compliant": True, "findings": 2})

    def test_passes_target_id(self):
        doc = _FakeDocumenter()
        documenter_audit(doc, target_id="audit-me")
        self.assertEqual(doc.last_call["target_id"], "audit-me")


class TestHandleRequestDispatcher(unittest.TestCase):
    """handle_request(request, deps) — in-process dispatcher."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _build_request(self, method, params=None, rid=1):
        req = {
            "jsonrpc": "2.0",
            "id": rid,
            "method": method,
        }
        if params is not None:
            req["params"] = params
        return req

    def _build_auth_params(self, token):
        return {"auth": {"token": token}}

    def test_success_council_status(self):
        deps = _make_deps(self.root)
        token = _make_token(deps.secret)
        req = self._build_request("council.status",
                                  params=self._build_auth_params(token))
        result = handle_request(req, deps.to_dict())
        self.assertIn("result", result)
        self.assertIn("notices", result["result"])

    def test_success_council_submit_task(self):
        deps = _make_deps(self.root)
        token = _make_token(deps.secret)
        req = self._build_request(
            "council.submit_task",
            params={**self._build_auth_params(token),
                    "task_brief": "Test",
                    "scenario_id": "scen-1"},
        )
        result = handle_request(req, deps.to_dict())
        self.assertIn("result", result)
        self.assertEqual(result["result"]["status"], "submitted")
        self.assertRegex(result["result"]["session_id"], _SESS_RE.pattern)

    def test_success_council_list_sessions(self):
        deps = _make_deps(self.root)
        token = _make_token(deps.secret)
        req = self._build_request(
            "council.list_sessions",
            params=self._build_auth_params(token),
        )
        result = handle_request(req, deps.to_dict())
        self.assertIn("result", result)

    def test_success_documenter_audit(self):
        deps = _make_deps(self.root)
        token = _make_token(deps.secret)
        req = self._build_request(
            "documenter.audit",
            params={**self._build_auth_params(token),
                    "target_id": "*"},
        )
        result = handle_request(req, deps.to_dict())
        self.assertIn("result", result)

    def test_missing_params_rejected(self):
        deps = _make_deps(self.root)
        req = {"jsonrpc": "2.0", "id": 1, "method": "council.status"}
        result = handle_request(req, deps.to_dict())
        self.assertIn("error", result)
        self.assertNotIn("result", result)

    def test_missing_params_auth_rejected(self):
        deps = _make_deps(self.root)
        req = self._build_request("council.status", params={})
        result = handle_request(req, deps.to_dict())
        self.assertIn("error", result)
        self.assertNotIn("result", result)

    def test_missing_token_rejected(self):
        deps = _make_deps(self.root)
        req = self._build_request("council.status",
                                  params={"auth": {}})
        result = handle_request(req, deps.to_dict())
        self.assertIn("error", result)
        self.assertNotIn("result", result)

    def test_auth_error_propagates(self):
        deps = _make_deps(self.root)
        req = self._build_request("council.status",
                                  params=self._build_auth_params("bad-token"))
        result = handle_request(req, deps.to_dict())
        self.assertIn("error", result)
        self.assertNotIn("result", result)
        self.assertTrue(
            result["error"]["data"]["code"].startswith("AUTH."),
            f"Expected AUTH.* code, got {result['error']['data']['code']!r}",
        )

    def test_unknown_method_config_002(self):
        deps = _make_deps(self.root)
        token = _make_token(deps.secret)
        req = self._build_request(
            "council.nonexistent_method",
            params=self._build_auth_params(token),
        )
        result = handle_request(req, deps.to_dict())
        self.assertIn("error", result)
        self.assertEqual(result["error"]["data"]["code"], "CONFIG.002")

    def test_deferred_tool_response(self):
        deps = _make_deps(self.root)
        token = _make_token(deps.secret)
        req = self._build_request(
            "council.get_artifacts",
            params=self._build_auth_params(token),
        )
        result = handle_request(req, deps.to_dict())
        self.assertIn("error", result)
        code = result["error"]["data"]["code"]
        self.assertTrue(
            code.startswith("CONFIG.") or code.startswith("DEFERRED."),
            f"Deferred tool should not produce regular result: {code}",
        )

    def test_no_secrets_on_result(self):
        deps = _make_deps(self.root)
        secret_val = deps.secret.get_hmac_secret()
        token = _make_token(deps.secret)
        req = self._build_request("council.status",
                                  params=self._build_auth_params(token))
        result = handle_request(req, deps.to_dict())
        result_str = json.dumps(result)
        self.assertNotIn(secret_val, result_str)

    def test_no_traceback_on_result(self):
        deps = _make_deps(self.root)
        req = self._build_request("council.status", params={})
        result = handle_request(req, deps.to_dict())
        result_str = json.dumps(result)
        self.assertNotIn("Traceback", result_str)


class TestHandleRequestAuthFailureNoSession(unittest.TestCase):
    """Auth failure: no session dir created under temp root."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _build_request(self, method, params=None, rid=1):
        req = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params:
            req["params"] = params
        return req

    def test_bad_token_no_session_dir(self):
        from operator_surface.adapters.session_store import MvpSessionStore
        store = MvpSessionStore(self.root)
        deps = _Deps(store, _FakeEvents(), _FakeDocumenter(),
                     _FakeSecretStore(), _FakeNoticesProvider())
        req = self._build_request("council.submit_task", params={
            "auth": {"token": "completely-wrong-token"}})
        result = handle_request(req, deps.to_dict())
        self.assertIn("error", result)
        self.assertNotIn("result", result)
        # No sessions created under root
        sessions_dir = os.path.join(self.root, "sessions")
        if os.path.isdir(sessions_dir):
            self.assertEqual(len(os.listdir(sessions_dir)), 0)

    def test_no_params_auth_no_session_dir(self):
        from operator_surface.adapters.session_store import MvpSessionStore
        store = MvpSessionStore(self.root)
        deps = _Deps(store, _FakeEvents(), _FakeDocumenter(),
                     _FakeSecretStore(), _FakeNoticesProvider())
        req = self._build_request("council.submit_task", params={})
        result = handle_request(req, deps.to_dict())
        self.assertIn("error", result)
        self.assertNotIn("result", result)
        sessions_dir = os.path.join(self.root, "sessions")
        if os.path.isdir(sessions_dir):
            self.assertEqual(len(os.listdir(sessions_dir)), 0)


class TestHandleRequestIdentityMarkers(unittest.TestCase):
    """Successful verb results carry operator_id and session_id markers."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _build_auth_params(self, token):
        return {"auth": {"token": token}}

    def test_submit_task_has_operator_id(self):
        deps = _make_deps(self.root)
        token = _make_token(deps.secret)
        req = {
            "jsonrpc": "2.0", "id": 1,
            "method": "council.submit_task",
            "params": {**self._build_auth_params(token),
                       "task_brief": "Test", "scenario_id": "scen-1"},
        }
        result = handle_request(req, deps.to_dict())
        self.assertEqual(result["result"]["operator_id"], "op-alice")

    def test_status_has_operator_id(self):
        deps = _make_deps(self.root)
        token = _make_token(deps.secret)
        req = {
            "jsonrpc": "2.0", "id": 1,
            "method": "council.status",
            "params": self._build_auth_params(token),
        }
        result = handle_request(req, deps.to_dict())
        self.assertEqual(result["result"]["operator_id"], "op-alice")

    def test_list_sessions_has_operator_id(self):
        deps = _make_deps(self.root)
        token = _make_token(deps.secret)
        req = {
            "jsonrpc": "2.0", "id": 1,
            "method": "council.list_sessions",
            "params": self._build_auth_params(token),
        }
        result = handle_request(req, deps.to_dict())
        self.assertEqual(result["result"]["operator_id"], "op-alice")


class TestHandleRequestEventEmission(unittest.TestCase):
    """submit_task emits events via the events port."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_event_emitted_on_submit_task(self):
        deps = _make_deps(self.root)
        token = _make_token(deps.secret)
        req = {
            "jsonrpc": "2.0", "id": 1,
            "method": "council.submit_task",
            "params": {**{"auth": {"token": token}},
                       "task_brief": "Test", "scenario_id": "scen-1"},
        }
        handle_request(req, deps.to_dict())
        self.assertGreater(len(deps.events.events), 0)

    def test_event_has_schema_version(self):
        deps = _make_deps(self.root)
        token = _make_token(deps.secret)
        req = {
            "jsonrpc": "2.0", "id": 1,
            "method": "council.submit_task",
            "params": {**{"auth": {"token": token}},
                       "task_brief": "Test", "scenario_id": "scen-1"},
        }
        handle_request(req, deps.to_dict())
        event = deps.events.events[0]
        self.assertEqual(event["schema_version"], 1)

    def test_event_has_event_id(self):
        deps = _make_deps(self.root)
        token = _make_token(deps.secret)
        req = {
            "jsonrpc": "2.0", "id": 1,
            "method": "council.submit_task",
            "params": {**{"auth": {"token": token}},
                       "task_brief": "Test", "scenario_id": "scen-1"},
        }
        handle_request(req, deps.to_dict())
        event = deps.events.events[0]
        self.assertRegex(event["event_id"], _EID_RE.pattern)


if __name__ == "__main__":
    unittest.main()
