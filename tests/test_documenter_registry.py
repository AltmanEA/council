"""Tests for the Documenter MVP audit registry (mvp-data-models §1).

test_registry_integrity, test_corrupt_registry_status, test_token_lifecycle,
test_clock_injection — chain continuity, corruption detection, checkpoint
before truncation, single-use bound tokens, deterministic freshness.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from documenter_service.__main__ import Service, main  # noqa: E402
from documenter_service.adapters.jsonl_registry import (  # noqa: E402
    JsonlAuditRegistry, REGISTRY_FILENAME)
from documenter_service.adapters.stdout_events import StdoutEventSink  # noqa: E402
from documenter_service.core import registry as reg  # noqa: E402
from documenter_service.core.errors import StructuredError  # noqa: E402

FIXTURE_CORPUS = os.path.join(REPO_ROOT, "tests", "fixtures", "documenter",
                              "corpus")


def _tmpdir():
    return tempfile.mkdtemp()


def _registry(tmp, clock=None):
    return JsonlAuditRegistry(os.path.join(tmp, "state"), clock=clock)


def _copy_if_fixture(root):
    """Copy the checked-in fixture corpus: audit() now writes state under
    root/documenter/ (hash store) — the fixture must stay pristine."""
    if os.path.abspath(root) == os.path.abspath(FIXTURE_CORPUS):
        base = tempfile.mkdtemp()
        work = os.path.join(base, "corpus")
        shutil.copytree(FIXTURE_CORPUS, work)
        return work
    return root


def _service(tmp, clock=None, root=FIXTURE_CORPUS, events=None):
    return Service(_copy_if_fixture(root),
                   registry=_registry(tmp, clock),
                   events=events or StdoutEventSink(io.StringIO()))


class TestRegistryIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmpdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_chain_continuous_after_series_appends(self):
        r = _registry(self.tmp)
        for i in range(5):
            r.append(reg.AUDIT_RECORD, {"audit_id": f"a{i}", "scope": "*",
                                        "findings": [], "scanned_ids": [],
                                        "has_remaining": False,
                                        "scan_cursor": None,
                                        "issued_at": "2026-11-13T00:00:00Z"})
        records, status = r.read_all()
        self.assertEqual(status, "healthy")
        self.assertEqual(len(records), 5)
        self.assertIsNone(records[0]["prev_hash"])
        for i in range(1, 5):
            self.assertEqual(records[i]["prev_hash"],
                             reg.record_hash(records[i - 1]))
        # envelope is exactly the three normative keys
        self.assertEqual(set(records[0]), {"record_type", "prev_hash", "data"})

    def test_tamper_middle_record_degraded(self):
        r = _registry(self.tmp)
        for i in range(4):
            r.append(reg.CHECKPOINT_RECORD, {"segment_hash": "0" * 64,
                                             "truncated_count": i})
        path = os.path.join(self.tmp, "state", REGISTRY_FILENAME)
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        rec = json.loads(lines[1])
        rec["data"]["truncated_count"] = 999  # silent edit, chain not updated
        lines[1] = json.dumps(rec, sort_keys=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        _, status = r.read_all()
        self.assertEqual(status, "degraded")

    def test_truncate_without_checkpoint_refused(self):
        r = _registry(self.tmp)
        for i in range(3):
            r.append(reg.AUDIT_RECORD, {"audit_id": f"a{i}"})
        with self.assertRaises(StructuredError) as ctx:
            r.truncate(2)
        self.assertEqual(ctx.exception.error_category, "gate_failure")
        self.assertIn("checkpoint", ctx.exception.message)
        # refusal changed nothing
        records, _ = r.read_all()
        self.assertEqual(len(records), 3)

    def test_truncate_after_checkpoint_ok_chain_holds(self):
        r = _registry(self.tmp)
        for i in range(5):
            r.append(reg.AUDIT_RECORD, {"audit_id": f"a{i}"})
        r.write_checkpoint()  # checkpoint covers the oldest records
        records, _ = r.read_all()
        count = records[-1]["data"]["truncated_count"]
        result = r.truncate(count)
        self.assertEqual(result["truncated_count"], count)
        records, status = r.read_all()
        self.assertEqual(status, "healthy")
        # checkpoint survives and remains the tail
        self.assertEqual(records[-1]["record_type"], reg.CHECKPOINT_RECORD)
        # chain still verifies (compaction head accepted)
        for i in range(1, len(records)):
            self.assertEqual(records[i]["prev_hash"],
                             reg.record_hash(records[i - 1]))

    def test_empty_file_is_healthy_zero_records(self):
        r = _registry(self.tmp)
        os.makedirs(os.path.join(self.tmp, "state"), exist_ok=True)
        open(os.path.join(self.tmp, "state", REGISTRY_FILENAME), "w").close()
        records, status = r.read_all()
        self.assertEqual(records, [])
        self.assertEqual(status, "healthy")
        env = r.append(reg.AUDIT_RECORD, {"audit_id": "x"})
        self.assertIsNone(env["prev_hash"])  # first record starts the chain


class TestCorruptRegistryStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmpdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _corrupt_with(self, content):
        state = os.path.join(self.tmp, "state")
        os.makedirs(state, exist_ok=True)
        with open(os.path.join(state, REGISTRY_FILENAME), "w",
                  encoding="utf-8") as fh:
            fh.write(content)

    def test_malformed_json_is_corrupt(self):
        self._corrupt_with('{"record_type": "audit_record"\n')
        r = _registry(self.tmp)
        self.assertEqual(r.status(), "corrupt")

    def test_truncated_last_line_is_corrupt(self):
        r = _registry(self.tmp)
        r.append(reg.AUDIT_RECORD, {"audit_id": "ok"})
        path = os.path.join(self.tmp, "state", REGISTRY_FILENAME)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write('{"record_type": "audit_record", "prev_hash": nul')
        self.assertEqual(r.status(), "corrupt")

    def test_status_reports_corrupt_without_crashing(self):
        self._corrupt_with("not json at all\n")
        os.environ["DOCUMENTER_DATA_DIR"] = os.path.join(self.tmp, "state")
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = main(["--root", _copy_if_fixture(FIXTURE_CORPUS),
                           "--status", "--json"])
        finally:
            os.environ.pop("DOCUMENTER_DATA_DIR", None)
        # exit 0: status answers despite corruption (the service must not go
        # silent — mvp-interfaces §3 Registry health)
        self.assertEqual(rc, 0, out.getvalue())
        resp = json.loads(out.getvalue().strip().splitlines()[-1])
        self.assertEqual(resp["registry"]["status"], "corrupt")

    def test_delegate_denied_on_corrupt_registry(self):
        self._corrupt_with("{ broken\n")
        svc = _service(self.tmp)
        with self.assertRaises(StructuredError) as ctx:
            svc.delegate(target_id="alpha", change_type="update",
                         trust_level="review", diff_input="eA==",
                         preview=True)
        self.assertEqual(ctx.exception.error_category, "gate_failure")

    def test_audit_denied_on_corrupt_registry(self):
        self._corrupt_with("{ broken\n")
        svc = _service(self.tmp)
        with self.assertRaises(StructuredError) as ctx:
            svc.audit(target_id="*")
        self.assertEqual(ctx.exception.error_category, "gate_failure")


class TestTokenLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmpdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _issue(self, r, value="tok-1", audit_id="aud-1", target="alpha"):
        r.issue_token("scan_cursor", value,
                      {"audit_id": audit_id, "target_id": target})

    def test_single_use_replay_rejected(self):
        r = _registry(self.tmp)
        self._issue(r)
        r.consume_token("tok-1", "alpha")
        with self.assertRaises(StructuredError) as ctx:
            r.consume_token("tok-1", "alpha")
        self.assertEqual(ctx.exception.error_category, "token_replay")
        self.assertEqual(ctx.exception.next_action, "rerun_audit")

    def test_bound_to_audit_and_target(self):
        r = _registry(self.tmp)
        self._issue(r, audit_id="aud-1", target="alpha")
        # wrong target: a cursor for A cannot resume a scan for B
        with self.assertRaises(StructuredError) as ctx:
            r.consume_token("tok-1", "beta")
        self.assertEqual(ctx.exception.error_category, "audit_mismatch")
        # wrong audit_id (explicit) also refused
        with self.assertRaises(StructuredError) as ctx:
            r.consume_token("tok-1", "alpha", audit_id="aud-other")
        self.assertEqual(ctx.exception.error_category, "audit_mismatch")
        # correct pair works and adopts the bound audit_id
        token = r.consume_token("tok-1", "alpha")
        self.assertEqual(token["bound_to"]["audit_id"], "aud-1")
        self.assertTrue(token["consumed"])

    def test_unknown_token_rejected(self):
        r = _registry(self.tmp)
        with self.assertRaises(StructuredError) as ctx:
            r.consume_token("forged", "alpha")
        self.assertEqual(ctx.exception.error_category, "audit_mismatch")

    def test_consumption_append_only(self):
        r = _registry(self.tmp)
        self._issue(r)
        path = os.path.join(self.tmp, "state", REGISTRY_FILENAME)
        with open(path, encoding="utf-8") as fh:
            before = fh.read()
        r.consume_token("tok-1", "alpha")
        with open(path, encoding="utf-8") as fh:
            after = fh.read()
        self.assertTrue(after.startswith(before))  # nothing rewritten


class TestClockInjection(unittest.TestCase):
    """Freshness boundaries of status().registry.last_audit.fresh are
    deterministic under an injected clock (mvp-contract §3.1)."""

    def setUp(self):
        self.tmp = _tmpdir()
        self.t0 = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
        self.now = [self.t0]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fresh_and_stale_boundaries(self):
        reg_r = _registry(self.tmp, clock=lambda: self.now[0])
        svc = Service(_copy_if_fixture(FIXTURE_CORPUS), registry=reg_r,
                      events=StdoutEventSink(io.StringIO()))
        svc.audit(target_id="alpha")
        # exactly at the boundary (30 min) → fresh (age <= window)
        self.now[0] = self.t0 + timedelta(minutes=30)
        resp = svc.status()
        self.assertTrue(resp["registry"]["last_audit"]["fresh"])
        # one second past → stale
        self.now[0] = self.t0 + timedelta(minutes=30, seconds=1)
        resp = svc.status()
        self.assertFalse(resp["registry"]["last_audit"]["fresh"])
        # well inside → fresh
        self.now[0] = self.t0 + timedelta(minutes=1)
        self.assertTrue(svc.status()["registry"]["last_audit"]["fresh"])

    def test_issued_at_from_injected_clock(self):
        reg_r = _registry(self.tmp, clock=lambda: self.now[0])
        env = reg_r.append(reg.AUDIT_RECORD, {"audit_id": "x"})
        self.assertEqual(env["data"], {"audit_id": "x"})
        self.assertEqual(reg_r.now(), "2026-11-13T12:00:00Z")


if __name__ == "__main__":
    unittest.main()
