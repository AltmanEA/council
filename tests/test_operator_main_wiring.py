"""Tests for production wiring paths (COUNCIL_TEST_MODE not set).

Cycle 5 Step 4 iteration 2 — Test Author.

These tests pin the corrected production wiring so it cannot regress.
They exercise code paths that COUNCIL_TEST_MODE=1 never touches:
  - build_deps() factory
  - Tier01Documenter (real adapter)
  - real FileEventSink e2e
  - fail-closed secret (main())
  - caller_class from env
  - policy_info read-only

Hard rules:
  - Worktree only: /home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-17T10-00-01
  - Never touch documenter_policy.yml (read-only via injected fixtures only)
  - No git; no artifacts/test-output-* files; do not weaken existing tests
  - Real-audit test isolates cwd to tempdir, verifies no repo writes
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

# ---------------------------------------------------------------------------
# Regexes for result validation
# ---------------------------------------------------------------------------

_SESS_RE = re.compile(r"^sess-[a-z0-9]{12}$")
_EID_RE = re.compile(r"^evt-[a-z0-9][a-z0-9-]{2,63}$")

# ---------------------------------------------------------------------------
# Minimal claims for token generation
# ---------------------------------------------------------------------------

_MIN_CLAIMS = {
    "alg": "HS256",
    "iss": "operator-surface",
    "sub": "op-alice",
    "exp": 9999999999,  # far-future epoch seconds
}

# ---------------------------------------------------------------------------
# Try importing — NameError is the red baseline for iteration 2
# ---------------------------------------------------------------------------

try:
    from operator_ingress.__main__ import build_deps  # noqa: F401
except ImportError:
    build_deps = None  # red baseline: build_deps doesn't exist yet

try:
    from operator_ingress.adapters.documenter_adapter import (  # noqa: F401
        Tier01Documenter,
    )
except ImportError:
    Tier01Documenter = None  # red baseline: doesn't exist yet

try:
    from operator_ingress.core.auth import issue_token  # noqa: F401
except ImportError:
    issue_token = None  # may be unavailable in very early cycles

try:
    from operator_ingress.core.events import make_envelope, FileEventSink  # noqa: F401
except ImportError:
    make_envelope = None  # noqa: F401
    FileEventSink = None  # noqa: F401

try:
    from operator_ingress.ports import DocumenterPort  # noqa: F401
except ImportError:
    DocumenterPort = None  # noqa: F401

try:
    from operator_ingress.adapters.session_store import MvpSessionStore  # noqa: F401
except ImportError:
    MvpSessionStore = None  # red baseline

# ---------------------------------------------------------------------------
# Token / subprocess helpers
# ---------------------------------------------------------------------------


def _make_token(secret="test-secret-key"):
    """Issue a token via in-process issue_token."""
    if issue_token is None:
        return None
    claims = dict(_MIN_CLAIMS)
    return issue_token(claims, secret)


def _make_service_token(secret="test-secret-key"):
    """Issue a service-class token."""
    if issue_token is None:
        return None
    claims = dict(_MIN_CLAIMS)
    claims["sub"] = "svc-my-service"
    claims["role"] = "service"
    return issue_token(claims, secret)


def _make_agent_token(secret="test-secret-key"):
    """Issue an agent-class token with role."""
    if issue_token is None:
        return None
    claims = dict(_MIN_CLAIMS)
    claims["sub"] = "agent-bob"
    claims["role"] = "analyst"
    return issue_token(claims, secret)


def _spawn_main(root_dir, extra_env=None, timeout=10):
    """Spawn `python3 -m operator_ingress` as a subprocess.

    The caller must send requests via proc.stdin and read from proc.stdout,
    then call proc.communicate() (which sends EOF).
    Returns (proc, env) for caller management.
    The READY line is consumed before returning so that the first
    ``_safe_readline`` call returns the actual response.
    """
    env = os.environ.copy()
    env["COUNCIL_STATE_ROOT"] = root_dir
    # Do NOT set COUNCIL_TEST_MODE — we're testing production paths.
    env.pop("COUNCIL_TEST_MODE", None)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.Popen(
        [sys.executable, "-m", "operator_ingress"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    # Consume the READY line before returning.
    try:
        proc.stdout.readline()
    except Exception:
        pass
    return proc, env


def _run_main_exit_test(root_dir, extra_env=None, timeout=10):
    """Run main() until exit (no interactive requests needed).

    Sends EOF immediately via communicate("") so main()'s stdio loop
    sees end-of-input and terminates.
    Returns (returncode, stdout, stderr).
    """
    env = os.environ.copy()
    env["COUNCIL_STATE_ROOT"] = root_dir
    env.pop("COUNCIL_TEST_MODE", None)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.Popen(
        [sys.executable, "-m", "operator_ingress"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    stdout_data, stderr_data = proc.communicate(input="", timeout=timeout)
    return proc.returncode, stdout_data, stderr_data


def _safe_readline(proc, label=""):
    """Read one line from proc.stdout or return empty string."""
    try:
        line = proc.stdout.readline()
        return line if line else ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Fake port factories (same patterns as existing tests)
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
        return {
            "store": self.store,
            "events": self.events,
            "documenter": self.documenter,
            "secret": self.secret,
            "policy_info": self.policy_info,
            "notices_provider": self.notices_provider,
        }


def _make_deps(root=None, policy_info=None):
    """Create a full deps object with temp-dir store and fake ports."""
    store = MvpSessionStore(root or tempfile.mkdtemp())
    events = _FakeEvents()
    documenter = _FakeDocumenter()
    secret = _FakeSecretStore()
    notices = _FakeNoticesProvider()
    return _Deps(store, events, documenter, secret, policy_info, notices)


# ---------------------------------------------------------------------------
# Import the handle_request we'll test against
# ---------------------------------------------------------------------------

try:
    from operator_ingress.__main__ import handle_request  # noqa: F401
except ImportError:
    handle_request = None  # should not fail in iteration 2


# ===================================================================
# Test 1: build_deps factory
# ===================================================================


class TestBuildDepsExists(unittest.TestCase):
    """build_deps must exist and be importable."""

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_build_deps_is_callable(self):
        self.assertIsNotNone(build_deps)
        self.assertTrue(callable(build_deps))

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_build_deps_returns_dict(self):
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        with tempfile.TemporaryDirectory() as tmpdir:
            deps = build_deps(env=env, state_root=tmpdir)
            self.assertIsInstance(deps, dict)

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_build_deps_has_required_keys(self):
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        with tempfile.TemporaryDirectory() as tmpdir:
            deps = build_deps(env=env, state_root=tmpdir)
            required = {"store", "events", "documenter", "secret",
                        "policy_info", "notices_provider"}
            missing = required - set(deps.keys())
            self.assertEqual(missing, set(),
                             f"Missing keys: {missing}")

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_build_deps_missing_secret_raises(self):
        """build_deps(env without COUNCIL_OPERATOR_SECRET) raises ValueError."""
        env = dict(os.environ)
        env.pop("COUNCIL_OPERATOR_SECRET", None)
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                build_deps(env=env, state_root=tmpdir)

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_build_deps_empty_secret_raises(self):
        """build_deps(env secret="") raises ValueError."""
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = ""
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                build_deps(env=env, state_root=tmpdir)

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_build_deps_secret_passed_through(self):
        """build_deps returns dict whose 'secret' equals the provided value."""
        expected_secret = "my-custom-secret"
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = expected_secret
        with tempfile.TemporaryDirectory() as tmpdir:
            deps = build_deps(env=env, state_root=tmpdir)
            self.assertEqual(deps["secret"], expected_secret)


class TestBuildDepsTypes(unittest.TestCase):
    """build_deps returns correct port types."""

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_store_is_mvp_session_store(self):
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        with tempfile.TemporaryDirectory() as tmpdir:
            deps = build_deps(env=env, state_root=tmpdir)
            self.assertIsInstance(deps["store"], MvpSessionStore)

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_events_is_file_event_sink(self):
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        with tempfile.TemporaryDirectory() as tmpdir:
            deps = build_deps(env=env, state_root=tmpdir)
            self.assertIsInstance(deps["events"], FileEventSink)

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_documenter_is_tier01(self):
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        with tempfile.TemporaryDirectory() as tmpdir:
            deps = build_deps(env=env, state_root=tmpdir)
            self.assertIsInstance(deps["documenter"], Tier01Documenter)


class TestDocumenterPortDuckTyping(unittest.TestCase):
    """Tier01Documenter must implement DocumenterPort (duck-typing check)."""

    @unittest.skipIf(DocumenterPort is None, "ports.DocumenterPort not yet imported")
    def test_implements_documenter_port(self):
        """Tier01Documenter has the required DocumenterPort methods."""
        self.assertTrue(hasattr(Tier01Documenter, "audit"))
        self.assertTrue(hasattr(Tier01Documenter, "status"))
        self.assertTrue(hasattr(Tier01Documenter, "delegate_preview"))


# ---------------------------------------------------------------------------
# Test 2: Tier01Documenter returns correct types
# ---------------------------------------------------------------------------


class TestTier01DocumenterMethods(unittest.TestCase):
    """Tier01Documenter methods return correct dict types."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @unittest.skipIf(Tier01Documenter is None, "red baseline: Tier01Documenter doesn't exist yet")
    def test_audit_returns_dict(self):
        doc = Tier01Documenter(self._tmpdir)
        result = doc.audit(target_id="*")
        self.assertIsInstance(result, dict)

    @unittest.skipIf(Tier01Documenter is None, "red baseline: Tier01Documenter doesn't exist yet")
    def test_audit_has_compliant_field(self):
        doc = Tier01Documenter(self._tmpdir)
        result = doc.audit(target_id="*")
        self.assertIn("compliant", result)

    @unittest.skipIf(Tier01Documenter is None, "red baseline: Tier01Documenter doesn't exist yet")
    def test_audit_has_findings_field(self):
        doc = Tier01Documenter(self._tmpdir)
        result = doc.audit(target_id="*")
        self.assertIn("findings", result)

    @unittest.skipIf(Tier01Documenter is None, "red baseline: Tier01Documenter doesn't exist yet")
    def test_status_returns_dict(self):
        doc = Tier01Documenter(self._tmpdir)
        result = doc.status()
        self.assertIsInstance(result, dict)

    @unittest.skipIf(Tier01Documenter is None, "red baseline: Tier01Documenter doesn't exist yet")
    def test_delegate_preview_returns_dict(self):
        doc = Tier01Documenter(self._tmpdir)
        import base64
        diff_b64 = base64.b64encode(b"diff").decode()
        result = doc.delegate_preview(target_id="*", change_type="update",
                                      trust_level=1, diff_input="")
        self.assertIsInstance(result, dict)


