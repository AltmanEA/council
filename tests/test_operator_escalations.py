"""Tests for volatile escalation store (Cycle 7 Step 6).

Frozen API contract:
  - class EscalationStore: open / get / list / resolve / supersede /
    mark_expired / had_escalations / volatile_notice
  - def render(record) -> dict  (exactly 4 keys: request, fallback_consequences,
    deadline, status)
  - Events: escalation.opened (on open), escalation.resolved (on resolve)
  - Volatile: two-store isolation, had_escalations, volatile_notice
  - NO disk I/O ever

Fakes:
  - ListEventSink — collects appended envelopes in a list

Target: red baseline (EscalationStore/render are None), back-compat:
  existing verbs + architecture GREEN.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import threading
import unittest

# ---------------------------------------------------------------------------
# Red-baseline imports (try/except sets names to None for skip guards)
# ---------------------------------------------------------------------------

try:
    from operator_surface.core.escalations import (  # noqa: F401
        EscalationStore,
        render,
    )
except ImportError:
    EscalationStore = None  # type: ignore[misc,assignment]
    render = None  # type: ignore[misc,assignment]

try:
    from operator_surface.core.events import make_envelope  # noqa: F401
except ImportError:
    make_envelope = None  # type: ignore[misc,assignment]

try:
    from operator_surface.ports import EventSink  # noqa: F401
except ImportError:
    EventSink = None  # type: ignore[misc,assignment]

try:
    from operator_surface.core.verbs import status  # noqa: F401
except ImportError:
    status = None  # type: ignore[misc,assignment]

# ---------------------------------------------------------------------------
# Red-baseline helpers: introspect status() signature
# ---------------------------------------------------------------------------


def _status_accepts_escalation_store():
    """Return True if the loaded status() accepts escalation_store kwarg."""
    if status is None:
        return False
    try:
        import inspect
        sig = inspect.signature(status)
        return "escalation_store" in sig.parameters
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class ListEventSink:
    """In-memory event sink that collects appended envelopes."""

    def __init__(self):
        self.events: list[dict] = []

    def append(self, event: dict) -> None:
        self.events.append(event)


# ---------------------------------------------------------------------------
# Test class: EscalationStore — lifecycle (cases A–F)
# ---------------------------------------------------------------------------

class TestEscalationStoreLifecycle(unittest.TestCase):
    """Cases A–F: open / get / list / resolve / supersede / mark_expired."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _store(self):
        return EscalationStore(self.tmpdir)

    # --- Case A: open → esc- regex, status pending, created_at Z, fields ---

    @unittest.skipIf(EscalationStore is None, "red baseline: EscalationStore not yet implemented")
    def test_case_A_open_creates_record(self):
        """open() produces esc-[a-z0-9...] id, status=pending,
        created_at with Z suffix, and all MVP fields present."""
        store = self._store()
        rec = store.open(
            session_id="sess-demo001",
            request="Resolve conflicting positions on scope A",
            fallback_strategy="apply phase 2 default",
            timeout_at="2026-12-31T23:59:59Z",
            resume_phase="3",
        )
        self.assertRegex(rec["escalation_id"], r"^esc-[a-z0-9][a-z0-9-]{2,63}$")
        self.assertEqual(rec["status"], "pending")
        self.assertTrue(rec["created_at"].endswith("Z"))
        self.assertEqual(rec["request"], "Resolve conflicting positions on scope A")
        self.assertEqual(rec["fallback_strategy"], "apply phase 2 default")
        self.assertEqual(rec["timeout_at"], "2026-12-31T23:59:59Z")
        self.assertEqual(rec["session_id"], "sess-demo001")
        self.assertEqual(rec["resume_phase"], "3")

    # --- Case B: get known / get unknown ---

    @unittest.skipIf(EscalationStore is None, "red baseline: EscalationStore not yet implemented")
    def test_case_B_get_known_and_unknown(self):
        """get(existing esc_id) → record; get(foreign) → None."""
        store = self._store()
        rec = store.open(
            session_id="sess-demo002",
            request="missing input",
            fallback_strategy="reject",
            timeout_at="2026-06-01T00:00:00Z",
            resume_phase="2",
        )
        self.assertEqual(store.get(rec["escalation_id"]), rec)
        self.assertIsNone(store.get("esc-nonexistent001"))

    # --- Case C: list(session) scoped; list() (no arg) → all ---

    @unittest.skipIf(EscalationStore is None, "red baseline: EscalationStore not yet implemented")
    def test_case_C_list_scoped_and_all(self):
        """list(session_id) returns only that session's records.
        list() (no arg) returns all records."""
        store = self._store()
        rec_a = store.open(
            session_id="sess-c0-a",
            request="scope A",
            fallback_strategy="a-default",
            timeout_at="2026-06-01T00:00:00Z",
            resume_phase="2",
        )
        rec_b = store.open(
            session_id="sess-c0-b",
            request="scope B",
            fallback_strategy="b-default",
            timeout_at="2026-06-01T00:00:00Z",
            resume_phase="2",
        )
        scoped = store.list("sess-c0-a")
        self.assertEqual(len(scoped), 1)
        self.assertEqual(scoped[0]["escalation_id"], rec_a["escalation_id"])
        all_recs = store.list()
        self.assertEqual(len(all_recs), 2)
        ids = {r["escalation_id"] for r in all_recs}
        self.assertIn(rec_a["escalation_id"], ids)
        self.assertIn(rec_b["escalation_id"], ids)

    # --- Case D: resolve: accept, reject, second resolve → ValueError,
    #              bad decision → ValueError; supersede/mark_expired post-resolve ---

    @unittest.skipIf(EscalationStore is None, "red baseline: EscalationStore not yet implemented")
    def test_case_D_resolve_accept_reject_terminal(self):
        """resolve(accept) → accepted; resolve(reject) → rejected;
        second resolve → ValueError; resolve with bad decision → ValueError;
        supersede after resolve → ValueError; mark_expired after resolve → ValueError."""
        store = self._store()
        rec = store.open(
            session_id="sess-d0",
            request="missing config",
            fallback_strategy="fallback",
            timeout_at="2026-06-01T00:00:00Z",
            resume_phase="3",
        )
        eid = rec["escalation_id"]

        # Accept
        r1 = store.resolve(eid, "accept", "op-alice")
        self.assertEqual(r1["status"], "accepted")

        # Second resolve → ValueError (terminal + immutable)
        with self.assertRaises(ValueError):
            store.resolve(eid, "accept", "op-bob")

        # Bad decision → ValueError
        rec2 = store.open(
            session_id="sess-d0b",
            request="missing input 2",
            fallback_strategy="f2",
            timeout_at="2026-06-01T00:00:00Z",
            resume_phase="3",
        )
        with self.assertRaises(ValueError):
            store.resolve(rec2["escalation_id"], "flip", "op-alice")

        # Resolved record → supersede raises ValueError
        with self.assertRaises(ValueError):
            store.supersede(eid)

        # Resolved record → mark_expired raises ValueError
        with self.assertRaises(ValueError):
            store.mark_expired(eid)

    # --- Case E: supersede pending → superseded; supersede twice → ValueError ---

    @unittest.skipIf(EscalationStore is None, "red baseline: EscalationStore not yet implemented")
    def test_case_E_supersede_pending_twice(self):
        """supersede on pending → superseded status;
        supersede on already superseded → ValueError."""
        store = self._store()
        rec = store.open(
            session_id="sess-e0",
            request="first escalation",
            fallback_strategy="f-default",
            timeout_at="2026-06-01T00:00:00Z",
            resume_phase="2",
        )
        eid = rec["escalation_id"]

        s1 = store.supersede(eid)
        self.assertEqual(s1["status"], "superseded")

        with self.assertRaises(ValueError):
            store.supersede(eid)

    # --- Case F: mark_expired pending → expired; past timeout_at still pending ---

    @unittest.skipIf(EscalationStore is None, "red baseline: EscalationStore not yet implemented")
    def test_case_F_mark_expired_and_no_auto_expiry(self):
        """mark_expired on pending → expired status.
        A record with timeout_at in the past stays 'pending' (no auto-expiry)."""
        store = self._store()

        # mark_expired path
        rec1 = store.open(
            session_id="sess-f0",
            request="expire me",
            fallback_strategy="f-default",
            timeout_at="2099-01-01T00:00:00Z",
            resume_phase="3",
        )
        me = store.mark_expired(rec1["escalation_id"])
        self.assertEqual(me["status"], "expired")

        # No auto-expiry: past timestamp still pending.
        rec2 = store.open(
            session_id="sess-f1",
            request="do not expire",
            fallback_strategy="f-other",
            timeout_at="2020-01-01T00:00:00Z",
            resume_phase="2",
        )
        self.assertEqual(rec2["status"], "pending")
        # No sleep needed — the record sits as pending with a 2020 timestamp.

    @unittest.skipIf(EscalationStore is None, "red baseline: EscalationStore not yet implemented")
    def test_case_D2_mutating_returned_record_does_not_change_store(self):
        """Mutating a returned record must NOT mutate the store.
        Mutating the open() return, get() return, list() returns,
        and resolve()/supersede()/mark_expired() returns — all
        independent copies. Re-get must still show internal state."""
        store = self._store()
        eid = "esc-dummy000"

        # open() return — mutate then re-get.
        rec = store.open(
            session_id="sess-d000",
            request="mutate me",
            fallback_strategy="f-default",
            timeout_at="2026-06-01T00:00:00Z",
            resume_phase="3",
        )
        eid = rec["escalation_id"]
        rec["status"] = "hacked"
        self.assertEqual(store.get(eid)["status"], "pending")

        # get() return — mutate then re-get.
        got = store.get(eid)
        got["status"] = "hacked2"
        got["escalation_id"] = "esc-hacked"
        self.assertEqual(store.get(eid)["status"], "pending")
        self.assertIn(eid, [r["escalation_id"] for r in store.list()])

        # list() returns — mutate then re-list.
        items = store.list("sess-d000")
        items[0]["status"] = "hacked3"
        items[0]["escalation_id"] = "esc-hacked2"
        self.assertIn(store.get(eid)["status"], ("pending",))

        # resolve() return — mutate the copy, store still transitions.
        r1 = store.resolve(eid, "accept", "op-alice")
        r1["status"] = "not_accepted"
        r1_2 = store.get(eid)
        self.assertEqual(r1_2["status"], "accepted")

        # Second resolve must still raise ValueError (terminal).
        with self.assertRaises(ValueError):
            store.resolve(eid, "reject", "op-bob")

        # supersede() return — mutate copy, store still guard.
        eid2 = store.open(
            session_id="sess-d001",
            request="supersede guard",
            fallback_strategy="f-x",
            timeout_at="2026-06-01T00:00:00Z",
            resume_phase="2",
        )["escalation_id"]
        s1 = store.supersede(eid2)
        s1["status"] = "not_superseded"
        s1_2 = store.get(eid2)
        self.assertEqual(s1_2["status"], "superseded")

        # mark_expired() return — mutate copy, store still guard.
        eid3 = store.open(
            session_id="sess-d002",
            request="expire guard",
            fallback_strategy="f-y",
            timeout_at="2099-01-01T00:00:00Z",
            resume_phase="3",
        )["escalation_id"]
        me1 = store.mark_expired(eid3)
        me1["status"] = "not_expired"
        me1_2 = store.get(eid3)
        self.assertEqual(me1_2["status"], "expired")

