"""Unit tests for the telemetry diagnostics control surface.

Covers: collect_telemetry.sh (collector) and install.sh (installer) telemetry
behaviours -- disabled-by-default, opt-out, redaction table, <=50 lines
stacktrace, hash-dedup, fail-closed, limits/rotation, --inspect, --bundle,
--read, installer with/without --enable-telemetry, disclosure text, and docs
contract strings.

Every test runs against a THROWAWAY temp directory (never the live repo).
The collector is invoked via subprocess from that temp dir.
"""
import gzip
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

# -- paths to implementation files (main repo, NOT the worktree) --------------
_WORKTREE_TESTS = os.path.dirname(os.path.abspath(__file__))
_WORKTREE_ROOT = os.path.dirname(_WORKTREE_TESTS)
try:
    _repo_out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=_WORKTREE_ROOT, capture_output=True, text=True, check=True,
    )
    REPO = _repo_out.stdout.strip()
except Exception:
    REPO = _WORKTREE_ROOT

SRC_COLLECT = os.path.join(REPO, "tools", "collect_telemetry.sh")
SRC_INSTALL = os.path.join(REPO, "dist", "install.sh")
SRC_README = os.path.join(REPO, "tools", "README.md")
SRC_RUNBOOK = os.path.join(REPO, "dist", "RUNBOOK.md")


def _write_jsonl(path, records):
    with open(path, "w") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _make_project_root():
    d = tempfile.mkdtemp(prefix="telemetry-test-")
    os.makedirs(os.path.join(d, ".council", "telemetry", "diagnostics"), exist_ok=True)
    os.makedirs(os.path.join(d, ".council", "telemetry", "metrics"), exist_ok=True)
    inp = os.path.join(d, "input.jsonl")
    _write_jsonl(inp, [_default_error_record("config")])
    return d, inp


def _default_error_record(category="config"):
    return {
        "schema_version": 1,
        "session_id": "test-session-001",
        "timestamp": "2026-11-22T12:00:00Z",
        "error_category": category,
        "stacktrace_hash": "",
        "stacktrace": [
            {"file": "/home/user/project/app/main.py", "line": 42,
             "function": "handle_request", "exception_type": "RuntimeError",
             "message": "Connection refused"}
        ]
    }


def _write_config(d, enabled=True, redact_symbols=False,
                  max_file_size_mb=10, max_total_dir_mb=50,
                  retention_days=30):
    cfg_path = os.path.join(d, ".council", "telemetry.yml")
    with open(cfg_path, "w") as fh:
        fh.write(f"enabled: {'true' if enabled else 'false'}\n")
        fh.write(f"project_name: test-project\n")
        fh.write(f"redact_symbols: {'true' if redact_symbols else 'false'}\n")
        fh.write(f"max_file_size_mb: {max_file_size_mb}\n")
        fh.write(f"max_total_dir_mb: {max_total_dir_mb}\n")
        fh.write(f"retention_days: {retention_days}\n")
        fh.write("collect:\n")


def _run_collect(d, args=None, stdin_path=None):
    """Run collect_telemetry.sh from *d* as CWD.

    If *stdin_path* is given, pipe that file.  If it is None and
    ``<d>/input.jsonl`` exists, pipe it automatically (the default input
    created by _make_project_root).  _run_collect_stdin is unaffected.
    """
    cmd = ["bash", SRC_COLLECT] + (args or [])
    stdin_fh = None
    if stdin_path:
        stdin_fh = open(stdin_path, "r")
    elif stdin_path is None:
        auto_input = os.path.join(d, "input.jsonl")
        if os.path.isfile(auto_input):
            stdin_fh = open(auto_input, "r")
    result = None
    try:
        result = subprocess.run(cmd, cwd=d, capture_output=True, text=True,
                                stdin=stdin_fh)
    finally:
        if stdin_fh:
            stdin_fh.close()
    return result


def _run_collect_stdin(d, data, args=None):
    cmd = ["bash", SRC_COLLECT] + (args or [])
    return subprocess.run(cmd, cwd=d, capture_output=True, text=True, input=data)


def _run_collect_bytes(d, args=None):
    """Run collect_telemetry.sh from *d* as CWD, returning raw bytes.

    Used for --bundle tests where the output is a gzip tarball (binary).
    """
    cmd = ["bash", SRC_COLLECT] + (args or [])
    return subprocess.run(cmd, cwd=d, capture_output=True, stdin=None)