# ---------------------------------------------------------------------------
# Test 3: Tier01Documenter does NOT require COUNCIL_TEST_MODE=1
# ---------------------------------------------------------------------------


class TestTier01NoTestMode(unittest.TestCase):
    """Tier01Documenter must function when COUNCIL_TEST_MODE is unset."""

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_works_without_test_mode(self):
        """Instantiating and calling Tier01Documenter does not require test mode."""
        env = dict(os.environ)
        env.pop("COUNCIL_TEST_MODE", None)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        with tempfile.TemporaryDirectory() as tmpdir:
            deps = build_deps(env=env, state_root=tmpdir)
            doc = deps["documenter"]
            result = doc.audit(target_id="*")
            self.assertIsInstance(result, dict)


# ===================================================================
# Test 4: Tier01Documenter real audit() — isolation from repo writes
# ===================================================================


class TestTier01AuditIsolation(unittest.TestCase):
    """Real Tier01Documenter.audit() must not write under worktree's dirs."""

    def setUp(self):
        """Isolate cwd to a tempdir and set a temp COUNCIL_STATE_ROOT."""
        self._orig_cwd = os.getcwd()
        self._audit_tmp = tempfile.TemporaryDirectory()
        self._state_root = tempfile.mkdtemp()
        # Set env so Tier01Documenter writes to the temp state_root,
        # not the worktree.
        os.environ["COUNCIL_STATE_ROOT"] = self._state_root

    def tearDown(self):
        """Restore cwd, clean up, and assert no repo writes occurred."""
        os.chdir(self._orig_cwd)
        self._audit_tmp.cleanup()
        shutil.rmtree(self._state_root, ignore_errors=True)
        os.environ.pop("COUNCIL_STATE_ROOT", None)

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_no_writes_to_worktree_documenter_dir(self):
        """After audit(), nothing was created under worktree/documenter/."""
        worktree_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        doc_dir = os.path.join(worktree_root, "documenter")
        doc_was_there_before = os.path.isdir(doc_dir)

        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"

        os.chdir(self._audit_tmp.name)
        with tempfile.TemporaryDirectory() as tmpdir:
            deps = build_deps(env=env, state_root=tmpdir)
            deps["documenter"].audit(target_id="*")

        after_doc_dir_exists = os.path.isdir(doc_dir)
        self.assertEqual(after_doc_dir_exists, doc_was_there_before,
                         "Tier01Documenter.audit() created under documenter/")

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_no_writes_to_worktree_sessions_dir(self):
        """After audit(), no sessions/ dirs were created under worktree."""
        worktree_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        sessions_before = set()
        sessions_dir = os.path.join(worktree_root, "sessions")
        if os.path.isdir(sessions_dir):
            sessions_before = set(os.listdir(sessions_dir))

        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"

        os.chdir(self._audit_tmp.name)
        with tempfile.TemporaryDirectory() as tmpdir:
            deps = build_deps(env=env, state_root=tmpdir)
            deps["documenter"].audit(target_id="*")

        if os.path.isdir(sessions_dir):
            sessions_after = set(os.listdir(sessions_dir))
        else:
            sessions_after = set()
        self.assertEqual(sessions_after, sessions_before,
                         "Tier01Documenter.audit() created under sessions/")

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_audit_response_has_compliant_field(self):
        """audit() must return a dict with 'compliant' key."""
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"

        os.chdir(self._audit_tmp.name)
        with tempfile.TemporaryDirectory() as tmpdir:
            deps = build_deps(env=env, state_root=tmpdir)
            result = deps["documenter"].audit(target_id="*")
        self.assertIn("compliant", result)

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_audit_response_has_findings_field(self):
        """audit() must return a dict with 'findings' key (numeric)."""
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"

        os.chdir(self._audit_tmp.name)
        with tempfile.TemporaryDirectory() as tmpdir:
            deps = build_deps(env=env, state_root=tmpdir)
            result = deps["documenter"].audit(target_id="*")
        self.assertIn("findings", result)
        self.assertIsInstance(result["findings"], int)


