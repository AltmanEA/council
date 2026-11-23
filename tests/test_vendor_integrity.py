"""Tests for tools/check_all.py vendor-integrity rule (G-1 guard).

Builds a throwaway git repo with a minimal vendored-engine layout
(defaults/translation.lock -> vendor/engine + SHA256SUMS) and exercises:
clean tree, undocumented deviation, recorded-patch match with/without the
lock annotation, and mismatched patch.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(WORKTREE, "tools"))

import check_all  # noqa: E402


def _git(repo, *args):
    subprocess.run(["git"] + list(args), cwd=repo, check=True,
                   capture_output=True)


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class TestVendorIntegrity(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        repo = self.tmp.name
        os.makedirs(os.path.join(repo, "vendor", "engine"))
        os.makedirs(os.path.join(repo, "defaults"))
        os.makedirs(os.path.join(repo, "docs", "en"))
        self._write_engine("print('release')\n")
        with open(os.path.join(repo, "defaults", "translation.lock"), "w") as f:
            f.write("repo: x\nlocal_path: vendor/engine\ntag: v0.1.0\n"
                    "commit: abc\nmode: external\n")
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "t@t")
        _git(repo, "config", "user.name", "t")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "release")

    def tearDown(self):
        self.tmp.cleanup()

    def _write_engine(self, content):
        repo = self.tmp.name
        with open(os.path.join(repo, "vendor", "engine", "engine.py"), "w") as f:
            f.write(content)
        # keep SHA256SUMS self-consistent (patches do this too)
        with open(os.path.join(repo, "vendor", "engine", "SHA256SUMS"), "w") as f:
            f.write(_sha(os.path.join(repo, "vendor", "engine", "engine.py"))
                    + "  engine.py\n")

    def _annotate_lock(self):
        lock = os.path.join(self.tmp.name, "defaults", "translation.lock")
        with open(lock, "a") as f:
            f.write("# patched: test patch (see patches/)\n")

    def _record_patch(self, name="test"):
        repo = self.tmp.name
        proc = subprocess.run(["git", "diff", "--", "vendor/engine/"],
                              cwd=repo, capture_output=True, text=True)
        pdir = os.path.join(repo, "documenter", "artifacts", "translation",
                            "patches")
        os.makedirs(pdir, exist_ok=True)
        with open(os.path.join(pdir, f"{name}.patch"), "w") as f:
            f.write(proc.stdout)

    def _run(self):
        corpus = check_all._Corpus(self.tmp.name)
        return [f["rule"] for f in check_all.check_vendor_integrity(corpus)]

    def test_clean_vendor_silent(self):
        self.assertEqual(self._run(), [])

    def test_undocumented_deviation_flagged(self):
        self._write_engine("print('patched')\n")
        self.assertEqual(self._run(), ["vendor-patch-undocumented"])

    def test_recorded_patch_with_annotation_clean(self):
        self._write_engine("print('patched')\n")
        self._record_patch()
        self._annotate_lock()
        self.assertEqual(self._run(), [])

    def test_recorded_patch_without_annotation_flagged(self):
        self._write_engine("print('patched')\n")
        self._record_patch()
        self.assertEqual(self._run(), ["vendor-patch-undocumented"])

    def test_mismatched_patch_flagged(self):
        self._write_engine("print('patched')\n")
        self._record_patch()
        self._annotate_lock()
        # further edit not covered by the recorded patch
        self._write_engine("print('different')\n")
        self.assertEqual(self._run(), ["vendor-patch-missing"])


if __name__ == "__main__":
    unittest.main()
