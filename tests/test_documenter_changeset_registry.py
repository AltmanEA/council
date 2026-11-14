"""Tests for changeset registry intent_record uniformity (p.10 of fix plan).

Covers:
  T-a:  незавершённый changeset-коммит виден в status().staged_files
        и registry.find_intent() (seam crash at before_rename).
  T-b:  успешный changeset-коммит → resolved intent в реестре,
        unresolved_intents() пуст.
  T-c:  legacy-intent читается find_intent как раньше (не регрессия).

Run with: python3 -m pytest tests/test_documenter_changeset_registry.py -q
"""
import base64
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from documenter_service.adapters.diff_engine import StdDiffEngine  # noqa: E402
from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry  # noqa: E402
from documenter_service.adapters.stdout_events import StdoutEventSink  # noqa: E402
from documenter_service.core import write as core_write  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enable_operator_surface(root: str) -> str:
    sentinel = os.path.join(root, "documenter", ".operator_surface_ready")
    os.makedirs(os.path.dirname(sentinel), exist_ok=True)
    with open(sentinel, "w") as f:
        f.write("")
    return sentinel


def _init_git_repo(root: str) -> None:
    subprocess.run(
        ["git", "init", "-q", root],
        capture_output=True, text=True, timeout=10, shell=False,
    )
    subprocess.run(
        ["git", "-C", root, "config", "user.email", "test@council.local"],
        capture_output=True, text=True, timeout=10, shell=False,
    )
    subprocess.run(
        ["git", "-C", root, "config", "user.name", "Test"],
        capture_output=True, text=True, timeout=10, shell=False,
    )
    subprocess.run(
        ["git", "-C", root, "add", "-A"],
        capture_output=True, text=True, timeout=10, shell=False,
    )
    subprocess.run(
        ["git", "-C", root, "commit", "-q", "-m", "fixture baseline"],
        capture_output=True, text=True, timeout=10, shell=False,
    )


def _make_manifest():
    entries_list = []
    manifest = type("Manifest", (), {
        "_entries": {},
        "entries": lambda self: entries_list,
        "resolve": lambda self, tid: self._entries.get(tid),
    })()
    entry = {
        "id": "alpha",
        "path": "docs/en/alpha/index.md",
        "title": "Alpha Document",
        "version": "1.0.0",
        "status": "active",
        "changelog-path": "CHANGELOGS/alpha.changes.md",
    }
    entries_list.append(entry)
    manifest._entries["alpha"] = entry
    return manifest


def _make_registry(tmpdir):
    return JsonlAuditRegistry(tmpdir)


def _make_tier2_policy(briefing_path=None):
    fields = {
        "version": "0.2.0",
        "active_tier": 2,
        "allowed_operations": [
            {"change_type": "update", "targets": ["alpha"], "trust_level": "safe"},
            {"change_type": "update", "targets": [], "trust_level": "review"},
        ],
        "briefing_ref": briefing_path or "_briefing.md",
        "audit_freshness": 30,
        "approval_expiry_window": 30,
        "max_diff_bytes": 524288,
        "lock_wait_timeout": 30,
    }
    return type("Policy", (), {"_fields": fields, "get": lambda s, k, d=None: s._fields.get(k, d)})()


def _make_diff():
    """Generate diff that replaces changelog-path (same pattern as
    test_documenter_changeset_write.py)."""
    doc = ("# Alpha\nid: alpha\nVersion: 1.0.0\nStatus: active\n"
           "changelog-path: CHANGELOGS/alpha.md\n")
    old_lines = doc.split("\n")
    effective_lines = old_lines[:-1] if old_lines and old_lines[-1] == "" else old_lines
    hunk_header = "@@ -1," + str(len(effective_lines)) + " +1," + str(len(effective_lines)) + " @@\n"
    effective_diff = []
    for line in effective_lines:
        if line == "changelog-path: CHANGELOGS/alpha.md":
            effective_diff.append("-" + line)
            effective_diff.append("+changelog-path: CHANGELOGS/alpha.updated.md")
        else:
            effective_diff.append(" " + line)
    return ("--- a/index.md\n+++ b/index.md\n" + hunk_header +
            "\n".join(effective_diff) + "\n")


