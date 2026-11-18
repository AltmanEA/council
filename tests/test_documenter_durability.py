"""Durability / crash-injection tests — mvp-contract §3.4 (Tier 2+).

Operator-approved variant: deterministic fault seams at EVERY boundary of
the durability sequence (stage → fsync → intent → rename → fsync(dir) →
resolve/consume) plus real SIGKILL at two key boundaries via
tests/fixtures/documenter/crash_apply_helper.py.

Invariant asserted at every boundary: a crash leaves a DETECTABLE partial
state — the target file is either untouched or fully new, and observable
evidence exists (staged .tmp artifact and/or unresolved intent_record), so
cold-start reconcile() classifies it instead of silently diverging.

Helpers are replicated locally (no imports from other Tier 2+ test modules)
to keep this suite independent.
"""
import base64
import hashlib
import json
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
from documenter_service.core.errors import StructuredError  # noqa: E402
from documenter_service.core.policy import Policy  # noqa: E402

HELPER = os.path.join(REPO_ROOT, "tests", "fixtures", "documenter",
                      "crash_apply_helper.py")

DOC = ("# Alpha\nid: alpha\nVersion: 1.0.0\nStatus: active\n"
       "changelog-path: CHANGELOGS/alpha.md\n")


class CrashHere(Exception):
    """Fault seam raise for deterministic crash injection."""


def _enable_operator_ingress(root):
    """Create the ADR-013 Operator Ingress readiness sentinel under root.

    Tier 2+ test corpora must opt into surface-readiness explicitly:
    check_tier2_authorized refuses (tier_interlock) while the sentinel is
    absent. Tests asserting the second interlock level omit this call.
    """
    sentinel = os.path.join(root, "documenter", ".operator_ingress_ready")
    os.makedirs(os.path.dirname(sentinel), exist_ok=True)
    with open(sentinel, "w") as f:
        f.write("")
    return sentinel


def _init_git_repo(root: str) -> None:
    """Initialise ``root`` as a git repo (quietly).

    Called by tests that exercise the apply_write path so that the
    pre-change git snapshot guard passes.
    """
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


def _sha(path):
    with open(path, "rb") as fh:
        return "sha256:" + hashlib.sha256(fh.read()).hexdigest()


def _make_diff():
    lines = DOC.rstrip("\n").split("\n")
    body = []
    for line in lines:
        if line == "changelog-path: CHANGELOGS/alpha.md":
            body.append("-changelog-path: CHANGELOGS/alpha.md")
            body.append("+changelog-path: CHANGELOGS/alpha.updated.md")
        else:
            body.append(" " + line)
    return ("--- a/index.md\n+++ b/index.md\n"
            f"@@ -1,{len(lines)} +1,{len(lines)} @@\n"
            + "\n".join(body) + "\n")


def _encode(diff_text):
    return base64.b64encode(diff_text.encode("utf-8")).decode("ascii")


def _make_manifest():
    entries = []
    manifest = type("Manifest", (), {
        "_entries": {},
        "entries": lambda self: entries,
        "resolve": lambda self, tid: self._entries.get(tid),
    })()
    for eid in ("alpha", "beta"):
        entry = {"id": eid, "path": f"docs/en/{eid}/index.md",
                 "title": eid.title(), "version": "1.0.0",
                 "status": "active"}
        entries.append(entry)
        manifest._entries[eid] = entry
    return manifest


def _policy(briefing):
    return Policy({
        "version": "0.2.0", "active_tier": 2,
        "allowed_operations": [
            {"change_type": "update", "targets": ["alpha"],
             "trust_level": "safe"}],
        "briefing_ref": briefing,
        "audit_freshness": 30, "approval_expiry_window": 30,
        "max_diff_bytes": 524288, "lock_wait_timeout": 5,
    })