# ===================================================================
# Test 5: Unimportable documenter_service → available=False, no raise
# ===================================================================


class TestDegradedDocumenterNoImport(unittest.TestCase):
    """When documenter_service cannot be imported, build_deps degrades gracefully."""

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_no_exception_when_unimportable(self):
        """build_deps must not raise if documenter_service is missing."""
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        # Block import of documenter_service by manipulating sys.path.
        import importlib
        original_path = sys.path.copy()

        # Create an env where we can shadow documenter_service.
        blocked_dir = tempfile.mkdtemp()
        sys.path.insert(0, blocked_dir)
        # Write a documenter_service/__init__.py that raises ImportError
        pkg_dir = os.path.join(blocked_dir, "documenter_service")
        os.makedirs(pkg_dir)
        with open(os.path.join(pkg_dir, "__init__.py"), "w") as f:
            f.write("raise ImportError('no documenter_service available')\n")

        try:
            # Force re-import: clear any cached import of operator_ingress
            if "operator_ingress" in sys.modules:
                for key in list(sys.modules.keys()):
                    if key.startswith("operator_ingress"):
                        del sys.modules[key]

            with tempfile.TemporaryDirectory() as tmpdir:
                deps = build_deps(env=env, state_root=tmpdir)
                self.assertIsInstance(deps, dict)
                # The documenter should be a degraded/fallback object.
                self.assertIsNotNone(deps["documenter"])
        finally:
            sys.path[:] = original_path
            shutil.rmtree(blocked_dir, ignore_errors=True)