def _make_minimal_dist():
    d = tempfile.mkdtemp(prefix="telemetry-dist-")
    for sub in ("core", "templates"):
        core_dir = os.path.join(d, sub)
        os.makedirs(core_dir)
        # Create dotfiles so shell globs work correctly
        with open(os.path.join(core_dir, ".gitkeep"), "w") as fh:
            fh.write("")
    with open(os.path.join(d, "version.txt"), "w") as fh:
        fh.write("v0.1.0\n")
    with open(os.path.join(d, "core-manifest.txt"), "w") as fh:
        fh.write("core/README.md\ncore/update.sh\n")
    with open(os.path.join(d, "build.sh"), "w") as fh:
        fh.write("#!/bin/bash\necho build\n")
    with open(os.path.join(d, "update.sh"), "w") as fh:
        fh.write("#!/bin/bash\necho update\n")
    install_dst = os.path.join(d, "install.sh")
    shutil.copy2(SRC_INSTALL, install_dst)
    return d


# ===================================================================
#  FILE EXISTENCE
# ===================================================================

class FileExistence(unittest.TestCase):
    def test_collect_telemetry_sh_exists(self):
        self.assertTrue(os.path.exists(SRC_COLLECT),
                        "tools/collect_telemetry.sh must exist")

    def test_collect_telemetry_sh_is_executable(self):
        self.assertTrue(os.path.isfile(SRC_COLLECT))
        self.assertTrue(os.access(SRC_COLLECT, os.X_OK),
                        "collect_telemetry.sh must have executable bit")

    def test_install_sh_exists(self):
        self.assertTrue(os.path.exists(SRC_INSTALL),
                        "dist/install.sh must exist")


# ===================================================================
#  DISABLED-BY-DEFAULT
# ===================================================================

class DisabledDefault(unittest.TestCase):
    def setUp(self):
        self.project_root, self.input_path = _make_project_root()

    def tearDown(self):
        shutil.rmtree(self.project_root, ignore_errors=True)

    def test_no_config_exits_0(self):
        proc = _run_collect(self.project_root)
        self.assertEqual(0, proc.returncode,
                         f"expected exit 0, got {proc.returncode}: {proc.stderr}")

    def test_no_config_writes_nothing(self):
        _run_collect(self.project_root)
        files = os.listdir(
            os.path.join(self.project_root, ".council", "telemetry", "diagnostics"))
        self.assertEqual(0, len(files),
                         f"diagnostics dir must be empty, found: {files}")

    def test_enabled_false_exits_0(self):
        _write_config(self.project_root, enabled=False)
        proc = _run_collect(self.project_root)
        self.assertEqual(0, proc.returncode,
                         f"expected exit 0, got {proc.returncode}: {proc.stderr}")

    def test_enabled_false_writes_nothing(self):
        _write_config(self.project_root, enabled=False)
        _run_collect(self.project_root)
        files = os.listdir(
            os.path.join(self.project_root, ".council", "telemetry", "diagnostics"))
        self.assertEqual(0, len(files),
                         f"diagnostics dir must be empty, found: {files}")


# ===================================================================
#  OPT-OUT
# ===================================================================

class OptOut(unittest.TestCase):
    def setUp(self):
        self.project_root, self.input_path = _make_project_root()

    def tearDown(self):
        shutil.rmtree(self.project_root, ignore_errors=True)

    def test_opt_out_prevents_write(self):
        _write_config(self.project_root, enabled=True)
        with open(os.path.join(self.project_root, ".council",
                               "opt-out-telemetry"), "w") as fh:
            fh.write("")
        proc = _run_collect(self.project_root)
        self.assertEqual(0, proc.returncode,
                         f"expected exit 0, got {proc.returncode}: {proc.stderr}")
        files = os.listdir(
            os.path.join(self.project_root, ".council", "telemetry", "diagnostics"))
        self.assertEqual(0, len(files),
                         f"diagnostics dir must be empty (opt-out), found: {files}")


# ===================================================================
#  REDACTION TABLE
# ===================================================================

