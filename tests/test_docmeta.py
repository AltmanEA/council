"""Unit tests for tools/docmeta.py (Stage A, plan sess-doc-reliability-algo)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import docmeta
from docmeta import DocMetaError, HeaderData, parse_header, validate

GOOD = """\
# My Document
id: my-doc
title: My Document Title
Version: 0.5.5
Status: draft
Abstraction: protocol
changelog-path: CHANGELOGS/my-doc.changes.md
references: [alpha, beta]

## Body
"""

MINIMAL = """\
# Minimal
id: minimal
Version: 1
Status: active
Abstraction: conceptual
changelog-path: CHANGELOGS/minimal.changes.md
"""


class ParseHeaderOk(unittest.TestCase):
    def test_full_fields(self):
        h = parse_header(GOOD, "docs/en/my-doc/index.md")
        self.assertEqual(h.h1_title, "My Document")
        self.assertEqual(h.fields["id"], "my-doc")
        self.assertEqual(h.fields["title"], "My Document Title")
        self.assertEqual(h.fields["Version"], "0.5.5")
        self.assertEqual(h.fields["references"], ["alpha", "beta"])
        self.assertEqual(h.warnings, [])

    def test_minimal_required_only(self):
        h = parse_header(MINIMAL, "docs/en/minimal/index.md")
        self.assertEqual(h.h1_title, "Minimal")
        self.assertEqual(set(h.fields), set(docmeta.REQUIRED_KEYS))

    def test_blank_line_between_h1_and_block_tolerated(self):
        h = parse_header("# T\n\nid: t\nVersion: 1\nStatus: draft\n"
                         "Abstraction: reference\nchangelog-path: CHANGELOGS/t.changes.md\n")
        self.assertEqual(h.fields["id"], "t")

    def test_bool_and_last_modified_normalized(self):
        h = parse_header("# T\nid: t\nVersion: 1\nStatus: draft\nAbstraction: reference\n"
                         "changelog-path: CHANGELOGS/t.changes.md\nallow_non_index_paths: true\n"
                         "Last Modified: 2026-11-12\n")
        self.assertIs(h.fields["allow_non_index_paths"], True)
        self.assertEqual(h.fields["Last Modified"], "2026-11-12")


class ParseHeaderErrors(unittest.TestCase):
    def _fail(self, text, reason_fragment):
        with self.assertRaises(DocMetaError) as ctx:
            parse_header(text, "bad.md")
        self.assertEqual(ctx.exception.filename, "bad.md")
        self.assertIn(reason_fragment, ctx.exception.reason)

    def test_no_h1(self):
        self._fail("id: x\nVersion: 1\n", "no H1")

    def test_missing_id(self):
        self._fail("# T\nVersion: 1\nStatus: draft\nAbstraction: reference\n"
                   "changelog-path: CHANGELOGS/t.changes.md\n", "id")

    def test_missing_version(self):
        self._fail("# T\nid: t\nStatus: draft\nAbstraction: reference\n"
                   "changelog-path: CHANGELOGS/t.changes.md\n", "Version")

    def test_missing_status(self):
        self._fail("# T\nid: t\nVersion: 1\nAbstraction: reference\n"
                   "changelog-path: CHANGELOGS/t.changes.md\n", "Status")

    def test_missing_abstraction(self):
        self._fail("# T\nid: t\nVersion: 1\nStatus: draft\n"
                   "changelog-path: CHANGELOGS/t.changes.md\n", "Abstraction")

    def test_missing_changelog_path(self):
        self._fail("# T\nid: t\nVersion: 1\nStatus: draft\nAbstraction: reference\n",
                   "changelog-path")

    def test_empty_block_reports_all_missing(self):
        with self.assertRaises(DocMetaError) as ctx:
            parse_header("# T\n", "bad.md")
        for key in docmeta.REQUIRED_KEYS:
            self.assertIn(key, ctx.exception.reason)

    def test_body_text_as_block_is_non_mapping_error(self):
        self._fail("# T\nsome body text, no block", "not a YAML mapping")

    def test_non_mapping_block(self):
        self._fail("# T\n- just\n- a\n- list\n", "not a YAML mapping")

    def test_unparsable_yaml(self):
        self._fail("# T\nid: t\nVersion: [unclosed\n", "unparsable YAML")


class ValidateSeverities(unittest.TestCase):
    def _root(self, files=()):
        """Temp repo root containing the given relative paths."""
        d = tempfile.mkdtemp()
        for rel in files:
            full = os.path.join(d, *rel.split("/"))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as fh:
                fh.write("<!-- CHANGES v1.0.0: test. -->\n")
        return d

    def _header(self, **over):
        fields = {"id": "t", "Version": "1.0.0", "Status": "draft",
                  "Abstraction": "protocol",
                  "changelog-path": "CHANGELOGS/t.changes.md"}
        fields.update(over)
        return HeaderData(h1_title="T", fields=fields)

    def test_clean_header_no_findings(self):
        root = self._root(["CHANGELOGS/t.changes.md"])
        self.assertEqual(validate(self._header(), "docs/en/t/index.md", root), [])

    def test_missing_changelog_file_high(self):
        root = self._root()  # changelog intentionally absent
        findings = validate(self._header(), "docs/en/t/index.md", root)
        self.assertEqual([f["rule"] for f in findings], ["changelog-path-missing"])
        self.assertEqual(findings[0]["severity"], "high")
        self.assertEqual(findings[0]["file"], "docs/en/t/index.md")

    def test_changelog_outside_changelogs_dir_medium(self):
        root = self._root(["notes/t.md"])
        findings = validate(self._header(**{"changelog-path": "notes/t.md"}),
                            "docs/en/t/index.md", root)
        rules = {f["rule"]: f["severity"] for f in findings}
        self.assertEqual(rules["changelog-path-location"], "medium")

    def test_references_without_allow_flag_high(self):
        root = self._root(["CHANGELOGS/t.changes.md"])
        h = self._header(references=["x"])
        findings = validate(h, "docs/en/t/extra.md", root)
        rules = {f["rule"]: f["severity"] for f in findings}
        self.assertEqual(rules["references-non-index"], "high")

    def test_references_allowed_on_canonical_index(self):
        root = self._root(["CHANGELOGS/t.changes.md"])
        h = self._header(references=["x"])
        findings = validate(h, "docs/en/t/index.md", root)
        self.assertEqual([f["rule"] for f in findings], [])

    def test_references_allowed_with_flag(self):
        root = self._root(["CHANGELOGS/t.changes.md"])
        h = self._header(references=["x"], allow_non_index_paths=True)
        findings = validate(h, "docs/en/t/extra.md", root)
        self.assertEqual([f["rule"] for f in findings], [])

    def test_unknown_key_low(self):
        root = self._root(["CHANGELOGS/t.changes.md"])
        findings = validate(self._header(Custom="x"), "docs/en/t/index.md", root)
        rules = {f["rule"]: f["severity"] for f in findings}
        self.assertEqual(rules["unknown-key"], "low")

    def test_last_modified_deprecated_warning(self):
        root = self._root(["CHANGELOGS/t.changes.md"])
        findings = validate(self._header(**{"Last Modified": "2026-11-12"}),
                            "docs/en/t/index.md", root)
        lm = [f for f in findings if f["rule"] == "last-modified-deprecated"]
        self.assertEqual(len(lm), 1)
        self.assertEqual(lm[0]["severity"], "warning")
        # not double-reported as unknown key
        self.assertNotIn("unknown-key", {f["rule"] for f in findings})

    def test_bad_version_format_high(self):
        root = self._root(["CHANGELOGS/t.changes.md"])
        findings = validate(self._header(Version="1.2.3.4"), "docs/en/t/index.md", root)
        rules = {f["rule"]: f["severity"] for f in findings}
        self.assertEqual(rules["version-format"], "high")

    def test_good_version_formats(self):
        root = self._root(["CHANGELOGS/t.changes.md"])
        for v in ("1", "0.5", "0.5.5", "0.19.0-draft", "2.0-draft"):
            findings = validate(self._header(Version=v), "docs/en/t/index.md", root)
            self.assertEqual(findings, [], f"version {v} should be valid")


if __name__ == "__main__":
    unittest.main()