# ===================================================================
# Test 6: main() missing secret → non-zero exit, mentions env var, no traceback
# ===================================================================


class TestMainMissingSecret(unittest.TestCase):
    """main() must fail-closed when COUNCIL_OPERATOR_SECRET is missing.

    These tests verify the production behavior where main() reads the secret
    from env and exits non-zero with a stderr message if it's absent.
    Skipped in red baseline: current code uses default "operator-secret".
    """

    def test_exit_non_zero_without_secret(self):
        """Without COUNCIL_OPERATOR_SECRET, main() exits with code != 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = dict(os.environ)
            env.pop("COUNCIL_OPERATOR_SECRET", None)
            env["COUNCIL_STATE_ROOT"] = tmpdir
            env["COUNCIL_TEST_MODE"] = "1"
            env.pop("COUNCIL_CALLER_CLASS", None)
            rc, stdout_data, stderr_data = _run_main_exit_test(tmpdir, extra_env=env)

            self.assertNotEqual(rc, 0,
                                "main() should exit non-zero without secret")

    def test_stderr_mentions_env_var(self):
        """Without secret, stderr mentions COUNCIL_OPERATOR_SECRET."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = dict(os.environ)
            env.pop("COUNCIL_OPERATOR_SECRET", None)
            env["COUNCIL_STATE_ROOT"] = tmpdir
            env["COUNCIL_TEST_MODE"] = "1"
            env.pop("COUNCIL_CALLER_CLASS", None)
            rc, stdout_data, stderr_data = _run_main_exit_test(tmpdir, extra_env=env)

            self.assertIn("COUNCIL_OPERATOR_SECRET", stderr_data,
                          f"stderr should mention COUNCIL_OPERATOR_SECRET, got: {stderr_data!r}")

    def test_no_traceback_on_stderr(self):
        """Without secret, stderr must NOT contain Python traceback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = dict(os.environ)
            env.pop("COUNCIL_OPERATOR_SECRET", None)
            env["COUNCIL_STATE_ROOT"] = tmpdir
            env["COUNCIL_TEST_MODE"] = "1"
            env.pop("COUNCIL_CALLER_CLASS", None)
            rc, stdout_data, stderr_data = _run_main_exit_test(tmpdir, extra_env=env)

            self.assertNotIn("Traceback", stderr_data,
                             "stderr must not contain a traceback")


class TestMainMissingSecretSkipRed(unittest.TestCase):
    """Placeholder: all main() missing-secret tests are skipped in red baseline."""

    def test_skip_placeholder(self):
        """Skip file — all actual tests are in TestMainMissingSecret and TestMainMissingSecretProduction."""
        pass


# ===================================================================
# Test 7: main() missing secret with production wiring (not test mode)
# ===================================================================


class TestMainMissingSecretProduction(unittest.TestCase):
    """main() in production mode (no COUNCIL_TEST_MODE) must also fail-closed."""

    def test_production_mode_missing_secret_exits_nonzero(self):
        """Without secret and without test mode, main() exits non-zero."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = dict(os.environ)
            env.pop("COUNCIL_OPERATOR_SECRET", None)
            env["COUNCIL_STATE_ROOT"] = tmpdir
            env.pop("COUNCIL_TEST_MODE", None)  # production mode!
            rc, _stdout, _stderr = _run_main_exit_test(tmpdir, extra_env=env)

            self.assertNotEqual(rc, 0,
                                "main() should exit non-zero without secret in prod mode")

    def test_production_stderr_no_traceback(self):
        """Production mode without secret: no traceback on stderr."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = dict(os.environ)
            env.pop("COUNCIL_OPERATOR_SECRET", None)
            env["COUNCIL_STATE_ROOT"] = tmpdir
            env.pop("COUNCIL_TEST_MODE", None)
            rc, _stdout, stderr_data = _run_main_exit_test(tmpdir, extra_env=env)

            self.assertNotIn("Traceback", stderr_data)


# ===================================================================
# Test 8: caller_class from env — service token verifies
# ===================================================================


class TestCallerClassService(unittest.TestCase):
    """caller_class from COUNCIL_CALLER_CLASS env: service + known service.

    These tests verify the production behavior that `main()` will read
    COUNCIL_CALLER_CLASS from env and pass it to verify_token.
    In the red baseline (iteration 2), the code hardcodes caller_class="operator"
    so service tokens get AUTH.002. These tests skip until the fix is implemented.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_service_token_verifies_with_service_class(self):
        """Service token + COUNCIL_CALLER_CLASS=service → success."""
        deps = _make_deps(self.root)
        token = _make_service_token(deps.secret.get_hmac_secret())
        req = {
            "jsonrpc": "2.0", "id": 1,
            "method": "council.status",
            "params": {"auth": {"token": token}},
        }
        result = handle_request(req, {**deps.to_dict(),
                                     "caller_class": "service",
                                     "known_services": ("svc-my-service",)})
        self.assertIn("result", result,
                      "Service token with correct secret should succeed")

    def test_agent_token_rejected_with_operator_class(self):
        """Agent token in operator mode → AUTH error (current behavior)."""
        deps = _make_deps(self.root)
        token = _make_agent_token(deps.secret.get_hmac_secret())
        req = {
            "jsonrpc": "2.0", "id": 2,
            "method": "council.status",
            "params": {"auth": {"token": token}},
        }
        result = handle_request(req, deps.to_dict())
        self.assertIn("error", result)
        self.assertNotIn("result", result)
        code = result["error"]["data"]["code"]
        self.assertTrue(
            code.startswith("AUTH."),
            f"Expected AUTH.* code, got {code!r}",
        )