class RedactionTable(unittest.TestCase):
    def setUp(self):
        self.project_root, self.input_path = _make_project_root()

    def tearDown(self):
        shutil.rmtree(self.project_root, ignore_errors=True)

    def _setup_collected(self, redact_symbols=False):
        _write_config(self.project_root, enabled=True, redact_symbols=redact_symbols)
        rec = _default_error_record()
        _write_jsonl(self.input_path, [rec])
        proc = _run_collect(self.project_root)
        self.assertEqual(0, proc.returncode, f"collect failed: {proc.stderr}")

    def _get_first_record(self):
        diag_dir = os.path.join(self.project_root, ".council", "telemetry",
                                "diagnostics")
        files = os.listdir(diag_dir)
        self.assertGreater(len(files), 0, "Expected output file")
        with open(os.path.join(diag_dir, files[0])) as fh:
            return json.loads(fh.readline())

    def test_redact_filesystem_paths(self):
        self._setup_collected()
        rec = self._get_first_record()
        redacted = rec["redacted_stack"][0]["file"]
        self.assertTrue(redacted.startswith("./"),
                        f"Path must start with ./, got: {redacted}")
        self.assertNotIn("/home/", redacted,
                         f"Host directory must be dropped: {redacted}")
        self.assertIn("main.py", redacted,
                      f"basename must remain: {redacted}")

    def test_redact_api_keys(self):
        rec = _default_error_record()
        rec["stacktrace"] = [{"file": "./main.py", "line": 1, "function": "auth",
             "exception_type": "ApiKeyError",
             "message": "Key abcdefghijklmnopqrstuvwxyz123456 was invalid"}]
        _write_config(self.project_root, enabled=True)
        _write_jsonl(self.input_path, [rec])
        _run_collect(self.project_root)
        rec_out = self._get_first_record()
        msg = rec_out["redacted_stack"][0]["message"]
        self.assertIn("[REDACTED]", msg, f"API key must be redacted: {msg}")

    def test_redact_private_ip(self):
        rec = _default_error_record()
        rec["stacktrace"] = [{"file": "./app.py", "line": 10, "function": "connect",
             "exception_type": "ConnectionError",
             "message": "Failed to connect to 192.168.1.1"}]
        _write_config(self.project_root, enabled=True)
        _write_jsonl(self.input_path, [rec])
        _run_collect(self.project_root)
        rec_out = self._get_first_record()
        msg = rec_out["redacted_stack"][0]["message"]
        self.assertIn("[local]", msg, f"Private IP must be redacted: {msg}")

    def test_redact_loopback_ip(self):
        rec = _default_error_record()
        rec["stacktrace"] = [{"file": "./app.py", "line": 1, "function": "ping",
             "exception_type": "TimeoutError",
             "message": "Timeout on 127.0.0.1:8080"}]
        _write_config(self.project_root, enabled=True)
        _write_jsonl(self.input_path, [rec])
        _run_collect(self.project_root)
        rec_out = self._get_first_record()
        msg = rec_out["redacted_stack"][0]["message"]
        self.assertIn("[local]", msg, f"Loopback IP must be redacted: {msg}")

    def test_redact_external_ip(self):
        rec = _default_error_record()
        rec["stacktrace"] = [{"file": "./client.py", "line": 5, "function": "fetch",
             "exception_type": "HTTPError",
             "message": "GET 8.8.8.8 returned 503"}]
        _write_config(self.project_root, enabled=True)
        _write_jsonl(self.input_path, [rec])
        _run_collect(self.project_root)
        rec_out = self._get_first_record()
        msg = rec_out["redacted_stack"][0]["message"]
        self.assertIn("[external]", msg, f"External IP must be redacted: {msg}")

    def test_redact_symbols_replaces_function(self):
        _write_config(self.project_root, enabled=True, redact_symbols=True)
        rec = _default_error_record()
        _write_jsonl(self.input_path, [rec])
        _run_collect(self.project_root)
        rec_out = self._get_first_record()
        func = rec_out["redacted_stack"][0]["function"]
        self.assertNotEqual(func, "handle_request",
                            "Function must be replaced by hash")

    def test_redact_stacktrace_fields_only(self):
        rec = _default_error_record()
        rec["stacktrace"] = [{"file": "/tmp/test.py", "line": 1, "function": "fn",
             "exception_type": "E", "message": "m", "extra_field": "hidden"}]
        _write_config(self.project_root, enabled=True)
        _write_jsonl(self.input_path, [rec])
        _run_collect(self.project_root)
        rec_out = self._get_first_record()
        allowed = {"file", "line", "function", "exception_type", "message"}
        self.assertEqual(set(rec_out["redacted_stack"][0].keys()), allowed,
                         f"Only allowed fields: {allowed}, got: {set(rec_out['redacted_stack'][0].keys())}")


