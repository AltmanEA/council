"""Ports (hexagon face) for the Documenter Service MVP — mvp-contract §1.

Five outbound ports per ADR-009 (Ports & Adapters; pure core, five ports).
The core (documenter_service/core) knows ONLY these abstractions; the adapters
package supplies the filesystem / stdout implementations. Tier interlocks and
fail-closed behavior are unit-testable without a filesystem.

| Port            | Direction  | Responsibility                                  |
|-----------------|------------|-------------------------------------------------|
| ManifestSource  | Read       | Parse docs-manifest.yaml; resolve document paths |
| AuditRegistry   | Read/Write | Append-only store; token lifecycle               |
| DiffEngine      | Compute    | Diff generation, normalization, hash (bidirect.) |
| WorkerPort      | Execute    | Documentation Worker via Layer 1 — Tier 2+ only  |
| EventSink       | Emit       | Structured JSON to stdout                        |

MVP note: WorkerPort has NO functioning adapter (worker_stub raises the tier
interlock — the Layer 1 worker is unbuilt); intent_record persistence lives in
the dormant Tier 2+ write branch (mvp-data-models §1): records are appended by
apply/reconcile only when the branch is policy-activated (ADR-013), while the
Tier 0/1 read-only surface never writes them.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = [
    "ManifestSource",
    "AuditRegistry",
    "DiffEngine",
    "WorkerPort",
    "EventSink",
]

#: Reserved record type (mvp-data-models §1): schema fixed by the contract,
#: persistence is a Tier 2+ capability. Declared as a constant — never emitted
#: by any MVP code path.
INTENT_RECORD_TYPE = "intent_record"


class ManifestSource(ABC):
    """Read-only view of the generated manifest (sole writer: gen_manifest).

    Adapters MUST resolve document paths/ids exclusively through
    `tools/gen_manifest.build_entries` — a blind filesystem scan is prohibited
    (AGENTS.md §2.2).
    """

    @abstractmethod
    def entries(self) -> list:
        """Return manifest entry dicts (sorted by id).

        Raises StructuredError on any manifest build error (fail closed).
        """

    @abstractmethod
    def resolve(self, target_id: str):
        """Return the manifest entry for ``target_id``, or None when absent."""


class AuditRegistry(ABC):
    """Append-only JSONL store with prev_hash chain and token lifecycle."""

    @abstractmethod
    def append(self, record_type: str, data: dict) -> dict:
        """Append one envelope record; returns the written envelope."""

    @abstractmethod
    def read_all(self) -> tuple:
        """Return (records, status): status ∈ healthy|degraded|corrupt."""

    @abstractmethod
    def find_audit(self, audit_id: str):
        """Return the audit_record data for ``audit_id`` or None."""


class DiffEngine(ABC):
    """Bidirectional canonical diff helper (generate → verify)."""

    @abstractmethod
    def normalize(self, diff_text: str) -> bytes:
        """CRLF→LF, strip trailing whitespace, single final newline; bytes."""

    @abstractmethod
    def diff_hash(self, normalized: bytes) -> str:
        """Return ``sha256:<hex>`` over the normalized bytes."""

    @abstractmethod
    def render(self, normalized: bytes) -> str:
        """Human-readable unified diff text for operator preview."""


class WorkerPort(ABC):
    """Layer 1 execution port to the Documentation Worker — Tier 2+ ONLY.

    Any invocation while the interlock holds raises StructuredError with
    ``error_category="tier_interlock"`` / ``next_action="preview_denied"``.
    """

    @abstractmethod
    def execute(self, intent: dict) -> dict:
        """Execute a worker intent. Forbidden in the MVP build."""


class EventSink(ABC):
    """Structured event emitter (MVP carrier: one JSON line on stdout)."""

    @abstractmethod
    def emit(self, event_type: str, payload: dict) -> None:
        """Emit ``event_type`` with a schema-checked, redacted payload.

        Unknown payload fields are rejected (VAL.001); document text in any
        payload string is rejected (mvp-data-models §3 redaction rule).
        """
