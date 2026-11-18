"""Tests for delegate_consent orchestrator.

Tests tools/delegate_consent.py which couples the operator consent terminal
(tools/consent_terminal.py) with the Documenter Service CLI.

Service calls are mocked via unittest.mock.patch on subprocess.run.
Real consent_terminal ops use TemporaryDirectory as state_root.

ANTI-REVERSED-TDD: delegate_consent.py does NOT exist yet — tests that
need it fail with ModuleNotFoundError (red baseline).

Run:  python3 -m unittest tests.test_delegate_consent -v
"""
from __future__ import annotations

import base64
import hashlib
import hmac as hmac_mod
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

# ---------------------------------------------------------------------------
# Repo convention: insert tools/ on sys.path
# ---------------------------------------------------------------------------
_WT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_WT_ROOT, "tools"))
sys.path.insert(0, _WT_ROOT)

import consent_terminal as ct  # noqa: E402  real consent API (not mocked)

# ---------------------------------------------------------------------------
# Paths relative to state_root
# ---------------------------------------------------------------------------
_DIFFS = os.path.join("documenter", "intent", "diffs")
_LINK = os.path.join("documenter", "intent", "delegate_consent_link.json")
_DRAFT = os.path.join("documenter", "intent", "consent_draft.json")
_APPROVALS = os.path.join("documenter", "intent", "approvals.jsonl")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_SECRET = "test-secret"
_OPERATOR_ID = "op-tester"
_TARGET_ID = "docs/en/foo/index.md"
_DIFF_CONTENT = "--- docs/en/foo/index.md\n+++ docs/en/foo/index.md\n@@ -1 +1 @@\n-Old\n+New\n"


def _make_state():
    td = tempfile.TemporaryDirectory()
    sd = td.name
    os.makedirs(os.path.join(sd, _DIFFS), exist_ok=True)
    os.makedirs(os.path.join(sd, "documenter", "intent"), exist_ok=True)
    return td, sd


def _write_draft(state_root, target=_TARGET_ID, summary="Update foo",
                 tier="safe", diff_file="foo.diff"):
    dp = os.path.join(state_root, _DRAFT)
    with open(dp, "w") as fh:
        json.dump({"target_path": target, "summary": summary,
                   "tier": tier, "diff_file": diff_file}, fh)
    df = os.path.join(state_root, _DIFFS, diff_file)
    with open(df, "w") as fh:
        fh.write(_DIFF_CONTENT)
    return dp, df


def _sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def _b64(data):
    return base64.b64encode(data.encode()).decode()


def _append_approvals(state_root, records):
    p = os.path.join(state_root, _APPROVALS)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, sort_keys=True) + "\n")


def _seed_consent_record(state_root, diff_file="foo.diff"):
    _write_draft(state_root, diff_file=diff_file)
    return ct.create_request(state_root, state_root=state_root)


def _sign_decision(record, secret=_SECRET, proposer=_OPERATOR_ID):
    """Create a signed approved decision record (mimics operator approve)."""
    fields = {
        "created_at": record["created_at"],
        "diff_hash": record["diff_hash"],
        "proposer_operator_id": proposer,
        "request_id": record["request_id"],
        "state": "approved",
    }
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()
    h = hmac_mod.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
    return {
        "request_id": record["request_id"],
        "state": "approved",
        "approver_operator_id": _OPERATOR_ID,
        "diff_hash": record["diff_hash"],
        "proposer_operator_id": proposer,
        "created_at": record["created_at"],
        "hmac": h,
        "signed_at": record["created_at"],
    }


def _load_dc():
    """Lazy import delegate_consent. Raises ModuleNotFoundError if absent."""
    import delegate_consent  # noqa: F402
    return delegate_consent


# ============================================================================
# TESTS: propose
# ============================================================================