# ---------------------------------------------------------------------------
# Test class: render (case G)
# ---------------------------------------------------------------------------


class TestRenderMVP(unittest.TestCase):
    """Case G: render(record) → dict with exactly 4 keys, verbatim fields."""

    @unittest.skipIf(render is None, "red baseline: render not yet implemented")
    def test_case_G_render_four_keys(self):
        """render produces exactly {request, fallback_consequences,
        deadline, status}. request verbatim (including special chars);
        deadline == timeout_at when set; None timeout_at → 'no deadline';
        status rendered as-is."""
        # request with special characters — verbatim comparison.
        request_text = 'Resolve "conflicting positions" on scope A & B'
        fallback_text = "apply phase 2 default"
        deadline_text = "2026-12-31T23:59:59Z"

        record_ok = {
            "escalation_id": "esc-render001",
            "request": request_text,
            "fallback_strategy": fallback_text,
            "timeout_at": deadline_text,
            "status": "pending",
            "session_id": "sess-g0",
            "resume_phase": "2",
            "created_at": "2026-01-01T00:00:00Z",
        }
        result = render(record_ok)
        self.assertEqual(set(result.keys()), {"request", "fallback_consequences", "deadline", "status"})
        self.assertEqual(len(result), 4)
        self.assertEqual(result["request"], request_text)
        self.assertEqual(result["fallback_consequences"], fallback_text)
        self.assertEqual(result["deadline"], deadline_text)
        self.assertEqual(result["status"], "pending")

        # deadline == "no deadline" when timeout_at is None.
        record_no_deadline = dict(record_ok, timeout_at=None)
        result2 = render(record_no_deadline)
        self.assertEqual(result2["deadline"], "no deadline")

        # status rendered as-is (e.g. after resolve).
        record_accepted = dict(record_ok, status="accepted")
        result3 = render(record_accepted)
        self.assertEqual(result3["status"], "accepted")

