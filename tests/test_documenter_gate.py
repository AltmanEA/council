"""Tests for the pre-audit gate, trust invariant, and tier interlock.

test_pre_audit_gate (mvp-contract §3.1: rules 1–5 each produce the canonical
error_category), test_tier_interlock (mvp-interfaces §2 preview, §4 enums),
trust classification matrix (index.md §Trust Classification).
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from documenter_service.adapters.diff_engine import (  # noqa: E402
    StdDiffEngine, decode_diff_input)
from documenter_service.adapters.worker_stub import InterlockedWorkerStub  # noqa: E402
from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry  # noqa: E402
from documenter_service.core import registry as reg  # noqa: E402
from documenter_service.core.audit import pre_audit_gate  # noqa: E402
from documenter_service.core.audit import delegate_preview  # noqa: E402
from documenter_service.__main__ import Service  # noqa: E402
from documenter_service.core.errors import (ERROR_CATEGORIES, NEXT_ACTIONS,  # noqa: E402
                                            StructuredError)
from documenter_service.core.trust import (CHANGE_TYPES, STATIC_FLOORS,  # noqa: E402
                                           TRUST_LEVELS, check_invariant,
                                           derive_trust, is_mechanical_line)

NOW = "2026-11-13T12:00:00Z"
T0 = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)


def _record(**over):
    data = {
        "audit_id": "aud-1",
        "issued_at": "2026-11-13T11:50:00Z",
        "scope": "*",
        "findings": [],
        "scanned_ids": ["alpha"],
        "has_remaining": False,
        "scan_cursor": None,
    }
    data.update(over)
    return data


class TestPreAuditGate(unittest.TestCase):
    """Pure function, no filesystem (mvp-contract §3.1)."""

    def test_all_rules_pass(self):
        self.assertIsNone(pre_audit_gate(_record(), "alpha", NOW, 30))

    def test_rule1_missing_audit_id(self):
        err = pre_audit_gate(None, "alpha", NOW, 30)
        self.assertEqual(err.error_category, "audit_mismatch")
        self.assertEqual(err.next_action, "rerun_audit")

    def test_rule2_stale_audit(self):
        stale = _record(issued_at="2026-11-13T11:00:00Z")  # 60 min old
        err = pre_audit_gate(stale, "alpha", NOW, 30)
        self.assertEqual(err.error_category, "audit_mismatch")
        self.assertIn("audit_freshness", err.message)

    def test_rule2_boundary_exactly_at_window_passes(self):
        edge = _record(issued_at=(T0 - timedelta(minutes=30)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"))
        self.assertIsNone(pre_audit_gate(edge, "alpha", NOW, 30))
        past = _record(issued_at=(T0 - timedelta(minutes=30, seconds=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"))
        self.assertIsNotNone(pre_audit_gate(past, "alpha", NOW, 30))

    def test_rule3_scope_not_covering_target(self):
        err = pre_audit_gate(_record(scope="beta"), "alpha", NOW, 30)
        self.assertEqual(err.error_category, "audit_mismatch")
        # exact-match scope covers; '*' covers anything
        self.assertIsNone(pre_audit_gate(_record(scope="alpha"), "alpha", NOW, 30))
        self.assertIsNone(pre_audit_gate(_record(scope="*"), "anything", NOW, 30))

    def test_rule4_blocking_high_finding(self):
        rec = _record(findings=[{"subject_id": "alpha", "severity": "high",
                                 "description": "d", "suggested_action": "a"}])
        err = pre_audit_gate(rec, "alpha", NOW, 30)
        self.assertEqual(err.error_category, "blocking_finding")
        self.assertEqual(err.next_action, "resolve_finding")

    def test_rule4_critical_blocks_and_medium_does_not(self):
        crit = _record(findings=[{"subject_id": "alpha", "severity": "critical",
                                  "description": "d", "suggested_action": "a"}])
        self.assertEqual(pre_audit_gate(crit, "alpha", NOW, 30).error_category,
                         "blocking_finding")
        med = _record(findings=[{"subject_id": "alpha", "severity": "medium",
                                 "description": "d", "suggested_action": "a"}])
        self.assertIsNone(pre_audit_gate(med, "alpha", NOW, 30))
        # high finding on ANOTHER subject does not block this target
        other = _record(findings=[{"subject_id": "beta", "severity": "high",
                                   "description": "d", "suggested_action": "a"}])
        self.assertIsNone(pre_audit_gate(other, "alpha", NOW, 30))

    def test_rule5_incomplete_scan(self):
        err = pre_audit_gate(_record(has_remaining=True,
                                     scan_cursor="tok"), "alpha", NOW, 30)
        self.assertEqual(err.error_category, "blocking_finding")
        self.assertEqual(err.next_action, "rescan_to_completion")

    def test_freshness_zero_disables_gate(self):
        self.assertIsNone(pre_audit_gate(None, "alpha", NOW, 0))


class TestTrustClassification(unittest.TestCase):
    """requested >= derived over the full change_type × trust_level matrix."""

    def test_static_floor_matrix(self):
        self.assertEqual(derive_trust("update")[0], "safe")
        self.assertIn("static floor", derive_trust("update")[1])
        for ctype in ("split", "create_ru", "custom"):
            self.assertEqual(derive_trust(ctype)[0], "review")

    def test_invariant_matrix(self):
        for ctype in CHANGE_TYPES:
            floor = STATIC_FLOORS[ctype]
            for requested in TRUST_LEVELS:
                if floor == "review" and requested == "safe":
                    with self.assertRaises(StructuredError) as ctx:
                        check_invariant(ctype, requested)
                    self.assertEqual(ctx.exception.error_category,
                                     "trust_mismatch")
                else:
                    derived, _ = check_invariant(ctype, requested)
                    self.assertEqual(derived, floor)

    def test_unknown_enums_are_defects(self):
        with self.assertRaises(StructuredError) as ctx:
            derive_trust("rewrite-everything")
        self.assertEqual(ctx.exception.error_category, "unknown")
        with self.assertRaises(StructuredError) as ctx:
            check_invariant("update", "yolo")
        self.assertEqual(ctx.exception.error_category, "unknown")


class TestTrustDynamicDerivation(unittest.TestCase):
    """Dynamic derivation for update with diff_text (mvp-interfaces §Trust)."""

    def test_all_mechanical_update_is_safe(self):
        """Table row add/remove, blank-line add, changelog-path change → safe."""
        diff = (
            "--- a/docs/en/alpha/index.md\n"
            "+++ b/docs/en/alpha/index.md\n"
            "@@ -2,1 +2,2 @@\n"
            "-|alpha|active|protocol|\n"
            "+|alpha|active|protocol|\n"
            "+|\n"
            "@@ -6 +7 @@\n"
            "-changelog-path: CHANGELOGS/alpha.changes.md\n"
            "+changelog-path: CHANGELOGS/alpha.v2.changes.md\n"
        )
        level, reason = derive_trust("update", diff)
        self.assertEqual(level, "safe")
        self.assertIn("mechanical", reason)

    def test_one_prose_change_triggers_review(self):
        """Multi-hunk diff where only hunk 2 has prose → review, reason has hunk 2."""
        diff = (
            "--- a/docs/en/alpha/index.md\n"
            "+++ b/docs/en/alpha/index.md\n"
            "@@ -2,1 +2,1 @@\n"
            "-|alpha|active|protocol|\n"
            "+|alpha|renamed|protocol|\n"
            "@@ -5,3 +5,3 @@\n"
            "## Purpose\n"
            "\n"
            "-Clean fixture document.\n"
            "+Updated fixture document.\n"
        )
        level, reason = derive_trust("update", diff)
        self.assertEqual(level, "review")
        self.assertIn("hunk 2", reason)

    def test_no_changed_lines_indeterminate(self):
        """Context-only diff → indeterminate → review."""
        diff = (
            "--- a/docs/en/alpha/index.md\n"
            "+++ b/docs/en/alpha/index.md\n"
            "@@ -1,3 +1,3 @@\n"
            "# Alpha Document\n"
            "id: alpha\n"
            "Version: 1.0.0\n"
        )
        level, reason = derive_trust("update", diff)
        self.assertEqual(level, "review")
        self.assertIn("indeterminate", reason)

    def test_broken_table_pipe_is_review(self):
        """'+|broken' starts with | but no closing | → not a table row."""
        diff = (
            "--- a/docs/en/alpha/index.md\n"
            "+++ b/docs/en/alpha/index.md\n"
            "@@ -1 +1,2 @@\n"
            "+|broken\n"
        )
        level, reason = derive_trust("update", diff)
        self.assertEqual(level, "review")

    def test_split_review_even_with_mechanical_diff(self):
        """Dynamic derivation cannot lower the review floor."""
        diff = (
            "--- a/docs/en/alpha/index.md\n"
            "+++ b/docs/en/alpha/index.md\n"
            "@@ -1 +1 @@\n"
            "-id: alpha\n"
            "+id: alpha\n"
        )
        for ct in ("split", "create_ru", "custom"):
            level, _ = derive_trust(ct, diff)
            self.assertEqual(level, "review")

    def test_update_no_diff_text_is_safe_static_floor(self):
        """Backward compat: derive_trust("update") → safe with static floor."""
        level, reason = derive_trust("update")
        self.assertEqual(level, "safe")
        self.assertIn("static floor", reason)

    def test_check_invariant_prose_rejects_safe_allows_review(self):
        """Prose diff derives review; safe is rejected, review passes."""
        prose_diff = (
            "--- a/docs/en/alpha/index.md\n"
            "+++ b/docs/en/alpha/index.md\n"
            "@@ -5 +5 @@\n"
            "-Clean fixture.\n"
            "+Updated fixture.\n"
        )
        with self.assertRaises(StructuredError) as ctx:
            check_invariant("update", "safe", prose_diff)
        self.assertEqual(ctx.exception.error_category, "trust_mismatch")
        derived, _ = check_invariant("update", "review", prose_diff)
        self.assertEqual(derived, "review")

    def test_check_invariant_unknown_level_first(self):
        """Unknown trust_level raises unknown even when diff_text is provided."""
        prose_diff = (
            "--- a/docs/en/alpha/index.md\n"
            "+++ b/docs/en/alpha/index.md\n"
            "@@ -5 +5 @@\n"
            "-Clean fixture.\n"
            "+Updated fixture.\n"
        )
        with self.assertRaises(StructuredError) as ctx:
            check_invariant("update", "yolo", prose_diff)
        self.assertEqual(ctx.exception.error_category, "unknown")


class TestTierInterlock(unittest.TestCase):
    def test_worker_stub_any_call(self):
        worker = InterlockedWorkerStub()
        for call in (lambda: worker.execute({}),
                     lambda: worker.execute({"target_ids": ["x"]})):
            with self.assertRaises(StructuredError) as ctx:
                call()
            self.assertEqual(ctx.exception.error_category, "tier_interlock")
            self.assertEqual(ctx.exception.next_action, "preview_denied")

    def test_error_enums_closed(self):
        # Closed enums from mvp-interfaces §4, verbatim.
        self.assertEqual(set(ERROR_CATEGORIES), {
            "audit_mismatch", "blocking_finding", "tier_interlock",
            "approval_expired", "approval_invalidated", "hash_mismatch",
            "trust_mismatch", "token_replay", "lock_conflict", "gate_failure",
            "unknown"})
        self.assertEqual(set(NEXT_ACTIONS), {
            "preview_only", "await_approval", "rerun_audit", "resolve_finding",
            "rescan_to_completion", "preview_denied", "escalate",
            "write_applied"})  # write_applied added by W2

    def test_structured_error_rejects_unknown_category(self):
        with self.assertRaises(ValueError):
            StructuredError("not-a-category", "boom")

    def test_delegate_preview_false_and_absent_denied(self):
        # Same refusal via the composition root for preview=False/None.
        from documenter_service.__main__ import Service
        svc = Service(FIXTURE_CORPUS_FOR_DELEGATE)
        for bad_preview in (False, None):
            with self.assertRaises(StructuredError) as ctx:
                svc.delegate(target_id="alpha", change_type="update",
                             trust_level="review", diff_input="eA==",
                             preview=bad_preview)
            self.assertEqual(ctx.exception.error_category, "tier_interlock")
            self.assertEqual(ctx.exception.next_action, "preview_denied")

    def test_reserved_intent_record_never_written(self):
        from documenter_service import ports
        from documenter_service.core import registry as reg
        self.assertEqual(ports.INTENT_RECORD_TYPE, "intent_record")
        self.assertIn(reg.INTENT_RECORD, reg.RECORD_TYPES)  # readable ...
        # ... but no MVP source file ever APPENDS it (schema reserved only).
        pkg = os.path.join(REPO_ROOT, "documenter_service")
        for dirpath, _dirs, files in os.walk(pkg):
            for name in files:
                if name.endswith(".py"):
                    with open(os.path.join(dirpath, name),
                              encoding="utf-8") as fh:
                        src = fh.read()
                    self.assertNotIn(
                        'append(reg.INTENT_RECORD', src,
                        f"intent_record append found in {name}")


class TestTrustClassificationGolden(unittest.TestCase):
    """Full trust-matrix golden test over golden_trust_matrix.json fixture
    (mvp-interfaces §2 Trust classification table, mvp-contract §3.1).

    For every case the fixture records expected_level and expected_reason_contains.
    The test verifies derive_trust output matches, and that the invariant
    requested >= derived holds both ways:
      - check_invariant(change_type, "review", diff) always succeeds;
      - check_invariant(change_type, "safe", diff) succeeds iff expected_level == "safe".
    """

    def setUp(self):
        self.engine = StdDiffEngine()
        with open(
            os.path.join(FIXTURES, "golden_trust_matrix.json"),
            encoding="utf-8",
        ) as fh:
            self.fixture = json.load(fh)

    def test_golden_trust_matrix(self):
        for c in self.fixture:
            ct = c["change_type"]
            dt = c["diff_text"]
            expected_level = c["expected_level"]
            expected_reason = c["expected_reason_contains"]

            level, reason = derive_trust(ct, dt)
            self.assertEqual(level, expected_level,
                             f"{c['case']}: expected {expected_level}, "
                             f"got {level}: {reason}")
            for substr in expected_reason:
                self.assertIn(substr, reason,
                              f"{c['case']}: reason missing {substr!r}: "
                              f"{reason}")

    def test_invariant_both_ways(self):
        """requested >= derived: 'review' always accepted; 'safe' only when safe."""
        for c in self.fixture:
            ct = c["change_type"]
            dt = c["diff_text"]
            expected_level = c["expected_level"]

            # review always accepted (it is the top of the scale)
            derived, _ = check_invariant(ct, "review", dt)
            self.assertEqual(derived, "review" if expected_level == "review"
                             else "safe")

            # safe accepted iff expected_level is safe
            if expected_level == "safe":
                derived, _ = check_invariant(ct, "safe", dt)
                self.assertEqual(derived, "safe")
            else:
                with self.assertRaises(StructuredError) as ctx:
                    check_invariant(ct, "safe", dt)
                self.assertEqual(ctx.exception.error_category, "trust_mismatch")

    def test_policy_floor_monotonicity(self):
        """STATIC_FLOORS values are within TRUST_LEVELS and every non-update
        floor == 'review' (mvp-interfaces §2 Trust classification table)."""
        for ct, floor in STATIC_FLOORS.items():
            self.assertIn(floor, TRUST_LEVELS,
                          f"{ct} floor {floor!r} not in TRUST_LEVELS")
        for ct in ("split", "create_ru", "custom"):
            self.assertEqual(STATIC_FLOORS[ct], "review",
                             f"non-update floor for {ct} must be 'review'")

FIXTURES = os.path.join(REPO_ROOT, "tests", "fixtures", "documenter")


class TestCanonicalDiffGolden(unittest.TestCase):
    """Full canonical-diff golden test over golden_diff_canon_full.json fixture
    (mvp-contract §3.1 test_canonical_diff, §3.3 golden fixtures).

    Cases: plain LF, CRLF->LF, bare CR->LF, trailing whitespace,
    trailing blanks collapse, empty input, unicode, mixed endings,
    whitespace-only line.  Semantically equal diffs must hash identically.
    """

    def setUp(self):
        self.engine = StdDiffEngine()
        with open(
            os.path.join(FIXTURES, "golden_diff_canon_full.json"),
            encoding="utf-8",
        ) as fh:
            data = json.load(fh)
        self.cases = data["cases"]

    def test_each_case_normalize_hash(self):
        for c in self.cases:
            inp = c["input_diff"]
            expected_norm = c["normalized_bytes"]
            expected_hash = c["diff_hash"]

            normalized = self.engine.normalize(inp)
            self.assertEqual(
                normalized.decode("utf-8"), expected_norm,
                f"{c['case']}: normalized text mismatch")

            computed_hash = self.engine.diff_hash(normalized)
            self.assertEqual(
                computed_hash, expected_hash,
                f"{c['case']}: diff_hash mismatch")

    def test_each_case_idempotent(self):
        """normalize(normalize(x).decode()) == normalize(x)."""
        for c in self.cases:
            inp = c["input_diff"]
            norm1 = self.engine.normalize(inp)
            norm2 = self.engine.normalize(norm1.decode("utf-8"))
            self.assertEqual(norm1, norm2,
                             f"{c['case']}: normalize not idempotent")

    def test_semantically_equal_same_hash(self):
        """C-requirement: semantically equal diffs (LF/CRLF/trailing-space
        variants of the same logical diff) produce identical diff_hash."""
        # Cases that should all hash to the same value:
        # plain_lf, crlf_to_lf, bare_cr_to_lf
        # (and trailing_whitespace, trailing_blank_lines, mixed_endings share
        # another hash among themselves)
        same_group_1 = {"plain_lf", "crlf_to_lf", "bare_cr_to_lf"}
        same_group_2 = {"trailing_whitespace", "trailing_blank_lines",
                        "mixed_endings"}

        for group_name, group_cases in [("group1", same_group_1),
                                         ("group2", same_group_2)]:
            hashes = set()
            for c in self.cases:
                if c["case"] in group_cases:
                    h = self.engine.diff_hash(
                        self.engine.normalize(c["input_diff"]))
                    hashes.add(h)
            self.assertEqual(len(hashes), 1,
                             f"{group_name}: expected 1 hash, got {hashes}")

    def test_render_diff_and_prose(self):
        """render(normalize(x)) returns normalized text for diff-shaped input;
        render raises StructuredError("unknown") for non-diff prose."""
        # Diff-shaped inputs: render should return normalized verbatim
        for c in self.cases:
            if c["case"] == "empty_input":
                # Empty input: render returns "" (no diff check triggered)
                norm = self.engine.normalize(c["input_diff"])
                rendered = self.engine.render(norm)
                self.assertEqual(rendered, "")
                continue
            norm = self.engine.normalize(c["input_diff"])
            rendered = self.engine.render(norm)
            self.assertEqual(rendered, norm.decode("utf-8"),
                             f"{c['case']}: render mismatch")

        # Non-diff prose: should raise StructuredError("unknown")
        with self.assertRaises(StructuredError) as ctx:
            self.engine.render(b"just some prose\n")
        self.assertEqual(ctx.exception.error_category, "unknown")

    def test_decode_diff_input_valid(self):
        import base64
        # Valid base64 roundtrip
        raw = b"--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n"
        b64 = base64.b64encode(raw).decode()
        result = decode_diff_input(b64)
        self.assertEqual(result, raw.decode("utf-8"))

    def test_decode_diff_input_invalid(self):
        # Invalid base64 -> StructuredError unknown
        with self.assertRaises(StructuredError) as ctx:
            decode_diff_input("!!!not base64!!!")
        self.assertEqual(ctx.exception.error_category, "unknown")

    def test_decode_diff_input_oversized(self):
        import base64
        big = base64.b64encode(b"x" * 1001).decode()
        with self.assertRaises(StructuredError) as ctx:
            decode_diff_input(big, max_diff_bytes=10)
        self.assertEqual(ctx.exception.error_category, "unknown")
        self.assertIn("max_diff_bytes", ctx.exception.message)

    def test_decode_diff_input_non_utf8(self):
        import base64
        non_utf8 = base64.b64encode(b"\xff\xfe").decode()
        with self.assertRaises(StructuredError) as ctx:
            decode_diff_input(non_utf8)
        self.assertEqual(ctx.exception.error_category, "unknown")
        self.assertIn("UTF-8", ctx.exception.message)

    def test_decode_diff_input_empty_string(self):
        with self.assertRaises(StructuredError) as ctx:
            decode_diff_input("")
        self.assertEqual(ctx.exception.error_category, "unknown")


FIXTURES_GOLDEN_CANON = os.path.join(FIXTURES, "golden_diff_canon.json")
FIXTURE_CORPUS_FOR_DELEGATE = os.path.join(
    REPO_ROOT, "tests", "fixtures", "documenter", "corpus")


class TestDelegateGateWiring(unittest.TestCase):
    """Wiring tests for delegate(preview) with optional audit_id gate (mvp-interfaces
    §Pre-audit gate: rules 1-5 exercised through the composition root).
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_dir = os.path.join(self.tmpdir, "state")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_service(self, clock=None):
        """Create a Service over the fixture corpus with a temp registry."""
        return Service(
            FIXTURE_CORPUS_FOR_DELEGATE,
            registry=JsonlAuditRegistry(self.state_dir, clock=clock),
        )

    def _append_audit(self, service, **over):
        """Seed an audit_record via the registry (mimics audit() output)."""
        record_data = {
            "audit_id": "aud-seed",
            "issued_at": service.registry.now(),
            "scope": "*",
            "findings": [],
            "scanned_ids": ["alpha"],
            "has_remaining": False,
            "scan_cursor": None,
        }
        record_data.update(over)
        return service.registry.append(reg.AUDIT_RECORD, record_data)

    def test_no_audit_id_no_gate_key(self):
        """delegate without audit_id → no 'gate' key, next_action=preview_only
        (back-compat with existing assertions)."""
        svc = self._make_service()
        import base64
        diff = base64.b64encode(
            b"--- a/docs/en/alpha/index.md\n"
            b"+++ b/docs/en/alpha/index.md\n"
            b"@@ -1 +1 @@\n"
            b"-|x|\n"
            b"+|y|\n").decode()
        resp = svc.delegate(
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=diff, preview=True)
        self.assertNotIn("gate", resp)
        self.assertEqual(resp["next_action"], "preview_only")

    def test_audit_id_passed_gate(self):
        """Valid audit_id with a passing record → gate verdict=passed."""
        svc = self._make_service()
        self._append_audit(svc)
        import base64
        diff = base64.b64encode(
            b"--- a/docs/en/alpha/index.md\n"
            b"+++ b/docs/en/alpha/index.md\n"
            b"@@ -1 +1 @@\n"
            b"-|x|\n"
            b"+|y|\n").decode()
        resp = svc.delegate(
            target_id="alpha", change_type="update", trust_level="safe",
            diff_input=diff, preview=True, audit_id="aud-seed")
        self.assertIn("gate", resp)
        self.assertEqual(resp["gate"]["audit_id"], "aud-seed")
        self.assertEqual(resp["gate"]["verdict"], "passed")
        self.assertEqual(resp["next_action"], "preview_only")

    def test_audit_id_missing(self):
        """audit_id not in registry → audit_mismatch / rerun_audit (rule 1)."""
        svc = self._make_service()
        import base64
        diff = base64.b64encode(
            b"--- a/docs/en/alpha/index.md\n"
            b"+++ b/docs/en/alpha/index.md\n"
            b"@@ -1 +1 @@\n"
            b"-|x|\n"
            b"+|y|\n").decode()
        with self.assertRaises(StructuredError) as ctx:
            svc.delegate(
                target_id="alpha", change_type="update", trust_level="safe",
                diff_input=diff, preview=True, audit_id="nonexistent")
        self.assertEqual(ctx.exception.error_category, "audit_mismatch")
        self.assertEqual(ctx.exception.next_action, "rerun_audit")

    def test_audit_id_stale(self):
        """Stale record (issued_at older than audit_freshness) → audit_mismatch
        / rerun_audit (rule 2)."""
        svc = self._make_service()
        # Seed with an old issued_at using the registry directly.
        # We cannot use a stale injected clock because now() and issued_at
        # come from the same clock → age=0.  Construct the record data
        # ourselves instead.
        svc.registry.append(reg.AUDIT_RECORD, {
            "audit_id": "aud-seed",
            "issued_at": "2020-01-01T00:00:00Z",  # years old
            "scope": "*",
            "findings": [],
            "scanned_ids": ["alpha"],
            "has_remaining": False,
            "scan_cursor": None,
        })
        import base64
        diff = base64.b64encode(
            b"--- a/docs/en/alpha/index.md\n"
            b"+++ b/docs/en/alpha/index.md\n"
            b"@@ -1 +1 @@\n"
            b"-|x|\n"
            b"+|y|\n").decode()
        with self.assertRaises(StructuredError) as ctx:
            svc.delegate(
                target_id="alpha", change_type="update", trust_level="safe",
                diff_input=diff, preview=True, audit_id="aud-seed")
        self.assertEqual(ctx.exception.error_category, "audit_mismatch")
        self.assertEqual(ctx.exception.next_action, "rerun_audit")

    def test_audit_id_high_finding(self):
        """Record with high finding for target → blocking_finding,
        next_action=resolve_finding (rule 4)."""
        svc = self._make_service()
        self._append_audit(svc, findings=[{
            "subject_id": "alpha", "severity": "high",
            "description": "blocked", "suggested_action": "fix",
        }])
        import base64
        diff = base64.b64encode(
            b"--- a/docs/en/alpha/index.md\n"
            b"+++ b/docs/en/alpha/index.md\n"
            b"@@ -1 +1 @@\n"
            b"-|x|\n"
            b"+|y|\n").decode()
        with self.assertRaises(StructuredError) as ctx:
            svc.delegate(
                target_id="alpha", change_type="update", trust_level="safe",
                diff_input=diff, preview=True, audit_id="aud-seed")
        self.assertEqual(ctx.exception.error_category, "blocking_finding")
        self.assertEqual(ctx.exception.next_action, "resolve_finding")

    def test_audit_id_has_remaining(self):
        """Record with has_remaining=True → blocking_finding,
        next_action=rescan_to_completion (rule 5)."""
        svc = self._make_service()
        self._append_audit(svc, has_remaining=True, scan_cursor="tok123")
        import base64
        diff = base64.b64encode(
            b"--- a/docs/en/alpha/index.md\n"
            b"+++ b/docs/en/alpha/index.md\n"
            b"@@ -1 +1 @@\n"
            b"-|x|\n"
            b"+|y|\n").decode()
        with self.assertRaises(StructuredError) as ctx:
            svc.delegate(
                target_id="alpha", change_type="update", trust_level="safe",
                diff_input=diff, preview=True, audit_id="aud-seed")
        self.assertEqual(ctx.exception.error_category, "blocking_finding")
        self.assertEqual(ctx.exception.next_action, "rescan_to_completion")

    def test_audit_id_no_registry(self):
        """audit_id supplied but registry=None at core level → unknown."""
        import base64
        # Use the repo root policy (documenter_policy.yml exists there).
        max_diff = 524288  # DEFAULTS["max_diff_bytes"]
        from documenter_service.adapters.fs_manifest import FsManifestSource
        manifest = FsManifestSource(FIXTURE_CORPUS_FOR_DELEGATE)
        diff = base64.b64encode(
            b"--- a/docs/en/alpha/index.md\n"
            b"+++ b/docs/en/alpha/index.md\n"
            b"@@ -1 +1 @@\n"
            b"-|x|\n"
            b"+|y|\n").decode()
        engine = StdDiffEngine()
        with self.assertRaises(StructuredError) as ctx:
            delegate_preview(FIXTURE_CORPUS_FOR_DELEGATE, manifest,
               target_id="alpha", change_type="update", trust_level="safe",
               diff_input=diff, preview=True, engine=engine,
               max_diff_bytes=max_diff, audit_id="aud-seed", registry=None)
        self.assertEqual(ctx.exception.error_category, "unknown")


if __name__ == "__main__":
    unittest.main()



