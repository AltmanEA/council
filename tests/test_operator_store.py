"""Unit tests for operator_surface.adapters.session_store (MvpSessionStoreAsStub).

Step 4 — MVP session store: CRUD-only JSONL under root/sessions/<sid>/.
Classes MUST be named TestMvpSessionStoreAsStub* (DoD f).
All state lives in tempfile.TemporaryDirectory(); never writes to real paths.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

try:
    from operator_surface.adapters.session_store import MvpSessionStore  # noqa: F401
except ImportError:
    MvpSessionStore = None  # will fail with NameError in anti-reversed-TDD


def _root_files(root):
    """Return all files under root sorted (via os.walk)."""
    files = []
    for dp, dns, fns in os.walk(root):
        for fn in fns:
            rel = os.path.relpath(os.path.join(dp, fn), root)
            files.append(rel)
    return sorted(files)


class TestMvpSessionStoreAsStubInit(unittest.TestCase):
    """__init__ stores root and does not create files immediately."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        shutil.rmtree(self.tmp.name, ignore_errors=True)

    def test_root_stored(self):
        store = MvpSessionStore(self.tmp.name)
        self.assertEqual(store._root, self.tmp.name)

    def test_no_files_created_on_init(self):
        store = MvpSessionStore(self.tmp.name)
        self.assertEqual(_root_files(self.tmp.name), [])


class TestMvpSessionStoreAsStubCreateSession(unittest.TestCase):
    """create_session(session_id) creates session.jsonl and returns the dict."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        shutil.rmtree(self.tmp.name, ignore_errors=True)

    def test_creates_session_dir(self):
        store = MvpSessionStore(self.tmp.name)
        sid = "sess-abc123"
        store.create_session(sid)
        self.assertTrue(
            os.path.isdir(os.path.join(self.tmp.name, "sessions", sid))
        )

    def test_writes_session_jsonl(self):
        store = MvpSessionStore(self.tmp.name)
        sid = "sess-abc123"
        store.create_session(sid)
        path = os.path.join(self.tmp.name, "sessions", sid, "session.jsonl")
        self.assertTrue(os.path.isfile(path))

    def test_session_record_is_valid_json(self):
        store = MvpSessionStore(self.tmp.name)
        sid = "sess-abc123"
        result = store.create_session(sid)
        path = os.path.join(self.tmp.name, "sessions", sid, "session.jsonl")
        with open(path, "r", encoding="utf-8") as fh:
            line = fh.readline().strip()
        obj = json.loads(line)
        self.assertIsInstance(obj, dict)

    def test_returns_session_dict(self):
        store = MvpSessionStore(self.tmp.name)
        sid = "sess-abc123"
        result = store.create_session(sid)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["session_id"], sid)

    def test_session_dict_has_status_submitted(self):
        store = MvpSessionStore(self.tmp.name)
        sid = "sess-abc123"
        result = store.create_session(sid)
        self.assertEqual(result["status"], "submitted")

    def test_creates_intent_jsonl(self):
        store = MvpSessionStore(self.tmp.name)
        sid = "sess-abc123"
        store.create_session(sid)
        path = os.path.join(self.tmp.name, "sessions", sid, "intent.jsonl")
        self.assertTrue(os.path.isfile(path))

    def test_session_jsonl_only_file(self):
        store = MvpSessionStore(self.tmp.name)
        sid = "sess-abc123"
        store.create_session(sid)
        # session.jsonl + intent.jsonl = 2 files
        files = _root_files(self.tmp.name)
        self.assertEqual(len(files), 2)


class TestMvpSessionStoreAsStubGetSession(unittest.TestCase):
    """get_session(session_id) returns the dict or None."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        shutil.rmtree(self.tmp.name, ignore_errors=True)

    def test_existing_session_returns_dict(self):
        store = MvpSessionStore(self.tmp.name)
        sid = "sess-abc123"
        store.create_session(sid)
        result = store.get_session(sid)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["session_id"], sid)

    def test_absent_session_returns_none(self):
        store = MvpSessionStore(self.tmp.name)
        self.assertIsNone(store.get_session("sess-nonexistent"))

    def test_different_session_returns_none(self):
        store = MvpSessionStore(self.tmp.name)
        store.create_session("sess-aaa")
        self.assertIsNone(store.get_session("sess-bbb"))