class TestPropose(unittest.TestCase):
    """Tests for the 'propose' subcommand."""

    def _run_propose(self, sr, extra_args=None):
        """Run propose CLI and return (exit_code, link_data_or_None)."""
        dc = _load_dc()
        args = ["propose", "--target", _TARGET_ID, "--diff-file", _TARGET_ID,
                "--root", sr]
        if extra_args:
            args.extend(extra_args)
        with unittest.mock.patch.dict(os.environ, {
            "COUNCIL_OPERATOR_SECRET": _SECRET,
            "COUNCIL_OPERATOR_ID": _OPERATOR_ID,
        }):
            rc = dc.main(args)
        link_path = os.path.join(sr, _LINK)
        link_data = None
        if os.path.exists(link_path):
            with open(link_path) as fh:
                link_data = json.load(fh)
        return rc, link_data

    def test_activation_gate_fail(self):
        """activation state != 'active' → exit 2, service delegate not called."""
        td, sr = _make_state()
        try:
            _write_draft(sr)
            dc = _load_dc()
            with unittest.mock.patch.object(
                dc, "subprocess", create=True
            ) as mock_sp:
                rc = dc.main([
                    "propose", "--target", _TARGET_ID,
                    "--diff-file", _TARGET_ID,
                    "--root", sr,
                    "--verify-activation",
                ])
                self.assertEqual(rc, 2)
                mock_sp.run.assert_not_called()
        finally:
            td.cleanup()

    def test_propose_happy_path(self):
        """Full happy: audit → delegate-write → consent request created.

        Link file written with correct metadata and consent_diff_hash.
        """
        td, sr = _make_state()
        try:
            _write_draft(sr, diff_file="foo.diff")
            record = _seed_consent_record(sr, diff_file="foo.diff")
            consent_hash = "sha256:" + _sha256_hex(_DIFF_CONTENT.encode())

            responses = [
                (0, {"audit_id": "aud-001"}),
                (0, {"approval_id": "app-001", "diff_hash": "h:001",
                     "next_action": "await_approval"}),
            ]

            def _fake_run(args, **kwargs):
                if responses:
                    rc, data = responses.pop(0)
                    stdout = json.dumps(data) + "\n" if isinstance(data, dict) else data
                    return subprocess.CompletedProcess(args, rc, stdout.encode(), b"")
                return subprocess.CompletedProcess(args, 0, json.dumps({}).encode(), b"")

            with unittest.mock.patch.object(
                _load_dc(), "subprocess", side_effect=lambda *a, **k: _fake_run(a, **k)
            ):
                with unittest.mock.patch.dict(os.environ, {
                    "COUNCIL_OPERATOR_SECRET": _SECRET,
                    "COUNCIL_OPERATOR_ID": _OPERATOR_ID,
                }):
                    rc = _load_dc().main([
                        "propose", "--target", _TARGET_ID,
                        "--diff-file", "foo.diff",
                        "--root", sr,
                    ])

            self.assertEqual(rc, 0)
            self.assertIsNotNone(record["request_id"])
            self.assertEqual(record["state"], "pending")

            # Check link file
            self.assertTrue(os.path.exists(os.path.join(sr, _LINK)))
            with open(os.path.join(sr, _LINK)) as fh:
                link = json.load(fh)
            self.assertEqual(link["request_id"], record["request_id"])
            self.assertEqual(link["approval_id"], "app-001")
            self.assertEqual(link["consent_diff_hash"], consent_hash)
            self.assertIn("diff_b64", link)
            self.assertIn("target_id", link)
            self.assertIn("created_at", link)

        finally:
            td.cleanup()

    def test_propose_delegate_error(self):
        """delegate-write returns error → exit 2."""
        td, sr = _make_state()
        try:
            _write_draft(sr, diff_file="foo.diff")

            responses = [
                (0, {"audit_id": "aud-002"}),
                (2, {"error": "rate_limit", "error_category": "rate_limit"}),
            ]

            def _fake_run(args, **kwargs):
                if responses:
                    rc, data = responses.pop(0)
                    stdout = json.dumps(data) + "\n" if isinstance(data, dict) else data
                    return subprocess.CompletedProcess(args, rc, stdout.encode(), b"")
                return subprocess.CompletedProcess(args, 0, json.dumps({}).encode(), b"")

            with unittest.mock.patch.object(
                _load_dc(), "subprocess", side_effect=lambda *a, **k: _fake_run(a, **k)
            ):
                with unittest.mock.patch.dict(os.environ, {
                    "COUNCIL_OPERATOR_SECRET": _SECRET,
                    "COUNCIL_OPERATOR_ID": _OPERATOR_ID,
                }):
                    rc = _load_dc().main([
                        "propose", "--target", _TARGET_ID,
                        "--diff-file", "foo.diff",
                        "--root", sr,
                    ])

            self.assertEqual(rc, 2)
            self.assertFalse(os.path.exists(os.path.join(sr, _LINK)))
        finally:
            td.cleanup()