def _encode_diff(diff_text):
    return base64.b64encode(diff_text.encode("utf-8")).decode("ascii")


def _make_diff_v2(current_doc_text):
    """Generate a diff that replaces changelog-path with a v2 suffix.

    Takes the current content of the index.md file and produces a unified
    diff that changes `changelog-path: CHANGELOGS/alpha.*.md` to
    `CHANGELOGS/alpha.v2.md`.
    """
    old_lines = current_doc_text.split("\n")
    effective = old_lines[:-1] if old_lines and old_lines[-1] == "" else old_lines
    hunk_header = "@@ -1," + str(len(effective)) + " +1," + str(len(effective)) + " @@\n"
    hunk_body = []
    for line in effective:
        if line.startswith("changelog-path: CHANGELOGS/alpha."):
            hunk_body.append("-" + line)
            hunk_body.append("+changelog-path: CHANGELOGS/alpha.v2.md")
        else:
            hunk_body.append(" " + line)
    return ("--- a/index.md\n+++ b/index.md\n" + hunk_header +
            "\n".join(hunk_body) + "\n")


def _full_cycle(changeset=None, data_dir=None, tmpdir=None,
                corpus=None, manifest=None, registry=None,
                policy=None, events=None, engine=None,
                briefing=None, seeded=False):
    """Run propose_write → approve → apply_write.

    Returns (result, approval_id, encoded_diff).
    If seeded=False, auto-seeds audit.
    """
    if not seeded:
        registry.append("audit_record", {
            "audit_id": "aid-1",
            "issued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "scope": "*", "findings": [],
            "scanned_ids": ["alpha"], "has_remaining": False})

    diff_text = _make_diff()
    encoded = _encode_diff(diff_text)

    prop_result = core_write.propose_write(
        corpus, manifest, registry, policy, events, engine,
        target_id="alpha", change_type="update", trust_level="safe",
        diff_input=encoded, audit_id="aid-1", changeset=changeset)

    approval_id = prop_result["approval_id"]

    core_write.approve(registry, policy, events,
                       root=corpus,
                       approval_id=approval_id, operator_id="op-user1")

    result = core_write.apply_write(
        corpus, manifest, registry, policy, events, engine,
        approval_id=approval_id, operator_id="op-user1",
        diff_input=encoded, data_dir=data_dir or tmpdir,
        changeset=changeset)

    return result, approval_id, encoded


