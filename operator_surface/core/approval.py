"""Approval registry and diff hashing — in-memory, stdlib only.

Provides:
  - hash_diff(diff) -> str  (sha256 hash with "sha256:" prefix)
  - ApprovalError(code, reason) with .code and .reason attributes
  - ApprovalRegistry with register_request, approve, get methods

No adapter imports — purely in-memory, volatile state.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

__all__ = [
    "ApprovalError",
    "ApprovalRegistry",
    "hash_diff",
]


# ---------------------------------------------------------------------------
# hash_diff
# ---------------------------------------------------------------------------


def hash_diff(diff: str) -> str:
    """SHA-256 hash of the diff text, with 'sha256:' prefix.

    Args:
        diff: the raw diff text to hash.

    Returns:
        String in the form "sha256:<hex>" where hex is the lowercase
        SHA-256 hexdigest of diff.encode("utf-8").
    """
    hex_digest = hashlib.sha256(diff.encode("utf-8")).hexdigest()
    return f"sha256:{hex_digest}"


# ---------------------------------------------------------------------------
# ApprovalError
# ---------------------------------------------------------------------------


class ApprovalError(Exception):
    """Structured approval error.

    Attributes:
        code: canonical error code string (e.g. "VAL.001", "VAL.003").
        reason: human-readable explanation.
    """

    def __init__(self, code: str, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}")


# ---------------------------------------------------------------------------
# ApprovalRegistry
# ---------------------------------------------------------------------------


class ApprovalRegistry:
    """In-memory registry of approval requests.

    Thread-unsafe; suitable for single-threaded MVP operations.
    No disk I/O — volatile.
    """

    def __init__(self) -> None:
        self._requests: dict[str, dict] = {}

    def register_request(
        self,
        request_id: str,
        diff_hash: str,
        proposer_operator_id: str,
    ) -> dict:
        """Register a new approval request with state 'pending'.

        Args:
            request_id: UUID4 string.
            diff_hash: "sha256:<hex>" hash of the diff text.
            proposer_operator_id: operator who created the request.

        Returns:
            A defensive COPY of the stored record dict.
        """
        record: dict = {
            "request_id": request_id,
            "diff_hash": diff_hash,
            "proposer_operator_id": proposer_operator_id,
            "state": "pending",
            "created_at": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "single_use": True,
        }
        self._requests[request_id] = record
        return dict(record)

    def approve(
        self,
        request_id: str,
        approver_operator_id: str,
        diff: str,
    ) -> dict:
        """Approve a request after applying all guard checks.

        Guard order (load-bearing — each must be checked in isolation):
          1. Unknown request_id  -> VAL.003 "unknown request_id"
          2. Non-pending (already approved/invalidated)
                                -> VAL.001 "request already consumed (single-use)"
          3. Self-approval       -> VAL.001 "approver must differ from proposer"
                                (NO state change; record STAYS "pending")
          4. Diff hash mismatch  -> set state "invalidated" +
                                VAL.001 "changed-diff invalidation"
          5. All pass            -> set state "approved"; return dict COPY

        Args:
            request_id: UUID string identifying the request.
            approver_operator_id: operator attempting the approval.
            diff: raw diff text (for hash verification).

        Returns:
            A defensive COPY of the record dict with state="approved"
            and approver_operator_id populated.

        Raises:
            ApprovalError: when any guard check fails.
        """
        record = self._requests.get(request_id)

        # Guard 1: unknown request_id
        if record is None:
            raise ApprovalError("VAL.003", "unknown request_id")

        # Guard 2: non-pending → single-use
        if record["state"] != "pending":
            raise ApprovalError(
                "VAL.001", "request already consumed (single-use)"
            )

        # Guard 3: self-approval (no state change — record stays pending)
        if approver_operator_id == record["proposer_operator_id"]:
            raise ApprovalError(
                "VAL.001", "approver must differ from proposer"
            )

        # Guard 4: diff hash mismatch → invalidate
        if hash_diff(diff) != record["diff_hash"]:
            record["state"] = "invalidated"
            raise ApprovalError(
                "VAL.001", "changed-diff invalidation"
            )

        # Guard 5: all pass → approved
        record["state"] = "approved"
        record["approver_operator_id"] = approver_operator_id
        return dict(record)

    def get(self, request_id: str) -> dict | None:
        """Return a defensive COPY of the record, or None if not found."""
        record = self._requests.get(request_id)
        if record is None:
            return None
        return dict(record)
