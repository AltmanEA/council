"""CLI Tier 2+ write API tests (subprocess-based).

Tests --delegate-write, --approve, --override-gate via real CLI subprocess.
Uses tmp corpus + policy + briefing like TestServiceWriteBranch but through
the CLI, with env DOCUMENTER_POLICY_PATH/DOCUMENTER_DATA_DIR/COUNCIL_OPERATOR_ID.

Run with: python3 -m unittest tests.test_documenter_cli_tier2
"""
import base64
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
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import yaml  # noqa: E402

from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry  # noqa: E402
from documenter_service.core.errors import StructuredError  # noqa: E402

FIXTURE_CORPUS = os.path.join(REPO_ROOT, "tests", "fixtures", "documenter",
                              "corpus")


# ---------------------------------------------------------------------------
# Helpers (mimic TestServiceWriteBranch recipe)
# ---------------------------------------------------------------------------

def _make_tier2_policy_fields(briefing_path=None):
    return {
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
        "lock_wait_timeout": 5,
    }


def _write_policy(tmpdir, tier=2):
    ops = ([{"change_type": "update", "targets": ["alpha"],
             "trust_level": "safe"}] if tier >= 2 else [])
    fields = {
        "version": "0.2.0",
        "active_tier": tier,
        "allowed_operations": ops,
        "audit_freshness": 30,
        "approval_expiry_window": 30,
        "max_diff_bytes": 524288,
        "lock_wait_timeout": 5,
    }
    if tier >= 2:
        fields["briefing_ref"] = os.path.join(tmpdir, "_briefing.md")
    doc = {"documenter_policy": fields}
    p = os.path.join(tmpdir, "pol.yml")
    with open(p, "w") as f:
        yaml.safe_dump(doc, f)
    return p


def _write_briefing(tmpdir):
    p = os.path.join(tmpdir, "_briefing.md")
    with open(p, "w") as f:
        f.write("# Briefing\n\nAuthorised operational context.\n")
    return p


def _make_corpus(tmpdir):
    corpus = os.path.join(tmpdir, "corpus")
    os.makedirs(os.path.join(corpus, "docs", "en", "alpha"))
    with open(os.path.join(corpus, "docs", "en", "alpha", "index.md"), "w") as f:
        f.write(
            "# Alpha\n"
            "id: alpha\n"
            "Version: 1.0.0\n"
            "Status: active\n"
            "Abstraction: protocol\n"
            "changelog-path: CHANGELOGS/alpha.changes.md\n"
        )
    os.makedirs(os.path.join(corpus, "CHANGELOGS"))
    with open(os.path.join(corpus, "CHANGELOGS", "alpha.changes.md"), "w") as f:
        f.write("<!-- CHANGES 1.0.0: initial -->\n")
    # ADR-013: surface-readiness sentinel — Tier 2+ CLI paths require it;
    # tier < 2 refusal tests still refuse at the first interlock level.
    sentinel = os.path.join(corpus, "documenter", ".operator_surface_ready")
    os.makedirs(os.path.dirname(sentinel), exist_ok=True)
    with open(sentinel, "w") as f:
        f.write("")
    # Initialize git repo for the pre-change git snapshot guard.
    subprocess.run(
        ["git", "init", "-q", corpus],
        capture_output=True, text=True, timeout=10, shell=False,
    )
    subprocess.run(
        ["git", "-C", corpus, "config", "user.email", "test@council.local"],
        capture_output=True, text=True, timeout=10, shell=False,
    )
    subprocess.run(
        ["git", "-C", corpus, "config", "user.name", "Test"],
        capture_output=True, text=True, timeout=10, shell=False,
    )
    subprocess.run(
        ["git", "-C", corpus, "add", "-A"],
        capture_output=True, text=True, timeout=10, shell=False,
    )
    subprocess.run(
        ["git", "-C", corpus, "commit", "-q", "-m", "fixture baseline"],
        capture_output=True, text=True, timeout=10, shell=False,
    )
    return corpus


