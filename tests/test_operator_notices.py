"""Unit tests for operator_surface.core.notices (Step 4 — notices subsystem).

Frozen API:
  default_notices(policy_info=None, layer1_stub=True) -> list[dict]

Each notice: {type, severity, text}
severity ∈ {"Info", "Advisory", "Blocking"}
"""
from __future__ import annotations

import unittest

try:
    from operator_surface.core.notices import (  # noqa: F401
        default_notices,
    )
except ImportError:
    default_notices = None  # NameError baseline


_VALID_SEVERITIES = {"Info", "Advisory", "Blocking"}
_VALID_NOTICE_TYPES = {
    "notice.simplification-applied",
    "notice.fallback-deferred",
    "notice.quick_review_disabled",
    "notice.documenter_tier2_interlock",
    "notice.layer1_stub_active",
}


class TestDefaultNoticesLayer1Stub(unittest.TestCase):
    """layer1_stub=True always includes the layer1_stub_active notice."""

    def test_includes_layer1_stub_active(self):
        notices = default_notices(layer1_stub=True)
        types = [n["type"] for n in notices]
        self.assertIn("notice.layer1_stub_active", types)

    def test_layer1_stub_text_exact(self):
        notices = default_notices(layer1_stub=True)
        for n in notices:
            if n["type"] == "notice.layer1_stub_active":
                self.assertEqual(
                    n["text"],
                    "temporary adapter; sessions are stored in a provisional format",
                )
                break
        else:
            self.fail("notice.layer1_stub_active not found")

    def test_layer1_stub_severity_advisory(self):
        notices = default_notices(layer1_stub=True)
        for n in notices:
            if n["type"] == "notice.layer1_stub_active":
                self.assertEqual(n["severity"], "Advisory")
                break
        else:
            self.fail("notice.layer1_stub_active not found")

    def test_layer1_stub_disabled_excludes(self):
        notices = default_notices(layer1_stub=False)
        types = [n["type"] for n in notices]
        self.assertNotIn("notice.layer1_stub_active", types)


class TestDefaultNoticesPolicyInterlock(unittest.TestCase):
    """policy_info active_tier < 2 → notice.documenter_tier2_interlock (Blocking)."""

    def test_active_tier_1_includes_interlock(self):
        notices = default_notices(policy_info={"active_tier": 1})
        types = [n["type"] for n in notices]
        self.assertIn("notice.documenter_tier2_interlock", types)

    def test_active_tier_0_includes_interlock(self):
        notices = default_notices(policy_info={"active_tier": 0})
        types = [n["type"] for n in notices]
        self.assertIn("notice.documenter_tier2_interlock", types)

    def test_interlock_severity_blocking(self):
        notices = default_notices(policy_info={"active_tier": 1})
        for n in notices:
            if n["type"] == "notice.documenter_tier2_interlock":
                self.assertEqual(n["severity"], "Blocking")
                break
        else:
            self.fail("notice.documenter_tier2_interlock not found")

    def test_policy_info_none_includes_interlock(self):
        """policy_info is None → fail closed → includes interlock."""
        notices = default_notices(policy_info=None)
        types = [n["type"] for n in notices]
        self.assertIn("notice.documenter_tier2_interlock", types)

    def test_active_tier_2_excludes_interlock(self):
        notices = default_notices(policy_info={"active_tier": 2})
        types = [n["type"] for n in notices]
        self.assertNotIn("notice.documenter_tier2_interlock", types)


class TestDefaultNoticesSeverity(unittest.TestCase):
    """Every notice severity ∈ {"Info", "Advisory", "Blocking"}."""

    def test_all_severities_valid(self):
        notices = default_notices(layer1_stub=True, policy_info={"active_tier": 1})
        for n in notices:
            self.assertIn(
                n["severity"], _VALID_SEVERITIES,
                f"Invalid severity {n['severity']!r} in {n['type']!r}",
            )


class TestDefaultNoticesStructure(unittest.TestCase):
    """Each notice dict has type, severity, text keys with correct types."""

    def test_all_have_required_keys(self):
        notices = default_notices(layer1_stub=True)
        required = {"type", "severity", "text"}
        for n in notices:
            self.assertTrue(
                required.issubset(set(n.keys())),
                f"Missing keys: {required - set(n.keys())}",
            )

    def test_types_valid(self):
        notices = default_notices(layer1_stub=True)
        for n in notices:
            self.assertIn(
                n["type"], _VALID_NOTICE_TYPES,
                f"Invalid notice type: {n['type']!r}",
            )

    def test_all_text_non_empty(self):
        notices = default_notices(layer1_stub=True)
        for n in notices:
            self.assertIsInstance(n["text"], str)
            self.assertTrue(len(n["text"]) > 0, f"Empty text for {n['type']!r}")


class TestDefaultNoticesReturnIsList(unittest.TestCase):
    """Return value is always a list (even when empty)."""

    def test_is_list(self):
        result = default_notices(layer1_stub=False, policy_info={"active_tier": 2})
        self.assertIsInstance(result, list)

    def test_is_list_with_layer1(self):
        result = default_notices(layer1_stub=True)
        self.assertIsInstance(result, list)

    def test_not_empty_with_layer1(self):
        result = default_notices(layer1_stub=True)
        self.assertGreater(len(result), 0)


if __name__ == "__main__":
    unittest.main()