class TestMvpSessionStoreAsStubListSessions(unittest.TestCase):
    """list_sessions() returns all session dicts (read-only)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        shutil.rmtree(self.tmp.name, ignore_errors=True)

    def test_empty_list(self):
        store = MvpSessionStore(self.tmp.name)
        self.assertEqual(store.list_sessions(), [])

    def test_returns_list_of_dicts(self):
        store = MvpSessionStore(self.tmp.name)
        store.create_session("sess-aaa")
        store.create_session("sess-bbb")
        result = store.list_sessions()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        for item in result:
            self.assertIsInstance(item, dict)

    def test_list_includes_all_sessions(self):
        store = MvpSessionStore(self.tmp.name)
        sids = ["sess-aaa", "sess-bbb", "sess-ccc"]
        for sid in sids:
            store.create_session(sid)
        result = store.list_sessions()
        result_ids = {r["session_id"] for r in result}
        for sid in sids:
            self.assertIn(sid, result_ids)

    def test_list_never_writes(self):
        store = MvpSessionStore(self.tmp.name)
        store.create_session("sess-aaa")
        before_files = set(_root_files(self.tmp.name))
        store.list_sessions()
        after_files = set(_root_files(self.tmp.name))
        self.assertEqual(before_files, after_files)


class TestMvpSessionStoreAsStubAppendRecord(unittest.TestCase):
    """append_record(session_id, record) appends to intent.jsonl and returns it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        shutil.rmtree(self.tmp.name, ignore_errors=True)

    def test_appends_to_intent_jsonl(self):
        store = MvpSessionStore(self.tmp.name)
        sid = "sess-aaa"
        store.create_session(sid)
        record = {"verb": "council.submit_task", "operator_id": "op-alice"}
        store.append_record(sid, record)
        path = os.path.join(self.tmp.name, "sessions", sid, "intent.jsonl")
        with open(path, "r", encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh if ln.strip()]
        self.assertEqual(len(lines), 1)

    def test_returns_record(self):
        store = MvpSessionStore(self.tmp.name)
        sid = "sess-aaa"
        store.create_session(sid)
        record = {"verb": "council.submit_task", "operator_id": "op-alice"}
        result = store.append_record(sid, record)
        self.assertEqual(result, record)

    def test_multiple_appends_accumulate(self):
        store = MvpSessionStore(self.tmp.name)
        sid = "sess-aaa"
        store.create_session(sid)
        store.append_record(sid, {"verb": "council.submit_task"})
        store.append_record(sid, {"verb": "council.list_sessions"})
        path = os.path.join(self.tmp.name, "sessions", sid, "intent.jsonl")
        with open(path, "r", encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh if ln.strip()]
        self.assertEqual(len(lines), 2)

    def test_returns_new_record_not_stored(self):
        store = MvpSessionStore(self.tmp.name)
        sid = "sess-aaa"
        store.create_session(sid)
        record = {"verb": "council.submit_task", "extra": True}
        result = store.append_record(sid, record)
        # The store does not mutate the record; returns it as-is
        self.assertEqual(result.get("extra"), True)


class TestMvpSessionStoreAsStubOD1Layout(unittest.TestCase):
    """OD-1 layout: sessions/<sid>/session.jsonl + intent.jsonl."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        shutil.rmtree(self.tmp.name, ignore_errors=True)

    def test_nested_under_sessions(self):
        store = MvpSessionStore(self.tmp.name)
        store.create_session("sess-layout")
        self.assertTrue(
            os.path.isdir(os.path.join(self.tmp.name, "sessions", "sess-layout"))
        )

    def test_no_files_outside_sessions(self):
        store = MvpSessionStore(self.tmp.name)
        store.create_session("sess-layout")
        files = _root_files(self.tmp.name)
        for f in files:
            self.assertTrue(f.startswith("sessions/"), f"Stray file: {f}")


if __name__ == "__main__":
    unittest.main()