# ===================================================================
#  STACKTRACE LIMIT (<=50 lines)
# ===================================================================

class StacktraceLimit(unittest.TestCase):
    def setUp(self):
        self.project_root, self.input_path = _make_project_root()

    def tearDown(self):
        shutil.rmtree(self.project_root, ignore_errors=True)

    def test_stacktrace_capped_at_50_lines(self):
        """A single stacktrace is capped at 50 lines (per spec)."""
        frames = []
        for i in range(75):
            frames.append({
                "file": "./app.py", "line": i, "function": "fn_" + str(i),
                "exception_type": "Error", "message": "frame " + str(i)
            })
        input_records = [{
            "schema_version": 1,
            "session_id": "test-session-001",
            "timestamp": "2026-11-22T12:00:00Z",
            "error_category": "tooling",
            "stacktrace_hash": "single",
            "stacktrace": frames
        }]
        _write_config(self.project_root, enabled=True)
        _write_jsonl(self.input_path, input_records)
        _run_collect(self.project_root)
        diag_dir = os.path.join(self.project_root, ".council", "telemetry",
                                "diagnostics")
        files = os.listdir(diag_dir)
        self.assertGreater(len(files), 0, "Expected output file")
        with open(os.path.join(diag_dir, files[0])) as fh:
            rec = json.loads(fh.readline())
        self.assertLessEqual(len(rec["redacted_stack"]), 50,
                             f"Stacktrace must have <=50 lines, got {len(rec['redacted_stack'])}")


# ===================================================================
#  HASH DEDUP
# ===================================================================

class HashDedup(unittest.TestCase):
    def setUp(self):
        self.project_root, self.input_path = _make_project_root()

    def tearDown(self):
        shutil.rmtree(self.project_root, ignore_errors=True)

    def test_duplicate_hash_skipped(self):
        rec1 = {
            "schema_version": 1, "session_id": "test-session-001",
            "timestamp": "2026-11-22T12:00:00Z", "error_category": "config",
            "stacktrace_hash": "same-hash",
            "stacktrace": [
                {"file": "/home/user/main.py", "line": 1, "function": "main",
                 "exception_type": "ValueError", "message": "dup"}
            ]
        }
        _write_config(self.project_root, enabled=True)
        _write_jsonl(self.input_path, [rec1, rec1])
        _run_collect(self.project_root)
        diag_dir = os.path.join(self.project_root, ".council", "telemetry",
                                "diagnostics")
        files = os.listdir(diag_dir)
        self.assertGreater(len(files), 0, "Expected output file")
        with open(os.path.join(diag_dir, files[0])) as fh:
            lines = [l for l in fh.readlines() if l.strip()]
        self.assertEqual(len(lines), 1,
                         f"Duplicate hash must produce exactly 1 record, got {len(lines)}")


# ===================================================================
#  FAIL-CLOSED
# ===================================================================

class FailClosed(unittest.TestCase):
    def setUp(self):
        self.project_root, self.input_path = _make_project_root()

    def tearDown(self):
        shutil.rmtree(self.project_root, ignore_errors=True)

    def test_invalid_json_exits_0(self):
        _write_config(self.project_root, enabled=True)
        proc = _run_collect_stdin(self.project_root, "not json at all\n")
        self.assertEqual(0, proc.returncode,
                         f"exit 0 required, got {proc.returncode}")

    def test_invalid_json_no_partial_record(self):
        _write_config(self.project_root, enabled=True)
        _run_collect_stdin(self.project_root, "bad json\n")
        diag_dir = os.path.join(self.project_root, ".council", "telemetry",
                                "diagnostics")
        files = os.listdir(diag_dir)
        self.assertEqual(0, len(files),
                         f"No file should be created on error, found: {files}")

    def test_invalid_json_warning_on_stderr(self):
        _write_config(self.project_root, enabled=True)
        proc = _run_collect_stdin(self.project_root, "bad json\n")
        self.assertIn("warning", proc.stderr.lower())

    def test_missing_category_exits_0(self):
        _write_config(self.project_root, enabled=True)
        rec = _default_error_record()
        del rec["error_category"]
        _write_jsonl(self.input_path, [rec])
        proc = _run_collect(self.project_root)
        self.assertEqual(0, proc.returncode,
                         f"exit 0 required, got {proc.returncode}")
        diag_dir = os.path.join(self.project_root, ".council", "telemetry",
                                "diagnostics")
        files = os.listdir(diag_dir)
        self.assertEqual(0, len(files),
                         f"No file should be created on error, found: {files}")


