"""Tests for policy loading (fail closed), canonical diff, and delegate preview.

test_policy_fail_closed (mvp-contract §3.1: every mvp-data-models §2 rule),
test_canonical_diff (golden fixture, semantically equal variants), preview
scope discipline and trust invariants over the fixture corpus.
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from documenter_service.__main__ import Service  # noqa: E402
from documenter_service.adapters.diff_engine import (  # noqa: E402
    MAX_DIFF_BYTES_DEFAULT, StdDiffEngine, decode_diff_input)
from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry  # noqa: E402
from documenter_service.adapters.stdout_events import StdoutEventSink  # noqa: E402
from documenter_service.core.errors import StructuredError  # noqa: E402
from documenter_service.core.policy import (  # noqa: E402
    PolicyError, load_policy, policy_structured_error, validate_policy)

FIXTURES = os.path.join(REPO_ROOT, "tests", "fixtures", "documenter")
CORPUS = os.path.join(FIXTURES, "corpus")
MANIFEST_IDS = {"alpha", "beta", "gamma"}


def _policy(**over):
    base = {
        "documenter_policy": {
            "version": "0.2.0",
            "active_tier": 0,
            "allowed_operations": [],
            "audit_freshness": 30,
            "briefing_ref": None,
        }
    }
    base["documenter_policy"].update(over)
    return base


def _service(root=CORPUS):
    tmp = tempfile.mkdtemp()
    return Service(root,
                   registry=JsonlAuditRegistry(os.path.join(tmp, "state")),
                   events=StdoutEventSink(io.StringIO()))


class TestPolicyFailClosed(unittest.TestCase):
    def test_valid_fixture_loads(self):
        env = {"DOCUMENTER_POLICY_PATH": os.path.join(FIXTURES,
                                                      "policy_valid.yaml")}
        policy = load_policy("/nonexistent-root", env=env,
                             manifest_ids=MANIFEST_IDS)
        self.assertEqual(policy.get("active_tier"), 1)
        self.assertEqual(policy.get("rescan_batch_ceiling"), 2)
        self.assertEqual(policy.get("max_diff_bytes"), 524288)

    def test_repository_policy_loads(self):
        policy = load_policy(REPO_ROOT, env={}, manifest_ids=None)
        self.assertIn(policy.get("active_tier"), (0, 1))

    def test_invalid_fixture_typo_active_tier(self):
        env = {"DOCUMENTER_POLICY_PATH": os.path.join(FIXTURES,
                                                      "policy_invalid.yaml")}
        with self.assertRaises(PolicyError) as ctx:
            load_policy("/nonexistent-root", env=env)
        self.assertIn("active_tier", ctx.exception.reason)

    def test_invalid_fixture_tier2_missing_briefing_ref(self):
        env = {"DOCUMENTER_POLICY_PATH": os.path.join(FIXTURES,
                                                      "policy_invalid_tier2.yaml")}
        with self.assertRaises(PolicyError) as ctx:
            load_policy("/nonexistent-root", env=env,
                        manifest_ids=MANIFEST_IDS)
        self.assertIn("briefing_ref", ctx.exception.reason)

    def test_rule1_unknown_version(self):
        with self.assertRaises(PolicyError) as ctx:
            validate_policy(_policy(version="9.9.9"))
        self.assertIn("version", ctx.exception.reason)

    def test_rule2_bad_tier_values(self):
        for bad in ("one", 5, -1, 2.0, None, True):
            with self.assertRaises(PolicyError):
                validate_policy(_policy(active_tier=bad))

    def test_rule3_nonempty_ops_below_tier2(self):
        policy = _policy(active_tier=1, allowed_operations=[
            {"type": "operation", "change_type": "update",
             "trust_level": "review", "targets": []}])
        with self.assertRaises(PolicyError) as ctx:
            validate_policy(policy, manifest_ids=MANIFEST_IDS)
        self.assertIn("allowed_operations", ctx.exception.reason)

    def test_rule3_tier2_requires_ops(self):
        with self.assertRaises(PolicyError) as ctx:
            validate_policy(_policy(active_tier=2,
                                    briefing_ref="briefings/x.md"))
        self.assertIn("allowed_operations", ctx.exception.reason)

    def test_rule4_trust_below_static_floor(self):
        # fixture B: split + safe is below the review floor
        env = {"DOCUMENTER_POLICY_PATH": os.path.join(FIXTURES,
                                                      "policy_invalid_ops.yaml")}
        with self.assertRaises(PolicyError) as ctx:
            load_policy("/nonexistent-root", env=env,
                        manifest_ids=MANIFEST_IDS)
        self.assertIn("floor", ctx.exception.reason)
        # pattern entries too
        with self.assertRaises(PolicyError):
            validate_policy(_policy(
                active_tier=2, briefing_ref="b",
                allowed_operations=[{"type": "pattern",
                                     "match_criteria": {"change_type": "split"},
                                     "trust_level": "safe"}]))

    def test_rule5_targets_must_be_manifest_ids(self):
        good = _policy(active_tier=2, briefing_ref="b",
                       allowed_operations=[
                           {"type": "operation", "change_type": "update",
                            "trust_level": "safe", "targets": ["gamma"]}])
        validate_policy(good, manifest_ids=MANIFEST_IDS)  # no raise
        with self.assertRaises(PolicyError) as ctx:
            validate_policy(good, manifest_ids={"alpha"})
        self.assertIn("targets", ctx.exception.reason)

    def test_rule6_tier2_needs_briefing_ref(self):
        with self.assertRaises(PolicyError) as ctx:
            validate_policy(_policy(
                active_tier=2, briefing_ref=None,
                allowed_operations=[{"type": "operation",
                                     "change_type": "update",
                                     "trust_level": "safe", "targets": []}]))
        self.assertIn("briefing_ref", ctx.exception.reason)

    def test_rule7_positive_ints_and_inline_mode(self):
        for field, bad in [("audit_freshness", 0), ("max_diff_bytes", -5),
                           ("rescan_batch_ceiling", "fifty")]:
            with self.assertRaises(PolicyError) as ctx:
                validate_policy(_policy(**{field: bad}))
            self.assertIn(field, ctx.exception.reason)
        with self.assertRaises(PolicyError) as ctx:
            validate_policy(_policy(notification_mode="async"))
        self.assertIn("notification_mode", ctx.exception.reason)
        with self.assertRaises(PolicyError):
            validate_policy(_policy(temperature=2.5))  # outside 0.0–2.0

    def test_missing_file_fail_closed(self):
        env = {"DOCUMENTER_POLICY_PATH": "/definitely/not/here.yml"}
        with self.assertRaises(PolicyError):
            load_policy("/nonexistent-root", env=env)

    def test_policy_error_maps_to_structured_delegate_refusal(self):
        err = policy_structured_error(PolicyError("boom"))
        self.assertEqual(err.error_category, "gate_failure")
        self.assertEqual(err.next_action, "rerun_audit")

    def test_broken_policy_does_not_block_audit_or_status(self):
        env = {"DOCUMENTER_POLICY_PATH": "/definitely/not/here.yml"}
        os.environ.update(env)
        try:
            svc = _service()
            resp = svc.audit(target_id="alpha")  # audit proceeds
            self.assertEqual(resp["coverage"]["status"], "complete")
            status = svc.status()  # status proceeds at fail-closed tier 0
            self.assertEqual(status["active_tier"], 0)
        finally:
            os.environ.pop("DOCUMENTER_POLICY_PATH", None)

    def test_broken_policy_delegates_preview_on_default_cap(self):
        env = {"DOCUMENTER_POLICY_PATH": "/definitely/not/here.yml"}
        os.environ.update(env)
        try:
            svc = _service()
            with redirect_stderr(io.StringIO()):  # expected degradation warning
                resp = svc.delegate(target_id="alpha", change_type="update",
                                    trust_level="review",
                                    diff_input="LS0tIGF4CisrKyBheAo=",
                                    preview=True)
            self.assertEqual(resp["next_action"], "preview_only")
        finally:
            os.environ.pop("DOCUMENTER_POLICY_PATH", None)


class TestCanonicalDiff(unittest.TestCase):
    def setUp(self):
        self.engine = StdDiffEngine()
        with open(os.path.join(FIXTURES, "golden_diff_canon.json"),
                  encoding="utf-8") as fh:
            self.golden = json.load(fh)

    def test_golden_input_to_hash(self):
        text = decode_diff_input(self.golden["input_diff_b64"])
        normalized = self.engine.normalize(text)
        self.assertEqual(normalized.decode("utf-8"),
                         self.golden["normalized_text"])
        self.assertEqual(self.engine.diff_hash(normalized),
                         self.golden["diff_hash"])
        self.assertEqual(self.engine.render(normalized),
                         self.golden["normalized_text"])

    def test_semantically_equal_variants_same_hash(self):
        lf = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"
        crlf = lf.replace("\n", "\r\n")
        trailing = "--- a/x  \n+++ b/x\t\n@@ -1 +1 @@\n-a  \n+b\t\n"
        trailing_lf = trailing.replace("\n", "\n")
        no_final = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b"
        hashes = {
            self.engine.diff_hash(self.engine.normalize(s))
            for s in (lf, crlf, trailing, trailing_lf, no_final)}
        self.assertEqual(len(hashes), 1, hashes)

    def test_decode_rejects_bad_base64_and_nonutf8(self):
        with self.assertRaises(StructuredError) as ctx:
            decode_diff_input("!!!not base64!!!")
        self.assertEqual(ctx.exception.error_category, "unknown")
        import base64
        with self.assertRaises(StructuredError) as ctx:
            decode_diff_input(base64.b64encode(b"\xff\xfe").decode())
        self.assertIn("UTF-8", ctx.exception.message)

    def test_size_cap_before_processing(self):
        import base64
        big = base64.b64encode(b"x" * (MAX_DIFF_BYTES_DEFAULT + 1)).decode()
        with self.assertRaises(StructuredError) as ctx:
            decode_diff_input(big, max_diff_bytes=MAX_DIFF_BYTES_DEFAULT)
        self.assertIn("max_diff_bytes", ctx.exception.message)
        self.assertEqual(ctx.exception.next_action, "escalate")

    def test_render_rejects_non_diff_payload(self):
        with self.assertRaises(StructuredError):
            self.engine.render(b"just some prose\n")


class TestDelegatePreview(unittest.TestCase):
    def setUp(self):
        import base64
        self.DIFF = base64.b64encode(
            b"--- a/docs/en/alpha/index.md\n"
            b"+++ b/docs/en/alpha/index.md\n"
            b"@@ -1,1 +1,1 @@\n-id: alpha\n+id: alpha-renamed\n").decode()

    def test_preview_response_fields(self):
        svc = _service()
        resp = svc.delegate(target_id="alpha", change_type="update",
                            trust_level="safe", diff_input=self.DIFF,
                            preview=True)
        self.assertEqual(set(resp), {"diff_hash", "diff_text",
                                     "derived_trust_level",
                                     "derived_trust_reason", "next_action",
                                     "findings"})
        self.assertTrue(resp["diff_hash"].startswith("sha256:"))
        self.assertEqual(len(resp["diff_hash"]), len("sha256:") + 64)
        self.assertEqual(resp["next_action"], "preview_only")
        self.assertEqual(resp["derived_trust_level"], "safe")

    def test_preview_trust_mismatch(self):
        svc = _service()
        with self.assertRaises(StructuredError) as ctx:
            svc.delegate(target_id="alpha", change_type="split",
                         trust_level="safe", diff_input=self.DIFF,
                         preview=True)
        self.assertEqual(ctx.exception.error_category, "trust_mismatch")

    def test_preview_scope_discipline_offmanifest(self):
        # Preview must not become a reconnaissance primitive.
        svc = _service()
        with self.assertRaises(StructuredError) as ctx:
            svc.delegate(target_id="../secrets", change_type="update",
                         trust_level="review", diff_input=self.DIFF,
                         preview=True)
        self.assertEqual(ctx.exception.error_category, "unknown")
        self.assertEqual(ctx.exception.next_action, "escalate")

    def test_diff_text_never_reaches_registry_or_events(self):
        svc = _service()
        svc.delegate(target_id="alpha", change_type="update",
                     trust_level="review", diff_input=self.DIFF,
                     preview=True)
        if os.path.exists(svc.registry.path):
            with open(svc.registry.path, encoding="utf-8") as fh:
                registry_dump = fh.read()
        else:
            registry_dump = ""
        events_dump = svc.events.stream.getvalue()
        for marker in ("diff_text", "alpha-renamed", "--- a/"):
            self.assertNotIn(marker, registry_dump)
            self.assertNotIn(marker, events_dump)


if __name__ == "__main__":
    unittest.main()
