"""DiffEngine adapter — canonical diff normalization (mvp-interfaces §2).

The operator approves the diff_text AS RENDERED by Documenter, not the base64
input: decode → normalize (CRLF→LF, trailing whitespace, final newline) →
`diff_hash = sha256:<hex>` over the NORMALIZED bytes → render diff_text.
This makes the approved object and the hash-bound object identical.

Bidirectionality (mvp-contract §1): `normalize`/`diff_hash` verify an inbound
diff, `render` reproduces the exact byte-level object behind the hash, so a
later apply-time comparison re-derives the same digest from the same bytes.

diff_text NEVER leaves this response path: it must not appear in any event
payload (mvp-data-models §3 redaction rule) — enforce by only ever passing
the response dict, never event schemas.
"""
from __future__ import annotations

import base64
import binascii
import hashlib

from ..core.errors import StructuredError
from ..ports import DiffEngine

__all__ = ["StdDiffEngine", "decode_diff_input"]

#: Decoded payload size cap fallback when policy cannot be loaded
#: (max_diff_bytes default, 512 KiB, policy-reference §Field Reference).
MAX_DIFF_BYTES_DEFAULT = 524288


class StdDiffEngine(DiffEngine):
    """Pure normalization/hashing adapter (no filesystem access)."""

    def normalize(self, diff_text: str) -> bytes:
        """Return canonical bytes: LF endings, no trailing whitespace, one
        final newline (empty input → empty bytes)."""
        text = diff_text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [ln.rstrip(" \t") for ln in text.split("\n")]
        while lines and not lines[-1]:
            lines.pop()
        canonical = "\n".join(lines)
        if canonical:
            canonical += "\n"
        return canonical.encode("utf-8")

    def diff_hash(self, normalized: bytes) -> str:
        return "sha256:" + hashlib.sha256(normalized).hexdigest()

    def render(self, normalized: bytes) -> str:
        """Human-readable unified diff text (the normalized bytes verbatim).

        Inbound diffs are already machine-readable unified diffs; rendering
        keeps a sanity check that the payload is diff-shaped so a malformed
        input cannot masquerade as a previewable diff.
        """
        text = normalized.decode("utf-8")
        if text and not _looks_like_diff(text):
            raise StructuredError(
                "unknown",
                "diff_input does not look like a machine-readable unified "
                "diff (expected '--- ', '+++ ', '@@', or 'diff ' lines)")
        return text


def _looks_like_diff(text: str) -> bool:
    for line in text.split("\n"):
        if line.startswith(("--- ", "+++ ", "@@", "diff ")):
            return True
    return False


def decode_diff_input(diff_input: str, max_diff_bytes: int
                      = MAX_DIFF_BYTES_DEFAULT) -> str:
    """Base64 → UTF-8 text, size-capped BEFORE any diff processing.

    Oversized payload is rejected at ingress (policy-reference §Field
    Reference, max_diff_bytes). Category is `unknown`: the closed enum defines
    no dedicated size category and oversized input is a client bug, not a gate
    condition (declared deviation, see documenter_service/README.md).
    """
    if not isinstance(diff_input, str) or not diff_input:
        raise StructuredError("unknown", "diff_input must be a non-empty string")
    try:
        raw = base64.b64decode(diff_input, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise StructuredError(
            "unknown", f"diff_input is not valid base64: {exc}") from exc
    if len(raw) > max_diff_bytes:
        raise StructuredError(
            "unknown",
            f"decoded diff payload is {len(raw)} bytes, exceeding "
            f"max_diff_bytes={max_diff_bytes}")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StructuredError(
            "unknown", f"decoded diff payload is not valid UTF-8: {exc}") from exc