# ===================================================================
#  --inspect (summary only)
# ===================================================================

class InspectMode(unittest.TestCase):
    def setUp(self):
        self.project_root, self.input_path = _make_project_root()

    def tearDown(self):
        shutil.rmtree(self.project_root, ignore_errors=True)

    def _setup_data(self):
        _write_config(self.project_root, enabled=True)
        rec = _default_error_record("config")
        rec["error_category"] = "tooling"
        _write_jsonl(self.input_path, [rec])
        proc = _run_collect(self.project_root)
        self.assertEqual(0, proc.returncode, f"collect failed: {proc.stderr}")

    def test_inspect_summary_no_record_content(self):
        self._setup_data()
        proc = _run_collect(self.project_root, ["--inspect"])
        self.assertEqual(0, proc.returncode,
                         f"exit 0 required, got {proc.returncode}: {proc.stderr}")
        output = proc.stdout
        self.assertNotIn("redacted_stack", output)
        self.assertIn("count", output.lower())

    def test_inspect_no_data_exits_0(self):
        proc = _run_collect(self.project_root, ["--inspect"])
        self.assertEqual(0, proc.returncode,
                         f"exit 0 required with no data, got {proc.returncode}")

    def test_inspect_shows_categories(self):
        self._setup_data()
        proc = _run_collect(self.project_root, ["--inspect"])
        self.assertIn("tooling", proc.stdout.lower())


# ===================================================================
#  --bundle (5-field manifest)
# ===================================================================

class BundleMode(unittest.TestCase):
    def setUp(self):
        self.project_root, self.input_path = _make_project_root()

    def tearDown(self):
        shutil.rmtree(self.project_root, ignore_errors=True)

    def _create_bundle_path(self, proc):
        """Write bundle output (bytes) to a temp file and return path."""
        bundle_path = os.path.join(self.project_root, "bundle.bin")
        with open(bundle_path, "wb") as f:
            f.write(proc.stdout)
        return bundle_path

    def _extract_manifest_from_bundle(self, bundle_path):
        """Decompress and extract manifest.json from a gzip tarball."""
        tar_path = bundle_path + ".tar"
        with open(bundle_path, "rb") as bf:
            with gzip.open(bf, "rb") as gf:
                with open(tar_path, "wb") as tf:
                    tf.write(gf.read())
        with tarfile.open(tar_path, "r") as tf:
            mf = tf.getmember("manifest.json")
            return json.loads(tf.extractfile(mf).read())

    def test_bundle_exits_0(self):
        _write_config(self.project_root, enabled=True)
        rec = _default_error_record("config")
        _write_jsonl(self.input_path, [rec])
        _run_collect(self.project_root)
        proc = _run_collect_bytes(self.project_root, ["--bundle"])
        self.assertEqual(0, proc.returncode,
                         f"exit 0 required, got {proc.returncode}: {proc.stderr}")
        self.assertTrue(len(proc.stdout) > 0, "bundle must produce output")

    def test_bundle_manifest_has_5_fields(self):
        _write_config(self.project_root, enabled=True)
        rec = _default_error_record("config")
        _write_jsonl(self.input_path, [rec])
        _run_collect(self.project_root)
        proc = _run_collect_bytes(self.project_root, ["--bundle"])
        self.assertEqual(0, proc.returncode)
        bundle_path = self._create_bundle_path(proc)
        manifest = self._extract_manifest_from_bundle(bundle_path)
        required = {"schema_version", "collector_version", "project_name",
                     "generated_at", "files"}
        self.assertEqual(set(manifest.keys()), required,
                         f"manifest must have exactly 5 fields: {required}, got: {set(manifest.keys())}")

    def test_bundle_includes_diagnostic_files(self):
        _write_config(self.project_root, enabled=True)
        rec = _default_error_record("config")
        _write_jsonl(self.input_path, [rec])
        _run_collect(self.project_root)
        proc = _run_collect_bytes(self.project_root, ["--bundle"])
        self.assertEqual(0, proc.returncode)
        bundle_path = self._create_bundle_path(proc)
        manifest = self._extract_manifest_from_bundle(bundle_path)
        self.assertIsInstance(manifest["files"], list)
        self.assertGreater(len(manifest["files"]), 0,
                           "manifest must list at least one file")


