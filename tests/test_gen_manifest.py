"""Unit tests for tools/gen_manifest.py (Stage A, plan sess-doc-reliability-algo).

Runs the generator in --check/--write mode against fixture corpora under
tests/fixtures/gen_manifest/. Never touches the live repo root or the live
docs-manifest.yaml.
"""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import gen_manifest

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "gen_manifest")
CORPUS = os.path.join(FIXTURES, "corpus")
GOLDEN = os.path.join(FIXTURES, "golden_manifest.yaml")


def _copy_corpus(broken=True):
    """Copy fixture corpus to a temp dir; optionally drop the broken file."""
    d = tempfile.mkdtemp()
    root = os.path.join(d, "repo")
    shutil.copytree(CORPUS, root)
    if not broken:
        os.remove(os.path.join(root, "docs", "en", "gamma", "broken.md"))
    return root


class CheckAgainstGolden(unittest.TestCase):
    def test_check_reproduces_golden_byte_exact(self):
        root = _copy_corpus(broken=False)
        shutil.copy(GOLDEN, os.path.join(root, "docs-manifest.yaml"))
        err = io.StringIO()
        with redirect_stderr(err):
            rc = gen_manifest.main(["--root", root, "--check"])
        self.assertEqual(rc, 0, err.getvalue())
        with open(GOLDEN, "rb") as fh:
            golden = fh.read()
        with open(os.path.join(root, "docs-manifest.yaml"), "rb") as fh:
            self.assertEqual(fh.read(), golden)

    def test_check_detects_drift_with_diff_exit_1(self):
        root = _copy_corpus(broken=False)
        with open(os.path.join(root, "docs-manifest.yaml"), "w") as fh:
            fh.write("documents: []\n")  # stale / hand-edited manifest
        err = io.StringIO()
        with redirect_stderr(err):
            rc = gen_manifest.main(["--root", root, "--check"])
        self.assertEqual(rc, 1)
        self.assertIn("---", err.getvalue())  # unified diff on stderr
        self.assertIn("id: alpha", err.getvalue())

    def test_generated_marker_present(self):
        root = _copy_corpus(broken=False)
        text, errors = gen_manifest.generate(root)
        self.assertEqual(errors, [])
        lines = text.splitlines()
        self.assertEqual(lines[0], "# Documentation Manifest")
        self.assertTrue(any("GENERATED" in ln and "DO NOT EDIT" in ln and
                            "gen_manifest.py" in ln for ln in lines))


class WriteIdempotence(unittest.TestCase):
    def test_write_rerun_identical_bytes(self):
        root = _copy_corpus(broken=False)
        self.assertEqual(gen_manifest.main(["--root", root, "--write"]), 0)
        target = os.path.join(root, "docs-manifest.yaml")
        with open(target, "rb") as fh:
            first = fh.read()
        # Second write must produce identical bytes (deterministic output).
        self.assertEqual(gen_manifest.main(["--root", root, "--write"]), 0)
        with open(target, "rb") as fh:
            second = fh.read()
        self.assertEqual(first, second)
        # And byte-exact against the golden file.
        with open(GOLDEN, "rb") as fh:
            self.assertEqual(first, fh.read())
        # No temp leftovers from atomic write.
        leftovers = [n for n in os.listdir(root) if n.startswith(".docs-manifest.")]
        self.assertEqual(leftovers, [])

    def test_entries_sorted_by_id_and_optional_fields_omitted(self):
        root = _copy_corpus(broken=False)
        text, errors = gen_manifest.generate(root)
        self.assertEqual(errors, [])
        self.assertLess(text.index("id: alpha"), text.index("id: beta"))
        # beta has no references / allow_non_index_paths -> keys absent.
        beta_block = text[text.index("id: beta"):]
        self.assertNotIn("references", beta_block)
        self.assertNotIn("allow_non_index_paths", beta_block)
        # alpha keeps both, plus H1-defaulted title for beta.
        alpha_block = text[text.index("id: alpha"):text.index("id: beta")]
        self.assertIn("allow_non_index_paths: true", alpha_block)
        self.assertIn("title: Beta Document", beta_block)


class BrokenCorpus(unittest.TestCase):
    def test_broken_corpus_exit_2_names_file_no_partial_write(self):
        root = _copy_corpus(broken=True)
        target = os.path.join(root, "docs-manifest.yaml")
        sentinel = "PRE-EXISTING SENTINEL\n"
        with open(target, "w") as fh:
            fh.write(sentinel)
        err = io.StringIO()
        with redirect_stderr(err):
            rc = gen_manifest.main(["--root", root, "--write"])
        self.assertEqual(rc, 2)
        self.assertIn("docs/en/gamma/broken.md", err.getvalue())
        self.assertIn("id", err.getvalue())  # reason names the missing key
        # NO partial write: original file untouched, no temp files.
        with open(target) as fh:
            self.assertEqual(fh.read(), sentinel)
        leftovers = [n for n in os.listdir(root) if n.startswith(".docs-manifest.")]
        self.assertEqual(leftovers, [])

    def test_check_on_broken_corpus_exit_2(self):
        root = _copy_corpus(broken=True)
        shutil.copy(GOLDEN, os.path.join(root, "docs-manifest.yaml"))
        err = io.StringIO()
        with redirect_stderr(err):
            rc = gen_manifest.main(["--root", root, "--check"])
        self.assertEqual(rc, 2)
        self.assertIn("docs/en/gamma/broken.md", err.getvalue())


if __name__ == "__main__":
    unittest.main()
