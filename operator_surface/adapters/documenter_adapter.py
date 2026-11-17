"""Tier 0-1 Documenter adapter for the Operator Surface.

Binds the real ``documenter_service`` (audit/status/delegate-preview)
with lazy import inside methods — ImportError produces graceful
degradation ``{"available": False, "reason": ...}``.

This module-level import never fails (the import happens inside methods).
"""
from __future__ import annotations

from ..ports import DocumenterPort


class Tier01Documenter(DocumenterPort):
    """DocumenterPort adapter binding the Tier 0-1 documenter_service.

    Uses lazy import inside each method so that module-level import
    never fails (graceful degradation on ImportError).

    The real ``Service`` instance is created ONCE from ``self.root``
    and cached on first call — subsequent calls reuse that instance.
    """

    def __init__(self, root: str) -> None:
        """Store the corpus root for Service instantiation.

        Args:
            root: Path to the corpus root (contains docs/, docs-manifest.yaml).
        """
        self.root = root
        self._service = None  # cached instance after first successful import

    def _get_service(self):
        """Import and return a Service *instance*, caching on success."""
        if self._service is not None:
            return self._service
        try:
            from documenter_service.__main__ import Service  # noqa: F401
            self._service = Service(self.root)
            return self._service
        except ImportError:
            self._service = None  # mark as failed so we don't retry
            return None

    def audit(self, target_id: str = "*", **kwargs) -> dict:
        """Run documenter audit.

        Returns dict with keys ``report`` and ``findings`` on success,
        or ``{"compliant": False, "findings": 0, "available": False,
        "reason": ...}`` on failure.
        """
        svc = self._get_service()
        if svc is None:
            return {
                "compliant": False,
                "findings": 0,
                "available": False,
                "reason": "documenter_service not importable",
            }
        try:
            return svc.audit(target_id=target_id, **kwargs)
        except Exception as exc:
            return {
                "compliant": False,
                "findings": 0,
                "available": False,
                "reason": str(exc),
            }

    def status(self, target_id: str | None = None) -> dict:
        """Get documenter service status.

        Returns dict with key ``healthy`` on success, or
        ``{"healthy": False, "available": False, "reason": ...}`` on failure.
        """
        svc = self._get_service()
        if svc is None:
            return {
                "healthy": False,
                "available": False,
                "reason": "documenter_service not importable",
            }
        try:
            return svc.status(target_id=target_id)
        except Exception as exc:
            return {
                "healthy": False,
                "available": False,
                "reason": str(exc),
            }

    def delegate_preview(
        self,
        target_id: str,
        change_type: str,
        trust_level: str,
        diff_input: str,
    ) -> dict:
        """Run documenter delegate preview.

        Delegates to the real ``Service.delegate(preview=True)`` method.

        Returns the service result dict on success, or
        ``{"available": False, "reason": ...}`` on failure.
        """
        svc = self._get_service()
        if svc is None:
            return {
                "available": False,
                "reason": "documenter_service not importable",
            }
        try:
            return svc.delegate(
                target_id=target_id,
                change_type=change_type,
                trust_level=trust_level,
                diff_input=diff_input,
                preview=True,
            )
        except Exception as exc:
            return {
                "available": False,
                "reason": str(exc),
            }