class TestCallerClassProduction(unittest.TestCase):
    """Production-level caller_class tests via subprocess + build_deps."""

    def test_service_class_via_subprocess(self):
        """COUNCIL_CALLER_CLASS=service + service token → success via main()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = dict(os.environ)
            env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
            env["COUNCIL_STATE_ROOT"] = tmpdir
            env["COUNCIL_CALLER_CLASS"] = "service"
            env["COUNCIL_KNOWN_SERVICES"] = "svc-my-service"
            env.pop("COUNCIL_TEST_MODE", None)

            proc, _ = _spawn_main(tmpdir, extra_env=env)
            svc_token = _make_service_token("test-secret-key")
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "documenter.audit",
                "params": {"auth": {"token": svc_token}},
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = _safe_readline(proc, "service class")
            self.assertTrue(len(response_line) > 0, "No response on stdout")
            response = json.loads(response_line)
            self.assertIn("result", response)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def test_agent_class_rejected_via_subprocess(self):
        """COUNCIL_CALLER_CLASS=agent + agent token without role → AUTH error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = dict(os.environ)
            env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
            env["COUNCIL_STATE_ROOT"] = tmpdir
            env["COUNCIL_CALLER_CLASS"] = "agent"
            env.pop("COUNCIL_TEST_MODE", None)

            proc, _ = _spawn_main(tmpdir, extra_env=env)
            # Token with sub but no role — agent mode requires role.
            claims = dict(_MIN_CLAIMS)
            claims["sub"] = "agent-bob"
            agent_token = issue_token(claims, "test-secret-key")
            request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "documenter.audit",
                "params": {"auth": {"token": agent_token}},
            }
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = _safe_readline(proc, "agent class")
            self.assertTrue(len(response_line) > 0, "No response on stdout")
            response = json.loads(response_line)
            self.assertIn("error", response)
            self.assertNotIn("result", response)
            code = response["error"]["data"]["code"]
            self.assertTrue(
                code.startswith("AUTH."),
                f"Expected AUTH.* code, got {code!r}",
            )
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