def _diff_for_alpha():
    """Create a diff that changes alpha's changelog-path."""
    old = (
        "+++ b/docs/en/alpha/index.md\n"
        "@@ -1,6 +1,6 @@\n"
        " # Alpha\n"
        " id: alpha\n"
        " Version: 1.0.0\n"
        " Status: active\n"
        " Abstraction: protocol\n"
        "-changelog-path: CHANGELOGS/alpha.changes.md\n"
        "+changelog-path: CHANGELOGS/alpha.changes.updated.md\n"
    )
    return base64.b64encode(old.encode("utf-8")).decode("ascii")


def _run_cli(argv, env_extra=None):
    """Run a CLI subprocess, return (last_stdout_json, returncode)."""
    merged_env = dict(os.environ)
    merged_env["PYTHONPATH"] = REPO_ROOT + os.pathsep + merged_env.get("PYTHONPATH", "")
    if env_extra:
        merged_env.update(env_extra)
    proc = subprocess.Popen(
        [sys.executable, "-m", "documenter_service"] + argv,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=merged_env, text=True)
    out, _err = proc.communicate()
    lines = [l for l in out.strip().splitlines() if l.strip()]
    parsed = []
    for line in lines:
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    last = parsed[-1] if parsed else None
    return last, proc.returncode


# ---------------------------------------------------------------------------
# Test 1: --delegate-write without tier2 policy → tier_interlock
# ---------------------------------------------------------------------------

class TestCLITier2Refusal(unittest.TestCase):
    """Tests that Tier 2+ features refuse without proper policy."""

    def test_delegate_write_tier1_interlock(self):
        """--delegate-write with tier1 policy (default) → exit 2, tier_interlock."""
        tmpdir = tempfile.mkdtemp()
        try:
            corpus = _make_corpus(tmpdir)
            policy_path = _write_policy(tmpdir, tier=1)
            data_dir = os.path.join(tmpdir, "state")
            argv = [
                "--delegate-write",
                "--root", corpus,
                "--target", "alpha",
                "--change-type", "update",
                "--trust-level", "safe",
                "--diff-base64", _diff_for_alpha(),
                "--json",
            ]
            result, rc = _run_cli(argv, env_extra={
                "DOCUMENTER_POLICY_PATH": policy_path,
                "DOCUMENTER_DATA_DIR": data_dir,
                "COUNCIL_OPERATOR_ID": "op-proposer",
            })
            self.assertEqual(rc, 2)
            self.assertIsNotNone(result)
            self.assertEqual(result["error_category"], "tier_interlock")
            self.assertEqual(result["next_action"], "preview_denied")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 2: Full happy path — audit → delegate-write → approve → apply
# ---------------------------------------------------------------------------

