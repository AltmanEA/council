"""HMAC-SHA256 token issue/verify for Operator Ingress AuthN — Step 1.

Provides ``issue_token`` and ``verify_token`` with minimal JWT-like format:
canonical-json claims + HMAC-SHA256 signature, base64url-encoded.

Error taxonomy:
  AUTH.001  — expired token
  AUTH.002  — malformed / bad signature / weak alg / sub format violation
  AUTH.003  — unauthorized caller (missing role, unknown service, unknown class)
  AUTH.004  — revoked credential

Secrets are function parameters; they must never appear in exception output.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time

__all__ = ["HS256", "AuthError", "issue_token", "verify_token"]

#: Accepted algorithm constant.
HS256 = "HS256"

#: Operator subject regex: op- then [a-z0-9] then [a-z0-9-]{2,63}.
_OP_SUB_RE = re.compile(r"^op-[a-z0-9][a-z0-9-]{2,63}$")

# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------

_REQUIRED = ("alg", "iss", "sub", "exp")


class AuthError(Exception):
    """Structured authentication / authorization error.

    Attributes:
        code: closed AUTH.* identifier.
        message: human-readable explanation.
        next_action: prescribed remediation step.
    """

    def __init__(self, code: str, message: str, next_action: str) -> None:
        self.code = code
        self.message = message
        self.next_action = next_action
        super().__init__(message)

    # Prevent the secret from leaking via repr/str by controlling __str__.
    def __str__(self) -> str:
        return self.message

    def __repr__(self) -> str:
        return f"AuthError({self.code!r}, {self.message!r}, {self.next_action!r})"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _b64url_encode(data: bytes) -> str:
    """Base64url-encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """Base64url-decode, adding padding as needed."""
    padded = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(padded)


def _fail(code: str, message: str, next_action: str) -> None:
    """Raise an AuthError (for cleaner call-sites)."""
    raise AuthError(code, message, next_action)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _get_secret_bytes(secret):
    """Extract HMAC secret bytes from either a string or a SecretStore-like object."""
    if hasattr(secret, "get_hmac_secret"):
        return secret.get_hmac_secret().encode("utf-8")
    return secret.encode("utf-8")


def issue_token(claims: dict, secret) -> str:
    """Sign a claims dict with HMAC-SHA256 and return a token string.

    Args:
        claims: dict containing at least alg, iss, sub, exp.
        secret: signing secret (string or object with get_hmac_secret()).

    Returns:
        base64url(payload).base64url(signature) token string.

    Raises:
        ValueError: if required claims are missing, empty, or exp is non-numeric.
    """
    # Validate required claims present and non-empty strings.
    for key in _REQUIRED:
        val = claims.get(key)
        if val is None:
            raise ValueError(f"Missing required claim: {key}")
        if isinstance(val, str) and val == "":
            raise ValueError(f"Claim '{key}' must not be empty")

    # exp must be numeric (int or float, not bool).
    exp_val = claims["exp"]
    if isinstance(exp_val, bool) or not isinstance(exp_val, (int, float)):
        raise ValueError(f"Claim 'exp' must be numeric, got {type(exp_val).__name__}")

    # Build canonical JSON payload (sorted keys, no whitespace).
    payload_json = json.dumps(claims, sort_keys=True, separators=(",", ":"))
    payload_bytes = payload_json.encode("utf-8")

    # HMAC-SHA256 signature.
    sig = hmac.new(
        _get_secret_bytes(secret), payload_bytes, hashlib.sha256
    ).digest()

    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(sig)}"


def verify_token(
    token: str,
    secret: str,
    *,
    caller_class: str = "operator",
    known_services: tuple = (),
    revoked_ids: tuple = (),
) -> dict:
    """Verify and decode a signed token, performing all AuthN/AuthZ checks.

    Verification order:
      1. Parse / decode token → AUTH.002 on failure
      2. Check alg (must be HS256) → AUTH.002
      3. Re-compute HMAC, constant-time compare → AUTH.002
      4. Check exp ≥ now → AUTH.001
      5. Check operator sub format → AUTH.002
      6. Check caller_class rules → AUTH.003
      7. Check revoked → AUTH.004

    Args:
        token: base64url-encoded token string.
        secret: signing secret for HMAC verification.
        caller_class: one of "operator", "agent", "service", or other.
        known_services: allowed service names for service class.
        revoked_ids: subject IDs that have been revoked.

    Returns:
        The original claims dict.

    Raises:
        AuthError: with code AUTH.001–004 depending on the failure.
    """
    # 1. Parse token structure.
    try:
        parts = token.split(".")
        if len(parts) != 2:
            _fail("AUTH.002", "malformed token", "use a valid signed token")
        payload_b64, sig_b64 = parts
    except Exception:
        _fail("AUTH.002", "malformed token", "use a valid signed token")

    # Decode payload bytes.
    try:
        payload_bytes = _b64url_decode(payload_b64)
        claims = json.loads(payload_bytes)
    except Exception:
        _fail("AUTH.002", "malformed token", "use a valid signed token")

    # 2. Check algorithm.
    alg = claims.get("alg")
    if alg != HS256:
        _fail("AUTH.002", "weak or unknown algorithm", "use HS256")

    # 3. Verify signature (constant-time).
    try:
        expected_sig = _b64url_decode(sig_b64)
        actual_sig = hmac.new(
            _get_secret_bytes(secret), payload_bytes, hashlib.sha256
        ).digest()
        if not hmac.compare_digest(actual_sig, expected_sig):
            _fail("AUTH.002", "invalid signature", "re-authenticate")
    except Exception:
        _fail("AUTH.002", "invalid signature", "re-authenticate")

    # 4. Check expiry.
    exp = claims.get("exp")
    if exp is None or not isinstance(exp, (int, float)) or isinstance(exp, bool):
        _fail("AUTH.002", "malformed token", "use a valid signed token")
    now = time.time()
    if exp < now:
        _fail("AUTH.001", "token expired", "renew token")

    # 5. Check caller class rules (caller_class must be known).
    if caller_class not in ("operator", "agent", "service"):
        _fail("AUTH.003", "unrecognized caller class", "use operator/agent/service")

    sub = claims.get("sub")

    if caller_class == "operator":
        if sub is None:
            _fail("AUTH.002", "malformed credential", "include operator sub claim")
        if not _OP_SUB_RE.match(sub):
            _fail("AUTH.002", "malformed credential", "use a valid operator id")
    elif caller_class == "agent":
        if "role" not in claims or not claims["role"]:
            _fail("AUTH.003", "missing role for agent", "include role claim")
    elif caller_class == "service":
        if sub not in known_services:
            _fail("AUTH.003", "unknown service", "register the service")

    # 7. Check revocation.
    if sub is not None and sub in revoked_ids:
        _fail("AUTH.004", "credential revoked", "request new credential")

    return claims