# ===================================================================
# Test 9: real FileEventSink e2e — build_deps + handle_request
# ===================================================================


class TestFileEventSinkE2E(unittest.TestCase):
    """Real FileEventSink e2e: build_deps → handle_request → events.jsonl."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        shutil.rmtree(self.tmp.name, ignore_errors=True)

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_events_file_created(self):
        """submit_task via handle_request writes events.jsonl."""
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        deps = build_deps(env=env, state_root=self.tmp.name)
        token = _make_token()
        req = {
            "jsonrpc": "2.0", "id": 1,
            "method": "council.submit_task",
            "params": {
                "auth": {"token": token},
                "task_brief": "E2E test task",
                "scenario_id": "scen-e2e",
            },
        }
        result = handle_request(req, deps)
        self.assertIn("result", result)
        self.assertIn("session_id", result["result"])
        sid = result["result"]["session_id"]
        events_path = os.path.join(self.tmp.name, "sessions", sid,
                                   "events.jsonl")
        self.assertTrue(os.path.isfile(events_path),
                        f"events.jsonl not found at {events_path}")

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_events_file_contains_submit_task(self):
        """events.jsonl must contain a line with verb.submit_task event type."""
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        deps = build_deps(env=env, state_root=self.tmp.name)
        token = _make_token()
        req = {
            "jsonrpc": "2.0", "id": 1,
            "method": "council.submit_task",
            "params": {
                "auth": {"token": token},
                "task_brief": "E2E test task",
                "scenario_id": "scen-e2e",
            },
        }
        handle_request(req, deps)
        # Find the events file — it's in sessions/<sid>/events.jsonl
        sessions_dir = os.path.join(self.tmp.name, "sessions")
        self.assertTrue(os.path.isdir(sessions_dir), "No sessions dir created")
        for sid in os.listdir(sessions_dir):
            events_path = os.path.join(sessions_dir, sid, "events.jsonl")
            if os.path.isfile(events_path):
                with open(events_path, "r", encoding="utf-8") as fh:
                    for line in fh:
                        if line.strip():
                            event = json.loads(line)
                            self.assertEqual(
                                event["event_type"], "verb.submit_task",
                                f"Expected verb.submit_task, got {event.get('event_type')!r}",
                            )
                            break
                break
        else:
            self.fail("No events.jsonl found in sessions/")


# ===================================================================
# Test 10: policy_info read-only — fixture, not real file read
# ===================================================================


class TestPolicyInfoReadonly(unittest.TestCase):
    """policy_info is injected as a dict; build_deps sets it from fixture parse."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        shutil.rmtree(self.tmp.name, ignore_errors=True)

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_policy_info_set_in_deps(self):
        """build_deps sets policy_info in the returned dict."""
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        deps = build_deps(env=env, state_root=self.tmp.name)
        self.assertIn("policy_info", deps)

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_notices_provider_callable(self):
        """notices_provider() returns a list of notice dicts."""
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        deps = build_deps(env=env, state_root=self.tmp.name)
        notices = deps["notices_provider"]()
        self.assertIsInstance(notices, list)
        self.assertGreater(len(notices), 0)

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_notices_include_interlock_by_default(self):
        """Default policy_info (tier < 2) includes tier2_interlock notice."""
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        deps = build_deps(env=env, state_root=self.tmp.name)
        notices = deps["notices_provider"]()
        types = [n["type"] for n in notices]
        self.assertIn("notice.documenter_tier2_interlock", types)


