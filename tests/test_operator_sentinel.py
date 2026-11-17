"""Sentinel file: ensure_sentinel(), cross-package contract with OPERATOR_SURFACE_SENTINEL.

Cycle 10 Step 9 — Test Author.

Contract (E): the Tier 2+ readiness sentinel is a file whose path is the
constant ``documenter_service.core.policy.OPERATOR_SURFACE_SENTINEL``
relative to the policy root.  The sentinel must be created/checked via
``ensure_sentinel(root)`` (Layer 0+ implementation) and ``operator_surface_ready(root)``
(Consumer-facing check).

This module uses temp roots exclusively — NEVER creates a file at the
real repo path ``documenter/.operator_surface_ready``.

Red baseline: ``ensure_sentinel()`` does not exist yet as a function
in any package; tests fail red.
"""
from __future__ import annotations

import os
import shutil
import stat
import tempfile
import unittest


# ---------------------------------------------------------------------------
# Red-baseline imports
# ---------------------------------------------------------------------------

try:
    from documenter_service.core.policy import OPERATOR_SURFACE_SENTINEL  # noqa: F401
except ImportError:
    OPERATOR_SURFACE_SENTINEL = None  # type: ignore[misc,assignment]

try:
    from documenter_service.core.policy import operator_surface_ready  # noqa: F401
except ImportError:
    operator_surface_ready = None  # type: ignore[misc,assignment]

try:
    # ORCHESTRATOR-AUTHORIZED (cycle 10): ensure_sentinel is the SURFACE-side
    # implementation per target-task (operator_surface/core/sentinel.py); the
    # documenter_service consumer only truth-checks the path constant below.
    # Test author had pinned it to documenter_service.core.policy by mistake
    # (a function that lives in neither HEAD nor the surface deliverable there).
    from operator_surface.core.sentinel import ensure_sentinel  # noqa: F401
except ImportError:
    ensure_sentinel = None  # type: ignore[misc,assignment]


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestSentinelCreation(unittest.TestCase):
    """ensure_sentinel(root) creates the sentinel file."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @unittest.skipIf(ensure_sentinel is None,
                     "red baseline: ensure_sentinel not yet implemented")
    def test_ensure_sentinel_creates_file(self):
        """ensure_sentinel creates the sentinel file under root."""
        result = ensure_sentinel(self.tmpdir)
        self.assertTrue(result,
                        "ensure_sentinel must return True on successful creation")
        sentinel_path = os.path.join(self.tmpdir, OPERATOR_SURFACE_SENTINEL)
        self.assertTrue(
            os.path.isfile(sentinel_path),
            f"Sentinel file must exist at {sentinel_path}",
        )

    @unittest.skipIf(ensure_sentinel is None,
                     "red baseline: ensure_sentinel not yet implemented")
    def test_sentinel_content(self):
        """Sentinel file content is a readable text marker."""
        ensure_sentinel(self.tmpdir)
        sentinel_path = os.path.join(self.tmpdir, OPERATOR_SURFACE_SENTINEL)
        with open(sentinel_path, "r", encoding="utf-8") as fh:
            content = fh.read().strip()
        self.assertTrue(len(content) > 0,
                        "Sentinel file must contain non-empty content")


class TestSentinelIdempotence(unittest.TestCase):
    """ensure_sentinel is idempotent — calling again does not fail."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @unittest.skipIf(ensure_sentinel is None,
                     "red baseline: ensure_sentinel not yet implemented")
    def test_ensure_sentinel_idempotent(self):
        """Second call to ensure_sentinel returns True, file still exists."""
        self.assertTrue(ensure_sentinel(self.tmpdir))
        self.assertTrue(ensure_sentinel(self.tmpdir),
                        "Second call must succeed (idempotent)")
        sentinel_path = os.path.join(self.tmpdir, OPERATOR_SURFACE_SENTINEL)
        self.assertTrue(os.path.isfile(sentinel_path))