# ---------------------------------------------------------------------------
# Test class: event emission (case H)
# ---------------------------------------------------------------------------


class TestEventEmission(unittest.TestCase):
    """Case H: open emits escalation.opened; resolve emits escalation.resolved;
    payload keys asserted; event_sink=None paths fine."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _store(self):
        return EscalationStore(self.tmpdir)

    @unittest.skipIf(EscalationStore is None, "red baseline: EscalationStore not yet implemented")
    def test_case_H_events_opened_and_resolved(self):
        """open emits [escalation.opened]; resolve emits escalation.resolved;
        payload keys present; event_sink=None does not crash."""
        sink = ListEventSink()
        store = self._store()
        rec = store.open(
            session_id="sess-h000",
            request="open me",
            fallback_strategy="f-default",
            timeout_at="2026-06-01T00:00:00Z",
            resume_phase="3",
            event_sink=sink,
            actor={"kind": "operator", "id": "op-alice"},
        )
        self.assertEqual(len(sink.events), 1)
        self.assertEqual(sink.events[0]["event_type"], "escalation.opened")
        self.assertEqual(sink.events[0]["session_id"], "sess-h000")
        payload = sink.events[0]["payload"]
        self.assertIn("escalation_id", payload)
        self.assertIn("session_id", payload)

        # Resolve emits escalation.resolved.
        eid = rec["escalation_id"]
        store.resolve(eid, "accept", "op-bob", event_sink=sink)
        self.assertEqual(len(sink.events), 2)
        self.assertEqual(sink.events[1]["event_type"], "escalation.resolved")
        payload2 = sink.events[1]["payload"]
        self.assertIn("escalation_id", payload2)
        self.assertIn("decision", payload2)
        self.assertIn("operator_id", payload2)
        self.assertEqual(payload2["decision"], "accept")
        self.assertEqual(payload2["operator_id"], "op-bob")

    @unittest.skipIf(EscalationStore is None, "red baseline: EscalationStore not yet implemented")
    def test_case_H_event_sink_none(self):
        """open/resolve with event_sink=None → no crash, no events."""
        store = self._store()
        rec = store.open(
            session_id="sess-h1",
            request="sink none",
            fallback_strategy="f-x",
            timeout_at="2026-06-01T00:00:00Z",
            resume_phase="3",
            event_sink=None,
        )
        store.resolve(rec["escalation_id"], "reject", "op-alice", event_sink=None)
        # If we reach here without exception: no crash.

    @unittest.skipIf(EscalationStore is None, "red baseline: EscalationStore not yet implemented")
    def test_case_H2_open_emits_with_default_actor(self):
        """open(..., event_sink=sink) WITHOUT actor → emits escalation.opened
        with actor {"kind": "service", "id": "operator-surface"}."""
        sink = ListEventSink()
        store = self._store()
        rec = store.open(
            session_id="sess-h000",
            request="default actor test",
            fallback_strategy="f-default",
            timeout_at="2026-06-01T00:00:00Z",
            resume_phase="3",
            event_sink=sink,
        )
        self.assertEqual(len(sink.events), 1)
        self.assertEqual(sink.events[0]["event_type"], "escalation.opened")
        self.assertEqual(sink.events[0]["session_id"], "sess-h000")
        self.assertEqual(
            sink.events[0]["actor"],
            {"kind": "service", "id": "operator-surface"},
        )
        self.assertIn("escalation_id", sink.events[0]["payload"])

# ---------------------------------------------------------------------------
# Test class: volatility (case I)
# ---------------------------------------------------------------------------


class TestVolatility(unittest.TestCase):
    """Case I: two-store isolation, had_escalations, volatile_notice."""

    def setUp(self):
        self.tmpdir_a = tempfile.mkdtemp()
        self.tmpdir_b = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir_a, ignore_errors=True)
        shutil.rmtree(self.tmpdir_b, ignore_errors=True)

    @unittest.skipIf(EscalationStore is None, "red baseline: EscalationStore not yet implemented")
    def test_case_I_two_store_isolation(self):
        """storeA.open(...) → storeB.get(same id) is None;
        storeB.list() == []; B.had_escalations() False;
        A.had_escalations() True; A.volatile_notice() present."""
        store_a = EscalationStore(self.tmpdir_a)
        store_b = EscalationStore(self.tmpdir_b)

        self.assertFalse(store_b.had_escalations())
        self.assertIsNone(store_b.volatile_notice())

        rec = store_a.open(
            session_id="sess-i0",
            request="isolation test",
            fallback_strategy="fallback",
            timeout_at="2026-06-01T00:00:00Z",
            resume_phase="2",
        )
        eid = rec["escalation_id"]

        # storeB is completely empty.
        self.assertIsNone(store_b.get(eid))
        self.assertEqual(store_b.list(), [])
        self.assertFalse(store_b.had_escalations())

        # storeA sees its own record.
        self.assertEqual(store_a.had_escalations(), True)
        notice = store_a.volatile_notice()
        self.assertIsNotNone(notice)
        self.assertEqual(notice["type"], "notice.fallback-deferred")
        self.assertEqual(notice["severity"], "Advisory")
        text_lower = notice["text"].lower()
        self.assertIn("escalation", text_lower)
        self.assertTrue(
            "persist" in text_lower or "restart" in text_lower,
            f"notice text must mention persist/restart, got: {notice['text']}",
        )

# ---------------------------------------------------------------------------
# Test class: status() integration (case J)
# ---------------------------------------------------------------------------


class TestStatusIntegration(unittest.TestCase):
    """Case J: status(store, notices_provider, escalation_store=...)"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @unittest.skipIf(
        EscalationStore is None or not _status_accepts_escalation_store(),
        "red baseline: EscalationStore or status() lacks escalation_store",
    )
    def test_case_J_status_with_escalation_store(self):
        """status(store, notices_provider, escalation_store=esc_store)
        returns result['escalations'] with render() of pending records only,
        and appends volatile_notice to result['notices']."""
        store = MvpSessionStore(self.tmpdir)
        notices_provider = lambda: ["stub notice"]
        esc_store = EscalationStore(self.tmpdir)

        # Open a pending escalation.
        esc_store.open(
            session_id="sess-j0",
            request="pending escalation",
            fallback_strategy="f-default",
            timeout_at="2026-06-01T00:00:00Z",
            resume_phase="3",
        )
        # Also open one and resolve it (should NOT appear in pending list).
        esc2 = esc_store.open(
            session_id="sess-j0b",
            request="resolved escalation",
            fallback_strategy="f-alt",
            timeout_at="2026-06-01T00:00:00Z",
            resume_phase="2",
        )
        esc_store.resolve(esc2["escalation_id"], "accept", "op-alice")

        result = status(store, notices_provider, operator_id="op-alice", escalation_store=esc_store)

        self.assertIn("escalations", result)
        esc_list = result["escalations"]
        # Only the pending one (not the resolved one).
        self.assertEqual(len(esc_list), 1)
        self.assertEqual(esc_list[0]["request"], "pending escalation")
        self.assertEqual(esc_list[0]["status"], "pending")
        # Volatile notice appended.
        self.assertIn("notices", result)
        self.assertEqual(result["notices"][-1]["type"], "notice.fallback-deferred")

    @unittest.skipIf(
        not _status_accepts_escalation_store(),
        "red baseline: status() lacks escalation_store parameter",
    )
    def test_case_J_no_escalation_store(self):
        """status(store, notices_provider, escalation_store=None)
        returns 'escalations': [] and notices unchanged."""
        store = MvpSessionStore(self.tmpdir)
        notices_provider = lambda: ["only notice"]

        result = status(store, notices_provider, operator_id="op-alice", escalation_store=None)

        self.assertEqual(result["escalations"], [])
        self.assertEqual(result["notices"], ["only notice"])

