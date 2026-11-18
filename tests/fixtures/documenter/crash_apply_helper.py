#!/usr/bin/env python3
"""Helper script for real kill -9 crash-injection tests.

Usage:
    python3 tests/fixtures/documenter/crash_apply_helper.py <tmpdir> <seam> <data_dir>

Builds a minimal corpus/policy/briefing/registry, registers a seam that sends
SIGKILL to os.getpid() at the named seam boundary, then runs apply_write.

Exit code is 0 on normal completion (the crash was at the very end), 1 if the
process was killed.  The test harness checks observable artifacts in the tmpdir
after the process dies.

This script is imported/run by the parent test via subprocess.Popen and is NOT
imported by production code.
"""
import base64
import json
import os
import signal
import subprocess
import sys
import time

# tests/fixtures/documenter/<this file> -> up 4 levels is the repo root
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from documenter_service.adapters.diff_engine import StdDiffEngine  # noqa: E402
from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry  # noqa: E402
from documenter_service.adapters.stdout_events import StdoutEventSink  # noqa: E402
from documenter_service.core import registry as reg  # noqa: E402
from documenter_service.core.errors import StructuredError  # noqa: E402
from documenter_service.core import write as core_write  # noqa: E402
from documenter_service.core.policy import Policy  # noqa: E402


def _make_tier2_policy(briefing_path=None):
    fields = {
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
        "lock_wait_timeout": 30,
    }
    return Policy(fields)


def _make_manifest():
    entries_list = []
    manifest = type("Manifest", (), {
        "_entries": {},
        "entries": lambda self: entries_list,
        "resolve": lambda self, tid: self._entries.get(tid),
    })()
    for eid in ["alpha", "beta", "gamma"]:
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


def _make_doc_text():
    return "# Alpha\nid: alpha\nVersion: 1.0.0\nStatus: active\nchangelog-path: CHANGELOGS/alpha.md\n"


def _make_diff():
    doc_text = _make_doc_text()
    old_lines = doc_text.split("\n")
    effective_lines = old_lines
    if old_lines and old_lines[-1] == "":
        effective_lines = old_lines[:-1]
    hunk_header = (
        "@@ -1," + str(len(effective_lines))
        + " +1," + str(len(effective_lines))
        + " @@\n"
    )
    effective_diff = []
    for line in effective_lines:
        if line == "changelog-path: CHANGELOGS/alpha.md":
            effective_diff.append("-changelog-path: CHANGELOGS/alpha.md")
            effective_diff.append("+changelog-path: CHANGELOGS/alpha.updated.md")
        else:
            effective_diff.append(" " + line)
    diff_text = (
        "--- a/index.md\n+++ b/index.md\n"
        + hunk_header
        + "\n".join(effective_diff)
        + "\n"
    )
    return diff_text


def _encode_diff(diff_text):
    return base64.b64encode(diff_text.encode("utf-8")).decode("ascii")


def main():
    if len(sys.argv) < 4:
        print(
            "Usage: crash_apply_helper.py <tmpdir> <seam> <data_dir>",
            file=sys.stderr,
        )
        sys.exit(1)

    tmpdir = sys.argv[1]
    seam_name = sys.argv[2]
    data_dir = sys.argv[3]

    corpus = os.path.join(tmpdir, "corpus")
    os.makedirs(os.path.join(corpus, "docs", "en", "alpha"), exist_ok=True)

    # ADR-013: Tier 2+ requires the Operator Ingress readiness sentinel.
    sentinel = os.path.join(corpus, "documenter", ".operator_ingress_ready")
    os.makedirs(os.path.dirname(sentinel), exist_ok=True)
    with open(sentinel, "w") as f:
        f.write("")

    alpha_path = os.path.join(corpus, "docs", "en", "alpha", "index.md")
    with open(alpha_path, "w") as f:
        f.write(_make_doc_text())

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

    briefing_path = os.path.join(tmpdir, "_briefing.md")
    with open(briefing_path, "w") as f:
        f.write("# Briefing\n\nAuthorised operational context.\n")

    registry = JsonlAuditRegistry(os.path.join(tmpdir, "state"))
    manifest = _make_manifest()
    policy = _make_tier2_policy(briefing_path)
    events = StdoutEventSink()
    engine = StdDiffEngine()

    audit_record = {
        "audit_id": "aid-crash",
        "issued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scope": "*",
        "findings": [],
        "scanned_ids": ["alpha", "beta", "gamma"],
        "has_remaining": False,
    }
    registry.append(reg.AUDIT_RECORD, audit_record)

    diff_text = _make_diff()
    encoded_diff = _encode_diff(diff_text)

    # propose
    prop_result = core_write.propose_write(
        corpus, manifest, registry, policy, events, engine,
        target_id="alpha", change_type="update", trust_level="safe",
        diff_input=encoded_diff, audit_id="aid-crash", preview=False,
        proposer_id="op-proposer1",
    )

    approval_id = prop_result["approval_id"]

    # approve
    core_write.approve(
        registry, policy, events,
        root=corpus,
        approval_id=approval_id, operator_id="op-approver",
    )

    # Define the kill seam
    def kill_at_seam():
        os.kill(os.getpid(), signal.SIGKILL)

    seams = {seam_name: kill_at_seam}

    # apply_write (this will either succeed or be killed mid-sequence)
    try:
        core_write.apply_write(
            corpus, manifest, registry, policy, events, engine,
            approval_id=approval_id, operator_id="op-approver",
            diff_input=encoded_diff,
            data_dir=data_dir,
            seams=seams,
        )
    except StructuredError:
        # If apply_write raises (shouldn't happen with kill seam unless
        # the kill is at a boundary and the process continues), that's fine.
        pass
    except OSError:
        # The SIGKILL was delivered; Python may or may not recover here.
        pass


if __name__ == "__main__":
    main()
