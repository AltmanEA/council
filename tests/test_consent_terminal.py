"""Tests for the Consent Terminal — operator approval for step-(5) changesets.

Covers the importable API contract from tools/consent_terminal.py:
  create_request(draft, state_root), prune_pending(state_root),
  verify_decision(record_pair, state_root), mark_consumed(request_id, state_root),
  read_pending(state_root), decide(record, keypresses).

Also covers minimal CLI subprocess behaviour (request --help, request no-draft).

ANTI-REVERSED-TDD: the module does not exist yet so the import raises at test
collection time (red baseline).  Every test asserts observable behaviour from
the target-task spec.  NO @unittest.skip guards — v2 fix.
"""
import fcntl
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Repo convention: insert tools/ on sys.path, then import by bare name.
# If consent_terminal.py does not exist the ImportError propagates here,
# causing collection errors → baseline exits non-zero (red).
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import consent_terminal as ct  # noqa: F401

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_APPROVALS = "documenter/intent/approvals.jsonl"
_QUARANTINE = "documenter/intent/quarantine"
_DIFFS = "documenter/intent/diffs"
_DRAFT = "documenter/intent/consent_draft.json"

MAX_DIFF_SIZE = 64 * 1024  # 64 KB


# ---------------------------------------------------------------------------
# Helpers — ALL state_root via TemporaryDirectory, never real documenter/.
# ---------------------------------------------------------------------------

def _mk_state():
    """Create a TemporaryDirectory with the expected consent layout."""
    td = tempfile.TemporaryDirectory()
    sd = td.name
    os.makedirs(os.path.join(sd, "documenter", "intent"), exist_ok=True)
    os.makedirs(os.path.join(sd, _DIFFS), exist_ok=True)
    return td, sd


def _make_draft(state_root, target_path="docs/en/foo/index.md",
                summary="Update foo", tier="safe", diff_file="foo.diff",
                expiry_minutes=30):
    """Write a consent draft + diff, return draft path."""
    draft_path = os.path.join(state_root, _DRAFT)
    payload = {
        "target_path": target_path,
        "summary": summary,
        "tier": tier,
        "diff_file": diff_file,
    }
    if expiry_minutes is not None:
        payload["expiry_minutes"] = expiry_minutes
    with open(draft_path, "w") as fh:
        json.dump(payload, fh)
    diff_path = os.path.join(state_root, _DIFFS, diff_file)
    with open(diff_path, "w") as fh:
        fh.write("diff content for " + target_path)
    return draft_path


def _make_diff(state_root, diff_file, content):
    """Write a diff file, return its path."""
    diff_path = os.path.join(state_root, _DIFFS, diff_file)
    with open(diff_path, "w") as fh:
        fh.write(content)
    return diff_path


def _read_all(state_root):
    """Read all JSONL records from approvals file (no-lock convenience)."""
    path = os.path.join(state_root, _APPROVALS)
    if not os.path.exists(path):
        return []
    result = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                result.append(json.loads(stripped))
    return result