# ============================================================================
# TESTS: consume
# ============================================================================

class TestConsume(unittest.TestCase):
    """Tests for the 'consume' subcommand."""

    def test_consume_no_link(self):
        """No link file → exit 1, nothing to consume."""
        td, sr = _make_state()
        try:
            with unittest.mock.patch.dict(os.environ, {
                "COUNCIL_OPERATOR_SECRET": _SECRET,
                "COUNCIL_OPERATOR_ID": _OPERATOR_ID,
            }):
                rc = _load_dc().main(["consume", "--root", sr])
            self.assertEqual(rc, 1)
        finally:
            td.cleanup()

    def test_consume_pending_decision(self):
        """Decision still pending → exit 1, no approve called, link stays."""
        td, sr = _make_state()
        try:
            _write_draft(sr, diff_file="foo.diff")
            record = _seed_consent_record(sr, diff_file="foo.diff")

            diff_b64 = _b64(_DIFF_CONTENT)
            consent_hash = "sha256:" + _sha256_hex(_DIFF_CONTENT.encode())
            link = {
                "request_id": record["request_id"],
                "approval_id": "app-001",
                "diff_b64": diff_b64,
                "consent_diff_hash": consent_hash,
                "target_id": _TARGET_ID,
                "change_type": "update",
                "trust_level": "safe",
                "created_at": "2026-01-01T00:00:00Z",
            }
            link_path = os.path.join(sr, _LINK)
            with open(link_path, "w") as fh:
                json.dump(link, fh)

            call_count = [0]

            def _fake_run(args, **kwargs):
                call_count[0] += 1
                return subprocess.CompletedProcess(
                    args, 0, json.dumps({"state": "pending"}).encode(), b"")

            with unittest.mock.patch.object(
                _load_dc(), "subprocess",
                side_effect=lambda *a, **k: _fake_run(a, **k)
            ):
                with unittest.mock.patch.dict(os.environ, {
                    "COUNCIL_OPERATOR_SECRET": _SECRET,
                    "COUNCIL_OPERATOR_ID": _OPERATOR_ID,
                }):
                    rc = _load_dc().main(["consume", "--root", sr])

            self.assertEqual(rc, 1)
            self.assertGreaterEqual(call_count[0], 1)
            self.assertTrue(os.path.exists(link_path))
        finally:
            td.cleanup()

    def test_consume_denied(self):
        """Operator denied → exit 1, no approve, link removed."""
        td, sr = _make_state()
        try:
            _write_draft(sr, diff_file="foo.diff")
            record = _seed_consent_record(sr, diff_file="foo.diff")

            denied = {
                "request_id": record["request_id"],
                "state": "denied",
                "reason": "operator_deny",
                "signed_at": record["created_at"],
            }
            _append_approvals(sr, [denied])

            diff_b64 = _b64(_DIFF_CONTENT)
            consent_hash = "sha256:" + _sha256_hex(_DIFF_CONTENT.encode())
            link = {
                "request_id": record["request_id"],
                "approval_id": "app-001",
                "diff_b64": diff_b64,
                "consent_diff_hash": consent_hash,
                "target_id": _TARGET_ID,
                "change_type": "update",
                "trust_level": "safe",
                "created_at": "2026-01-01T00:00:00Z",
            }
            link_path = os.path.join(sr, _LINK)
            with open(link_path, "w") as fh:
                json.dump(link, fh)

            with unittest.mock.patch.object(
                _load_dc(), "subprocess", create=True
            ) as mock_sp:
                with unittest.mock.patch.dict(os.environ, {
                    "COUNCIL_OPERATOR_SECRET": _SECRET,
                    "COUNCIL_OPERATOR_ID": _OPERATOR_ID,
                }):
                    rc = _load_dc().main(["consume", "--root", sr])

            self.assertEqual(rc, 1)
            mock_sp.run.assert_not_called()
            self.assertFalse(os.path.exists(link_path))
        finally:
            td.cleanup()

    def test_consume_approved_valid(self):
        """Approved with valid HMAC + matching hashes → approve→apply,
        mark_consumed, link removed, exit 0."""
        td, sr = _make_state()
        try:
            _write_draft(sr, diff_file="foo.diff")
            record = _seed_consent_record(sr, diff_file="foo.diff")

            decision = _sign_decision(record)
            _append_approvals(sr, [decision])

            diff_b64 = _b64(_DIFF_CONTENT)
            consent_hash = "sha256:" + _sha256_hex(_DIFF_CONTENT.encode())
            link = {
                "request_id": record["request_id"],
                "approval_id": "app-001",
                "diff_b64": diff_b64,
                "consent_diff_hash": consent_hash,
                "target_id": _TARGET_ID,
                "change_type": "update",
                "trust_level": "safe",
                "created_at": "2026-01-01T00:00:00Z",
            }
            link_path = os.path.join(sr, _LINK)
            with open(link_path, "w") as fh:
                json.dump(link, fh)

            responses = [
                (0, {"decision": "approved"}),
                (0, {"applied": True}),
            ]

            def _fake_run(args, **kwargs):
                if responses:
                    rc, data = responses.pop(0)
                    stdout = json.dumps(data) + "\n" if isinstance(data, dict) else data
                    return subprocess.CompletedProcess(args, rc, stdout.encode(), b"")
                return subprocess.CompletedProcess(args, 0, json.dumps({}).encode(), b"")

            with unittest.mock.patch.object(
                _load_dc(), "subprocess",
                side_effect=lambda *a, **k: _fake_run(a, **k)
            ) as mock_sub:
                with unittest.mock.patch.dict(os.environ, {
                    "COUNCIL_OPERATOR_SECRET": _SECRET,
                    "COUNCIL_OPERATOR_ID": _OPERATOR_ID,
                }):
                    rc = _load_dc().main(["consume", "--root", sr])

            self.assertEqual(rc, 0)
            self.assertEqual(mock_sub.call_count, 2)
            self.assertFalse(os.path.exists(link_path))
        finally:
            td.cleanup()

    def test_consume_tampered_diff(self):
        """link diff_b64 doesn't match stored → exit 2, no approve called."""
        td, sr = _make_state()
        try:
            _write_draft(sr, diff_file="foo.diff")
            record = _seed_consent_record(sr, diff_file="foo.diff")

            decision = _sign_decision(record)
            _append_approvals(sr, [decision])

            tampered_b64 = _b64("_DIFF_CONTENT = 'hacked content'")
            consent_hash = "sha256:" + _sha256_hex(_DIFF_CONTENT.encode())
            link = {
                "request_id": record["request_id"],
                "approval_id": "app-001",
                "diff_b64": tampered_b64,
                "consent_diff_hash": consent_hash,
                "target_id": _TARGET_ID,
                "change_type": "update",
                "trust_level": "safe",
                "created_at": "2026-01-01T00:00:00Z",
            }
            link_path = os.path.join(sr, _LINK)
            with open(link_path, "w") as fh:
                json.dump(link, fh)

            with unittest.mock.patch.object(
                _load_dc(), "subprocess", create=True
            ) as mock_sp:
                with unittest.mock.patch.dict(os.environ, {
                    "COUNCIL_OPERATOR_SECRET": _SECRET,
                    "COUNCIL_OPERATOR_ID": _OPERATOR_ID,
                }):
                    rc = _load_dc().main(["consume", "--root", sr])

            self.assertEqual(rc, 2)
            mock_sp.run.assert_not_called()
            self.assertTrue(os.path.exists(link_path))
        finally:
            td.cleanup()


# ============================================================================
# Baseline: verify red state when module absent
# ============================================================================

class TestModuleExists(unittest.TestCase):
    """Track whether the module exists (for red baseline tracking)."""

    def test_module_should_be_missing(self):
        """Baseline check: retire gracefully if implementation is present."""
        mod_path = os.path.join(_WT_ROOT, "tools", "delegate_consent.py")
        if os.path.exists(mod_path):
            self.skipTest("implementation present; baseline check retired")
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
