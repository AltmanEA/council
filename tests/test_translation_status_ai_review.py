"""Tests for tools/translation_status.py compute_status — G-2 ai_review cap.

Reports must carry ai_review == 'passed' to earn `verified`; absent/failed
caps the status at `unverified` (contract.md §Sidecar).
"""
import hashlib
import os
import sys
import tempfile
import unittest

WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(WORKTREE, "tools"))

import translation_status as ts  # noqa: E402


class TestAiReviewCap(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.en = os.path.join(self.tmp.name, "en.md")
        self.ru = os.path.join(self.tmp.name, "ru.md")
        with open(self.en, "w", encoding="utf-8") as f:
            f.write("English source\n")
        with open(self.ru, "w", encoding="utf-8") as f:
            f.write("Русский перевод\n")
        self.base = {
            "exit_code": 0,
            "source_sha256": ts.sha256_file(self.en),
            "output_sha256": ts.sha256_file(self.ru),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def _status(self, **extra):
        report = dict(self.base)
        report.update(extra)
        return ts.compute_status("x", self.en, self.ru, report)

    def test_verified_requires_ai_review_passed(self):
        status, extra = self._status(ai_review="passed")
        self.assertEqual(status, "verified")
        self.assertEqual(extra, {})

    def test_absent_ai_review_caps_unverified(self):
        status, extra = self._status()
        self.assertEqual(status, "unverified")
        self.assertEqual(extra.get("note"), "ai_review=not_run")

    def test_failed_ai_review_caps_unverified(self):
        status, extra = self._status(ai_review="failed")
        self.assertEqual(status, "unverified")
        self.assertEqual(extra.get("note"), "ai_review=failed")

    def test_error_and_drift_precedence_unaffected(self):
        status, _ = self._status(exit_code=4, ai_review="passed")
        self.assertEqual(status, "error-4")
        report = dict(self.base, ai_review="passed", source_sha256="0" * 64)
        status, _ = ts.compute_status("x", self.en, self.ru, report)
        self.assertEqual(status, "drift")


if __name__ == "__main__":
    unittest.main()
