"""Benchmark: run_precheck wall time with fake port returning ~200 findings.

Cycle 10 Step 9 — Test Author.

Contract (B): run_precheck with a fake port that returns a canned result
with ~200 findings must complete in < 0.05s (50ms), while the
PRE_CHECK_TIMEOUT_SECONDS constant is 5.0s.  The margin must be positive
(time saved vs timeout).

Red baseline: run_precheck may not complete under 0.05s, or timing guard
doesn't exist yet.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest

# ---------------------------------------------------------------------------
# Red-baseline imports
# ---------------------------------------------------------------------------

try:
    from operator_surface.core.precheck import run_precheck  # noqa: F401
except ImportError:
    run_precheck = None  # type: ignore[misc,assignment]

try:
    from operator_surface.core.precheck import PRE_CHECK_TIMEOUT_SECONDS  # noqa: F401
except ImportError:
    PRE_CHECK_TIMEOUT_SECONDS = None  # type: ignore[misc,assignment]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Wall-time budget for benchmark success.
BENCHMARK_THRESHOLD_SECONDS = 0.05  # 50ms

# ---------------------------------------------------------------------------
# Fake port: canned ~200 findings
# ---------------------------------------------------------------------------

class _FakeDocumenterPort:
    """DocumenterPort that returns ~200 canned findings instantly."""

    def __init__(self, finding_count=200):
        self._finding_count = finding_count

    def audit(self, target_id="*", pre_check=False, **kwargs):
        findings = []
        for i in range(self._finding_count):
            findings.append({
                "id": f"find-{i:04d}",
                "severity": "low",  # all low → pass (not blocking)
                "description": f"Canned finding {i}",
                "path": f"docs/en/section/{i}.md",
            })
        return {
            "compliant": True,
            "findings": self._finding_count,
            "report": {"findings": findings},
        }

    def status(self, target_id=None):
        return {"healthy": True}

    def delegate_preview(self, target_id, change_type, trust_level, diff_input):
        return {"diff": "canned"}


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestBenchmark(unittest.TestCase):
    """run_precheck performance with canned findings."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @unittest.skipIf(run_precheck is None,
                     "red baseline: run_precheck not yet implemented")
    def test_run_precheck_200_findings_under_threshold(self):
        """run_precheck with 200 low-severity findings completes in < 50ms."""
        port = _FakeDocumenterPort(finding_count=200)
        start = time.perf_counter()
        result = run_precheck(
            target_id="scen-bench",
            documenter_port=port,
        )
        elapsed = time.perf_counter() - start

        self.assertEqual(
            result.get("verdict"), "pass",
            "200 low-severity findings must pass",
        )
        self.assertLess(
            elapsed, BENCHMARK_THRESHOLD_SECONDS,
            f"run_precheck with 200 findings must complete in < "
            f"{BENCHMARK_THRESHOLD_SECONDS}s (actual: {elapsed:.4f}s)",
        )

    @unittest.skipIf(run_precheck is None,
                     "red baseline: run_precheck not yet implemented")
    def test_run_precheck_200_high_severity_under_threshold(self):
        """run_precheck with 200 high-severity findings completes in < 50ms."""
        class _HighPort:
            def audit(self, target_id="*", pre_check=False, **kwargs):
                findings = []
                for i in range(200):
                    findings.append({
                        "id": f"find-{i:04d}",
                        "severity": "critical",  # blocking!
                        "description": f"Critical finding {i}",
                        "path": f"docs/en/section/{i}.md",
                    })
                return {
                    "compliant": False,
                    "findings": 200,
                    "report": {"findings": findings},
                }
            def status(self, target_id=None):
                return {"healthy": True}
            def delegate_preview(self, target_id, change_type, trust_level, diff_input):
                return {"diff": "canned"}

        port = _HighPort()
        start = time.perf_counter()
        result = run_precheck(
            target_id="scen-bench-high",
            documenter_port=port,
        )
        elapsed = time.perf_counter() - start

        self.assertEqual(
            result.get("verdict"), "fail",
            "200 critical findings must fail the precheck",
        )
        self.assertLess(
            elapsed, BENCHMARK_THRESHOLD_SECONDS,
            f"run_precheck with 200 critical findings must complete in < "
            f"{BENCHMARK_THRESHOLD_SECONDS}s (actual: {elapsed:.4f}s)",
        )

    @unittest.skipIf(PRE_CHECK_TIMEOUT_SECONDS is None,
                     "red baseline: PRE_CHECK_TIMEOUT_SECONDS not yet implemented")
    def test_timeout_constant_is_5_0(self):
        """PRE_CHECK_TIMEOUT_SECONDS must be exactly 5.0."""
        self.assertEqual(
            PRE_CHECK_TIMEOUT_SECONDS, 5.0,
            f"PRE_CHECK_TIMEOUT_SECONDS must be 5.0, got {PRE_CHECK_TIMEOUT_SECONDS}",
        )

    @unittest.skipIf(run_precheck is None or PRE_CHECK_TIMEOUT_SECONDS is None,
                     "red baseline: run_precheck or PRE_CHECK_TIMEOUT_SECONDS not available")
    def test_margin_vs_timeout(self):
        """Print margin: 5.0 - elapsed = margin (must be positive)."""
        port = _FakeDocumenterPort(finding_count=200)
        start = time.perf_counter()
        result = run_precheck(
            target_id="scen-bench-margin",
            documenter_port=port,
        )
        elapsed = time.perf_counter() - start
        margin = PRE_CHECK_TIMEOUT_SECONDS - elapsed

        self.assertGreater(
            margin, 0,
            f"Margin must be positive: {PRE_CHECK_TIMEOUT_SECONDS} - "
            f"{elapsed:.4f} = {margin:.4f}s",
        )
        # Bonus assertion: margin should be at least 4.95s (99% of timeout).
        self.assertGreater(
            margin, 4.95,
            f"Margin should be >= 4.95s (run_precheck is much faster than timeout). "
            f"Actual margin: {margin:.4f}s",
        )


class TestBenchmarkNoPort(unittest.TestCase):
    """run_precheck with no port is instant (no audit call)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @unittest.skipIf(run_precheck is None,
                     "red baseline: run_precheck not yet implemented")
    def test_run_precheck_no_port_under_threshold(self):
        """run_precheck with documenter_port=None must complete under 50ms."""
        start = time.perf_counter()
        result = run_precheck(
            target_id="scen-bench-noport",
            documenter_port=None,
        )
        elapsed = time.perf_counter() - start

        self.assertEqual(
            result.get("verdict"), "unavailable",
            "No port must return unavailable",
        )
        self.assertLess(
            elapsed, BENCHMARK_THRESHOLD_SECONDS,
            f"run_precheck with no port must complete in < "
            f"{BENCHMARK_THRESHOLD_SECONDS}s (actual: {elapsed:.4f}s)",
        )


if __name__ == "__main__":
    unittest.main()