class TestCLIFullLifecycle(unittest.TestCase):
    """Full lifecycle: audit → delegate-write → approve → apply (file changed)."""

    def test_delegate_approve_apply(self):
        tmpdir = tempfile.mkdtemp()
        try:
            corpus = _make_corpus(tmpdir)
            briefing = _write_briefing(tmpdir)
            policy_path = _write_policy(tmpdir, tier=2)
            data_dir = os.path.join(tmpdir, "state")

            diff_b64 = _diff_for_alpha()

            # Step 1: audit to get audit_id
            resp, rc = _run_cli([
                "--audit", "--root", corpus,
                "--target", "*", "--json"],
                env_extra={
                    "DOCUMENTER_POLICY_PATH": policy_path,
                    "DOCUMENTER_DATA_DIR": data_dir,
                })
            self.assertEqual(rc, 0)
            self.assertIsNotNone(resp)
            audit_id = resp["audit_id"]

            # Step 2: delegate-write → await_approval
            resp, rc = _run_cli([
                "--delegate-write", "--root", corpus,
                "--target", "alpha",
                "--change-type", "update",
                "--trust-level", "safe",
                "--diff-base64", diff_b64,
                "--audit-id", audit_id,
                "--json"],
                env_extra={
                    "DOCUMENTER_POLICY_PATH": policy_path,
                    "DOCUMENTER_DATA_DIR": data_dir,
                    "COUNCIL_OPERATOR_ID": "op-sandbox",
                })
            self.assertEqual(rc, 0)
            self.assertEqual(resp["next_action"], "await_approval")
            self.assertTrue(resp["approval_required"])
            approval_id = resp["approval_id"]

            # Verify file NOT changed yet
            with open(os.path.join(corpus, "docs", "en", "alpha", "index.md")) as f:
                content = f.read()
            self.assertIn("CHANGELOGS/alpha.changes.md", content)

            # Step 3: approve with different operator
            resp, rc = _run_cli([
                "--approve", "--root", corpus,
                "--approval-id", approval_id,
                "--json"],
                env_extra={
                    "DOCUMENTER_POLICY_PATH": policy_path,
                    "DOCUMENTER_DATA_DIR": data_dir,
                    "COUNCIL_OPERATOR_ID": "op-approver",
                })
            self.assertEqual(rc, 0)
            self.assertEqual(resp["decision"], "approved")

            # Step 4: delegate-write with approval_id → write_applied
            resp, rc = _run_cli([
                "--delegate-write", "--root", corpus,
                "--target", "alpha",
                "--change-type", "update",
                "--trust-level", "safe",
                "--diff-base64", diff_b64,
                "--audit-id", audit_id,
                "--approval-id", approval_id,
                "--json"],
                env_extra={
                    "DOCUMENTER_POLICY_PATH": policy_path,
                    "DOCUMENTER_DATA_DIR": data_dir,
                    "COUNCIL_OPERATOR_ID": "op-applier",
                })
            self.assertEqual(rc, 0)
            self.assertEqual(resp["next_action"], "write_applied")
            self.assertTrue(resp.get("applied", False))

            # Verify file WAS changed
            with open(os.path.join(corpus, "docs", "en", "alpha", "index.md")) as f:
                content = f.read()
            self.assertIn("CHANGELOGS/alpha.changes.updated.md", content)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 3: Self-approval denied
# ---------------------------------------------------------------------------

class TestCLISelfApproval(unittest.TestCase):
    """--approve with same operator as proposer → gate_failure self-approval."""

    def test_self_approval_denied(self):
        tmpdir = tempfile.mkdtemp()
        try:
            corpus = _make_corpus(tmpdir)
            briefing = _write_briefing(tmpdir)
            policy_path = _write_policy(tmpdir, tier=2)
            data_dir = os.path.join(tmpdir, "state")
            diff_b64 = _diff_for_alpha()

            # Audit
            resp, _ = _run_cli([
                "--audit", "--root", corpus,
                "--target", "*", "--json"],
                env_extra={
                    "DOCUMENTER_POLICY_PATH": policy_path,
                    "DOCUMENTER_DATA_DIR": data_dir,
                })
            audit_id = resp["audit_id"]

            # delegate-write
            resp, _ = _run_cli([
                "--delegate-write", "--root", corpus,
                "--target", "alpha",
                "--change-type", "update",
                "--trust-level", "safe",
                "--diff-base64", diff_b64,
                "--audit-id", audit_id,
                "--json"],
                env_extra={
                    "DOCUMENTER_POLICY_PATH": policy_path,
                    "DOCUMENTER_DATA_DIR": data_dir,
                    "COUNCIL_OPERATOR_ID": "op-same",
                })
            approval_id = resp["approval_id"]

            # approve with same operator → gate_failure self-approval
            resp, rc = _run_cli([
                "--approve", "--root", corpus, "--approval-id", approval_id,
                "--json"],
                env_extra={
                    "DOCUMENTER_POLICY_PATH": policy_path,
                    "DOCUMENTER_DATA_DIR": data_dir,
                    "COUNCIL_OPERATOR_ID": "op-same",
                })
            self.assertEqual(rc, 2)
            self.assertEqual(resp["error_category"], "gate_failure")
            self.assertIn("self-approval", resp["message"].lower())
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 4: approve without COUNCIL_OPERATOR_ID
# ---------------------------------------------------------------------------