# ===================================================================
#  --read (schema mismatch -> warning + skip, exit 0)
# ===================================================================

class ReadMode(unittest.TestCase):
    def setUp(self):
        self.project_root, self.input_path = _make_project_root()

    def tearDown(self):
        shutil.rmtree(self.project_root, ignore_errors=True)

    def _make_fake_bundle(self, schema_version, bundle_name):
        fake_tgz = tempfile.mktemp(suffix=".tgz")
        manifest_data = json.dumps({
            "schema_version": schema_version,
            "collector_version": "0.1.0",
            "project_name": "test-proj",
            "generated_at": "2026-11-22T12:00:00Z",
            "files": ["fake.jsonl"]
        })
        with tarfile.open(fake_tgz, "w:gz") as tf:
            info = tarfile.TarInfo(name="manifest.json")
            info.size = len(manifest_data.encode())
            tf.addfile(info, io.BytesIO(manifest_data.encode()))
            info2 = tarfile.TarInfo(name="fake.jsonl")
            info2.size = 0
            tf.addfile(info2, io.BytesIO(b""))
        bundle_path = os.path.join(self.project_root, bundle_name)
        shutil.copy2(fake_tgz, bundle_path)
        return bundle_path

    def test_read_unsupported_schema_exits_0(self):
        bundle_path = self._make_fake_bundle(99, "bad-schema.tgz")
        proc = _run_collect(self.project_root, ["--read", bundle_path])
        self.assertEqual(0, proc.returncode,
                         f"exit 0 on schema mismatch, got {proc.returncode}: {proc.stderr}")
        self.assertIn("warning", proc.stderr.lower())

    def test_read_valid_schema_prints_file_list(self):
        bundle_path = self._make_fake_bundle(1, "good-schema.tgz")
        proc = _run_collect(self.project_root, ["--read", bundle_path])
        self.assertEqual(0, proc.returncode,
                         f"exit 0 required, got {proc.returncode}: {proc.stderr}")
        self.assertNotIn("redacted_stack", proc.stdout)


# ===================================================================
#  install.sh with --enable-telemetry
# ===================================================================

class InstallEnableTelemetry(unittest.TestCase):
    def setUp(self):
        self.dist_dir = _make_minimal_dist()
        self.target_dir = tempfile.mkdtemp(prefix="telemetry-target-")

    def tearDown(self):
        shutil.rmtree(self.dist_dir, ignore_errors=True)
        shutil.rmtree(self.target_dir, ignore_errors=True)

    def _install_with_telemetry(self, mode="init", project_name="my-project"):
        return subprocess.run(
            ["bash", os.path.join(self.dist_dir, "install.sh"),
             "--target", self.target_dir, "--mode", mode,
             "--project-name", project_name,
             "--enable-telemetry", "--skip-deps-check"],
            capture_output=True, text=True,
        )

    def test_install_with_flag_exits_0(self):
        proc = self._install_with_telemetry()
        self.assertEqual(0, proc.returncode,
                         f"exit 0 required, got {proc.returncode}: {proc.stderr}")

    def test_install_creates_telemetry_yml(self):
        self._install_with_telemetry()
        cfg_path = os.path.join(self.target_dir, ".council", "telemetry.yml")
        self.assertTrue(os.path.exists(cfg_path), "telemetry.yml must be created")

    def test_install_telemetry_yml_enabled(self):
        self._install_with_telemetry()
        with open(os.path.join(self.target_dir, ".council", "telemetry.yml")) as fh:
            content = fh.read()
        self.assertIn("enabled: true", content)

    def test_install_telemetry_yml_project_name(self):
        self._install_with_telemetry()
        with open(os.path.join(self.target_dir, ".council", "telemetry.yml")) as fh:
            content = fh.read()
        self.assertIn("project_name: my-project", content)

    def test_install_creates_telemetry_dirs(self):
        self._install_with_telemetry()
        for sub in ("diagnostics", "metrics"):
            d = os.path.join(self.target_dir, ".council", "telemetry", sub)
            self.assertTrue(os.path.isdir(d), f"{sub}/ must exist")

    def test_install_creates_telemetry_gitignore(self):
        self._install_with_telemetry()
        gi = os.path.join(self.target_dir, ".council", "telemetry", ".gitignore")
        self.assertTrue(os.path.exists(gi), ".gitignore must be created in telemetry/")

    def test_install_creates_telemetry_readme(self):
        self._install_with_telemetry()
        readme = os.path.join(self.target_dir, ".council", "telemetry", "README.md")
        self.assertTrue(os.path.exists(readme), "README.md must be created in telemetry/")

    def test_install_overlay_does_not_overwrite_config(self):
        self._install_with_telemetry(project_name="original")
        cfg_path = os.path.join(self.target_dir, ".council", "telemetry.yml")
        self.assertTrue(os.path.exists(cfg_path))
        with open(cfg_path) as fh:
            original = fh.read()
        self._install_with_telemetry(mode="overlay", project_name="new-name")
        with open(cfg_path) as fh:
            after = fh.read()
        self.assertEqual(original, after, "Overlay must not overwrite existing config")