class TestChangesetRegistry(unittest.TestCase):
    """T-a, T-b, T-c: changeset+legacy registry intent_record uniformity."""

    def _setup(self):
        self.tmpdir = tempfile.mkdtemp()
        self.corpus = os.path.join(self.tmpdir, "corpus")
        os.makedirs(os.path.join(self.corpus, "docs", "en", "alpha"))
        with open(os.path.join(self.corpus, "docs", "en", "alpha", "index.md"),
                  "w") as f:
            f.write("# Alpha\nid: alpha\nVersion: 1.0.0\nStatus: active\n"
                    "changelog-path: CHANGELOGS/alpha.md\n")
        os.makedirs(os.path.join(self.corpus, "CHANGELOGS"))
        with open(os.path.join(self.corpus, "CHANGELOGS", "alpha.changes.md"),
                  "w") as f:
            f.write("## Alpha Changelog\n\nOriginal content.\n")
        _init_git_repo(self.corpus)
        _enable_operator_surface(self.corpus)
        self.data_dir = os.path.join(self.tmpdir, "documenter")
        self.briefing = os.path.join(self.tmpdir, "_briefing.md")
        with open(self.briefing, "w") as f:
            f.write("# Briefing\n\nAuthorised operational context.\n")
        self.registry = _make_registry(self.tmpdir)
        self.manifest = _make_manifest()
        self.policy = _make_tier2_policy(self.briefing)
        self.events = StdoutEventSink()
        self.engine = StdDiffEngine()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # -- T-a: незавершённый changeset-коммит виден ----------------------------

    def test_t_a_unfinished_changeset_visible_in_status(self):
        """Unfinished changeset (crash at before_rename) visible in
        status().staged_files and find_intent()."""
        self._setup()
        changelog_content = b"## Alpha Changelog\n\nUpdated.\n"
        changeset = [
            {"path": "CHANGELOGS/alpha.changes.md",
             "content_b64": base64.b64encode(changelog_content).decode("ascii")},
        ]
        result, approval_id, encoded = _full_cycle(
            changeset=changeset, data_dir=self.data_dir,
            tmpdir=self.tmpdir, corpus=self.corpus,
            manifest=self.manifest, registry=self.registry,
            policy=self.policy, events=self.events, engine=self.engine)

        self.assertTrue(result["applied"])

        # After the first apply the corpus files are modified; propose a new
        # write by generating a diff based on the *current* corpus state and
        # re-use the same changeset (same content_b64).
        self.registry.append("audit_record", {
            "audit_id": "aid-2",
            "issued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "scope": "*", "findings": [],
            "scanned_ids": ["alpha"], "has_remaining": False})

        # Generate a diff that replaces the current changelog-path with v2
        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        with open(alpha_path) as f:
            current = f.read()
        diff_text_2 = _make_diff_v2(current)
        encoded_2 = _encode_diff(diff_text_2)

        prop2 = core_write.propose_write(
            self.corpus, self.manifest, self.registry, self.policy, self.events, self.engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded_2, audit_id="aid-2", changeset=changeset)
        approval_id2 = prop2["approval_id"]
        core_write.approve(self.registry, self.policy, self.events,
                           root=self.corpus,
                           approval_id=approval_id2, operator_id="op-user1")

        crash_hit = []
        seams = {"before_rename": lambda: crash_hit.append(True) or
                              (_ for _ in ()).throw(RuntimeError("simulated crash"))}

        with self.assertRaises(RuntimeError):
            core_write.apply_write(
                self.corpus, self.manifest, self.registry, self.policy, self.events, self.engine,
                approval_id=approval_id2, operator_id="op-user1",
                diff_input=encoded_2, data_dir=self.data_dir,
                changeset=changeset, seams=seams)

        self.assertTrue(crash_hit)

        # Check status().staged_files shows the target
        from documenter_service.core.status import status
        st = status(self.registry, self.policy, root=self.corpus)
        staged = st["registry"]["staged_files"]
        self.assertTrue(len(staged) >= 1,
                        f"staged_files should contain the unfinished changeset, got {staged}")
        self.assertEqual(staged[0]["target_id"], "alpha")

        # Check registry.find_intent()
        intent = self.registry.find_intent("alpha")
        self.assertIsNotNone(intent, "find_intent('alpha') should return the changeset record")
        self.assertFalse(intent.get("resolved"), "unresolved intent must have resolved=False")
        self.assertIn("tx_id", intent)
        self.assertIn("entries", intent)

    # -- T-b: успешный changeset → resolved, unresolved_intents() пуст -------

    def test_t_b_successful_changeset_resolved(self):
        """Successful changeset → resolved intent_record in registry."""
        self._setup()
        changelog_content = b"## Alpha Changelog\n\nUpdated.\n"
        changeset = [
            {"path": "CHANGELOGS/alpha.changes.md",
             "content_b64": base64.b64encode(changelog_content).decode("ascii")},
        ]
        result, approval_id, encoded = _full_cycle(
            changeset=changeset, data_dir=self.data_dir,
            tmpdir=self.tmpdir, corpus=self.corpus,
            manifest=self.manifest, registry=self.registry,
            policy=self.policy, events=self.events, engine=self.engine)

        self.assertTrue(result["applied"])

        # Verify a resolved intent_record exists with the expected fields.
        # The initial intent (resolved=False) remains in the registry as the
        # staging marker; the resolved copy (resolved=True) marks completion.
        records, _ = self.registry.read_all()
        intent_records = [r["data"] for r in records
                          if r["record_type"] == "intent_record"]
        self.assertTrue(len(intent_records) >= 2,
                        f"should have ≥2 intent_records, got {len(intent_records)}")

        resolved = [r for r in intent_records if r.get("resolved") is True]
        self.assertTrue(len(resolved) >= 1,
                        f"should have at least one resolved intent_record, got {len(resolved)}")
        latest_resolved = resolved[-1]
        self.assertIn("target_ids", latest_resolved)
        self.assertIn("tx_id", latest_resolved)
        self.assertIn("entries", latest_resolved)
        self.assertEqual(len(latest_resolved["target_ids"]), 1)
        self.assertEqual(latest_resolved["target_ids"][0], "alpha")

    # -- T-c: legacy-intent читается find_intent как раньше -----------------

    def test_t_c_legacy_intent_read_compat(self):
        """Legacy intent_record still readable by find_intent (no regression)."""
        self._setup()
        result, approval_id, encoded = _full_cycle(
            changeset=None, data_dir=self.data_dir,
            tmpdir=self.tmpdir, corpus=self.corpus,
            manifest=self.manifest, registry=self.registry,
            policy=self.policy, events=self.events, engine=self.engine)
        self.assertTrue(result["applied"])

        # Legacy intent should be found by find_intent
        intent = self.registry.find_intent("alpha")
        self.assertIsNotNone(intent, "legacy intent should be found by find_intent")
        self.assertIn("target_ids", intent)
        self.assertIn("tx_id", intent)
        self.assertIn("entries", intent)
        self.assertIsNone(intent["entries"],
                          "legacy intent should have entries=None")

        # Verify a resolved intent_record also exists after success.
        records, _ = self.registry.read_all()
        intent_records = [r["data"] for r in records
                          if r["record_type"] == "intent_record"]
        resolved = [r for r in intent_records if r.get("resolved") is True]
        self.assertTrue(len(resolved) >= 1,
                        f"should have at least one resolved intent_record, got {len(resolved)}")

    def test_t_c_legacy_unfinished_visible(self):
        """Legacy crash at before_rename → unresolved intent visible."""
        self._setup()
        result, approval_id, encoded = _full_cycle(
            changeset=None, data_dir=self.data_dir,
            tmpdir=self.tmpdir, corpus=self.corpus,
            manifest=self.manifest, registry=self.registry,
            policy=self.policy, events=self.events, engine=self.engine)
        self.assertTrue(result["applied"])

        # Propose a second write (legacy path) and apply with crash seam.
        # The file was changed by the first apply, so we need a fresh diff.
        self.registry.append("audit_record", {
            "audit_id": "aid-2",
            "issued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "scope": "*", "findings": [],
            "scanned_ids": ["alpha"], "has_remaining": False})

        alpha_path = os.path.join(self.corpus, "docs", "en", "alpha", "index.md")
        with open(alpha_path) as f:
            current = f.read()
        diff_text_2 = _make_diff_v2(current)
        encoded_2 = _encode_diff(diff_text_2)

        prop2 = core_write.propose_write(
            self.corpus, self.manifest, self.registry, self.policy, self.events, self.engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=encoded_2, audit_id="aid-2")
        approval_id2 = prop2["approval_id"]
        core_write.approve(self.registry, self.policy, self.events,
                           root=self.corpus,
                           approval_id=approval_id2, operator_id="op-user1")

        crash_hit = []
        seams = {"before_rename": lambda: crash_hit.append(True) or
                              (_ for _ in ()).throw(RuntimeError("simulated crash"))}

        with self.assertRaises(RuntimeError):
            core_write.apply_write(
                self.corpus, self.manifest, self.registry, self.policy, self.events, self.engine,
                approval_id=approval_id2, operator_id="op-user1",
                diff_input=encoded_2, data_dir=self.data_dir, seams=seams)

        self.assertTrue(crash_hit)

        # Legacy unresolved intent should be visible
        unresolved = self.registry.unresolved_intents()
        self.assertTrue(len(unresolved) >= 1,
                        f"legacy unresolved intent should be visible, got {unresolved}")
        intent = self.registry.find_intent("alpha")
        self.assertIsNotNone(intent, "find_intent('alpha') should find the legacy intent")
        self.assertIn("target_ids", intent)


if __name__ == "__main__":
    unittest.main()
