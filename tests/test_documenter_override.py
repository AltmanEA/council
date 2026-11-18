"""Tests for override_gate + post_mortems (mvp-contract §2.2.6, §4, Tier 2+).

Covers:
  - override_gate: happy path, guard chain, dedup, consume semantics,
    event emission, critical finding block, tier interlock, malformed inputs,
    corrupt registry.
  - post_mortems: write, list, redaction, temp cleanup.
  - Service.override_gate: integration via Service class.

Run with: python3 -m unittest tests.test_documenter_override
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry  # noqa: E402
from documenter_service.adapters.stdout_events import (  # noqa: E402
    StdoutEventSink, MVP_EVENT_TYPES, EVENT_SCHEMAS)
from documenter_service.core.errors import StructuredError  # noqa: E402
from documenter_service.core import registry as reg  # noqa: E402
from documenter_service.core.policy import (  # noqa: E402
    check_tier2_authorized, operator_id_valid, Policy)
from documenter_service.__main__ import Service  # noqa: E402
from documenter_service.core import override as core_override  # noqa: E402

# Hex strings for diff_hash values (must be valid hex: 0-9, a-f)
HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64
HEX_D = "d" * 64
HEX_E = "e" * 64
HEX_F = "f" * 64
HEX_0 = "0" * 64
HEX_1 = "1" * 64
HEX_2 = "2" * 64
HEX_3 = "3" * 64
HEX_4 = "4" * 64
HEX_5 = "5" * 64
HEX_6 = "6" * 64
HEX_7 = "7" * 64
HEX_8 = "8" * 64
HEX_9 = "9" * 64


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_tier2_policy(briefing_path=None):
    """Create a Tier-2 Policy with a valid briefing_ref."""
    fields = {
        "version": "0.2.0",
        "active_tier": 2,
        "allowed_operations": [
            {
                "change_type": "update",
                "targets": ["alpha"],
                "trust_level": "safe",
            },
            {
                "change_type": "update",
                "targets": [],
                "trust_level": "review",
            },
        ],
        "briefing_ref": briefing_path or "_briefing.md",
        "audit_freshness": 30,
        "approval_expiry_window": 30,
        "max_diff_bytes": 524288,
        "lock_wait_timeout": 30,
    }
    return Policy(fields)


def _make_tier0_policy():
    """Create a Tier-0 Policy (no write intent)."""
    return Policy({
        "version": "0.2.0",
        "active_tier": 0,
        "allowed_operations": [],
        "audit_freshness": 30,
        "approval_expiry_window": 30,
        "max_diff_bytes": 524288,
    })


def _make_manifest(doc_ids=None):
    """Create an in-memory manifest from corpus entries."""
    if doc_ids is None:
        doc_ids = ["alpha", "beta", "gamma"]
    entries_list = []
    manifest = type("Manifest", (), {
        "_entries": {},
        "entries": lambda self: entries_list,
        "resolve": lambda self, tid: self._entries.get(tid),
    })()
    for eid in doc_ids:
        entry = {
            "id": eid,
            "path": "docs/en/" + eid + "/index.md",
            "title": eid.title() + " Document",
            "version": "1.0.0",
            "status": "active",
        }
        entries_list.append(entry)
        manifest._entries[eid] = entry
    return manifest


def _make_registry(tmpdir):
    return JsonlAuditRegistry(tmpdir)


def _make_briefing(tmpdir):
    """Create a briefing file at the expected path."""
    path = os.path.join(tmpdir, "_briefing.md")
    with open(path, "w") as f:
        f.write("# Briefing\n\nAuthorised operational context.\n")
    return path


def _make_audit_record(audit_id, issued_at=None, scope="*", findings=None,
                       has_remaining=False):
    now = issued_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "audit_id": audit_id,
        "issued_at": now,
        "scope": scope,
        "findings": findings or [],
        "scanned_ids": ["alpha", "beta", "gamma"],
        "has_remaining": has_remaining,
    }


def _make_finding(subject_id, severity, description="test finding",
                  suggested_action="review"):
    return {
        "subject_id": subject_id,
        "severity": severity,
        "description": description,
        "suggested_action": suggested_action,
    }


# ---------------------------------------------------------------------------
# Helper: setup a minimal working override call (tier 2, no critical findings)
# ---------------------------------------------------------------------------

def _make_override_setup(tmpdir, target_id="alpha", audit_id="aid-1",
                         tier_policy=True, root=None):
    """Return (registry, policy, events, manifest, tmpdir) for override tests."""
    manifest = _make_manifest()
    reg_obj = _make_registry(os.path.join(tmpdir, "state"))
    briefing = _make_briefing(tmpdir) if tier_policy else None
    policy = _make_tier2_policy(briefing) if tier_policy else _make_tier0_policy()
    stream = io.StringIO()
    events = StdoutEventSink(stream)

    # Create an audit record so override_gate can find one
    record = _make_audit_record(audit_id, scope="*")
    reg_obj.append("audit_record", record)

    # Attach manifest to registry for _is_corpus_level_finding lookup
    reg_obj._manifest_for_override = manifest
    reg_obj._root_for_override = root or tmpdir

    # ADR-013: override_gate runs check_tier2_authorized against root — the
    # surface-readiness sentinel must exist for Tier 2+ override paths.
    r = root or tmpdir
    sentinel = os.path.join(r, "documenter", ".operator_ingress_ready")
    os.makedirs(os.path.dirname(sentinel), exist_ok=True)
    with open(sentinel, "w") as f:
        f.write("")

    return reg_obj, policy, events, manifest, tmpdir


# ===========================================================================
# Test class: TestOverrideGate
# ===========================================================================

class TestOverrideGate(unittest.TestCase):
    """Unit tests for override_gate (core/override.py)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    # -- happy path ----------------------------------------------------------

    def test_happy_returns_override_id_and_next_action(self):
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(self.tmpdir)
        result = core_override.override_gate(
            self.tmpdir, os.path.join(self.tmpdir, "documenter"),
            reg_obj, policy, events,
            target_id="alpha", diff_hash="sha256:" + HEX_A,
            reason="operator approved this override", operator_id="op-user1")
        self.assertIn("override_id", result)
        self.assertEqual(result["target_id"], "alpha")
        self.assertEqual(result["diff_hash"], "sha256:" + HEX_A)
        self.assertEqual(result["next_action"], "rerun_audit")
        self.assertEqual(result["reason"], "operator approved this override")
        self.assertEqual(result["operator_id"], "op-user1")
        self.assertIn("emitted_at", result)

    def test_happy_two_token_records_appended(self):
        """One token_record appended (consumed=True in one shot)."""
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(self.tmpdir)
        core_override.override_gate(
            self.tmpdir, os.path.join(self.tmpdir, "documenter"),
            reg_obj, policy, events,
            target_id="alpha", diff_hash="sha256:" + HEX_B,
            reason="test", operator_id="op-user1")
        records, _ = reg_obj.read_all()
        override_tokens = [
            r for r in records
            if r["record_type"] == "token_record"
            and r["data"].get("token_type") == "override_gate"
        ]
        self.assertEqual(len(override_tokens), 1)
        self.assertTrue(override_tokens[0]["data"]["consumed"])
        self.assertIsNotNone(override_tokens[0]["data"]["consumed_at"])

    def test_happy_event_emitted(self):
        stream = io.StringIO()
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(self.tmpdir)
        events = StdoutEventSink(stream)
        diff_hash_val = "sha256:" + HEX_C
        core_override.override_gate(
            self.tmpdir, os.path.join(self.tmpdir, "documenter"),
            reg_obj, policy, events,
            target_id="alpha", diff_hash=diff_hash_val,
            reason="test reason", operator_id="op-user1")
        stream.seek(0)
        event_line = stream.readline().strip()
        event = json.loads(event_line)
        self.assertEqual(event["event_type"], "documenter.override_gate")
        self.assertEqual(event["payload"]["target_id"], "alpha")
        self.assertEqual(event["payload"]["reason"], "test reason")
        self.assertEqual(event["payload"]["operator_id"], "op-user1")

    def test_happy_token_bound_to_target_and_diff(self):
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(self.tmpdir)
        core_override.override_gate(
            self.tmpdir, os.path.join(self.tmpdir, "documenter"),
            reg_obj, policy, events,
            target_id="alpha", diff_hash="sha256:" + HEX_D,
            reason="test", operator_id="op-user1")
        records, _ = reg_obj.read_all()
        token = [r for r in records if r["record_type"] == "token_record"
                 and r["data"].get("token_type") == "override_gate"][0]
        self.assertEqual(token["data"]["bound_to"]["target_id"], "alpha")
        self.assertEqual(token["data"]["diff_hash"], "sha256:" + HEX_D)

    # -- guard: tier < 2 / policy None → tier_interlock ----------------------

    def test_tier0_interlock(self):
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(
            self.tmpdir, tier_policy=False)
        with self.assertRaises(StructuredError) as ctx:
            core_override.override_gate(
                self.tmpdir, os.path.join(self.tmpdir, "documenter"),
                reg_obj, policy, events,
                target_id="alpha", diff_hash="sha256:" + HEX_E,
                reason="test", operator_id="op-user1")
        self.assertEqual(ctx.exception.error_category, "tier_interlock")

    def test_policy_none_interlock(self):
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(self.tmpdir)
        with self.assertRaises(StructuredError) as ctx:
            core_override.override_gate(
                self.tmpdir, os.path.join(self.tmpdir, "documenter"),
                reg_obj, None, events,
                target_id="alpha", diff_hash="sha256:" + HEX_F,
                reason="test", operator_id="op-user1")
        self.assertEqual(ctx.exception.error_category, "tier_interlock")

    # -- guard: critical finding blocks → blocking_finding -------------------

    def test_critical_finding_for_target_blocks(self):
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(self.tmpdir)
        # Override the audit record with a critical finding for "alpha"
        audit_data = _make_audit_record("aid-1", scope="*")
        audit_data["findings"] = [_make_finding("alpha", "critical")]
        reg_obj.append("audit_record", audit_data)
        with self.assertRaises(StructuredError) as ctx:
            core_override.override_gate(
                self.tmpdir, os.path.join(self.tmpdir, "documenter"),
                reg_obj, policy, events,
                target_id="alpha", diff_hash="sha256:" + HEX_1,
                reason="test", operator_id="op-user1")
        self.assertEqual(ctx.exception.error_category, "blocking_finding")
        self.assertEqual(ctx.exception.next_action, "resolve_finding")
        self.assertIn("post-mortem remediation", ctx.exception.message)
        # No token_record appended.
        records, _ = reg_obj.read_all()
        tokens = [r for r in records if r["record_type"] == "token_record"
                  and r["data"].get("token_type") == "override_gate"]
        self.assertEqual(len(tokens), 0)

    def test_critical_corpus_level_finding_blocks(self):
        """A corpus-level finding (subject_id is a path) blocks override
        when the target is not itself a corpus-level ID."""
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(
            self.tmpdir)
        audit_data = _make_audit_record("aid-1", scope="*")
        # Corpus-level subject: a file path, not a simple document ID
        audit_data["findings"] = [
            _make_finding("docs/en/protocol-core/index.md", "critical")
        ]
        reg_obj.append("audit_record", audit_data)
        with self.assertRaises(StructuredError) as ctx:
            core_override.override_gate(
                self.tmpdir, os.path.join(self.tmpdir, "documenter"),
                reg_obj, policy, events,
                target_id="alpha", diff_hash="sha256:" + HEX_2,
                reason="test", operator_id="op-user1")
        self.assertEqual(ctx.exception.error_category, "blocking_finding")
        self.assertEqual(ctx.exception.next_action, "resolve_finding")

    def test_low_severity_does_not_block(self):
        """Non-critical findings should not block override."""
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(self.tmpdir)
        audit_data = _make_audit_record("aid-1", scope="*")
        audit_data["findings"] = [_make_finding("alpha", "low")]
        reg_obj.append("audit_record", audit_data)
        result = core_override.override_gate(
            self.tmpdir, os.path.join(self.tmpdir, "documenter"),
            reg_obj, policy, events,
            target_id="alpha", diff_hash="sha256:" + HEX_3,
            reason="low finding not blocking", operator_id="op-user1")
        self.assertIn("override_id", result)

    # -- guard: malformed operator_id / empty reason / bad diff_hash ---------

    def test_malformed_operator_id(self):
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(self.tmpdir)
        with self.assertRaises(StructuredError) as ctx:
            core_override.override_gate(
                self.tmpdir, os.path.join(self.tmpdir, "documenter"),
                reg_obj, policy, events,
                target_id="alpha", diff_hash="sha256:" + HEX_4,
                reason="test", operator_id="invalid-op")
        self.assertEqual(ctx.exception.error_category, "unknown")

    def test_empty_reason(self):
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(self.tmpdir)
        with self.assertRaises(StructuredError) as ctx:
            core_override.override_gate(
                self.tmpdir, os.path.join(self.tmpdir, "documenter"),
                reg_obj, policy, events,
                target_id="alpha", diff_hash="sha256:" + HEX_5,
                reason="", operator_id="op-user1")
        self.assertEqual(ctx.exception.error_category, "unknown")

    def test_reason_too_long(self):
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(self.tmpdir)
        with self.assertRaises(StructuredError) as ctx:
            core_override.override_gate(
                self.tmpdir, os.path.join(self.tmpdir, "documenter"),
                reg_obj, policy, events,
                target_id="alpha", diff_hash="sha256:" + HEX_6,
                reason="x" * 501, operator_id="op-user1")
        self.assertEqual(ctx.exception.error_category, "unknown")

    def test_bad_diff_hash_prefix(self):
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(self.tmpdir)
        with self.assertRaises(StructuredError) as ctx:
            core_override.override_gate(
                self.tmpdir, os.path.join(self.tmpdir, "documenter"),
                reg_obj, policy, events,
                target_id="alpha", diff_hash="md5:abc",
                reason="test", operator_id="op-user1")
        self.assertEqual(ctx.exception.error_category, "unknown")

    def test_bad_diff_hash_length(self):
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(self.tmpdir)
        with self.assertRaises(StructuredError) as ctx:
            core_override.override_gate(
                self.tmpdir, os.path.join(self.tmpdir, "documenter"),
                reg_obj, policy, events,
                target_id="alpha", diff_hash="sha256:abc",
                reason="test", operator_id="op-user1")
        self.assertEqual(ctx.exception.error_category, "unknown")

    # -- guard: corrupt registry → gate_failure ------------------------------

    def test_corrupt_registry(self):
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(self.tmpdir)
        # Write garbage to registry
        with open(reg_obj.path, "w") as f:
            f.write("not valid json at all\n")
        with self.assertRaises(StructuredError) as ctx:
            core_override.override_gate(
                self.tmpdir, os.path.join(self.tmpdir, "documenter"),
                reg_obj, policy, events,
                target_id="alpha", diff_hash="sha256:" + HEX_7,
                reason="test", operator_id="op-user1")
        self.assertEqual(ctx.exception.error_category, "gate_failure")

    # -- dedup: token_replay for active override -----------------------------

    def test_second_override_same_pair_is_token_replay(self):
        """mvp-contract §4: one consumption per (target_id, diff_hash).

        Every invocation consumes immediately, so a second override of the
        same pair within the window is a replay — consumed flag is not an
        escape hatch (that would make the one-shot bound vacuous).
        """
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(self.tmpdir)
        result1 = core_override.override_gate(
            self.tmpdir, os.path.join(self.tmpdir, "documenter"),
            reg_obj, policy, events,
            target_id="alpha", diff_hash="sha256:" + HEX_8,
            reason="first", operator_id="op-user1")
        self.assertIn("override_id", result1)
        stream2 = io.StringIO()
        events2 = StdoutEventSink(stream2)
        with self.assertRaises(StructuredError) as ctx:
            core_override.override_gate(
                self.tmpdir, os.path.join(self.tmpdir, "documenter"),
                reg_obj, policy, events2,
                target_id="alpha", diff_hash="sha256:" + HEX_8,
                reason="second", operator_id="op-user2")
        self.assertEqual(ctx.exception.error_category, "token_replay")

    def test_expired_override_allows_new(self):
        """After approval_expiry_window the pair may be overridden again."""
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(self.tmpdir)
        result1 = core_override.override_gate(
            self.tmpdir, os.path.join(self.tmpdir, "documenter"),
            reg_obj, policy, events,
            target_id="alpha", diff_hash="sha256:" + HEX_9,
            reason="first", operator_id="op-user1")
        self.assertIn("override_id", result1)
        # Age the first token beyond the window: rewrite the registry file
        # with a past created_at (the dedup logic reads created_at vs now).
        import json as _json
        from datetime import datetime, timedelta, timezone
        from documenter_service.core import registry as _reg
        past = (datetime.now(timezone.utc)
                - timedelta(minutes=int(policy.get("approval_expiry_window")) + 5)
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
        aged = reg_obj.read_all()[0]
        for rec in aged:
            if (rec["record_type"] == "token_record"
                    and rec["data"].get("token_type") == "override_gate"):
                rec["data"]["created_at"] = past
        reg2 = JsonlAuditRegistry(os.path.join(self.tmpdir, "state2"))
        os.makedirs(reg2.data_dir, exist_ok=True)
        with open(reg2.path, "w", encoding="utf-8") as fh:
            prev = None
            for rec in aged:
                env = _reg.make_envelope(rec["record_type"], rec["data"], prev)
                fh.write(_json.dumps(env, sort_keys=True) + "\n")
                prev = _reg.record_hash(env)
        events2 = StdoutEventSink(io.StringIO())
        result2 = core_override.override_gate(
            self.tmpdir, os.path.join(self.tmpdir, "documenter"),
            reg2, policy, events2,
            target_id="alpha", diff_hash="sha256:" + HEX_9,
            reason="after expiry", operator_id="op-user2")
        self.assertIn("override_id", result2)

    def test_different_diff_hash_not_replay(self):
        """Different diff_hash for same target → separate override."""
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(self.tmpdir)
        core_override.override_gate(
            self.tmpdir, os.path.join(self.tmpdir, "documenter"),
            reg_obj, policy, events,
            target_id="alpha", diff_hash="sha256:" + HEX_A,
            reason="first hash", operator_id="op-user1")
        # Different diff_hash should be allowed.
        stream2 = io.StringIO()
        events2 = StdoutEventSink(stream2)
        reg_obj2, _, _, _, _ = _make_override_setup(self.tmpdir)
        reg_obj2._manifest_for_override = manifest
        reg_obj2._root_for_override = self.tmpdir
        result2 = core_override.override_gate(
            self.tmpdir, os.path.join(self.tmpdir, "documenter"),
            reg_obj2, policy, events2,
            target_id="alpha", diff_hash="sha256:" + HEX_B,
            reason="second hash", operator_id="op-user1")
        self.assertIn("override_id", result2)

    # ===========================================================================
    # Test class: TestPostMortems
    # ===========================================================================

    class TestPostMortems(unittest.TestCase):
        """Tests for write_post_mortem / list_post_mortems."""

        def setUp(self):
            self.tmpdir = tempfile.mkdtemp()

        def tearDown(self):
            shutil.rmtree(self.tmpdir)

        def test_write_creates_file(self):
            data_dir = os.path.join(self.tmpdir, "documenter")
            findings = [_make_finding("alpha", "critical")]
            path = core_override.write_post_mortem(
                data_dir, audit_id="aid-1",
                findings=findings, reason="override blocked by critical",
                operator_id="op-user1")
            self.assertTrue(os.path.exists(path))
            self.assertTrue(path.endswith(".json"))

        def test_write_roundtrip_fields(self):
            data_dir = os.path.join(self.tmpdir, "documenter")
            findings = [_make_finding("alpha", "critical", "desc", "action")]
            path = core_override.write_post_mortem(
                data_dir, audit_id="aid-1",
                findings=findings, reason="test reason",
                operator_id="op-user1")
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("post_mortem_id", data)
            self.assertEqual(data["audit_id"], "aid-1")
            self.assertEqual(data["reason"], "test reason")
            self.assertEqual(data["operator_id"], "op-user1")
            self.assertIn("created_at", data)
            self.assertTrue(data["created_at"].endswith("Z"))

        def test_write_findings_redacted(self):
            data_dir = os.path.join(self.tmpdir, "documenter")
            findings = [
                {
                    "subject_id": "alpha",
                    "severity": "critical",
                    "description": "test desc",
                    "suggested_action": "fix it",
                    "extra_field": "should be stripped",
                }
            ]
            path = core_override.write_post_mortem(
                data_dir, audit_id="aid-1",
                findings=findings, reason="redaction test",
                operator_id="op-user1")
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            pm_findings = data["findings"]
            self.assertEqual(len(pm_findings), 1)
            f0 = pm_findings[0]
            self.assertEqual(f0["subject_id"], "alpha")
            self.assertEqual(f0["severity"], "critical")
            self.assertEqual(f0["description"], "test desc")
            self.assertEqual(f0["suggested_action"], "fix it")
            self.assertNotIn("extra_field", f0)

        def test_list_sorted_by_created_at(self):
            data_dir = os.path.join(self.tmpdir, "documenter")
            core_override.write_post_mortem(
                data_dir, audit_id="aid-1",
                findings=[], reason="first", operator_id="op-user1")
            time.sleep(0.05)  # ensure different timestamps
            core_override.write_post_mortem(
                data_dir, audit_id="aid-2",
                findings=[], reason="second", operator_id="op-user1")
            items = core_override.list_post_mortems(data_dir)
            self.assertEqual(len(items), 2)
            self.assertLessEqual(items[0]["created_at"],
                                 items[1]["created_at"])

        def test_list_empty_when_no_post_mortems(self):
            data_dir = os.path.join(self.tmpdir, "documenter")
            items = core_override.list_post_mortems(data_dir)
            self.assertEqual(items, [])

        def test_temp_file_absent_after_write(self):
            data_dir = os.path.join(self.tmpdir, "documenter")
            core_override.write_post_mortem(
                data_dir, audit_id="aid-1",
                findings=[], reason="cleanup", operator_id="op-user1")
            postmortems_dir = os.path.join(data_dir, "post_mortems")
            for fname in os.listdir(postmortems_dir):
                self.assertFalse(
                    fname.endswith(".tmp"),
                    "temp file {} was not cleaned up".format(fname))

        def test_list_no_json_extension_skipped(self):
            """Non-JSON files in post_mortems dir should be skipped."""
            data_dir = os.path.join(self.tmpdir, "documenter")
            pm_dir = os.path.join(data_dir, "post_mortems")
            os.makedirs(pm_dir, exist_ok=True)
            # Create a non-JSON file
            with open(os.path.join(pm_dir, "readme.txt"), "w") as f:
                f.write("ignore me")
            items = core_override.list_post_mortems(data_dir)
            self.assertEqual(items, [])

    # ===========================================================================
    # Test class: TestServiceOverrideGate
    # ===========================================================================

    class TestServiceOverrideGate(unittest.TestCase):
        """Integration tests via Service.override_gate()."""

        def setUp(self):
            self.tmpdir = tempfile.mkdtemp()
            self.briefing = _make_briefing(self.tmpdir)

        def tearDown(self):
            shutil.rmtree(self.tmpdir)

        def test_service_happy_path(self):
            svc = Service(self.tmpdir,
                          registry=_make_registry(
                              os.path.join(self.tmpdir, "state")),
                          manifest=_make_manifest())
            # Add an audit record
            audit_rec = _make_audit_record("aid-1")
            svc.registry.append("audit_record", audit_rec)

            result = svc.override_gate(
                target_id="alpha", diff_hash="sha256:" + HEX_0,
                reason="operator override", operator_id="op-user1")
            self.assertIn("override_id", result)
            self.assertEqual(result["next_action"], "rerun_audit")
            self.assertEqual(result["target_id"], "alpha")

        def test_service_tier0_blocks(self):
            svc = Service(self.tmpdir,
                          registry=_make_registry(
                              os.path.join(self.tmpdir, "state")),
                          manifest=_make_manifest())
            audit_rec = _make_audit_record("aid-1")
            svc.registry.append("audit_record", audit_rec)
            with self.assertRaises(StructuredError) as ctx:
                svc.override_gate(
                    target_id="alpha", diff_hash="sha256:" + HEX_2,
                    reason="test", operator_id="op-user1")
            self.assertEqual(ctx.exception.error_category, "tier_interlock")

        def test_service_event_emitted(self):
            stream = io.StringIO()
            svc = Service(self.tmpdir,
                          registry=_make_registry(
                              os.path.join(self.tmpdir, "state")),
                          manifest=_make_manifest(),
                          events=StdoutEventSink(stream))
            audit_rec = _make_audit_record("aid-1")
            svc.registry.append("audit_record", audit_rec)

            svc.override_gate(
                target_id="alpha", diff_hash="sha256:" + HEX_3,
                reason="emission test", operator_id="op-user1")
            stream.seek(0)
            event_line = stream.readline().strip()
            event = json.loads(event_line)
            self.assertEqual(event["event_type"], "documenter.override_gate")

        def test_service_critical_finding_blocks(self):
            svc = Service(self.tmpdir,
                          registry=_make_registry(
                              os.path.join(self.tmpdir, "state")),
                          manifest=_make_manifest())
            audit_rec = _make_audit_record("aid-1")
            audit_rec["findings"] = [_make_finding("alpha", "critical")]
            svc.registry.append("audit_record", audit_rec)
            with self.assertRaises(StructuredError) as ctx:
                svc.override_gate(
                    target_id="alpha", diff_hash="sha256:" + HEX_4,
                    reason="test", operator_id="op-user1")
            self.assertEqual(ctx.exception.error_category, "blocking_finding")

    # ===========================================================================
    # Test class: TestMvpEventTypesUnblocked
    # ===========================================================================

    class TestMvpEventTypesUnblocked(unittest.TestCase):
        """Verify that documenter.override_gate is in MVP_EVENT_TYPES."""

        def test_event_type_in_mvp_list(self):
            self.assertIn("documenter.override_gate", MVP_EVENT_TYPES)

        def test_schema_declared(self):
            self.assertIn(
                "documenter.override_gate", EVENT_SCHEMAS)
            schema = EVENT_SCHEMAS["documenter.override_gate"]
            self.assertEqual(schema, frozenset(
                {"reason", "operator_id", "target_id"}))


# ===========================================================================
# Test class: TestOverrideCounterAlignment
# ===========================================================================

class TestOverrideCounterAlignment(unittest.TestCase):
    """Verify that override tokens align with the registry token model.

    Override tokens use token_type="override_gate" and consumed=True from
    the start (one-shot semantics).  The counter in status() (currently pinned
    at 0 in the MVP build) will count these once status.py is updated to
    derive override_counter from token_records.

    NOTE: The MVP status() hardcodes override_counter=0 (core/status.py line 74).
    This test verifies the token model is correct for future alignment:
    status() should count token_type=='override_gate' records with
    consumed=True.  The override implementation creates exactly one such
    record per invocation, so the count will be 1 per override call.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_token_type_is_override_gate(self):
        """The token_record must have token_type='override_gate'."""
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(self.tmpdir)
        core_override.override_gate(
            self.tmpdir, os.path.join(self.tmpdir, "documenter"),
            reg_obj, policy, events,
            target_id="alpha", diff_hash="sha256:" + HEX_E,
            reason="alignment test", operator_id="op-user1")
        records, _ = reg_obj.read_all()
        tokens = [r for r in records if r["record_type"] == "token_record"
                  and r["data"].get("token_type") == "override_gate"]
        self.assertEqual(len(tokens), 1)
        self.assertTrue(tokens[0]["data"]["consumed"])

    def test_multiple_overrides_increase_count(self):
        """Two different (target,diff) pairs should produce two token records."""
        reg_obj, policy, events, manifest, tmpdir = _make_override_setup(self.tmpdir)
        # First override
        core_override.override_gate(
            self.tmpdir, os.path.join(self.tmpdir, "documenter"),
            reg_obj, policy, events,
            target_id="alpha", diff_hash="sha256:" + HEX_A,
            reason="first", operator_id="op-user1")
        # Second override on different target
        stream2 = io.StringIO()
        events2 = StdoutEventSink(stream2)
        core_override.override_gate(
            self.tmpdir, os.path.join(self.tmpdir, "documenter"),
            reg_obj, policy, events2,
            target_id="beta", diff_hash="sha256:" + HEX_B,
            reason="second", operator_id="op-user2")
        records, _ = reg_obj.read_all()
        tokens = [r for r in records if r["record_type"] == "token_record"
                  and r["data"].get("token_type") == "override_gate"]
        self.assertEqual(len(tokens), 2)  # two different (target,diff) pairs


if __name__ == "__main__":
    unittest.main()