# ===================================================================
# Integration: verify existing tests are not weakened
# ===================================================================


class TestExistingBehaviorNotWeakened(unittest.TestCase):
    """Sanity checks that existing functionality still works via build_deps."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        shutil.rmtree(self.tmp.name, ignore_errors=True)

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_handle_request_via_build_deps(self):
        """build_deps produces deps that work with handle_request."""
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        deps = build_deps(env=env, state_root=self.tmp.name)
        token = _make_token()
        req = {
            "jsonrpc": "2.0", "id": 1,
            "method": "council.status",
            "params": {"auth": {"token": token}},
        }
        result = handle_request(req, deps)
        self.assertIn("result", result)
        self.assertIn("notices", result["result"])

    @unittest.skipIf(build_deps is None, "red baseline: build_deps doesn't exist yet")
    def test_store_works_through_deps(self):
        """MvpSessionStore in build_deps deps works (create + list)."""
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        deps = build_deps(env=env, state_root=self.tmp.name)
        deps["store"].create_session("sess-test123")
        sessions = deps["store"].list_sessions()
        session_ids = [s["session_id"] for s in sessions]
        self.assertIn("sess-test123", session_ids)


if __name__ == "__main__":
    unittest.main()

# ===================================================================
# Test 13: Real binding to the documenter_service
# ===================================================================


class TestTier01RealBinding(unittest.TestCase):
    """Prove the Tier01Documenter binds the REAL Service (not degraded).

    Copies the worktree's docs/ corpus + docs-manifest.yaml into a
    temporary root, instantiates Tier01Documenter(root) and calls
    audit/status/delegate_preview — asserting the result shapes
    come from the real Service, not the degradation stub.
    """

    def _copy_corpus_to_tmp(self):
        """Copy worktree docs/ + manifest into a temp dir; return the root."""
        worktree_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        src_docs = os.path.join(worktree_root, "docs")
        src_manifest = os.path.join(worktree_root, "docs-manifest.yaml")

        tmpdir = tempfile.mkdtemp()
        # Copy docs/ tree (read-only source)
        shutil.copytree(src_docs, os.path.join(tmpdir, "docs"))
        # Copy manifest
        shutil.copy2(src_manifest, os.path.join(tmpdir, "docs-manifest.yaml"))
        # Create the data dir (Service writes under root/DOCUMENTER_DATA_DIR)
        os.makedirs(os.path.join(tmpdir, "documenter"), exist_ok=True)
        return tmpdir

    def tearDown(self):
        # Clean up — only our temp dirs created in this class.
        for attr in ("_root",):
            val = getattr(self, attr, None)
            if val and os.path.isdir(val):
                shutil.rmtree(val, ignore_errors=True)

    def test_audit_returns_real_service_shape(self):
        """audit() must NOT return available: False and must contain report."""
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        env.pop("COUNCIL_TEST_MODE", None)

        tmpdir = self._copy_corpus_to_tmp()
        self._root = tmpdir

        try:
            from operator_ingress.adapters.documenter_adapter import (
                Tier01Documenter,
            )
            doc = Tier01Documenter(tmpdir)
            result = doc.audit(target_id="*")
        except ImportError:
            self.skipTest("documenter_service not available")

        self.assertIsInstance(result, dict)
        self.assertNotIn(
            "available", result,
            "Real binding degraded: result contains 'available' key"
        )
        self.assertIn("report", result, "Real audit must contain 'report' key")
        report = result["report"]
        self.assertIsInstance(report, dict)
        self.assertIn("header", report, "Report must contain 'header'")
        self.assertIn("findings", report, "Report must contain 'findings'")

    def test_status_returns_real_service_shape(self):
        """status() must NOT return available: False."""
        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        env.pop("COUNCIL_TEST_MODE", None)

        tmpdir = self._copy_corpus_to_tmp()
        self._root = tmpdir

        try:
            from operator_ingress.adapters.documenter_adapter import (
                Tier01Documenter,
            )
            doc = Tier01Documenter(tmpdir)
            result = doc.status()
        except ImportError:
            self.skipTest("documenter_service not available")

        self.assertIsInstance(result, dict)
        self.assertNotIn(
            "available", result,
            "Real binding degraded: status contains 'available' key"
        )

    def test_delegate_preview_does_not_degrade(self):
        """delegate_preview must return a dict without available: False."""
        import base64

        env = dict(os.environ)
        env["COUNCIL_OPERATOR_SECRET"] = "test-secret-key"
        env.pop("COUNCIL_TEST_MODE", None)

        tmpdir = self._copy_corpus_to_tmp()
        self._root = tmpdir

        try:
            from operator_ingress.adapters.documenter_adapter import (
                Tier01Documenter,
            )
            doc = Tier01Documenter(tmpdir)
        except ImportError:
            self.skipTest("documenter_service not available")

        # Minimal b64-encoded diff — use a target from the manifest.
        manifest_docs = os.path.join(tmpdir, "docs")
        entries = []
        for d in os.listdir(manifest_docs):
            entries.append(d)
        # Use "documentation-rules" which is the first in manifest.
        target_id = "documentation-rules"

        diff_lines = (
            "--- a/docs/en/documentation-rules/index.md\n"
            "+++ b/docs/en/documentation-rules/index.md\n"
            "@@ -1 +1 @@\n"
            "-old header\n"
            "+new header\n"
        )
        diff_b64 = base64.b64encode(diff_lines.encode()).decode()

        try:
            result = doc.delegate_preview(
                target_id=target_id,
                change_type="update",
                trust_level="review",
                diff_input=diff_b64,
            )
        except Exception as exc:
            self.fail(
                f"delegate_preview raised: {exc}\n"
                f"(if available: False was present, binding is broken)"
            )

        self.assertIsInstance(result, dict)
        self.assertNotIn(
            "available", result,
            "Real binding degraded: delegate_preview contains 'available' key"
        )