class TestCLIAuthIngress(unittest.TestCase):
    """--approve without COUNCIL_OPERATOR_ID → exit 2 unknown."""

    def test_approve_no_operator(self):
        tmpdir = tempfile.mkdtemp()
        try:
            corpus = _make_corpus(tmpdir)
            policy_path = _write_policy(tmpdir, tier=2)
            data_dir = os.path.join(tmpdir, "state")

            resp, rc = _run_cli([
                "--approve", "--approval-id", "app-1",
                "--json"],
                env_extra={
                    "DOCUMENTER_POLICY_PATH": policy_path,
                    "DOCUMENTER_DATA_DIR": data_dir,
                })
            self.assertEqual(rc, 2)
            self.assertEqual(resp["error_category"], "unknown")
            self.assertIn("COUNCIL_OPERATOR_ID", resp["message"])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 5: --override-gate
# ---------------------------------------------------------------------------

class TestCLIOverrideGate(unittest.TestCase):
    """override_gate: tier_interlock on tier1, happy path on tier2."""

    def test_override_gate_tier1_interlock(self):
        """--override-gate on tier1 → tier_interlock."""
        tmpdir = tempfile.mkdtemp()
        try:
            corpus = _make_corpus(tmpdir)
            policy_path = _write_policy(tmpdir, tier=1)
            data_dir = os.path.join(tmpdir, "state")

            resp, rc = _run_cli([
                "--override-gate",
                "--root", corpus,
                "--target", "alpha",
                "--diff-hash", "sha256:" + "a" * 64,
                "--reason", "test override",
                "--json"],
                env_extra={
                    "DOCUMENTER_POLICY_PATH": policy_path,
                    "DOCUMENTER_DATA_DIR": data_dir,
                    "COUNCIL_OPERATOR_ID": "op-override",
                })
            self.assertEqual(rc, 2)
            self.assertEqual(resp["error_category"], "tier_interlock")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_override_gate_tier2_success(self):
        """--override-gate on tier2 with clean audit → override_id + rerun_audit."""
        tmpdir = tempfile.mkdtemp()
        try:
            corpus = _make_corpus(tmpdir)
            briefing = _write_briefing(tmpdir)
            policy_path = _write_policy(tmpdir, tier=2)
            data_dir = os.path.join(tmpdir, "state")

            # Do an audit first to get an audit_id
            resp, _ = _run_cli([
                "--audit", "--root", corpus,
                "--target", "*", "--json"],
                env_extra={
                    "DOCUMENTER_POLICY_PATH": policy_path,
                    "DOCUMENTER_DATA_DIR": data_dir,
                })
            audit_id = resp["audit_id"]

            # Now override_gate
            resp, rc = _run_cli([
                "--override-gate",
                "--root", corpus,
                "--target", "alpha",
                "--diff-hash", "sha256:" + "b" * 64,
                "--reason", "test override reason",
                "--audit-id", audit_id,
                "--json"],
                env_extra={
                    "DOCUMENTER_POLICY_PATH": policy_path,
                    "DOCUMENTER_DATA_DIR": data_dir,
                    "COUNCIL_OPERATOR_ID": "op-override",
                })
            self.assertEqual(rc, 0)
            self.assertIn("override_id", resp)
            self.assertEqual(resp["target_id"], "alpha")
            self.assertEqual(resp["next_action"], "rerun_audit")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_override_gate_blocking_finding(self):
        """--override-gate with critical finding in audit → blocking_finding."""
        tmpdir = tempfile.mkdtemp()
        try:
            corpus = _make_corpus(tmpdir)
            briefing = _write_briefing(tmpdir)
            policy_path = _write_policy(tmpdir, tier=2)
            data_dir = os.path.join(tmpdir, "state")

            # Manually seed a critical finding in the audit record
            reg = JsonlAuditRegistry(data_dir)
            audit_record = {
                "audit_id": "aid-seed",
                "issued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "scope": "*",
                "findings": [
                    {
                        "subject_id": "alpha",
                        "severity": "critical",
                        "description": "Critical issue in alpha",
                        "suggested_action": "fix alpha",
                    }
                ],
                "scanned_ids": ["alpha"],
                "has_remaining": False,
            }
            reg.append("audit_record", audit_record)

            # override_gate on this audit → blocking_finding
            resp, rc = _run_cli([
                "--override-gate",
                "--root", corpus,
                "--target", "alpha",
                "--diff-hash", "sha256:" + "c" * 64,
                "--reason", "test override with critical",
                "--audit-id", "aid-seed",
                "--json"],
                env_extra={
                    "DOCUMENTER_POLICY_PATH": policy_path,
                    "DOCUMENTER_DATA_DIR": data_dir,
                    "COUNCIL_OPERATOR_ID": "op-override",
                })
            self.assertEqual(rc, 2)
            self.assertEqual(resp["error_category"], "blocking_finding")
            self.assertEqual(resp["next_action"], "resolve_finding")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI --reconcile tests (Service-level, not subprocess — manual intent
# construction to simulate leftover state)
# ---------------------------------------------------------------------------

class TestReconcileCli(unittest.TestCase):
    """CLI --reconcile: Service.reconcile + JSON output + exit 0."""

    def _get_alpha_hash(self, tmpdir):
        """Return the sha256 of the alpha index.md file."""
        corpus = os.path.join(tmpdir, "corpus")
        alpha_path = os.path.join(corpus, "docs", "en", "alpha", "index.md")
        with open(alpha_path, "rb") as f:
            return "sha256:" + __import__("hashlib").sha256(f.read()).hexdigest()

    def test_reconcile_leftover_intent_resolved(self):
        """--reconcile with a leftover staged intent whose source hash
        matches → exit 0, no needs_attention (resolved silently).

        The reconcile function silently resolves clean intents.
        """
        tmpdir = tempfile.mkdtemp()
        try:
            corpus = _make_corpus(tmpdir)
            briefing = _write_briefing(tmpdir)
            policy_path = _write_policy(tmpdir, tier=2)
            data_dir = os.path.join(tmpdir, "state")

            # Compute the actual file hash so reconcile sees a match.
            alpha_sha = self._get_alpha_hash(tmpdir)

            # Manually create a leftover intent (unresolved) in the
            # registry — mimicking a crash between stage and rename.
            reg = JsonlAuditRegistry(data_dir)
            intent_record = {
                "target_ids": ["alpha"],
                "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "per_file_sha256": {"alpha": alpha_sha},
                "resolved": False,
                "git_snapshot": {},
            }
            reg.append("intent_record", intent_record)

            # Run --reconcile via CLI (subprocess).
            resp, rc = _run_cli([
                "--reconcile", "--root", corpus, "--json"],
                env_extra={
                    "DOCUMENTER_POLICY_PATH": policy_path,
                    "DOCUMENTER_DATA_DIR": data_dir,
                })
            self.assertEqual(rc, 0)
            self.assertIn("resolutions", resp)
            self.assertIn("counts", resp)
            # Clean resolution: needs_attention is false (no resolution
            # dicts produced for silently-resolved intents).
            self.assertFalse(resp["needs_attention"])
            self.assertEqual(resp["counts"]["needs_attention"], 0)
            self.assertEqual(resp["counts"]["reconciled"], 1)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_reconcile_noop_on_second_run(self):
        """--reconcile a second time → already no unresolved intents (in the
        subprocess that ran the first reconcile), counts all zero."""
        tmpdir = tempfile.mkdtemp()
        try:
            corpus = _make_corpus(tmpdir)
            briefing = _write_briefing(tmpdir)
            policy_path = _write_policy(tmpdir, tier=2)
            data_dir = os.path.join(tmpdir, "state")

            # Create a leftover intent and reconcile once.
            alpha_sha = self._get_alpha_hash(tmpdir)
            reg = JsonlAuditRegistry(data_dir)
            intent_record = {
                "target_ids": ["alpha"],
                "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "per_file_sha256": {"alpha": alpha_sha},
                "resolved": False,
                "git_snapshot": {},
            }
            reg.append("intent_record", intent_record)

            # First reconcile
            _, rc1 = _run_cli(["--reconcile", "--root", corpus, "--json"],
                              env_extra={
                                  "DOCUMENTER_POLICY_PATH": policy_path,
                                  "DOCUMENTER_DATA_DIR": data_dir,
                              })
            self.assertEqual(rc1, 0)

            # Second reconcile → the first run appended a resolved copy of the
            # intent; latest-per-intent selection masks the original record,
            # so there is nothing left to resolve and counts are all zero.
            resp2, rc2 = _run_cli(["--reconcile", "--root", corpus, "--json"],
                                   env_extra={
                                       "DOCUMENTER_POLICY_PATH": policy_path,
                                       "DOCUMENTER_DATA_DIR": data_dir,
                                   })
            self.assertEqual(rc2, 0)
            self.assertEqual(len(resp2["resolutions"]), 0)
            self.assertEqual(resp2["counts"]["reconciled"], 0)
            self.assertEqual(resp2["counts"]["needs_attention"], 0)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


    def test_reconcile_hash_mismatch_needs_attention(self):
        """--reconcile with an unresolved intent whose per_file_sha256 no
        longer matches the file on disk → exit 0, needs_attention=true,
        counts.needs_attention>=1 (needs_attention is data, not refusal)."""
        tmpdir = tempfile.mkdtemp()
        try:
            corpus = _make_corpus(tmpdir)
            briefing = _write_briefing(tmpdir)
            policy_path = _write_policy(tmpdir, tier=2)
            data_dir = os.path.join(tmpdir, "state")

            reg = JsonlAuditRegistry(data_dir)
            intent_record = {
                "target_ids": ["alpha"],
                "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                # Wrong hash → mismatch against the actual file.
                "per_file_sha256": {"alpha": "sha256:" + "f" * 64},
                "resolved": False,
                "git_snapshot": {},
            }
            reg.append("intent_record", intent_record)

            resp, rc = _run_cli([
                "--reconcile", "--root", corpus, "--json"],
                env_extra={
                    "DOCUMENTER_POLICY_PATH": policy_path,
                    "DOCUMENTER_DATA_DIR": data_dir,
                })
            # Exit code stays 0 per decision E0.1 — status is in JSON.
            self.assertEqual(rc, 0)
            self.assertTrue(resp["needs_attention"])
            self.assertGreaterEqual(resp["counts"]["needs_attention"], 1)
            statuses = [r.get("status") for r in resp["resolutions"]]
            self.assertIn("needs_attention", statuses)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# DOCUMENTER_LOG_LEVEL — stderr warning filter helper (P.12f)
# ---------------------------------------------------------------------------


def _run_cli_stderr(argv, env_extra=None):
    """Run a CLI subprocess, return (last_stdout_json, stderr_text, returncode)."""
    merged_env = dict(os.environ)
    merged_env["PYTHONPATH"] = REPO_ROOT + os.pathsep + merged_env.get("PYTHONPATH", "")
    if env_extra:
        merged_env.update(env_extra)
    proc = subprocess.Popen(
        [sys.executable, "-m", "documenter_service"] + argv,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=merged_env, text=True)
    out, err = proc.communicate()
    lines = [l for l in out.strip().splitlines() if l.strip()]
    parsed = []
    for line in lines:
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    last = parsed[-1] if parsed else None
    return last, err, proc.returncode


class TestDocumenterLogLevel(unittest.TestCase):
    """DOCUMENTER_LOG_LEVEL filters _stderr_log output (P.12f).

    A broken policy triggers a degradation warning via _stderr_log.
    The warning should appear when DOCUMENTER_LOG_LEVEL >= warn (default info),
    and be suppressed when DOCUMENTER_LOG_LEVEL = error.

    The warning is emitted in Service.delegate(preview=True) path.
    """

    def _make_broken_policy_env(self, tmpdir):
        """Write a policy file with an invalid tier to trigger the warning."""
        policy_path = os.path.join(tmpdir, "documenter_policy.yml")
        with open(policy_path, "w") as f:
            yaml.dump({
                "documenter_policy": {
                    "version": "0.2.0",
                    "active_tier": "invalid_tier",  # will fail load
                }
            }, f)
        return policy_path

    def test_stderr_log_default_info_shows_warning(self):
        """Default (no env) → policy warning on stderr (level info ≥ info).
        Uses --delegate-preview which triggers the policy warning."""
        tmpdir = tempfile.mkdtemp()
        try:
            policy_path = self._make_broken_policy_env(tmpdir)
            corpus = os.path.join(tmpdir, "docs", "en", "alpha")
            os.makedirs(corpus, exist_ok=True)
            with open(os.path.join(corpus, "index.md"), "w") as f:
                f.write("# Alpha\nid: alpha\n")
            _, stderr, _ = _run_cli_stderr(
                ["--delegate-preview", "--root", tmpdir, "--target", "alpha",
                 "--change-type", "update", "--trust-level", "safe",
                 "--diff-base64", "ZABj"],  # simple base64 payload
                env_extra={"DOCUMENTER_POLICY_PATH": policy_path})
            self.assertIn("WARNING", stderr)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_stderr_log_error_filters_warning(self):
        """DOCUMENTER_LOG_LEVEL=error → warning suppressed (warn < error)."""
        tmpdir = tempfile.mkdtemp()
        try:
            policy_path = self._make_broken_policy_env(tmpdir)
            corpus = os.path.join(tmpdir, "docs", "en", "alpha")
            os.makedirs(corpus, exist_ok=True)
            with open(os.path.join(corpus, "index.md"), "w") as f:
                f.write("# Alpha\nid: alpha\n")
            _, stderr, _ = _run_cli_stderr(
                ["--delegate-preview", "--root", tmpdir, "--target", "alpha",
                 "--change-type", "update", "--trust-level", "safe",
                 "--diff-base64", "ZABj"],
                env_extra={"DOCUMENTER_POLICY_PATH": policy_path,
                           "DOCUMENTER_LOG_LEVEL": "error"})
            self.assertNotIn("WARNING", stderr)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_stderr_log_invalid_level_falls_back_to_info(self):
        """DOCUMENTER_LOG_LEVEL=<garbage> → falls back to info (shows warning)."""
        tmpdir = tempfile.mkdtemp()
        try:
            policy_path = self._make_broken_policy_env(tmpdir)
            corpus = os.path.join(tmpdir, "docs", "en", "alpha")
            os.makedirs(corpus, exist_ok=True)
            with open(os.path.join(corpus, "index.md"), "w") as f:
                f.write("# Alpha\nid: alpha\n")
            _, stderr, _ = _run_cli_stderr(
                ["--delegate-preview", "--root", tmpdir, "--target", "alpha",
                 "--change-type", "update", "--trust-level", "safe",
                 "--diff-base64", "ZABj"],
                env_extra={"DOCUMENTER_POLICY_PATH": policy_path,
                           "DOCUMENTER_LOG_LEVEL": "mushroom_level_???!!!"})
            self.assertIn("WARNING", stderr)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Usage refusals as structured responses (fix plan p.24)
# ---------------------------------------------------------------------------

class TestCLIUsageRefusalJson(unittest.TestCase):
    """Mandatory-argument mistakes are refusals: JSON object on stdout
    (last-line contract), exit 2 — not a bare stderr ERROR line."""

    def test_approve_without_approval_id_json_refusal(self):
        tmpdir = tempfile.mkdtemp()
        try:
            corpus = _make_corpus(tmpdir)
            result, rc = _run_cli(
                ["--approve", "--root", corpus, "--json"],
                env_extra={"COUNCIL_OPERATOR_ID": "op-user1"})
            self.assertEqual(rc, 2)
            self.assertIsNotNone(result, "refusal JSON must be on stdout")
            self.assertEqual(result["error_category"], "unknown")
            self.assertIn("--approval-id", result["message"])
            self.assertEqual(result["next_action"], "preview_denied")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_delegate_write_missing_diff_json_refusal(self):
        tmpdir = tempfile.mkdtemp()
        try:
            corpus = _make_corpus(tmpdir)
            result, rc = _run_cli(
                ["--delegate-write", "--root", corpus, "--json",
                 "--target", "alpha", "--change-type", "update",
                 "--trust-level", "safe"],
                env_extra={"COUNCIL_OPERATOR_ID": "op-user1"})
            self.assertEqual(rc, 2)
            self.assertIsNotNone(result)
            self.assertEqual(result["error_category"], "unknown")
            self.assertIn("--diff-base64", result["message"])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