def _append_record(state_root, record):
    """Append a record dict to approvals.jsonl."""
    path = os.path.join(state_root, _APPROVALS)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _future_deadline(minutes=30):
    return (datetime.now(timezone.utc)
            + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _past_deadline():
    return (datetime.now(timezone.utc)
            - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _prepare_council_dir(secret=b"test-secret"):
    """Write ~/.council/operator_secret and operator_id for HMAC tests."""
    home = os.path.expanduser("~")
    cdir = os.path.join(home, ".council")
    os.makedirs(cdir, exist_ok=True)
    spath = os.path.join(cdir, "operator_secret")
    with open(spath, "w") as fh:
        fh.write(secret.decode() if isinstance(secret, bytes) else secret)
    os.chmod(spath, 0o600)
    idpath = os.path.join(cdir, "operator_id")
    if not os.path.exists(idpath):
        with open(idpath, "w") as fh:
            fh.write("test-operator\n")


def _run_cli(args):
    """Run the CLI as a subprocess from WT (consent_terminal.py in tools/)."""
    wt_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return subprocess.run(
        ["python3", "tools/consent_terminal.py"] + list(args),
        cwd=wt_dir,
        capture_output=True,
        timeout=30,
    )


# ============================================================================
# TEST SUITE — 39+ cases per target-task acceptance criteria
# ============================================================================

class TestConsentTerminal(unittest.TestCase):
    """Tests for the consent terminal importable API and CLI."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.state_root = self._tmpdir.name
        os.makedirs(os.path.join(self.state_root, _DIFFS), exist_ok=True)
        self.draft_path = _make_draft(self.state_root)

    def tearDown(self):
        self._tmpdir.cleanup()

    # ---------------------------------------------------------------
    # 1. Request happy path
    # ---------------------------------------------------------------

    def test_create_request_happy_path(self):
        """Draft + diff file → pending record, correct fields, exit 0."""
        rec = ct.create_request(self.draft_path, state_root=self.state_root)
        self.assertIsInstance(rec, dict)
        self.assertIn("request_id", rec)
        self.assertEqual(len(rec["request_id"]), 8)

        records = _read_all(self.state_root)
        self.assertEqual(len(records), 1)
        r = records[0]

        self.assertEqual(r["target_path"], "docs/en/foo/index.md")
        self.assertEqual(r["summary"], "Update foo")
        self.assertEqual(r["tier"], "safe")
        self.assertTrue(r["diff_hash"].startswith("sha256:"))
        self.assertEqual(len(r["diff_hash"].split(":", 1)[1]), 64)
        self.assertEqual(r["state"], "pending")
        self.assertTrue(r.get("single_use"))

        # Draft is removed after successful creation
        self.assertFalse(
            os.path.exists(
                os.path.join(self.state_root, _DRAFT)))

    # ---------------------------------------------------------------
    # 2. Rejection branches (each → exit 2, quarantine, no pending)
    # ---------------------------------------------------------------

    def test_reject_missing_draft_file(self):
        """No draft file → FileNotFoundError (fail-closed)."""
        os.remove(self.draft_path)
        with self.assertRaises(FileNotFoundError):
            ct.create_request(self.draft_path, state_root=self.state_root)
        self.assertEqual(len(_read_all(self.state_root)), 0)

    def test_reject_malformed_json(self):
        """Invalid JSON → ValueError (fail-closed)."""
        with open(self.draft_path, "w") as fh:
            fh.write("{not valid json!!!")
        with self.assertRaises(ValueError):
            ct.create_request(self.draft_path, state_root=self.state_root)
        self.assertEqual(len(_read_all(self.state_root)), 0)

    def test_reject_missing_required_key(self):
        """Missing `target_path` key → ValueError."""
        with open(self.draft_path, "w") as fh:
            json.dump({"tier": "safe"}, fh)
        with self.assertRaises(ValueError):
            ct.create_request(self.draft_path, state_root=self.state_root)
        self.assertEqual(len(_read_all(self.state_root)), 0)

    def test_reject_unknown_tier(self):
        """tier not in {safe, review} → ValueError."""
        with open(self.draft_path, "w") as fh:
            json.dump({
                "target_path": "x.md", "summary": "s",
                "tier": "critical", "diff_file": "d.txt",
            }, fh)
        with self.assertRaises(ValueError):
            ct.create_request(self.draft_path, state_root=self.state_root)
        self.assertEqual(len(_read_all(self.state_root)), 0)

    def test_reject_summary_too_long(self):
        """Summary > 200 chars → ValueError."""
        with open(self.draft_path, "w") as fh:
            json.dump({
                "target_path": "x.md", "summary": "a" * 201,
                "tier": "safe", "diff_file": "d.txt",
            }, fh)
        with self.assertRaises(ValueError):
            ct.create_request(self.draft_path, state_root=self.state_root)
        self.assertEqual(len(_read_all(self.state_root)), 0)

    def test_reject_diff_file_missing(self):
        """Referenced diff file missing → FileNotFoundError."""
        with open(self.draft_path, "w") as fh:
            json.dump({
                "target_path": "x.md", "summary": "s",
                "tier": "safe", "diff_file": "nonexistent.diff",
            }, fh)
        with self.assertRaises(FileNotFoundError):
            ct.create_request(self.draft_path, state_root=self.state_root)
        self.assertEqual(len(_read_all(self.state_root)), 0)

    def test_reject_diff_too_large(self):
        """Diff > 64 KB → ValueError (reject)."""
        big_path = _make_diff(self.state_root, "big.diff", "x" * (MAX_DIFF_SIZE + 1))
        with open(self.draft_path, "w") as fh:
            json.dump({
                "target_path": "x.md", "summary": "s",
                "tier": "safe", "diff_file": "big.diff",
            }, fh)
        with self.assertRaises(ValueError):
            ct.create_request(self.draft_path, state_root=self.state_root)
        self.assertEqual(len(_read_all(self.state_root)), 0)

    def test_reject_quarantine_created(self):
        """On rejection the draft is quarantined with a timestamped name."""
        with open(self.draft_path, "w") as fh:
            fh.write("{bad json")
        try:
            ct.create_request(self.draft_path, state_root=self.state_root)
        except (ValueError, FileNotFoundError):
            pass  # expected

        qdir = os.path.join(self.state_root, _QUARANTINE)
        self.assertTrue(os.path.isdir(qdir))
        quarantined = [
            f for f in os.listdir(qdir) if f.startswith("consent_draft")
        ]
        self.assertGreater(len(quarantined), 0)

    # ---------------------------------------------------------------
    # 3. No Tier-2+ interlock dependencies (security constraint)
    # ---------------------------------------------------------------

    def test_no_tier2_interlock_references(self):
        """Module must not reference Tier 2+ interlock components."""
        import inspect
        source = inspect.getsource(ct)
        forbidden = ["documenter_policy", "operator_ingress",
                     "OperatorSurface", "active_tier", "briefing_ref"]
        for token in forbidden:
            self.assertNotIn(
                token, source,
                f"Module must not reference {token}")

    # ---------------------------------------------------------------
    # 4. HMAC sign / verify — correct secret, tamper detection (5 variants)
    # ---------------------------------------------------------------

    def _make_approved(self, state_root, **overrides):
        """Helper: create_request + append an approved record. Returns rec."""
        ct.create_request(state_root, state_root=state_root)
        r = _read_all(state_root)[0]
        fields = {
            "created_at": r["created_at"],
            "diff_hash": r["diff_hash"],
            "proposer_operator_id": "test-proposer",
            "request_id": r["request_id"],
            "state": "approved",
        }
        fields.update(overrides)
        canonical = json.dumps(
            fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
        h = hmac.new(
            b"test-secret", canonical, hashlib.sha256).hexdigest()
        decision = {
            "request_id": r["request_id"],
            "state": fields["state"],
            "diff_hash": r["diff_hash"],
            "proposer_operator_id": "test-proposer",
            "created_at": r["created_at"],
            "hmac": h,
            "signed_at": _now_iso(),
        }
        decision.update(overrides)
        _append_record(state_root, decision)
        return r, decision

    def test_hmac_verify_valid(self):
        """Decision with correct HMAC → verify passes."""
        _prepare_council_dir()
        r, d = self._make_approved(self.state_root)
        self.assertTrue(ct.verify_decision(r, d, state_root=self.state_root))

    def test_hmac_tamper_request_id(self):
        """Changing request_id → verify fails."""
        _prepare_council_dir()
        r, d = self._make_approved(self.state_root)
        d["request_id"] = "tampered"
        self.assertFalse(
            ct.verify_decision(r, d, state_root=self.state_root))

    def test_hmac_tamper_diff_hash(self):
        """Changing diff_hash → verify fails."""
        _prepare_council_dir()
        r, d = self._make_approved(self.state_root)
        d["diff_hash"] = "sha256:" + "a" * 64
        self.assertFalse(
            ct.verify_decision(r, d, state_root=self.state_root))

    def test_hmac_state_flip_denied_to_approved(self):
        """Flipping state from denied→approved → verify fails."""
        _prepare_council_dir()
        ct.create_request(self.draft_path, state_root=self.state_root)
        r = _read_all(self.state_root)[0]
        denied_fields = {
            "created_at": r["created_at"],
            "diff_hash": r["diff_hash"],
            "proposer_operator_id": "test",
            "request_id": r["request_id"],
            "state": "denied",
        }
        canonical = json.dumps(
            denied_fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
        h = hmac.new(
            b"test-secret", canonical, hashlib.sha256).hexdigest()
        denied = {
            "request_id": r["request_id"],
            "state": "denied",
            "diff_hash": r["diff_hash"],
            "proposer_operator_id": "test",
            "created_at": r["created_at"],
            "hmac": h,
        }
        _append_record(self.state_root, denied)
        approved = dict(denied)
        approved["state"] = "approved"  # flip
        self.assertFalse(
            ct.verify_decision(r, approved, state_root=self.state_root))

    def test_hmac_state_flip_approved_to_denied(self):
        """Flipping state from approved→denied → verify fails."""
        _prepare_council_dir()
        r, d = self._make_approved(self.state_root)
        d["state"] = "denied"  # flip
        self.assertFalse(
            ct.verify_decision(r, d, state_root=self.state_root))

    # ---------------------------------------------------------------
    # 5. Integrity-fail prune
    # ---------------------------------------------------------------

    def test_prune_integrity_fail(self):
        """diff_text mismatch → pruned as denied reason=integrity_fail."""
        ct.create_request(self.draft_path, state_root=self.state_root)
        recs = _read_all(self.state_root)
        recs[0]["diff_text"] = "corrupted content"
        path = os.path.join(self.state_root, _APPROVALS)
        with open(path, "w", encoding="utf-8") as fh:
            for rec in recs:
                fh.write(json.dumps(rec, sort_keys=True) + "\n")

        pruned = ct.prune_pending(state_root=self.state_root)
        self.assertEqual(len(pruned), 1)
        self.assertEqual(pruned[0]["state"], "denied")
        self.assertEqual(pruned[0]["reason"], "integrity_fail")

        remaining = [r for r in _read_all(self.state_root)
                     if r.get("state") == "pending"]
        self.assertEqual(len(remaining), 0)

    # ---------------------------------------------------------------
    # 6. Expiry prune
    # ---------------------------------------------------------------

    def test_prune_expired(self):
        """Record past expiry_deadline → pruned as denied reason=expired."""
        ct.create_request(self.draft_path, state_root=self.state_root)
        recs = _read_all(self.state_root)
        recs[0]["expiry_deadline"] = _past_deadline()
        path = os.path.join(self.state_root, _APPROVALS)
        with open(path, "w", encoding="utf-8") as fh:
            for rec in recs:
                fh.write(json.dumps(rec, sort_keys=True) + "\n")

        pruned = ct.prune_pending(state_root=self.state_root)
        self.assertEqual(len(pruned), 1)
        self.assertEqual(pruned[0]["state"], "denied")
        self.assertEqual(pruned[0]["reason"], "expired")

    # ---------------------------------------------------------------
    # 7. Latest-record-wins (append-only log)
    # ---------------------------------------------------------------

    def test_latest_wins_pending_approved_consumed(self):
        """pending → approved → consumed: read_pending returns consumed."""
        ct.create_request(self.draft_path, state_root=self.state_root)
        rid = _read_all(self.state_root)[0]["request_id"]

        _append_record(self.state_root, {
            "request_id": rid, "state": "approved",
            "diff_hash": "sha256:" + "b" * 64,
            "proposer_operator_id": "test", "created_at": _now_iso(),
            "hmac": "fake", "signed_at": _now_iso(),
        })
        _append_record(self.state_root, {
            "request_id": rid, "state": "consumed",
            "diff_hash": "sha256:" + "c" * 64,
            "proposer_operator_id": "test", "created_at": _now_iso(),
        })

        result = ct.read_pending(state_root=self.state_root)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["state"], "consumed")

    def test_latest_wins_multiple_approvals(self):
        """Multiple approvals for same request_id: last one wins."""
        ct.create_request(self.draft_path, state_root=self.state_root)
        rid = _read_all(self.state_root)[0]["request_id"]

        _append_record(self.state_root, {
            "request_id": rid, "state": "approved",
            "diff_hash": "sha256:" + "a" * 64,
            "proposer_operator_id": "test", "created_at": _now_iso(),
            "hmac": "fake", "signed_at": _now_iso(),
        })
        _append_record(self.state_root, {
            "request_id": rid, "state": "approved",
            "diff_hash": "sha256:" + "b" * 64,
            "proposer_operator_id": "test2", "created_at": _now_iso(),
            "hmac": "fake2", "signed_at": _now_iso(),
        })

        result = ct.read_pending(state_root=self.state_root)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["diff_hash"], "sha256:" + "b" * 64)

    # ---------------------------------------------------------------
    # 8. mark_consumed — 3 cases
    # ---------------------------------------------------------------

    def test_mark_consumed_unknown_id(self):
        """mark_consumed on nonexistent request_id → False."""
        self.assertFalse(
            ct.mark_consumed("nonexistent-id", state_root=self.state_root))

    def test_mark_consumed_non_decided(self):
        """mark_consumed on pure pending (no decision) → False."""
        ct.create_request(self.draft_path, state_root=self.state_root)
        rid = _read_all(self.state_root)[0]["request_id"]
        self.assertFalse(ct.mark_consumed(rid, state_root=self.state_root))

    def test_mark_consumed_success(self):
        """pending → approved → mark_consumed → consumed state."""
        ct.create_request(self.draft_path, state_root=self.state_root)
        rid = _read_all(self.state_root)[0]["request_id"]
        _append_record(self.state_root, {
            "request_id": rid, "state": "approved",
            "diff_hash": "sha256:" + "a" * 64,
            "proposer_operator_id": "test", "created_at": _now_iso(),
            "hmac": "fake", "signed_at": _now_iso(),
        })
        self.assertTrue(ct.mark_consumed(rid, state_root=self.state_root))
        recs = _read_all(self.state_root)
        self.assertEqual(recs[-1]["state"], "consumed")

    # ---------------------------------------------------------------
    # 9. FIFO ordering
    # ---------------------------------------------------------------

    def test_read_pending_fifo_ordering(self):
        """read_pending returns records by created_at, oldest first."""
        _append_record(self.state_root, {
            "request_id": "older", "target_path": "a.md",
            "summary": "old", "tier": "safe",
            "diff_hash": "sha256:" + "a" * 64,
            "created_at": _past_deadline(),
            "expiry_deadline": _future_deadline(),
            "state": "pending",
        })
        _append_record(self.state_root, {
            "request_id": "newer", "target_path": "b.md",
            "summary": "new", "tier": "safe",
            "diff_hash": "sha256:" + "b" * 64,
            "created_at": _now_iso(),
            "expiry_deadline": _future_deadline(),
            "state": "pending",
        })

        pending = ct.read_pending(state_root=self.state_root)
        self.assertEqual(len(pending), 2)
        self.assertEqual(pending[0]["request_id"], "older")
        self.assertEqual(pending[1]["request_id"], "newer")

    # ---------------------------------------------------------------
    # 10. Pure decide() keypress grammar
    # ---------------------------------------------------------------

    def test_decide_safe_y_immediate(self):
        """Safe tier: 'y' → approved immediately."""
        rec = {"state": "pending", "tier": "safe",
               "expiry_deadline": _future_deadline()}
        self.assertEqual(ct.decide(rec, ["y"]), "approved")

    def test_decide_safe_n(self):
        """Safe tier: 'n' → denied."""
        rec = {"state": "pending", "tier": "safe",
               "expiry_deadline": _future_deadline()}
        self.assertEqual(ct.decide(rec, ["n"]), "denied")

    def test_decide_safe_q(self):
        """Safe tier: 'q' → no_decision."""
        rec = {"state": "pending", "tier": "safe",
               "expiry_deadline": _future_deadline()}
        self.assertEqual(ct.decide(rec, ["q"]), "no_decision")

    def test_decide_review_y_then_enter(self):
        """Review tier: 'y' → confirming; Enter '-> approved."""
        rec = {"state": "pending", "tier": "review",
               "expiry_deadline": _future_deadline()}
        self.assertEqual(ct.decide(rec, ["y"]), "confirming")
        self.assertEqual(ct.decide(rec, ["\n"]), "approved")

    def test_decide_review_n(self):
        """Review tier: 'n' → denied."""
        rec = {"state": "pending", "tier": "review",
               "expiry_deadline": _future_deadline()}
        self.assertEqual(ct.decide(rec, ["n"]), "denied")

    def test_decide_review_q(self):
        """Review tier: 'q' → no_decision."""
        rec = {"state": "pending", "tier": "review",
               "expiry_deadline": _future_deadline()}
        self.assertEqual(ct.decide(rec, ["q"]), "no_decision")

    def test_decide_expired_skip(self):
        """Expired record → skipped regardless of keypress."""
        rec = {"state": "pending", "tier": "safe",
               "expiry_deadline": _past_deadline()}
        self.assertEqual(ct.decide(rec, ["y"]), "skipped_expired")

    def test_decide_unknown_key_stays(self):
        """Unknown key → stays pending."""
        rec = {"state": "pending", "tier": "safe",
               "expiry_deadline": _future_deadline()}
        self.assertEqual(ct.decide(rec, ["x"]), "pending")

    def test_decide_empty_keypress(self):
        """Empty keypress list → pending."""
        rec = {"state": "pending", "tier": "safe",
               "expiry_deadline": _future_deadline()}
        self.assertEqual(ct.decide(rec, []), "pending")

    def test_decide_missing_state_key(self):
        """Malformed record missing 'state' → skip gracefully."""
        rec = {"tier": "safe"}
        self.assertEqual(ct.decide(rec, ["y"]), "skipped_expired")

    def test_decide_missing_tier_key(self):
        """Malformed record missing 'tier' → skip gracefully."""
        rec = {"state": "pending"}
        self.assertEqual(ct.decide(rec, ["y"]), "skipped_expired")

    def test_decide_review_y_then_y_not_enter(self):
        """Review: 'y' → confirming, 'y' again → still confirming."""
        rec = {"state": "pending", "tier": "review",
               "expiry_deadline": _future_deadline()}
        self.assertEqual(ct.decide(rec, ["y"]), "confirming")
        self.assertEqual(ct.decide(rec, ["y"]), "confirming")
        self.assertEqual(ct.decide(rec, ["\n"]), "approved")

    # ---------------------------------------------------------------
    # 11. CLI subprocess tests
    # ---------------------------------------------------------------

    def test_cli_help_exits_0(self):
        """--help exits with code 0."""
        result = _run_cli(["--help"])
        self.assertEqual(result.returncode, 0)

    def test_cli_request_no_draft_exits_2(self):
        """request with no draft file → exit 2."""
        result = _run_cli(["request"])
        self.assertEqual(result.returncode, 2)


# ============================================================================
# ADDITIONS — iteration 3: pin the three diff-review hardening fixes
# ============================================================================

class TestConsentHardening(unittest.TestCase):
    """Pin regression tests for the three hardening patches:
    A. flock on JSONL read/append
    B. no busy-spin in _cmd_review (select timeout guard)
    C. Ctrl-C / Ctrl-D raw deny in decide() + expiry precedence
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.state_root = self._tmpdir.name
        os.makedirs(os.path.join(self.state_root, _DIFFS), exist_ok=True)
        os.makedirs(os.path.join(self.state_root, "documenter", "intent"),
                     exist_ok=True)

    def tearDown(self):
        self._tmpdir.cleanup()

    # ---------------------------------------------------------------
    # A. LOCKED READ — flock used on read and append
    # ---------------------------------------------------------------

    def test_flock_used_on_jsonl_read(self):
        """_jsonl_read_all calls fcntl.flock with LOCK_SH."""
        # Pre-seed one record
        _append_record(self.state_root, {
            "request_id": "abc12345", "state": "pending",
            "tier": "safe", "diff_hash": "sha256:" + "c" * 64,
            "created_at": _now_iso(),
            "expiry_deadline": _future_deadline(),
        })
        with unittest.mock.patch("consent_terminal.fcntl.flock",
                                 wraps=fcntl.flock) as mock_flock:
            ct._jsonl_read_all(self.state_root)
            # Must have been called at least once with LOCK_SH
            calls = mock_flock.call_args_list
            lock_modes = [c[0][1] for c in calls]
            self.assertIn(fcntl.LOCK_SH, lock_modes,
                          "_jsonl_read_all must use LOCK_SH")

    def test_flock_used_on_jsonl_append(self):
        """_jsonl_append_locked calls fcntl.flock with LOCK_EX."""
        rec = {"request_id": "locktest", "state": "approved",
               "diff_hash": "sha256:" + "d" * 64,
               "proposer_operator_id": "test",
               "created_at": _now_iso(), "hmac": "x", "signed_at": _now_iso()}
        with unittest.mock.patch("consent_terminal.fcntl.flock",
                                 wraps=fcntl.flock) as mock_flock:
            ct._jsonl_append_locked(self.state_root, rec)
            calls = mock_flock.call_args_list
            lock_modes = [c[0][1] for c in calls]
            self.assertIn(fcntl.LOCK_EX, lock_modes,
                          "_jsonl_append_locked must use LOCK_EX")

    # ---------------------------------------------------------------
    # B. NO BUSY-SPIN — select timeout must not be zero
    # ---------------------------------------------------------------

    def test_no_busy_spin_in_review(self):
        """_cmd_review does not use select.select with timeout 0.

        Source-scan guard: behavioral CPU measurement is flaky in CI,
        so we verify the code structure statically instead.
        """
        import inspect
        source = inspect.getsource(ct._cmd_review)

        # Must NOT contain a busy-spin pattern: select.select(..., 0)
        self.assertNotIn(
            "select.select([sys.stdin], [], [], 0)", source,
            "_cmd_review must not use select with timeout=0 (busy-spin)")

        # Any select.select call must use None or a float >= 0.05
        # (blocking or meaningful timeout, not busy-loop)
        import re
        matches = re.findall(
            r"select\.select\(\[sys\.stdin\],\s*\[\],\s*\[\],\s*([^)]+)\)",
            source)
        for timeout_val in matches:
            # Strip trailing whitespace/paren
            timeout_val = timeout_val.strip()
            self.assertIn(timeout_val,
                          ("None", "None)"),
                          f"select timeout must be None (blocking), "
                          f"got {timeout_val}")

    # ---------------------------------------------------------------
    # C. CTRL-C / CTRL-D RAW DENY in decide()
    # ---------------------------------------------------------------

    def test_decide_ctrl_c_safe_denied(self):
        """Safe tier: Ctrl-C (\\x03) → denied (not approved)."""
        rec = {"state": "pending", "tier": "safe",
               "expiry_deadline": _future_deadline()}
        self.assertEqual(ct.decide(rec, ["\x03"]), "denied")

    def test_decide_ctrl_d_safe_denied(self):
        """Safe tier: Ctrl-D (\\x04) → denied."""
        rec = {"state": "pending", "tier": "safe",
               "expiry_deadline": _future_deadline()}
        self.assertEqual(ct.decide(rec, ["\x04"]), "denied")

    def test_decide_expired_ctrl_c_skipped_expired(self):
        """Expired record: Ctrl-C → skipped_expired (expiry precedence).

        The spec says ctrl is checked AFTER expiry but BEFORE tier logic,
        so an expired record cannot be overridden by a signal key.
        """
        rec = {"state": "pending", "tier": "safe",
               "expiry_deadline": _past_deadline()}
        self.assertEqual(ct.decide(rec, ["\x03"]), "skipped_expired")
