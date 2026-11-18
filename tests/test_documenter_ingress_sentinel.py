"""ADR-013 dual interlock — Operator Ingress readiness sentinel (CS-2).

check_tier2_authorized enforces TWO independent levels:
  1. policy gate: active_tier >= 2, briefing_ref, archived briefing file;
  2. surface gate: sentinel documenter/.operator_ingress_ready under root
     (runtime proxy for "the Operator Ingress exists as code providing
     authenticated ingress" — the spec alone is not sufficient, ADR-013).

Matrix covered here: sentinel absent/present × tier < 2 / tier >= 2, plus
status() tier_interlock visibility (mvp-interfaces §3) and the fail-closed
default (no sentinel file → refusal).
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry  # noqa: E402
from documenter_service.core.errors import StructuredError  # noqa: E402
from documenter_service.core.policy import (  # noqa: E402
    Policy, check_tier2_authorized,
    check_tier3_authorized,
    OPERATOR_INGRESS_SENTINEL, operator_ingress_ready)
from documenter_service.core.status import status as status_core  # noqa: E402


def _policy(active_tier, briefing_ref):
    return Policy({
        "version": "0.2.0",
        "active_tier": active_tier,
        "allowed_operations": [{"change_type": "update", "targets": [],
                                "trust_level": "review"}],
        "briefing_ref": briefing_ref,
        "audit_freshness": 30,
        "approval_expiry_window": 30,
        "max_diff_bytes": 524288,
        "lock_wait_timeout": 30,
    })


def _briefing(root):
    path = os.path.join(root, "_briefing.md")
    with open(path, "w") as f:
        f.write("# Briefing\n\ncontext\n")
    return path


def _sentinel(root):
    return os.path.join(root, "documenter", ".operator_ingress_ready")


class TestSurfaceSentinel(unittest.TestCase):
    """check_tier2_authorized sentinel matrix."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_sentinel(self):
        path = _sentinel(self.tmpdir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("")

    # -- fail-closed default --------------------------------------------------

    def test_no_sentinel_dir_refuses(self):
        """Repo-like default: no sentinel anywhere under root → tier_interlock."""
        bp = _briefing(self.tmpdir)
        with self.assertRaises(StructuredError) as ctx:
            check_tier2_authorized(_policy(2, bp), self.tmpdir)
        self.assertEqual(ctx.exception.error_category, "tier_interlock")
        self.assertEqual(ctx.exception.next_action, "preview_denied")
        self.assertIn("Operator Ingress not built", ctx.exception.message)
        self.assertIn(OPERATOR_INGRESS_SENTINEL, ctx.exception.message)

    def test_empty_sentinel_file_counts(self):
        """The proxy is existence, not content."""
        os.makedirs(os.path.dirname(_sentinel(self.tmpdir)), exist_ok=True)
        open(_sentinel(self.tmpdir), "w").close()
        bp = _briefing(self.tmpdir)
        check_tier2_authorized(_policy(2, bp), self.tmpdir)  # no raise

    def test_sentinel_as_directory_refuses(self):
        """isfile semantics: a directory at the sentinel path is not ready."""
        os.makedirs(_sentinel(self.tmpdir), exist_ok=True)
        self.assertFalse(operator_ingress_ready(self.tmpdir))

    # -- policy gate precedes the sentinel ------------------------------------

    def test_tier1_refuses_even_with_sentinel(self):
        """First interlock level wins: sentinel present, tier < 2 → refusal."""
        self._create_sentinel()
        bp = _briefing(self.tmpdir)
        with self.assertRaises(StructuredError) as ctx:
            check_tier2_authorized(_policy(1, bp), self.tmpdir)
        self.assertIn("active_tier=1 < 2", ctx.exception.message)

    def test_both_levels_released_passes(self):
        self._create_sentinel()
        bp = _briefing(self.tmpdir)
        check_tier2_authorized(_policy(2, bp), self.tmpdir)  # no raise

    def test_tier3_also_requires_sentinel(self):
        """check_tier3_authorized inherits the second level via tier2 check."""
        bp = _briefing(self.tmpdir)
        with self.assertRaises(StructuredError) as ctx:
            check_tier3_authorized(_policy(3, bp), self.tmpdir)
        self.assertIn("Operator Ingress not built", ctx.exception.message)
        self._create_sentinel()
        check_tier3_authorized(_policy(3, bp), self.tmpdir)  # no raise

    # -- status() visibility (mvp-interfaces §3) ------------------------------

    def test_status_policy_gate_reason(self):
        reg = JsonlAuditRegistry(os.path.join(self.tmpdir, "state"))
        out = status_core(reg, _policy(1, "_briefing.md"), root=self.tmpdir)
        self.assertTrue(out["tier_interlock"]["tier_2_plus_locked"])
        self.assertIn("active_tier=1 < 2", out["tier_interlock"]["reason"])

    def test_status_surface_not_built_reason(self):
        reg = JsonlAuditRegistry(os.path.join(self.tmpdir, "state"))
        out = status_core(reg, _policy(2, "_briefing.md"), root=self.tmpdir)
        self.assertTrue(out["tier_interlock"]["tier_2_plus_locked"])
        self.assertIn("Operator Ingress not built",
                      out["tier_interlock"]["reason"])
        self.assertIn(OPERATOR_INGRESS_SENTINEL,
                      out["tier_interlock"]["reason"])

    def test_status_both_released(self):
        reg = JsonlAuditRegistry(os.path.join(self.tmpdir, "state"))
        self._create_sentinel()
        out = status_core(reg, _policy(2, "_briefing.md"), root=self.tmpdir)
        self.assertFalse(out["tier_interlock"]["tier_2_plus_locked"])

    def test_status_without_root_is_conservative(self):
        """root unknown → locked (fail closed) with the static dual reason."""
        reg = JsonlAuditRegistry(os.path.join(self.tmpdir, "state"))
        out = status_core(reg, _policy(2, "_briefing.md"))
        self.assertTrue(out["tier_interlock"]["tier_2_plus_locked"])


if __name__ == "__main__":
    unittest.main()