# ===================================================================
#  install.sh without --enable-telemetry
# ===================================================================

class InstallNoTelemetry(unittest.TestCase):
    def setUp(self):
        self.dist_dir = _make_minimal_dist()
        self.target_dir = tempfile.mkdtemp(prefix="telemetry-target-")

    def tearDown(self):
        shutil.rmtree(self.dist_dir, ignore_errors=True)
        shutil.rmtree(self.target_dir, ignore_errors=True)

    def _install_no_telemetry(self, mode="init", project_name="my-project"):
        return subprocess.run(
            ["bash", os.path.join(self.dist_dir, "install.sh"),
             "--target", self.target_dir, "--mode", mode,
             "--project-name", project_name, "--skip-deps-check"],
            capture_output=True, text=True,
        )

    def test_install_without_flag_exits_0(self):
        proc = self._install_no_telemetry()
        self.assertEqual(0, proc.returncode,
                         f"exit 0 required, got {proc.returncode}: {proc.stderr}")

    def test_install_no_telemetry_yml(self):
        self._install_no_telemetry()
        self.assertFalse(os.path.exists(
            os.path.join(self.target_dir, ".council", "telemetry.yml")),
            "telemetry.yml must NOT be created")

    def test_install_no_telemetry_dirs(self):
        self._install_no_telemetry()
        self.assertFalse(os.path.exists(
            os.path.join(self.target_dir, ".council", "telemetry")),
            "telemetry/ dir must NOT be created")


# ===================================================================
#  disclosure text
# ===================================================================

class DisclosureText(unittest.TestCase):
    def setUp(self):
        self.dist_dir = _make_minimal_dist()
        self.target_dir = tempfile.mkdtemp(prefix="telemetry-target-")

    def tearDown(self):
        shutil.rmtree(self.dist_dir, ignore_errors=True)
        shutil.rmtree(self.target_dir, ignore_errors=True)

    def _install_with_telemetry(self):
        return subprocess.run(
            ["bash", os.path.join(self.dist_dir, "install.sh"),
             "--target", self.target_dir, "--mode", "init",
             "--project-name", "my-project",
             "--enable-telemetry", "--skip-deps-check"],
            capture_output=True, text=True,
        )

    def test_disclosure_printed_with_flag(self):
        proc = self._install_with_telemetry()
        output = proc.stdout
        self.assertIn("default", output.lower())
        self.assertIn("opt", output.lower())

    def test_disclosure_mentions_no_transmission(self):
        proc = self._install_with_telemetry()
        output = proc.stdout
        self.assertIn("never transmitted", output)
        self.assertIn("opt-out", output)


# ===================================================================
#  docs contract strings
# ===================================================================

class DocsContract(unittest.TestCase):
    def test_readme_has_collect_telemetry_row(self):
        with open(SRC_README) as fh:
            content = fh.read()
        self.assertIn("collect_telemetry.sh", content,
                      "tools/README.md must reference collect_telemetry.sh")

    def test_runbook_has_telemetry_section(self):
        with open(SRC_RUNBOOK) as fh:
            content = fh.read()
        self.assertIn("Telemetry", content)
        self.assertIn("opt", content.lower())

    def test_readme_has_safety_sentence(self):
        with open(SRC_README) as fh:
            content = fh.read()
        self.assertIn(".git/", content, "README must mention .git/ safety")


if __name__ == "__main__":
    unittest.main()
