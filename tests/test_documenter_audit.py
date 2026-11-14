"""Tests for the Documenter MVP audit core (mvp-interfaces §1, mvp-contract §3.2).

test_manifest_parity, test_event_redaction, test_coverage_header,
test_audit_no_rule_fork, test_cli_core_parity, plus golden-fixture checks.
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import check_all  # noqa: E402
import gen_manifest  # noqa: E402
from documenter_service.__main__ import Service, main  # noqa: E402
from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry  # noqa: E402
from documenter_service.adapters.stdout_events import StdoutEventSink  # noqa: E402
from documenter_service.core.audit import (  # noqa: E402
    AUDIT_RULE_NAMES, PARTIAL_WRITE_DECISION_NOTE)
from documenter_service.core.errors import StructuredError  # noqa: E402

FIXTURE_CORPUS = os.path.join(REPO_ROOT, "tests", "fixtures", "documenter",
                              "corpus")
GOLDEN = os.path.join(REPO_ROOT, "tests", "fixtures", "documenter",
                      "golden_audit.yaml")
MARKER = "UNIQUE-CORPUS-MARKER-PHRASE-zq7xk9"


def _corpus_copy():
    root = tempfile.mkdtemp()
    dst = os.path.join(root, "corpus")
    shutil.copytree(FIXTURE_CORPUS, dst)
    return root, dst


def _service(root, events=None):
    # The corpus is copied when it is the checked-in fixture: audit() now
    # mutates state under root/documenter/ (hash store) — the fixture must
    # stay pristine. Registry state lives in its own temp dir as before.
    if os.path.abspath(root) == os.path.abspath(FIXTURE_CORPUS):
        base = tempfile.mkdtemp()
        root = os.path.join(base, "corpus")
        shutil.copytree(FIXTURE_CORPUS, root)
    tmp = tempfile.mkdtemp()
    return Service(root,
                   registry=JsonlAuditRegistry(os.path.join(tmp, "state")),
                   events=events if events is not None
                   else StdoutEventSink(io.StringIO()))


class TestGoldenAudit(unittest.TestCase):
    def test_fixture_manifest_is_in_parity(self):
        # Guard: the checked-in fixture manifest must equal generator output
        # (same contract tools/test_check_all.py enforces for its corpus).
        with open(os.path.join(FIXTURE_CORPUS, "docs-manifest.yaml"),
                  "rb") as fh:
            on_disk = fh.read()
        text, errors = gen_manifest.generate(FIXTURE_CORPUS)
        self.assertEqual(errors, [])
        self.assertEqual(text.encode("utf-8"), on_disk)

    def test_audit_matches_golden(self):
        with open(GOLDEN, encoding="utf-8") as fh:
            golden = yaml.safe_load(fh)
        svc = _service(FIXTURE_CORPUS)
        resp = svc.audit(target_id="*")
        self.assertEqual(resp["coverage"], golden["coverage"])
        self.assertEqual(resp["has_remaining"], golden["has_remaining"])
        self.assertEqual(resp["report"]["header"], golden["report_header"])
        got = sorted((f["subject_id"], f["severity"], f["description"],
                      f["suggested_action"])
                     for f in resp["report"]["findings"])
        want = sorted((f["subject_id"], f["severity"], f["description"],
                       f["suggested_action"])
                      for f in golden["findings"])
        self.assertEqual(got, want)


class TestManifestParity(unittest.TestCase):
    def test_drift_detected_and_matches_generator_check(self):
        _, root = _corpus_copy()
        try:
            # Desynchronize the manifest: regenerate at a different version.
            with open(os.path.join(root, "docs-manifest.yaml"), encoding="utf-8") as fh:
                text = fh.read()
            drifted = text.replace("version: 1.0.0", "version: 9.9.9", 1)
            self.assertNotEqual(drifted, text)
            with open(os.path.join(root, "docs-manifest.yaml"), "w",
                      encoding="utf-8") as fh:
                fh.write(drifted)
            # gen_manifest --check disagrees (exit 1) ...
            self.assertEqual(gen_manifest.check(root), 1)
            # ... and audit() reports manifest-drift on the corpus subject.
            svc = _service(root)
            resp = svc.audit(target_id="*")
            drift = [f for f in resp["report"]["findings"]
                     if f["severity"] == "high" and "manifest" in f["description"].lower()]
            self.assertTrue(drift, resp["report"]["findings"])
            # drift is corpus-level: it surfaces even on the first batch
            svc2 = _service(root)
            part = svc2.audit(target_id="*", rescan_batch_ceiling=1)
            self.assertTrue(any("manifest" in f["description"].lower()
                                for f in part["report"]["findings"]))
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestEventRedaction(unittest.TestCase):
    def _emit_capturing(self, fn):
        out = io.StringIO()
        events = StdoutEventSink(out)
        fn(events)
        return out.getvalue()

    def test_no_corpus_text_in_events_or_registry(self):
        out = io.StringIO()
        svc = _service(FIXTURE_CORPUS, events=StdoutEventSink(out))
        resp = svc.audit(target_id="*")
        with open(os.path.join(FIXTURE_CORPUS, "docs", "en", "gamma",
                               "index.md"), encoding="utf-8") as fh:
            gamma_text = fh.read()
        self.assertIn(MARKER, gamma_text)  # sanity: fixture has marker
        blob = out.getvalue()
        for f in resp["report"]["findings"]:
            blob += json.dumps(f)
        registry_path = svc.registry.path
        with open(registry_path, encoding="utf-8") as fh:
            blob += fh.read()
        self.assertNotIn(MARKER, blob)

    def test_unknown_payload_field_rejected(self):
        def emit(events):
            events.emit("documenter.issue", {
                "audit_id": "a", "subject_id": "s", "severity": "low",
                "description": "d", "diff_text": "--- secret diff"})
        with self.assertRaises(StructuredError) as ctx:
            self._emit_capturing(emit)
        self.assertEqual(ctx.exception.error_category, "unknown")
        self.assertEqual(ctx.exception.next_action, "escalate")

    def test_missing_payload_field_rejected(self):
        def emit(events):
            events.emit("precheck.passed", {"audit_id": "a"})
        with self.assertRaises(StructuredError):
            self._emit_capturing(emit)

    def test_diff_text_cannot_enter_any_event(self):
        # diff_text is not a legal payload key in ANY declared schema.
        from documenter_service.adapters.stdout_events import EVENT_SCHEMAS
        for keys in EVENT_SCHEMAS.values():
            self.assertNotIn("diff_text", keys)

    def test_oversized_description_rejected(self):
        def emit(events):
            events.emit("documenter.issue", {
                "audit_id": "a", "subject_id": "s", "severity": "low",
                "description": "x" * 501})
        with self.assertRaises(StructuredError):
            self._emit_capturing(emit)


class TestCoverageHeader(unittest.TestCase):
    def test_partial_report_states_write_decision_impossible(self):
        svc = _service(FIXTURE_CORPUS)
        resp = svc.audit(target_id="*", rescan_batch_ceiling=2)
        self.assertEqual(resp["coverage"]["status"], "partial")
        self.assertTrue(resp["has_remaining"])
        header = resp["report"]["header"]
        self.assertIn("write decision cannot be made", header)
        self.assertIn(PARTIAL_WRITE_DECISION_NOTE, header)

    def test_complete_report_has_no_partial_claim(self):
        svc = _service(FIXTURE_CORPUS)
        resp = svc.audit(target_id="*", rescan_batch_ceiling=50)
        self.assertEqual(resp["coverage"]["status"], "complete")
        self.assertNotIn("PARTIAL", resp["report"]["header"])
        self.assertIsNone(resp["scan_cursor"])


class TestNoRuleFork(unittest.TestCase):
    def test_all_finding_rules_are_produced_by_tools_layer(self):
        # Names check_all.scan actually emits on the fixture corpus ...
        svc = _service(FIXTURE_CORPUS)
        resp = svc.audit(target_id="*")
        emitted_raw = {f["rule"] for f in check_all.scan(FIXTURE_CORPUS)}
        self.assertTrue(emitted_raw)
        # ... every rule name audit() maps comes from the dispatch's own
        # RULE_GROUPS sets (no invented rule namespace).
        for rule in emitted_raw:
            self.assertIn(rule, AUDIT_RULE_NAMES,
                          f"audit maps a rule outside check_all.RULE_GROUPS: {rule}")
        # and no finding survives with a rule key at all (Finding shape).
        for f in resp["report"]["findings"]:
            self.assertEqual(set(f), {"subject_id", "severity", "description",
                                      "suggested_action"})

    def test_module_never_claims_rules_1_to_6_coverage(self):
        # Regression guard for AGENTS.md §8: the package must never ASSERT
        # coverage of "rules 1-6"; only explicit NOT-claiming phrasing is
        # allowed to mention the string at all.
        pkg = os.path.join(REPO_ROOT, "documenter_service")
        offenders = []
        claim_re = re.compile(r"rules? 1[-\u2013]6")
        for dirpath, _dirs, files in os.walk(pkg):
            for name in files:
                if not name.endswith((".py", ".md")):
                    continue
                path = os.path.join(dirpath, name)
                with open(path, encoding="utf-8") as fh:
                    for lineno, line in enumerate(fh, 1):
                        for m in claim_re.finditer(line):
                            window = line[max(0, m.start() - 80):m.end() + 80]
                            if not re.search(
                                    r"never|not |NOT|non-claim|claim",
                                    window):
                                offenders.append(f"{path}:{lineno}: {line.strip()}")
        self.assertEqual(offenders, [])

    def test_severity_mapping_at_boundary(self):
        # internal warning (last-modified-deprecated on gamma) → medium;
        # internal low stays low; no finding carries a critical severity
        # (no critical producers in MVP).
        svc = _service(FIXTURE_CORPUS)
        resp = svc.audit(target_id="*")
        sevs = {f["description"]: f["severity"] for f in resp["report"]["findings"]}
        self.assertEqual(sevs["`Last Modified` field is deprecated "
                             "(derived from git; remove it)"], "medium")
        self.assertIn("low", {f["severity"] for f in resp["report"]["findings"]})
        self.assertNotIn("critical", {f["severity"] for f in resp["report"]["findings"]})


class TestCliCoreParity(unittest.TestCase):
    """CLI and direct-core invocations produce identical JSON except the
    volatile fields (audit_id, issued_at, scan_cursor tokens)."""

    def _cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = main(argv)
        return rc, out.getvalue(), err.getvalue()

    def _last_json(self, text):
        return json.loads(text.strip().splitlines()[-1])

    def test_status_parity(self):
        tmp = tempfile.mkdtemp()
        try:
            common = ["--root", FIXTURE_CORPUS]
            # fresh registries for both paths so last_audit is identical
            os.environ.pop("DOCUMENTER_DATA_DIR", None)
            svc = _service(FIXTURE_CORPUS)
            direct = svc.status()
            # CLI against the same registry via env var
            os.environ["DOCUMENTER_DATA_DIR"] = os.path.join(tmp, "cli-state")
            try:
                # run the audit twice through both surfaces first: audit_id/
                # issued_at differ, so compare the deterministic projection.
                rc, out, _ = self._cli(common + ["--status", "--json"])
                self.assertEqual(rc, 0)
                cli = self._last_json(out)
            finally:
                os.environ.pop("DOCUMENTER_DATA_DIR", None)
            # fresh empty registries: only last_audit differs structurally?
            # direct had no audits either → identical except nothing volatile
            cli["registry"].pop("last_audit")
            direct["registry"].pop("last_audit")
            self.assertEqual(cli, direct)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_audit_and_delegate_parity_via_env_registry(self):
        tmp = tempfile.mkdtemp()
        try:
            os.environ["DOCUMENTER_DATA_DIR"] = os.path.join(tmp, "state")
            try:
                rc, out, _ = self._cli(
                    ["--root", FIXTURE_CORPUS, "--audit", "--target", "*",
                     "--json"])
                self.assertEqual(rc, 0)
                cli_audit = self._last_json(out)
                rc, out, _ = self._cli(
                    ["--root", FIXTURE_CORPUS, "--status", "--json"])
                cli_status = self._last_json(out)
                import base64
                diff = base64.b64encode(
                    b"--- a/docs/en/alpha/index.md\n+++ b/docs/en/alpha/index.md\n"
                    b"@@ -1 +1 @@\n-|x|\n+|y|\n").decode()
                rc, out, _ = self._cli(
                    ["--root", FIXTURE_CORPUS, "--delegate-preview",
                     "--target", "alpha", "--change-type", "update",
                     "--trust-level", "safe", "--diff-base64", diff, "--json"])
                self.assertEqual(rc, 0)
                cli_del = self._last_json(out)
            finally:
                os.environ.pop("DOCUMENTER_DATA_DIR", None)

            # direct core over a parallel registry + same corpus
            svc = _service(FIXTURE_CORPUS)
            direct_audit = svc.audit(target_id="*")
            direct_status = svc.status()
            direct_del = svc.delegate(target_id="alpha", change_type="update",
                                      trust_level="safe", diff_input=diff,
                                      preview=True)

            # volatile: audit ids, timestamps, cursors
            for key in ("audit_id", "scan_cursor"):
                cli_audit.pop(key, None)
                direct_audit.pop(key, None)
            self.assertEqual(cli_audit, direct_audit)

            for s in (cli_status, direct_status):
                s["registry"].pop("last_audit")
            self.assertEqual(cli_status, direct_status)

            self.assertEqual(cli_del, direct_del)  # fully deterministic
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_delegate_preview_nonexistent_audit_id(self):
        """CLI --delegate-preview with --audit-id pointing to nonexistent id:
        exit code 2, JSON error with error_category=audit_mismatch."""
        import base64
        diff = base64.b64encode(
            b"--- a/docs/en/alpha/index.md\n"
            b"+++ b/docs/en/alpha/index.md\n"
            b"@@ -1 +1 @@\n"
            b"-|x|\n"
            b"+|y|\n").decode()
        rc, out, _ = self._cli([
            "--root", FIXTURE_CORPUS,
            "--delegate-preview",
            "--target", "alpha",
            "--change-type", "update",
            "--trust-level", "safe",
            "--diff-base64", diff,
            "--json",
            "--audit-id", "nonexistent-audit-uuid",
        ])
        self.assertEqual(rc, 2)
        error = self._last_json(out)
        self.assertEqual(error["error_category"], "audit_mismatch")
        self.assertEqual(error["next_action"], "rerun_audit")


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Read-before-use & sync-latency-budget tests (mvp-contract §2.1.3,
# mvp-interfaces §5)
# ---------------------------------------------------------------------------


class TestReadBeforeUse(unittest.TestCase):
    """mvp-contract §2.1.3: read-before-use hash stability loop."""

    def _build_service(self, root):
        """Minimal Service over *root* with in-memory events."""
        tmp = tempfile.mkdtemp()
        return Service(root,
                       registry=JsonlAuditRegistry(
                           os.path.join(tmp, "state")),
                       events=StdoutEventSink(io.StringIO()))

    def _record_audit_count(self, root):
        """Return the number of audit records in the registry."""
        # The Service creates its own temp registry, so read the file
        # directly from the temp dir we track.
        return 0  # placeholder — see individual tests below

    def test_stable_corpus_persists_one_record(self):
        """No file changes during scan → first pass stable → findings persisted.
        """
        from unittest.mock import patch
        _, root = _corpus_copy()
        tmp_dir = tempfile.mkdtemp()
        try:
            svc = Service(root,
                          registry=JsonlAuditRegistry(
                              os.path.join(tmp_dir, "state")),
                          events=StdoutEventSink(io.StringIO()))

            # Patch _raw_findings to verify it gets called exactly once
            from documenter_service.core import audit as audit_mod
            original_raw = audit_mod._raw_findings
            call_count = [0]

            def patched_raw(_root):
                call_count[0] += 1
                return original_raw(_root)

            with patch.object(audit_mod, '_raw_findings', patched_raw):
                resp = svc.audit(target_id="*")
                self.assertFalse(resp["has_remaining"])
                self.assertEqual(resp["coverage"]["status"], "complete")
                self.assertEqual(call_count[0], 1)

            # Verify exactly one audit record in the registry.
            records, status = svc.registry.read_all()
            audit_records = [r["data"] for r in records
                             if r["record_type"] == "audit_record"]
            self.assertEqual(len(audit_records), 1)
            self.assertEqual(audit_records[0]["scope"], "*")
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_hash_change_discards_first_pass_and_retries(self):
        """A file is modified between scan and hash-check → first pass
        discarded, second pass stable → findings from second pass persisted,
        exactly one audit_record."""
        from unittest.mock import patch
        _, root = _corpus_copy()
        tmp_dir = tempfile.mkdtemp()
        try:
            svc = Service(root,
                          registry=JsonlAuditRegistry(
                              os.path.join(tmp_dir, "state")),
                          events=StdoutEventSink(io.StringIO()))
            target_file = os.path.join(root, "docs", "en", "alpha",
                                       "index.md")

            from documenter_service.core import audit as audit_mod
            original_raw = audit_mod._raw_findings
            first_call = [True]

            def patched_raw(_root):
                if first_call[0]:
                    first_call[0] = False
                    # Mutate the file during the "scan" (first call): drop the
                    # changelog-path line → deterministic changelog-path-missing
                    # finding for alpha in the re-scan.
                    with open(target_file, encoding="utf-8") as f:
                        text = f.read()
                    text = "\n".join(
                        ln for ln in text.splitlines()
                        if not ln.startswith("changelog-path:")) + "\n"
                    with open(target_file, "w", encoding="utf-8") as f:
                        f.write(text)
                return original_raw(_root)

            with patch.object(audit_mod, '_raw_findings', patched_raw):
                resp = svc.audit(target_id="*")
                self.assertFalse(resp["has_remaining"])

            # Verify exactly one audit record was persisted (from second pass).
            records, _ = svc.registry.read_all()
            audit_records = [r["data"] for r in records
                             if r["record_type"] == "audit_record"]
            self.assertEqual(len(audit_records), 1,
                             f"expected 1 record, got {len(audit_records)}")

            # The second pass re-scans after the mutation, so the findings
            # must carry the changelog-path-missing finding for alpha.
            finding_ids = [f["subject_id"]
                           for f in audit_records[0]["findings"]]
            self.assertIn("alpha", finding_ids)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_repeated_hash_change_raises_structured_error(self):
        """File changes on every pass → 2 passes exhaust → StructuredError
        with error_category=hash_mismatch, next_action=rerun_audit."""
        from unittest.mock import patch
        _, root = _corpus_copy()
        tmp_dir = tempfile.mkdtemp()
        try:
            svc = Service(root,
                          registry=JsonlAuditRegistry(
                              os.path.join(tmp_dir, "state")),
                          events=StdoutEventSink(io.StringIO()))
            target_file = os.path.join(root, "docs", "en", "alpha",
                                       "index.md")

            from documenter_service.core import audit as audit_mod
            original_raw = audit_mod._raw_findings
            call_count = [0]

            def patched_raw(_root):
                call_count[0] += 1
                # Mutate the file on EVERY call (including retries).
                with open(target_file, "a", encoding="utf-8") as f:
                    f.write(f"\n# drift-{call_count[0]}\n")
                return original_raw(_root)

            with patch.object(audit_mod, '_raw_findings', patched_raw):
                with self.assertRaises(StructuredError) as ctx:
                    svc.audit(target_id="*")
                self.assertEqual(ctx.exception.error_category, "hash_mismatch")
                self.assertEqual(ctx.exception.next_action, "rerun_audit")
                self.assertIn("corpus changed repeatedly",
                              ctx.exception.message.lower())
                # Zero records persisted (the failing pass is discarded).
                self.assertEqual(call_count[0], 2)

            records, _ = svc.registry.read_all()
            audit_records = [r["data"] for r in records
                             if r["record_type"] == "audit_record"]
            self.assertEqual(len(audit_records), 0)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestSyncLatencyBudget(unittest.TestCase):
    """mvp-interfaces §5: sync_latency_budget_ms enforcement."""

    def test_audit_budget_exceeded_raises_gate_failure(self):
        """sync_latency_budget_ms=0 → deadline already past → StructuredError
        with error_category=gate_failure and 'sync_latency_budget_ms' in
        the message."""
        _, root = _corpus_copy()
        tmp_dir = tempfile.mkdtemp()
        try:
            svc = Service(root,
                          registry=JsonlAuditRegistry(
                              os.path.join(tmp_dir, "state")),
                          events=StdoutEventSink(io.StringIO()))
            with self.assertRaises(StructuredError) as ctx:
                svc.audit(target_id="*", sync_latency_budget_ms=0)
            self.assertEqual(ctx.exception.error_category, "gate_failure")
            self.assertIn("sync_latency_budget_ms=0", ctx.exception.message)
            self.assertEqual(ctx.exception.next_action, "rerun_audit")
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_audit_default_budget_works(self):
        """Default sync_latency_budget_ms=30000 should allow audit to
        complete on a small fixture corpus."""
        _, root = _corpus_copy()
        tmp_dir = tempfile.mkdtemp()
        try:
            svc = Service(root,
                          registry=JsonlAuditRegistry(
                              os.path.join(tmp_dir, "state")),
                          events=StdoutEventSink(io.StringIO()))
            resp = svc.audit(target_id="*")
            self.assertFalse(resp["has_remaining"])
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_delegate_preview_budget_exceeded(self):
        """sync_latency_budget_ms=0 on delegate_preview → gate_failure at
        the first budget check (before scope resolution)."""
        _, root = _corpus_copy()
        tmp_dir = tempfile.mkdtemp()
        try:
            svc = Service(root,
                          registry=JsonlAuditRegistry(
                              os.path.join(tmp_dir, "state")),
                          events=StdoutEventSink(io.StringIO()))
            import base64
            diff = base64.b64encode(
                b"--- a/docs/en/alpha/index.md\n"
                b"+++ b/docs/en/alpha/index.md\n"
                b"@@ -1 +1 @@\n"
                b"-old\n"
                b"+new\n").decode()
            with self.assertRaises(StructuredError) as ctx:
                svc.delegate(
                    target_id="alpha",
                    change_type="update",
                    trust_level="review",
                    diff_input=diff,
                    preview=True,
                    sync_latency_budget_ms=0)
            self.assertEqual(ctx.exception.error_category, "gate_failure")
            self.assertIn("sync_latency_budget_ms=0", ctx.exception.message)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_delegate_preview_default_budget_works(self):
        """Default budget should allow delegate_preview to complete."""
        _, root = _corpus_copy()
        tmp_dir = tempfile.mkdtemp()
        try:
            svc = Service(root,
                          registry=JsonlAuditRegistry(
                              os.path.join(tmp_dir, "state")),
                          events=StdoutEventSink(io.StringIO()))
            import base64
            diff = base64.b64encode(
                b"--- a/docs/en/alpha/index.md\n"
                b"+++ b/docs/en/alpha/index.md\n"
                b"@@ -1 +1 @@\n"
                b"-old\n"
                b"+new\n").decode()
            resp = svc.delegate(
                target_id="alpha",
                change_type="update",
                trust_level="review",
                diff_input=diff,
                preview=True)
            self.assertEqual(resp["next_action"], "preview_only")
            self.assertIn("diff_hash", resp)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)

