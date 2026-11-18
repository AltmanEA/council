"""Unit tests for operator_ingress.core.auth (Step 1 — HMAC-SHA256 AuthN).

Acceptance criteria (target-task.md, plan Step 1):
  - round-trip issue→verify returns claims;
  - expired exp → AUTH.001; tampered payload / bad sig → AUTH.002;
    alg "none"/missing/unknown → AUTH.002;
  - operator sub format violations → AUTH.002;
  - agent class requires role claim (missing → AUTH.003);
    service class unknown name → AUTH.003; revoked → AUTH.004;
  - missing required claims at issue → ValueError;
    non-numeric exp at issue → ValueError;
  - canary-secret absent from str(exc)/repr(exc) on every failure path;
  - AuthError carries code/message/next_action.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import unittest

# --------------- helpers (no implementation dependency) ----------------------

_CANARY_SECRET = "CANARY_SECRET_DO_NOT_LEAK_9f8e7d6c5b4a3"

#: Minimal valid claims dict for issuer.
_VALID_CLAIMS = {
    "alg": "HS256",
    "iss": "operator-surface",
    "sub": "op-alice",
    "exp": time.time() + 3600,  # 1 hour from now
}

#: Minimal agent claims (with role).
_AGENT_CLAIMS = {
    "alg": "HS256",
    "iss": "operator-surface",
    "sub": "op-agent1",
    "exp": time.time() + 3600,
    "role": "reviewer",
}

#: Good operator sub samples.
_GOOD_OPERATOR_SUBS = ["op-alice", "op-a1-b", "op-a1-b2-c3"]

#: Bad operator sub samples (cover all failure modes).
_BAD_OPERATOR_SUBS = [
    "op-",          # no chars after op-
    "op-a",         # only 1 char after op- (need ≥ 3)
    "OP-Alice",     # uppercase
    "op-Al3ce",     # uppercase A in first char after op-
    "op--double-",  # first char after op- is '-', not [a-z0-9]
    "op-",          # empty body after op-
    "op-A",         # uppercase letter (violates [a-z0-9])
    "op_a",         # underscore not allowed
    "op!bad",       # special char not allowed
]


def _craft_token(claims: dict, secret: str) -> str:
    """Manually build a signed token (bypasses issue_token validation).

    Mirrors auth.py encoding: canonical JSON + HMAC-SHA256 signature,
    base64url-encoded. Used for alg-missing cases where issue_token
    would raise ValueError before producing a token.
    """
    payload_json = json.dumps(claims, sort_keys=True, separators=(",", ":"))
    payload_bytes = payload_json.encode("utf-8")
    sig = hmac.new(
        secret.encode("utf-8"), payload_bytes, hashlib.sha256
    ).digest()
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode(
        "ascii"
    )
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    return f"{payload_b64}.{sig_b64}"

# ---------------------------------------------------------------------------
# Import the module under test — must fail before implementation exists
# ---------------------------------------------------------------------------
try:
    from operator_ingress.core.auth import (  # noqa: F401
        HS256,
        AuthError,
        issue_token,
        verify_token,
    )
except ImportError as _import_err:
    # Module not yet implemented; tests will fail with ImportError.
    _import_err  # silence unused-variable


class TestAuthErrorAttributes(unittest.TestCase):
    """AuthError carries code/message/next_action."""

    def test_auth_error_has_code(self):
        err = AuthError("AUTH.001", "expired", "renew")
        self.assertEqual(err.code, "AUTH.001")

    def test_auth_error_has_message(self):
        err = AuthError("AUTH.001", "expired", "renew")
        self.assertEqual(err.message, "expired")

    def test_auth_error_has_next_action(self):
        err = AuthError("AUTH.001", "expired", "renew")
        self.assertEqual(err.next_action, "renew")

    def test_auth_error_inherits_exception(self):
        err = AuthError("AUTH.001", "expired", "renew")
        self.assertIsInstance(err, Exception)

    def test_auth_error_canary_not_in_str(self):
        err = AuthError("AUTH.001", "expired", "renew")
        self.assertNotIn(_CANARY_SECRET, str(err))

    def test_auth_error_canary_not_in_repr(self):
        err = AuthError("AUTH.001", "expired", "renew")
        self.assertNotIn(_CANARY_SECRET, repr(err))


class TestHmacAlgorithmConstant(unittest.TestCase):
    """HS256 constant must be "HS256"."""

    def test_hs256_value(self):
        self.assertEqual(HS256, "HS256")


class TestRoundTripIssueVerify(unittest.TestCase):
    """issue→verify round-trip returns the claims dict."""

    def test_round_trip_returns_claims(self):
        secret = "test-secret"
        token = issue_token(dict(_VALID_CLAIMS), secret)
        claims = verify_token(token, secret)
        self.assertEqual(claims, _VALID_CLAIMS)

    def test_round_trip_returns_claims_with_canary_secret(self):
        token = issue_token(dict(_VALID_CLAIMS), _CANARY_SECRET)
        claims = verify_token(token, _CANARY_SECRET)
        self.assertEqual(claims, _VALID_CLAIMS)
        self.assertNotIn(_CANARY_SECRET, str(claims))


class TestExpiredToken(unittest.TestCase):
    """Expired exp → AUTH.001."""

    def test_expired_token_raises_auth_001(self):
        secret = "test-secret"
        claims = dict(_VALID_CLAIMS)
        claims["exp"] = time.time() - 1  # 1 second ago
        token = issue_token(claims, secret)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, secret)
        self.assertEqual(ctx.exception.code, "AUTH.001")
        self.assertNotIn(_CANARY_SECRET, str(ctx.exception))

    def test_expired_token_canary_not_in_repr(self):
        secret = "test-secret"
        claims = dict(_VALID_CLAIMS)
        claims["exp"] = time.time() - 1
        token = issue_token(claims, secret)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, secret)
        self.assertNotIn(_CANARY_SECRET, repr(ctx.exception))


class TestTamperedSignature(unittest.TestCase):
    """Tampered payload bytes / bad signature → AUTH.002."""

    def test_tampered_payload_raises_auth_002(self):
        secret = "test-secret"
        token = issue_token(dict(_VALID_CLAIMS), secret)
        # Tamper with the payload (middle of the token string).
        token_list = list(token)
        mid = len(token_list) // 2
        token_list[mid] = "X" if token_list[mid] != "X" else "Y"
        tampered = "".join(token_list)
        with self.assertRaises(AuthError) as ctx:
            verify_token(tampered, secret)
        self.assertEqual(ctx.exception.code, "AUTH.002")
        self.assertNotIn(_CANARY_SECRET, str(ctx.exception))

    def test_wrong_secret_raises_auth_002(self):
        secret = "correct-secret"
        token = issue_token(dict(_VALID_CLAIMS), secret)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, "wrong-secret")
        self.assertEqual(ctx.exception.code, "AUTH.002")
        self.assertNotIn(_CANARY_SECRET, str(ctx.exception))

    def test_tampered_token_canary_not_in_repr(self):
        secret = "test-secret"
        token = issue_token(dict(_VALID_CLAIMS), secret)
        token_list = list(token)
        mid = len(token_list) // 2
        token_list[mid] = "X" if token_list[mid] != "X" else "Y"
        tampered = "".join(token_list)
        with self.assertRaises(AuthError) as ctx:
            verify_token(tampered, secret)
        self.assertNotIn(_CANARY_SECRET, repr(ctx.exception))


class TestWeakAlgorithm(unittest.TestCase):
    """alg "none"/missing/unknown → AUTH.002."""

    def test_alg_none_raises_auth_002(self):
        secret = "test-secret"
        claims = dict(_VALID_CLAIMS)
        claims["alg"] = "none"
        token = issue_token(claims, secret)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, secret)
        self.assertEqual(ctx.exception.code, "AUTH.002")
        self.assertNotIn(_CANARY_SECRET, str(ctx.exception))

    def test_alg_missing_raises_auth_002(self):
        secret = "test-secret"
        claims = dict(_VALID_CLAIMS)
        del claims["alg"]
        token = _craft_token(claims, secret)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, secret)
        self.assertEqual(ctx.exception.code, "AUTH.002")

    def test_alg_unknown_raises_auth_002(self):
        secret = "test-secret"
        claims = dict(_VALID_CLAIMS)
        claims["alg"] = "RS256"
        token = issue_token(claims, secret)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, secret)
        self.assertEqual(ctx.exception.code, "AUTH.002")

    def test_alg_none_canary_not_in_repr(self):
        claims = dict(_VALID_CLAIMS)
        claims["alg"] = "none"
        token = issue_token(claims, _CANARY_SECRET)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, _CANARY_SECRET)
        self.assertNotIn(_CANARY_SECRET, repr(ctx.exception))


class TestOperatorSubFormat(unittest.TestCase):
    """Operator sub must match ^op-[a-z0-9][a-z0-9-]{2,63}$.

    Good samples: op-alice, op-a1-b
    Bad: op-, opa, OP-Alice, op-Al3ce, op--double-
    """

    def test_good_operator_subs_pass(self):
        secret = "test-secret"
        for sub in _GOOD_OPERATOR_SUBS:
            claims = dict(_VALID_CLAIMS)
            claims["sub"] = sub
            token = issue_token(claims, secret)
            result = verify_token(token, secret, caller_class="operator")
            self.assertEqual(result["sub"], sub)

    def test_bad_operator_sub_raises_auth_002(self):
        secret = "test-secret"
        for sub in _BAD_OPERATOR_SUBS:
            claims = dict(_VALID_CLAIMS)
            claims["sub"] = sub
            token = issue_token(claims, secret)
            with self.assertRaises(AuthError) as ctx:
                verify_token(token, secret, caller_class="operator")
            self.assertEqual(ctx.exception.code, "AUTH.002")

    def test_bad_operator_sub_canary_not_in_str(self):
        secret = "test-secret"
        claims = dict(_VALID_CLAIMS)
        claims["sub"] = "OP-BadCase"
        token = issue_token(claims, _CANARY_SECRET)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, _CANARY_SECRET, caller_class="operator")
        self.assertNotIn(_CANARY_SECRET, str(ctx.exception))

    def test_bad_operator_sub_canary_not_in_repr(self):
        claims = dict(_VALID_CLAIMS)
        claims["sub"] = "OP-BadCase"
        token = issue_token(claims, _CANARY_SECRET)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, _CANARY_SECRET, caller_class="operator")
        self.assertNotIn(_CANARY_SECRET, repr(ctx.exception))


class TestAgentClassMissingRole(unittest.TestCase):
    """Agent class requires role claim; missing → AUTH.003."""

    def test_agent_without_role_raises_auth_003(self):
        secret = "test-secret"
        claims = dict(_AGENT_CLAIMS)
        claims["sub"] = "op-agent-no-role"
        del claims["role"]  # remove role
        token = issue_token(claims, secret)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, secret, caller_class="agent")
        self.assertEqual(ctx.exception.code, "AUTH.003")
        self.assertNotIn(_CANARY_SECRET, str(ctx.exception))

    def test_agent_without_role_canary_not_in_repr(self):
        claims = dict(_AGENT_CLAIMS)
        claims["sub"] = "op-agent-no-role"
        del claims["role"]
        token = issue_token(claims, _CANARY_SECRET)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, _CANARY_SECRET, caller_class="agent")
        self.assertNotIn(_CANARY_SECRET, repr(ctx.exception))

    def test_agent_with_role_passes(self):
        secret = "test-secret"
        claims = dict(_AGENT_CLAIMS)
        token = issue_token(claims, secret)
        result = verify_token(token, secret, caller_class="agent")
        self.assertEqual(result["sub"], _AGENT_CLAIMS["sub"])
        self.assertEqual(result["role"], _AGENT_CLAIMS["role"])


class TestServiceClassUnknownName(unittest.TestCase):
    """Service class: unknown service name → AUTH.003."""

    def test_unknown_service_raises_auth_003(self):
        secret = "test-secret"
        claims = dict(_VALID_CLAIMS)
        claims["sub"] = "unknown-service"
        token = issue_token(claims, secret)
        with self.assertRaises(AuthError) as ctx:
            verify_token(
                token, secret, caller_class="service",
                known_services=["known-service"],
            )
        self.assertEqual(ctx.exception.code, "AUTH.003")
        self.assertNotIn(_CANARY_SECRET, str(ctx.exception))

    def test_unknown_service_canary_not_in_repr(self):
        claims = dict(_VALID_CLAIMS)
        claims["sub"] = "unknown-service"
        token = issue_token(claims, _CANARY_SECRET)
        with self.assertRaises(AuthError) as ctx:
            verify_token(
                token, _CANARY_SECRET, caller_class="service",
                known_services=["known-service"],
            )
        self.assertNotIn(_CANARY_SECRET, repr(ctx.exception))

    def test_known_service_passes(self):
        secret = "test-secret"
        claims = dict(_VALID_CLAIMS)
        claims["sub"] = "known-service"
        token = issue_token(claims, secret)
        result = verify_token(
            token, secret, caller_class="service",
            known_services=["known-service"],
        )
        self.assertEqual(result["sub"], "known-service")


class TestRevokedCredential(unittest.TestCase):
    """Revoked credential → AUTH.004."""

    def test_revoked_token_raises_auth_004(self):
        secret = "test-secret"
        claims = dict(_VALID_CLAIMS)
        token = issue_token(claims, secret)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, secret, revoked_ids=["op-alice"])
        self.assertEqual(ctx.exception.code, "AUTH.004")
        self.assertNotIn(_CANARY_SECRET, str(ctx.exception))

    def test_revoked_token_canary_not_in_repr(self):
        claims = dict(_VALID_CLAIMS)
        token = issue_token(claims, _CANARY_SECRET)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, _CANARY_SECRET, revoked_ids=["op-alice"])
        self.assertNotIn(_CANARY_SECRET, repr(ctx.exception))

    def test_non_revoked_passes(self):
        secret = "test-secret"
        token = issue_token(dict(_VALID_CLAIMS), secret)
        result = verify_token(token, secret, revoked_ids=["op-other"])
        self.assertEqual(result["sub"], "op-alice")


class TestIssueMissingClaims(unittest.TestCase):
    """Missing required claims at issue → ValueError."""

    def test_missing_alg_raises_value_error(self):
        claims = dict(_VALID_CLAIMS)
        del claims["alg"]
        with self.assertRaises(ValueError):
            issue_token(claims, "test-secret")

    def test_missing_iss_raises_value_error(self):
        claims = dict(_VALID_CLAIMS)
        del claims["iss"]
        with self.assertRaises(ValueError):
            issue_token(claims, "test-secret")

    def test_missing_sub_raises_value_error(self):
        claims = dict(_VALID_CLAIMS)
        del claims["sub"]
        with self.assertRaises(ValueError):
            issue_token(claims, "test-secret")

    def test_missing_exp_raises_value_error(self):
        claims = dict(_VALID_CLAIMS)
        del claims["exp"]
        with self.assertRaises(ValueError):
            issue_token(claims, "test-secret")

    def test_all_good_claims_issue_succeeds(self):
        """Verify that complete claims pass the issue path."""
        token = issue_token(dict(_VALID_CLAIMS), "test-secret")
        self.assertIsInstance(token, str)


class TestIssueNonNumericExp(unittest.TestCase):
    """Non-numeric exp at issue → ValueError."""

    def test_string_exp_raises_value_error(self):
        claims = dict(_VALID_CLAIMS)
        claims["exp"] = "not-a-number"
        with self.assertRaises(ValueError):
            issue_token(claims, "test-secret")

    def test_none_exp_raises_value_error(self):
        claims = dict(_VALID_CLAIMS)
        claims["exp"] = None
        with self.assertRaises(ValueError):
            issue_token(claims, "test-secret")


class TestSecretLeakageAllPaths(unittest.TestCase):
    """Canary-secret must not appear in any exception output across ALL
    failure paths (the exhaustive leakage test)."""

    def _leak_check(self, exception):
        """Assert canary secret is absent from str(exc) and repr(exc)."""
        self.assertNotIn(
            _CANARY_SECRET, str(exception),
            f"Canary leaked in str(): {str(exception)!r}")
        self.assertNotIn(
            _CANARY_SECRET, repr(exception),
            f"Canary leaked in repr(): {repr(exception)!r}")

    def test_expired_leak_check(self):
        claims = dict(_VALID_CLAIMS)
        claims["exp"] = time.time() - 1
        token = issue_token(claims, _CANARY_SECRET)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, _CANARY_SECRET)
        self._leak_check(ctx.exception)

    def test_tampered_leak_check(self):
        token = issue_token(dict(_VALID_CLAIMS), _CANARY_SECRET)
        token_list = list(token)
        mid = len(token_list) // 2
        token_list[mid] = "X" if token_list[mid] != "X" else "Y"
        with self.assertRaises(AuthError) as ctx:
            verify_token("".join(token_list), _CANARY_SECRET)
        self._leak_check(ctx.exception)

    def test_wrong_secret_leak_check(self):
        token = issue_token(dict(_VALID_CLAIMS), _CANARY_SECRET)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, "other-secret")
        self._leak_check(ctx.exception)

    def test_alg_none_leak_check(self):
        claims = dict(_VALID_CLAIMS)
        claims["alg"] = "none"
        token = issue_token(claims, _CANARY_SECRET)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, _CANARY_SECRET)
        self._leak_check(ctx.exception)

    def test_alg_missing_leak_check(self):
        claims = dict(_VALID_CLAIMS)
        del claims["alg"]
        token = _craft_token(claims, _CANARY_SECRET)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, _CANARY_SECRET)
        self._leak_check(ctx.exception)

    def test_alg_unknown_leak_check(self):
        claims = dict(_VALID_CLAIMS)
        claims["alg"] = "RS256"
        token = issue_token(claims, _CANARY_SECRET)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, _CANARY_SECRET)
        self._leak_check(ctx.exception)

    def test_bad_operator_sub_leak_check(self):
        claims = dict(_VALID_CLAIMS)
        claims["sub"] = "OP-BadCase"
        token = issue_token(claims, _CANARY_SECRET)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, _CANARY_SECRET, caller_class="operator")
        self._leak_check(ctx.exception)

    def test_agent_missing_role_leak_check(self):
        claims = dict(_AGENT_CLAIMS)
        claims["sub"] = "op-agent-no-role"
        del claims["role"]
        token = issue_token(claims, _CANARY_SECRET)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, _CANARY_SECRET, caller_class="agent")
        self._leak_check(ctx.exception)

    def test_unknown_service_leak_check(self):
        claims = dict(_VALID_CLAIMS)
        claims["sub"] = "ghost-svc"
        token = issue_token(claims, _CANARY_SECRET)
        with self.assertRaises(AuthError) as ctx:
            verify_token(
                token, _CANARY_SECRET, caller_class="service",
                known_services=["real-svc"],
            )
        self._leak_check(ctx.exception)

    def test_revoked_leak_check(self):
        token = issue_token(dict(_VALID_CLAIMS), _CANARY_SECRET)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, _CANARY_SECRET, revoked_ids=["op-alice"])
        self._leak_check(ctx.exception)


# ---------------------------------------------------------------------------
# Coverage-gap tests (iter 3): unknown caller class; missing sub
# ---------------------------------------------------------------------------


class TestCallerClassAndSubValidation(unittest.TestCase):
    """Unknown caller class → AUTH.003; missing sub → AUTH.002."""

    def test_unknown_caller_class_raises_auth_003(self):
        secret = "test-secret"
        token = issue_token(dict(_VALID_CLAIMS), secret)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, secret, caller_class="alien")
        self.assertEqual(ctx.exception.code, "AUTH.003")
        self.assertNotIn(_CANARY_SECRET, str(ctx.exception))

    def test_unknown_caller_class_canary_not_in_repr(self):
        token = issue_token(dict(_VALID_CLAIMS), _CANARY_SECRET)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, _CANARY_SECRET, caller_class="alien")
        self.assertNotIn(_CANARY_SECRET, repr(ctx.exception))

    def test_missing_sub_operator_raises_auth_002(self):
        secret = "test-secret"
        claims = dict(_VALID_CLAIMS)
        del claims["sub"]
        token = _craft_token(claims, secret)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, secret, caller_class="operator")
        self.assertEqual(ctx.exception.code, "AUTH.002")
        self.assertNotIn(_CANARY_SECRET, str(ctx.exception))

    def test_missing_sub_operator_canary_not_in_repr(self):
        claims = dict(_VALID_CLAIMS)
        del claims["sub"]
        token = _craft_token(claims, _CANARY_SECRET)
        with self.assertRaises(AuthError) as ctx:
            verify_token(token, _CANARY_SECRET, caller_class="operator")
        self.assertNotIn(_CANARY_SECRET, repr(ctx.exception))


if __name__ == "__main__":
    unittest.main()