# ---------------------------------------------------------------------------
# Test class: no disk writes (case K)
# ---------------------------------------------------------------------------


class TestNoDiskWrites(unittest.TestCase):
    """Case K: full lifecycle must NOT create any files on disk."""

    @unittest.skipIf(EscalationStore is None, "red baseline: EscalationStore not yet implemented")
    def test_case_K_no_disk_write_lifecycle(self):
        """Run open → supersede → mark_expired (or full chain) inside
        a fresh empty tempdir; assert os.listdir of that dir is empty."""
        tmpdir = tempfile.mkdtemp()
        try:
            store = EscalationStore(tmpdir)
            rec = store.open(
                session_id="sess-k0",
                request="no disk please",
                fallback_strategy="none",
                timeout_at="2026-06-01T00:00:00Z",
                resume_phase="2",
            )
            # Even a full lifecycle produces zero files.
            store.supersede(rec["escalation_id"])
            rec2 = store.open(
                session_id="sess-k0b",
                request="second esc",
                fallback_strategy="f2",
                timeout_at="2026-06-01T00:00:00Z",
                resume_phase="3",
            )
            store.mark_expired(rec2["escalation_id"])
            # The escalation module must not open() files.
            listing = os.listdir(tmpdir)
            self.assertEqual(listing, [])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Back-compat imports
# ---------------------------------------------------------------------------

try:
    from operator_surface.adapters.session_store import MvpSessionStore  # noqa: F401
except ImportError:
    MvpSessionStore = None  # type: ignore[misc,assignment]


if __name__ == "__main__":
    unittest.main()