class _Harness(unittest.TestCase):
    """Shared tmp corpus/registry + approved proposal fixture."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.corpus = os.path.join(self.tmpdir, "corpus")
        self.state = os.path.join(self.tmpdir, "state")
        self.data_dir = os.path.join(self.tmpdir, "documenter")
        os.makedirs(os.path.join(self.corpus, "docs", "en", "alpha"))
        _enable_operator_ingress(self.corpus)
        self.target = os.path.join(self.corpus, "docs", "en", "alpha",
                                   "index.md")
        with open(self.target, "w") as fh:
            fh.write(DOC)
        _init_git_repo(self.corpus)
        self.briefing = os.path.join(self.tmpdir, "_briefing.md")
        with open(self.briefing, "w") as fh:
            fh.write("# Briefing\n\ncontext\n")
        self.registry = JsonlAuditRegistry(self.state)
        self.manifest = _make_manifest()
        self.policy = _policy(self.briefing)
        self.events = StdoutEventSink()
        self.engine = StdDiffEngine()
        self.diff = _make_diff()
        self.encoded = _encode(self.diff)
        self.registry.append("audit_record", {
            "audit_id": "aid-1",
            "issued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "scope": "*", "findings": [],
            "scanned_ids": ["alpha", "beta"], "has_remaining": False})

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def approved(self, approver="op-approver", proposer=None):
        prop = core_write.propose_write(
            self.corpus, self.manifest, self.registry, self.policy,
            self.events, self.engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=self.encoded, audit_id="aid-1",
            proposer_id=proposer)
        aid = prop["approval_id"]
        self.registry.resolve_approval(aid, decision="approved",
                                       operator_id=approver)
        return aid

    def apply(self, aid, seams=None, encoded=None):
        return core_write.apply_write(
            self.corpus, self.manifest, self.registry, self.policy,
            self.events, self.engine,
            approval_id=aid, operator_id="op-applier",
            diff_input=encoded or self.encoded, data_dir=self.data_dir,
            seams=seams)

    def staged_files(self):
        d = os.path.dirname(self.target)
        return [f for f in os.listdir(d)
                if f.startswith(".index.md.") and f.endswith(".tmp")]


# ---------------------------------------------------------------------------
# A. Seam-based fault injection at every boundary
# ---------------------------------------------------------------------------

class TestSeamCrashes(_Harness):

    def _crash_seam(self):
        def boom():
            raise CrashHere("crash")
        return boom

    def test_crash_after_stage_detectable(self):
        # Boundary: stage+fsync done, intent NOT yet appended — evidence is
        # the staged artifact itself (durable intent arrives at after_intent).
        aid = self.approved()
        before = _sha(self.target)
        with self.assertRaises(CrashHere):
            self.apply(aid, seams={"after_stage": self._crash_seam()})
        self.assertEqual(_sha(self.target), before, "target must be untouched")
        self.assertTrue(self.staged_files(), "staged artifact must be visible")

    def test_crash_after_intent_detectable(self):
        aid = self.approved()
        before = _sha(self.target)
        with self.assertRaises(CrashHere):
            self.apply(aid, seams={"after_intent": self._crash_seam()})
        self.assertEqual(_sha(self.target), before)
        self.assertTrue(self.staged_files())
        self.assertTrue(self.registry.unresolved_intents())
        intent_file = os.path.join(self.data_dir, f"intent_{aid}.json")
        self.assertTrue(os.path.isfile(intent_file),
                        "durable intent file must survive the crash")

    def test_crash_before_rename_detectable(self):
        aid = self.approved()
        before = _sha(self.target)
        with self.assertRaises(CrashHere):
            self.apply(aid, seams={"before_rename": self._crash_seam()})
        self.assertEqual(_sha(self.target), before)
        self.assertTrue(self.registry.unresolved_intents())

    def test_crash_after_rename_new_content_unresolved(self):
        """Post-rename crash: new bytes in place, intent still unresolved.

        reconcile() MUST classify this as needs_attention (source hash now
        differs from per_file_sha256) and MUST NOT auto-fix.
        """
        aid = self.approved()
        with self.assertRaises(CrashHere):
            self.apply(aid, seams={"after_rename": self._crash_seam()})
        with open(self.target) as fh:
            self.assertIn("alpha.updated.md", fh.read(),
                          "rename already happened — content is fully new")
        self.assertTrue(self.registry.unresolved_intents())
        results = core_write.reconcile(self.registry, self.manifest,
                                       self.corpus, self.data_dir)
        self.assertTrue(any(r["status"] == "needs_attention"
                            for r in results),
                        "post-rename crash must be flagged, not auto-fixed")

    def test_recovery_reapply_after_before_rename_crash(self):
        aid = self.approved()
        with self.assertRaises(CrashHere):
            self.apply(aid, seams={"before_rename": self._crash_seam()})
        # fresh re-invocation, no seams: stale staged file is overwritten
        result = self.apply(aid)
        self.assertTrue(result["applied"])
        with open(self.target) as fh:
            self.assertIn("alpha.updated.md", fh.read())
        # the new apply appended its own resolved intent; the earlier
        # unresolved one remains evidence until reconciled
        core_write.reconcile(self.registry, self.manifest,
                             self.corpus, self.data_dir)

    def test_registry_chain_healthy_after_seam_crashes(self):
        for seam in ("after_stage", "after_intent", "before_rename",
                     "after_rename"):
            aid = self.approved()
            try:
                self.apply(aid, seams={seam: self._crash_seam()})
            except CrashHere:
                pass
            except StructuredError:
                pass
        _, status = self.registry.read_all()
        self.assertEqual(status, "healthy",
                         "seam crashes must not damage the JSONL chain")


# ---------------------------------------------------------------------------
# B. Real SIGKILL at two boundaries (subprocess)
# ---------------------------------------------------------------------------

class TestKill9(_Harness):

    def _run_killed(self, seam):
        proc = subprocess.Popen(
            [sys.executable, HELPER, self.tmpdir, seam, self.data_dir],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # The helper SIGKILLs itself at the seam; the observable evidence is
        # seam-specific and must appear BEFORE the process exits:
        #   after_stage  -> staged .tmp artifact
        #   after_intent -> durable intent_<approval>.json in data_dir
        # Waiting for the process to exit is not enough (its parent-visible
        # death may lag the evidence write), and polling only on the staged
        # file would let the harness return before the intent append lands.
        deadline = time.time() + 15
        while time.time() < deadline:
            if seam == "after_intent":
                has_intent = (os.path.isdir(self.data_dir)
                              and any(f.startswith("intent_")
                                      and f.endswith(".json")
                                      for f in os.listdir(self.data_dir)))
                if has_intent and proc.poll() is not None:
                    break
            else:
                if self.staged_files() and proc.poll() is not None:
                    break
            if proc.poll() is not None:
                break  # died (possibly early crash) — assert downstream
            time.sleep(0.05)
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        return proc

    def _prefix_integrity(self):
        """All complete lines parse; chain verifies over the complete prefix.

        A kill mid-append may leave a partial last line (registry verdict
        corrupt) — the prefix before it must still parse and chain-verify.
        """
        path = os.path.join(self.state, "audit_registry.jsonl")
        with open(path, encoding="utf-8") as fh:
            raw_lines = [ln for ln in fh.read().splitlines() if ln.strip()]
        complete = []
        for ln in raw_lines:
            try:
                json.loads(ln)
                complete.append(ln)
            except ValueError:
                break  # partial tail (or corruption) — prefix ends here
        self.assertGreaterEqual(len(complete), 3,
                                "propose/approve/audit records must survive")
        from documenter_service.core import registry as reg
        records = [reg.parse_line(ln) for ln in complete]
        self.assertEqual(reg.verify_chain(records), "healthy")

    def test_kill9_after_stage(self):
        proc = self._run_killed("after_stage")
        self.assertNotEqual(proc.returncode, 0,
                            "helper must die from SIGKILL")
        with open(self.target) as fh:
            content = fh.read()
        self.assertIn("CHANGELOGS/alpha.md\n", content)
        self.assertNotIn("alpha.updated.md", content,
                         "killed before rename — target must be untouched")
        self.assertTrue(self.staged_files()
                        or self.registry.unresolved_intents(),
                        "crash must leave observable evidence")
        self._prefix_integrity()

    def test_kill9_after_intent(self):
        proc = self._run_killed("after_intent")
        self.assertNotEqual(proc.returncode, 0)
        self.assertTrue(self.registry.unresolved_intents(),
                        "intent record must be observable after the kill")
        self._prefix_integrity()


# ---------------------------------------------------------------------------
# C. Apply-time verification (mvp-contract §2.2.3, conflict C2)
# ---------------------------------------------------------------------------

class TestApplyTimeVerification(_Harness):

    def test_external_source_edit_denied(self):
        aid = self.approved()

        def tamper():
            with open(self.target, "w") as fh:
                fh.write(DOC + "injected\n")

        with self.assertRaises(StructuredError) as ctx:
            self.apply(aid, seams={"after_stage": tamper})
        self.assertEqual(ctx.exception.error_category, "hash_mismatch")
        with open(self.target) as fh:
            self.assertIn("injected", fh.read(),
                          "tampered content must remain — write denied")
        self.assertTrue(self.registry.unresolved_intents())

    def test_staged_tampering_denied(self):
        aid = self.approved()

        def tamper_staged():
            staged = os.path.join(os.path.dirname(self.target),
                                  self.staged_files()[0])
            with open(staged, "w") as fh:
                fh.write("EVIL\n")

        with self.assertRaises(StructuredError) as ctx:
            self.apply(aid, seams={"after_intent": tamper_staged})
        self.assertEqual(ctx.exception.error_category, "hash_mismatch")
        with open(self.target) as fh:
            self.assertEqual(fh.read(), DOC, "target untouched")

    def test_changed_diff_invalidates_approval(self):
        aid = self.approved()
        changed = _encode(self.diff.replace("alpha.updated.md",
                                            "alpha.evil.md"))
        with self.assertRaises(StructuredError) as ctx:
            self.apply(aid, encoded=changed)
        self.assertEqual(ctx.exception.error_category,
                         "approval_invalidated")

    def test_double_apply_is_token_replay(self):
        aid = self.approved()
        result = self.apply(aid)
        self.assertTrue(result["applied"])
        with self.assertRaises(StructuredError) as ctx:
            self.apply(aid)
        self.assertEqual(ctx.exception.error_category, "token_replay")


# ---------------------------------------------------------------------------
# D. Token replay suite (§3.4)
# ---------------------------------------------------------------------------

class TestTokenReplay(_Harness):

    def test_approve_double_resolve_replay(self):
        aid = self.approved()
        with self.assertRaises(StructuredError) as ctx:
            self.registry.resolve_approval(aid, decision="approved",
                                           operator_id="op-other")
        self.assertEqual(ctx.exception.error_category, "token_replay")

    def test_scan_cursor_replay(self):
        from documenter_service.core.registry import (AUDIT_RECORD,
                                                      TOKEN_RECORD)
        self.registry.issue_token("scan_cursor", "tok-1",
                                  {"audit_id": "aid-1",
                                   "target_id": "alpha"})
        self.registry.consume_token("tok-1", "alpha")
        with self.assertRaises(StructuredError) as ctx:
            self.registry.consume_token("tok-1", "alpha")
        self.assertEqual(ctx.exception.error_category, "token_replay")

    def test_override_replay_same_pair(self):
        from documenter_service.core.override import override_gate
        diff_hash = self.engine.diff_hash(self.engine.normalize(self.diff))
        override_gate(self.corpus, self.data_dir, self.registry,
                      self.policy, self.events,
                      target_id="alpha", diff_hash=diff_hash,
                      reason="first", operator_id="op-first")
        with self.assertRaises(StructuredError) as ctx:
            override_gate(self.corpus, self.data_dir, self.registry,
                          self.policy, self.events,
                          target_id="alpha", diff_hash=diff_hash,
                          reason="second", operator_id="op-second")
        self.assertEqual(ctx.exception.error_category, "token_replay")

    def test_forged_resolved_intent_not_unresolved(self):
        """Threat model: append-only, git history is the audit trail.

        A writer may append resolved=True directly; the honest invariant is
        that such a record never surfaces as UNRESOLVED (find_intent /
        unresolved_intents filter on resolved).
        """
        self.registry.append("intent_record", {
            "target_ids": ["alpha"],
            "staged_at": self.registry.now(),
            "per_file_sha256": {"alpha": "sha256:" + "0" * 64},
            "resolved": True})
        self.assertIsNone(self.registry.find_intent("alpha"))
        self.assertEqual(self.registry.unresolved_intents(), [])

    def test_pending_approval_cannot_apply(self):
        prop = core_write.propose_write(
            self.corpus, self.manifest, self.registry, self.policy,
            self.events, self.engine,
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=self.encoded, audit_id="aid-1",
            proposer_id="op-bot1"
        )
        with self.assertRaises(StructuredError) as ctx:
            self.apply(prop["approval_id"])
        self.assertEqual(ctx.exception.error_category, "gate_failure")


# ---------------------------------------------------------------------------
# E. Reconcile moves staged leftovers to documenter/staged/
# ---------------------------------------------------------------------------

class TestReconcileCleanup(_Harness):

    def test_clean_crash_staged_moved_to_staged_dir(self):
        aid = self.approved()
        try:
            self.apply(aid, seams={"after_intent": lambda: (_ for _ in ()).throw(
                CrashHere("x"))})
        except CrashHere:
            pass
        staged_before = self.staged_files()
        self.assertTrue(staged_before)
        # The unresolved intent hashed the ORIGINAL source, which is still
        # in place → reconcile classifies clean and must move the leftover.
        results = core_write.reconcile(self.registry, self.manifest,
                                       self.corpus, self.data_dir)
        self.assertEqual([r for r in results
                          if r["status"] == "needs_attention"], [])
        self.assertEqual(self.staged_files(), [],
                         "leftover staged temp files must be swept")
        staged_dir = os.path.join(self.data_dir, "staged")
        self.assertTrue(os.path.isdir(staged_dir))
        self.assertTrue(os.listdir(staged_dir),
                        "leftovers move into documenter/staged/ (data-models §4)")


if __name__ == "__main__":
    unittest.main()