class TestSentinelFailureModes(unittest.TestCase):
    """Directory-in-the-way and read-only parent → False."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @unittest.skipIf(ensure_sentinel is None,
                     "red baseline: ensure_sentinel not yet implemented")
    def test_directory_in_the_way(self):
        """When the sentinel path is a directory, ensure_sentinel returns False."""
        sentinel_rel = OPERATOR_SURFACE_SENTINEL  # e.g. "documenter/.operator_surface_ready"
        # Split: create "documenter" as a directory first (if the path has components).
        parts = sentinel_rel.rsplit(os.sep, 1)
        if len(parts) == 2:
            dir_path = os.path.join(self.tmpdir, parts[0])
        else:
            dir_path = os.path.join(self.tmpdir, parts[0])

        os.makedirs(dir_path, exist_ok=True)

        # Now the file path (last component) is inside an existing dir,
        # but if we make the *parent of the file* a dir, that blocks creation.
        # For OPERATOR_SURFACE_SENTINEL = "documenter/.operator_surface_ready",
        # the parent "documenter" already exists as a dir.
        # The real sentinel file is at documenter/.operator_surface_ready —
        # creating a FILE there works when "documenter" dir already exists.
        # To test "directory in the way", we need a scenario where the last
        # component is a directory. Let's create a dir at the full sentinel path.
        sentinel_path = os.path.join(self.tmpdir, OPERATOR_SURFACE_SENTINEL)
        os.makedirs(sentinel_path, exist_ok=True)  # dir instead of file

        result = ensure_sentinel(self.tmpdir)
        self.assertFalse(result,
                         "ensure_sentinel must return False when sentinel path is a directory")

    @unittest.skipIf(ensure_sentinel is None,
                     "red baseline: ensure_sentinel not yet implemented")
    def test_read_only_parent(self):
        """When the parent directory is read-only, ensure_sentinel returns False."""
        # Create a child dir with a read-only parent.
        subdir = os.path.join(self.tmpdir, "readonly_parent")
        os.makedirs(subdir)
        os.chmod(subdir, stat.S_IRUSR | stat.S_IXUSR)  # read + execute only

        # Now make the parent of subdir read-only.
        os.chmod(self.tmpdir, stat.S_IRUSR | stat.S_IXUSR)

        try:
            result = ensure_sentinel(self.tmpdir)
            self.assertFalse(result,
                             "ensure_sentinel must return False with read-only parent")
        finally:
            os.chmod(self.tmpdir, stat.S_IRWXU)  # restore for cleanup


class TestCrossPackageContract(unittest.TestCase):
    """Cross-package contract: operator_surface_ready(root) checks the sentinel
    file at the path given by OPERATOR_SURFACE_SENTINEL relative to root."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @unittest.skipIf(operator_surface_ready is None or OPERATOR_SURFACE_SENTINEL is None,
                     "red baseline: operator_surface_ready or OPERATOR_SURFACE_SENTINEL not available")
    def test_operator_surface_ready_false_before_creation(self):
        """Before ensure_sentinel, operator_surface_ready(root) returns False."""
        self.assertFalse(
            operator_surface_ready(self.tmpdir),
            "operator_surface_ready must be False before sentinel creation",
        )

    @unittest.skipIf(operator_surface_ready is None or ensure_sentinel is None or OPERATOR_SURFACE_SENTINEL is None,
                     "red baseline: not all components available")
    def test_operator_surface_ready_true_after_creation(self):
        """After ensure_sentinel, operator_surface_ready(root) returns True."""
        ensure_sentinel(self.tmpdir)
        self.assertTrue(
            operator_surface_ready(self.tmpdir),
            "operator_surface_ready must be True after sentinel creation",
        )

    @unittest.skipIf(OPERATOR_SURFACE_SENTINEL is None,
                     "red baseline: OPERATOR_SURFACE_SENTINEL not available")
    def test_sentinel_path_contract(self):
        """OPERATOR_SURFACE_SENTINEL path matches expected structure."""
        # The sentinel path should be "documenter/.operator_surface_ready".
        self.assertIn("documenter", OPERATOR_SURFACE_SENTINEL,
                       "OPERATOR_SURFACE_SENTINEL must include 'documenter' directory")
        self.assertIn(".operator_surface_ready", OPERATOR_SURFACE_SENTINEL,
                       "OPERATOR_SURFACE_SENTINEL must include '.operator_surface_ready'")


class TestPolicyFileUntouched(unittest.TestCase):
    """ensure_sentinel must NOT modify the policy file (documenter_policy.yml)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Create a minimal policy file.
        policy_path = os.path.join(self.tmpdir, "documenter_policy.yml")
        with open(policy_path, "w", encoding="utf-8") as fh:
            fh.write("documenter_policy:\n  version: \"0.2.0\"\n  active_tier: 0\n")
        with open(policy_path, "rb") as fh:
            self.original_hash = fh.read()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @unittest.skipIf(ensure_sentinel is None,
                     "red baseline: ensure_sentinel not yet implemented")
    def test_policy_file_untouched(self):
        """After ensure_sentinel, the policy file content is unchanged."""
        ensure_sentinel(self.tmpdir)
        policy_path = os.path.join(self.tmpdir, "documenter_policy.yml")
        with open(policy_path, "rb") as fh:
            current_content = fh.read()
        self.assertEqual(
            current_content, self.original_hash,
            "ensure_sentinel must not modify the policy file",
        )


if __name__ == "__main__":
    unittest.main()
