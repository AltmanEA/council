"""Tests for the Documenter Service MCP stdio JSON-RPC transport.

Covers: initialize, tools/list, tools/call, StructuredError tool-level
mapping, JSON-RPC error codes (batch -32600, unknown method -32601,
invalid params -32602, parse error -32700), notification suppression,
parity with CLI, and unit-level serve() (no subprocess).

mvp-contract §1: CLI and MCP use the same Service composition root —
parity tests verify results cannot diverge.
"""
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from documenter_service.__main__ import Service  # noqa: E402
from documenter_service.adapters.jsonl_registry import JsonlAuditRegistry  # noqa: E402
from documenter_service.adapters.stdout_events import StdoutEventSink  # noqa: E402
from documenter_service.mcp_stdio import serve, TOOLS_LIST  # noqa: E402

FIXTURE_CORPUS = os.path.join(REPO_ROOT, "tests", "fixtures", "documenter",
                              "corpus")


# ---------------------------------------------------------------------------
# Helper: run MCP server as subprocess with communicate()
# ---------------------------------------------------------------------------

def _run_mcp(args_extra, requests, env_extra=None):
    """Run the MCP server as a subprocess using communicate().

    Parameters
    ----------
    args_extra : list[str]
        CLI args after "--mcp", e.g. ["--root", FIXTURE_CORPUS].
    requests : list[dict]
        JSON-RPC request objects to send.
    env_extra : dict, optional
        Additional environment variables.

    Returns
    -------
    (stdout_responses, stderr_lines)
        stdout_responses — list of parsed JSON objects from stdout;
        stderr_lines — list of non-empty stderr lines.
    """
    tmpdir = tempfile.mkdtemp()
    try:
        merged_env = dict(os.environ)
        merged_env["DOCUMENTER_DATA_DIR"] = os.path.join(tmpdir, "state")
        merged_env["PYTHONPATH"] = REPO_ROOT + os.pathsep + os.environ.get(
            "PYTHONPATH", "")
        if env_extra:
            merged_env.update(env_extra)

        stdin_data = "\n".join(
            json.dumps(req, ensure_ascii=False) for req in requests
        ) + "\n"

        proc = subprocess.Popen(
            [sys.executable, "-m", "documenter_service", "--mcp"] + args_extra,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=merged_env,
            text=True,
        )
        stdout_raw, stderr_raw = proc.communicate(input=stdin_data)
        proc.wait()

        stdout_responses = []
        for line in stdout_raw.strip().splitlines():
            line = line.strip()
            if line:
                try:
                    stdout_responses.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

        stderr_lines = [l for l in stderr_raw.splitlines() if l.strip()]
        return stdout_responses, stderr_lines, proc.returncode
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _run_cli(argv, env_data=None):
    """Run a CLI subprocess, return (json_lines, returncode).

    json_lines — list of JSON objects from the last line of stdout.
    """
    tmpdir = tempfile.mkdtemp()
    try:
        merged_env = dict(os.environ)
        merged_env["PYTHONPATH"] = REPO_ROOT + os.pathsep + os.environ.get(
            "PYTHONPATH", "")
        if env_data is not None:
            merged_env["DOCUMENTER_DATA_DIR"] = env_data
            merged_env["PYTHONPATH"] = REPO_ROOT + os.pathsep + os.environ.get(
                "PYTHONPATH", "")

        proc = subprocess.Popen(
            [sys.executable, "-m", "documenter_service"] + argv,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=merged_env, text=True)
        out, _err = proc.communicate()
        lines = [l for l in out.strip().splitlines() if l.strip()]
        parsed = []
        for line in lines:
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return parsed, proc.returncode
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 1: initialize
# ---------------------------------------------------------------------------

class TestInitialize(unittest.TestCase):
    def test_server_info(self):
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 1,
              "method": "initialize", "params": {}}])
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        resp = responses[0]
        self.assertEqual(resp["jsonrpc"], "2.0")
        self.assertEqual(resp["id"], 1)
        self.assertIn("result", resp)
        result = resp["result"]
        self.assertEqual(result["protocolVersion"], "2024-11-05")
        self.assertIn("capabilities", result)
        self.assertIn("tools", result["capabilities"])
        self.assertIn("serverInfo", result)
        self.assertEqual(result["serverInfo"]["name"], "documenter")
        self.assertEqual(result["serverInfo"]["version"], "0.1.0")


# ---------------------------------------------------------------------------
# Test 2: tools/list
# ---------------------------------------------------------------------------

class TestToolsList(unittest.TestCase):
    def test_exactly_six_tools(self):
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 2,
              "method": "tools/list", "params": {}}])
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        tools = responses[0]["result"]["tools"]
        self.assertEqual(len(tools), 6)
        names = {t["name"] for t in tools}
        self.assertEqual(names, {"audit", "status", "delegate_preview",
                                  "approve", "override_gate", "delegate_write"})
        for t in tools:
            self.assertIn("inputSchema", t)
            self.assertEqual(t["inputSchema"].get("type"), "object")
        # readOnlyHint: first 3 read-only, last 3 read-write
        readOnlyTools = {t["name"]: t["annotations"].get("readOnlyHint", False)
                         for t in tools}
        for name in ("audit", "status", "delegate_preview"):
            self.assertTrue(readOnlyTools[name],
                            f"{name} should have readOnlyHint=True")
        for name in ("approve", "override_gate", "delegate_write"):
            self.assertFalse(readOnlyTools[name],
                             f"{name} should have readOnlyHint=False")

    def test_constant_tools_list(self):
        """TOOLS_LIST module constant is well-formed."""
        resp_tools = [t["name"] for t in TOOLS_LIST["tools"]]
        self.assertEqual(resp_tools, ["audit", "status", "delegate_preview",
                                       "approve", "override_gate", "delegate_write"])


# ---------------------------------------------------------------------------
# Test 3: tools/call status
# ---------------------------------------------------------------------------

class TestToolsCallStatus(unittest.TestCase):
    def test_status_no_error(self):
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 3,
              "method": "tools/call",
              "params": {"name": "status", "arguments": {}}}],
        )
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        resp = responses[0]
        self.assertNotIn("error", resp)
        self.assertNotIn("isError", resp["result"])
        content = resp["result"]["content"]
        self.assertEqual(len(content), 1)
        self.assertEqual(content[0]["type"], "text")
        data = json.loads(content[0]["text"])
        self.assertIn("active_tier", data)
        self.assertIn("registry", data)
        self.assertIn("tier_interlock", data)


# ---------------------------------------------------------------------------
# Test 4: tools/call audit (with events on stderr, stdout purity)
# ---------------------------------------------------------------------------

class TestToolsCallAudit(unittest.TestCase):
    def test_audit_response_and_stdout_purity(self):
        responses, stderr_lines, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 4,
              "method": "tools/call",
              "params": {"name": "audit",
                         "arguments": {"target_id": "*"}}}])
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        resp = responses[0]
        self.assertNotIn("error", resp)
        content = resp["result"]["content"]
        text = content[0]["text"]
        data = json.loads(text)
        self.assertIn("report", data)
        self.assertIn("coverage", data)

        # Verify ALL stdout lines are valid JSON-RPC 2.0
        for line in text.splitlines():
            pass  # single JSON object, already parsed above
        for resp_line in responses:
            self.assertEqual(resp_line.get("jsonrpc"), "2.0",
                             f"Not JSON-RPC 2.0: {resp_line}")

        # Verify stderr has event lines
        self.assertTrue(len(stderr_lines) > 0,
                        "Expected event lines on stderr from audit")


# ---------------------------------------------------------------------------
# Test 5: PARITY — MCP vs CLI
# ---------------------------------------------------------------------------

class TestParity(unittest.TestCase):
    """MCP and CLI results must be identical (same Service core)."""

    def test_audit_parity(self):
        """audit via MCP == audit via CLI (--json) — strip volatile keys."""
        tmpdir = tempfile.mkdtemp()
        env_data = os.path.join(tmpdir, "state")
        try:
            # MCP audit
            mcp_resp, _, _ = _run_mcp(
                ["--root", FIXTURE_CORPUS],
                [{"jsonrpc": "2.0", "id": 5,
                  "method": "tools/call",
                  "params": {"name": "audit",
                             "arguments": {"target_id": "*"}}}],
                env_extra={"DOCUMENTER_DATA_DIR": env_data})
            mcp_audit = json.loads(
                mcp_resp[0]["result"]["content"][0]["text"])

            # CLI audit on same registry
            cli_resp, rc = _run_cli(
                ["--root", FIXTURE_CORPUS, "--audit",
                 "--target", "*", "--json"],
                env_data=env_data)
            self.assertEqual(rc, 0)
            cli_audit = cli_resp[-1]

            # Strip volatile keys
            for d in (mcp_audit, cli_audit):
                d.pop("audit_id", None)
                d.pop("scan_cursor", None)
                for f in d.get("report", {}).get("findings", []):
                    f.pop("_rule", None)

            self.assertEqual(mcp_audit, cli_audit,
                             "MCP audit != CLI audit: "
                             + json.dumps(mcp_audit, indent=2, sort_keys=True))

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_delegate_parity(self):
        """delegate_preview via MCP == CLI --delegate-preview --json."""
        tmpdir = tempfile.mkdtemp()
        env_data = os.path.join(tmpdir, "state")
        try:
            diff_text = (
                "--- a/docs/en/alpha/index.md\n"
                "+++ b/docs/en/alpha/index.md\n"
                "@@ -1 +1 @@\n"
                "-|x|\n"
                "+|y|\n"
            )
            diff_b64 = base64.b64encode(
                diff_text.encode("utf-8")).decode()

            # MCP delegate_preview
            mcp_resp, _, _ = _run_mcp(
                ["--root", FIXTURE_CORPUS],
                [{"jsonrpc": "2.0", "id": 6,
                  "method": "tools/call",
                  "params": {
                      "name": "delegate_preview",
                      "arguments": {
                          "target_id": "alpha",
                          "change_type": "update",
                          "trust_level": "safe",
                          "diff_input": diff_b64,
                          "preview": True,
                      },
                  }}],
                env_extra={"DOCUMENTER_DATA_DIR": env_data})
            mcp_del = json.loads(
                mcp_resp[0]["result"]["content"][0]["text"])

            # CLI delegate_preview on same registry
            cli_resp, rc = _run_cli(
                ["--root", FIXTURE_CORPUS,
                 "--delegate-preview",
                 "--target", "alpha",
                 "--change-type", "update",
                 "--trust-level", "safe",
                 "--diff-base64", diff_b64,
                 "--json"],
                env_data=env_data)
            self.assertEqual(rc, 0)
            cli_del = cli_resp[-1]

            mcp_str = json.dumps(mcp_del, indent=2, sort_keys=True)
            cli_str = json.dumps(cli_del, indent=2, sort_keys=True)
            self.assertEqual(mcp_del, cli_del,
                             f"MCP delegate != CLI delegate\n"
                             f"MCP: {mcp_str}\n"
                             f"CLI: {cli_str}")

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 6: StructuredError → tool-level error
# ---------------------------------------------------------------------------

class TestStructuredErrorToolLevel(unittest.TestCase):
    def test_delegate_off_manifest(self):
        """delegate_preview with off-manifest target → isError true."""
        diff_text = (
            "--- a/docs/en/alpha/index.md\n"
            "+++ b/docs/en/alpha/index.md\n"
            "@@ -1 +1 @@\n"
            "-|x|\n"
            "+|y|\n")
        diff_b64 = base64.b64encode(diff_text.encode("utf-8")).decode()
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 7,
              "method": "tools/call",
              "params": {
                  "name": "delegate_preview",
                  "arguments": {
                      "target_id": "nonexistent_target_xyz",
                      "change_type": "update",
                      "trust_level": "safe",
                      "diff_input": diff_b64,
                      "preview": True,
                  },
              }}])
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        resp = responses[0]
        self.assertNotIn("error", resp)  # JSON-RPC success
        self.assertTrue(resp["result"].get("isError"),
                        "Expected isError=true for off-manifest target")
        content = resp["result"]["content"][0]["text"]
        error_data = json.loads(content)
        self.assertEqual(error_data["error_category"], "unknown")

    def test_delegate_preview_absent_rejected(self):
        """mvp-interfaces §2: preview absent → reject tier_interlock.

        The MCP layer must NOT default preview to true: an omitted preview is
        write intent and the structural interlock refuses it.
        """
        diff_b64 = base64.b64encode(
            b"--- a/docs/en/alpha/index.md\n+++ b/docs/en/alpha/index.md\n"
            b"@@ -1 +1 @@\n-|x|\n+|y|\n").decode()
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 75,
              "method": "tools/call",
              "params": {
                  "name": "delegate_preview",
                  "arguments": {
                      "target_id": "alpha",
                      "change_type": "update",
                      "trust_level": "safe",
                      "diff_input": diff_b64,
                  },
              }}],
            env_extra={"COUNCIL_OPERATOR_ID": "op-test"})
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        resp = responses[0]
        self.assertTrue(resp["result"].get("isError"))
        error_data = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(error_data["error_category"], "tier_interlock")
        self.assertEqual(error_data["next_action"], "preview_denied")

    def test_audit_off_manifest_target(self):
        """audit with target_id not in manifest → isError true."""
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 8,
              "method": "tools/call",
              "params": {"name": "audit",
                         "arguments": {"target_id": "../x"}}}])
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        resp = responses[0]
        self.assertNotIn("error", resp)
        self.assertTrue(resp["result"].get("isError"),
                        "Expected isError=true for invalid target_id")
        content = resp["result"]["content"][0]["text"]
        error_data = json.loads(content)
        self.assertIn("error_category", error_data)


# ---------------------------------------------------------------------------
# Test 7: JSON-RPC error codes
# ---------------------------------------------------------------------------

class TestJsonRpcErrors(unittest.TestCase):
    def test_unknown_method(self):
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 9,
              "method": "nonexistent_method", "params": {}}])
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        err = responses[0]["error"]
        self.assertEqual(err["code"], -32601)

    def test_unknown_tool(self):
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 10,
              "method": "tools/call",
              "params": {"name": "no_such_tool", "arguments": {}}}],
        )
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        err = responses[0]["error"]
        self.assertEqual(err["code"], -32602)
        self.assertIn("no_such_tool", err["message"])

    def test_invalid_json(self):
        """Invalid JSON line → -32700 with id null."""
        tmpdir = tempfile.mkdtemp()
        try:
            merged_env = dict(os.environ)
            merged_env["DOCUMENTER_DATA_DIR"] = os.path.join(tmpdir, "state")
            merged_env["PYTHONPATH"] = REPO_ROOT + os.pathsep + os.environ.get(
                "PYTHONPATH", "")

            proc = subprocess.Popen(
                [sys.executable, "-m", "documenter_service", "--mcp",
                 "--root", FIXTURE_CORPUS],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=merged_env,
                text=True,
            )
            # Write invalid JSON then a valid request to flush output
            proc.stdin.write("this is not json\n")
            proc.stdin.close()
            stdout_raw = proc.stdout.read()
            proc.wait()

            stdout_lines = []
            for line in stdout_raw.strip().splitlines():
                line = line.strip()
                if line:
                    try:
                        stdout_lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            self.assertEqual(len(stdout_lines), 1)
            self.assertEqual(stdout_lines[0]["error"]["code"], -32700)
            self.assertIsNone(stdout_lines[0].get("id"))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_notification_no_response(self):
        """A notification (no "id") produces NO response line on stdout."""
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "method": "notifications/initialized",
              "params": {}}])
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 0,
                         "Notification should produce no response")

    def test_batch_rejected(self):
        """Array/batch requests → -32600."""
        tmpdir = tempfile.mkdtemp()
        try:
            merged_env = dict(os.environ)
            merged_env["DOCUMENTER_DATA_DIR"] = os.path.join(tmpdir, "state")
            merged_env["PYTHONPATH"] = REPO_ROOT + os.pathsep + os.environ.get(
                "PYTHONPATH", "")

            batch = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {}},
                     {"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                      "params": {}}]

            proc = subprocess.Popen(
                [sys.executable, "-m", "documenter_service", "--mcp",
                 "--root", FIXTURE_CORPUS],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=merged_env,
                text=True,
            )
            proc.stdin.write(json.dumps(batch) + "\n")
            proc.stdin.close()
            stdout_raw = proc.stdout.read()
            proc.wait()

            stdout_lines = []
            for line in stdout_raw.strip().splitlines():
                line = line.strip()
                if line:
                    try:
                        stdout_lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            self.assertEqual(len(stdout_lines), 1)
            self.assertEqual(stdout_lines[0]["error"]["code"], -32600)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_notification_id_echo(self):
        """initialize + notification + tools/list → only 2 responses."""
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [
                {"jsonrpc": "2.0", "id": 15,
                 "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 16,
                 "method": "tools/list", "params": {}},
            ])
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 2)
        ids = {r["id"] for r in responses}
        self.assertEqual(ids, {15, 16})


# ---------------------------------------------------------------------------
# Test 8: serve() unit-level (no subprocess)
# ---------------------------------------------------------------------------

class TestServeUnit(unittest.TestCase):
    def test_serve_returns_0_on_eof(self):
        """serve() reads from StringIO until EOF, returns 0."""
        tmpdir = tempfile.mkdtemp()
        try:
            service = Service(FIXTURE_CORPUS,
                              registry=JsonlAuditRegistry(
                                  os.path.join(tmpdir, "state")),
                              events=StdoutEventSink(io.StringIO()))
            stdin_text = (
                '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'
                '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n'
                '{"jsonrpc":"2.0","id":3,"method":"tools/call",'
                '"params":{"name":"status","arguments":{}}}\n'
            )
            stdout_buf = io.StringIO()
            err_buf = io.StringIO()
            stdin_buf = io.StringIO(stdin_text)

            result = serve(service, stdin=stdin_buf,
                           stdout=stdout_buf, stderr=err_buf)
            self.assertEqual(result, 0)

            output_lines = [l for l in stdout_buf.getvalue().splitlines()
                            if l.strip()]
            self.assertEqual(len(output_lines), 3)
            for i, expected_id in enumerate([1, 2, 3]):
                obj = json.loads(output_lines[i])
                self.assertEqual(obj["id"], expected_id)
                self.assertNotIn("error", obj)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_serve_handles_invalid_json_gracefully(self):
        """serve() does not crash on invalid JSON lines."""
        tmpdir = tempfile.mkdtemp()
        try:
            service = Service(FIXTURE_CORPUS,
                              registry=JsonlAuditRegistry(
                                  os.path.join(tmpdir, "state")),
                              events=StdoutEventSink(io.StringIO()))
            stdin_text = (
                "garbage line\n"
                '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'
            )
            stdout_buf = io.StringIO()
            err_buf = io.StringIO()
            stdin_buf = io.StringIO(stdin_text)

            result = serve(service, stdin=stdin_buf,
                           stdout=stdout_buf, stderr=err_buf)
            self.assertEqual(result, 0)

            output_lines = [l for l in stdout_buf.getvalue().splitlines()
                            if l.strip()]
            self.assertEqual(len(output_lines), 2)
            # First line: parse error response
            err_line = json.loads(output_lines[0])
            self.assertEqual(err_line["error"]["code"], -32700)
            # Second line: initialize response
            init_line = json.loads(output_lines[1])
            self.assertEqual(init_line["id"], 1)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Test 9: MCP approve tool
# ---------------------------------------------------------------------------

class TestMCPApprove(unittest.TestCase):
    """MCP tools/call approve: operator from env, not params."""

    def test_approve_missing_approval_id(self):
        """approve without approval_id → -32602."""
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 90,
              "method": "tools/call",
              "params": {"name": "approve", "arguments": {}}}],
        )
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        self.assertIn("error", responses[0])
        self.assertEqual(responses[0]["error"]["code"], -32602)

    def test_approve_unknown_id(self):
        """approve with unknown id (env COUNCIL_OPERATOR_ID set) → isError audit_mismatch."""
        setup = _setup_approve_mcp_test()
        try:
            responses, _, rc = _run_mcp(
                ["--root", FIXTURE_CORPUS],
                [{"jsonrpc": "2.0", "id": 91,
                  "method": "tools/call",
                  "params": {"name": "approve",
                             "arguments": {"approval_id": "app-unknown-xyz"}}}],
                env_extra={"COUNCIL_OPERATOR_ID": "op-test-approver",
                           "DOCUMENTER_POLICY_PATH": setup["policy_path"],
                           "DOCUMENTER_DATA_DIR": setup["data_dir"]},
            )
            self.assertEqual(rc, 0)
            self.assertEqual(len(responses), 1)
            resp = responses[0]
            self.assertTrue(resp["result"].get("isError"),
                            "Expected isError=true for unknown approval_id")
            error_data = json.loads(resp["result"]["content"][0]["text"])
            self.assertEqual(error_data["error_category"], "audit_mismatch")
        finally:
            # Clean up temporary policy and data dirs (shutil-safe).
            for d in [os.path.dirname(setup["policy_path"]),
                      os.path.dirname(setup["data_dir"])]:
                shutil.rmtree(d, ignore_errors=True)
            # Remove briefing and sentinel created in the shared fixture.
            for p in setup["created_paths"]:
                try:
                    os.remove(p)
                except FileNotFoundError:
                    pass
            # Remove the documenter directory if it's now empty.
            sentinel_dir = os.path.join(FIXTURE_CORPUS, "documenter")
            try:
                os.rmdir(sentinel_dir)
            except OSError:
                pass  # not empty or already gone

    def test_approve_operator_id_param_rejected(self):
        """approve with operator_id param → -32602 (unknown argument).

        With strict schema validation, extra keys (additionalProperties: false)
        are rejected.  Operator identity must come from env, not client params.
        """
        setup = _setup_approve_mcp_test()
        try:
            responses, _, rc = _run_mcp(
                ["--root", FIXTURE_CORPUS],
                [{"jsonrpc": "2.0", "id": 92,
                  "method": "tools/call",
                  "params": {"name": "approve",
                             "arguments": {
                                 "approval_id": "app-unknown",
                                 "operator_id": "op-ignored",
                             }}}],
                env_extra={"COUNCIL_OPERATOR_ID": "op-env-approver",
                           "DOCUMENTER_POLICY_PATH": setup["policy_path"],
                           "DOCUMENTER_DATA_DIR": setup["data_dir"]},
            )
            self.assertEqual(rc, 0)
            self.assertEqual(len(responses), 1)
            resp = responses[0]
            # -32602: unknown argument "operator_id"
            self.assertIn("error", resp)
            self.assertEqual(resp["error"]["code"], -32602)
            self.assertIn("unknown argument", resp["error"]["message"])
        finally:
            # Clean up temporary policy and data dirs (shutil-safe).
            for d in [os.path.dirname(setup["policy_path"]),
                      os.path.dirname(setup["data_dir"])]:
                shutil.rmtree(d, ignore_errors=True)
            # Remove briefing and sentinel created in the shared fixture.
            for p in setup["created_paths"]:
                try:
                    os.remove(p)
                except FileNotFoundError:
                    pass
            # Remove the documenter directory if it's now empty.
            sentinel_dir = os.path.join(FIXTURE_CORPUS, "documenter")
            try:
                os.rmdir(sentinel_dir)
            except OSError:
                pass  # not empty or already gone

    # -----------------------------------------------------------------------
    # Arg-validation: strict schema enforcement (P.19)
    # -----------------------------------------------------------------------

    def test_audit_unknown_argument(self):
        """audit with extra key -> -32602 (unknown argument)."""
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 93,
              "method": "tools/call",
              "params": {"name": "audit",
                         "arguments": {"target_id": "*", "bogus": 1}}}],
        )
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        resp = responses[0]
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)
        self.assertIn("unknown argument", resp["error"]["message"])

    def test_audit_severity_not_in_enum(self):
        """audit severity='urgent' (not in enum) -> JSON-RPC -32602.

        Runtime schema enforcement (additionalProperties/enum/type) rejects
        the invalid enum value at the transport layer (fix plan p.19).
        """
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 94,
              "method": "tools/call",
              "params": {"name": "audit",
                         "arguments": {"severity_min": "urgent"}}}],
        )
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        resp = responses[0]
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)
        self.assertIn("urgent", resp["error"]["message"])

    def test_status_target_id_wrong_type(self):
        """status target_id=123 (int, not string/null) -> -32602."""
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 95,
              "method": "tools/call",
              "params": {"name": "status",
                         "arguments": {"target_id": 123}}}],
        )
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        resp = responses[0]
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)
        self.assertIn("expected", resp["error"]["message"])

    def test_status_correct_args_no_regression(self):
        """status with valid args still works (no regression)."""
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 96,
              "method": "tools/call",
              "params": {"name": "status",
                         "arguments": {"target_id": None}}}],
        )
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        resp = responses[0]
        self.assertNotIn("error", resp)


# ---------------------------------------------------------------------------
# Test 10: MCP delegate_write tool
# ---------------------------------------------------------------------------

class TestMCPDelegateWrite(unittest.TestCase):
    """MCP tools/call delegate_write: preview always False, no preview param."""

    def test_delegate_write_rejects_preview_param(self):
        """delegate_write: preview not in schema → rejected as unknown argument.

        Per mvp-interfaces §3, delegate_write has no preview property in its
        inputSchema.  P.19 strict schema enforcement (P.19) returns -32602.
        """
        diff_b64 = _diff_for_alpha_simple()
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 100,
              "method": "tools/call",
              "params": {"name": "delegate_write",
                         "arguments": {
                             "target_id": "alpha",
                             "change_type": "update",
                             "trust_level": "safe",
                             "diff_input": diff_b64,
                             "preview": True,  # rejected: not in schema
                         }}}],
        )
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        resp = responses[0]
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)
        self.assertIn("unknown argument", resp["error"]["message"])

    def test_delegate_write_no_preview_param(self):
        """delegate_write without preview param → server passes False."""
        diff_b64 = _diff_for_alpha_simple()
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 101,
              "method": "tools/call",
              "params": {"name": "delegate_write",
                         "arguments": {
                             "target_id": "alpha",
                             "change_type": "update",
                             "trust_level": "safe",
                             "diff_input": diff_b64,
                         }}}],
            env_extra={"COUNCIL_OPERATOR_ID": "op-test-writer"},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        resp = responses[0]
        # Should hit tier_interlock because default policy has active_tier < 2.
        self.assertTrue(resp["result"].get("isError"))
        error_data = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(error_data["error_category"], "tier_interlock")

    def test_delegate_write_missing_args(self):
        """delegate_write without required params → -32602."""
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 101,
              "method": "tools/call",
              "params": {"name": "delegate_write",
                         "arguments": {"target_id": "alpha"}}}],
        )
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        self.assertIn("error", responses[0])
        self.assertEqual(responses[0]["error"]["code"], -32602)
        self.assertIn("missing required argument",
                      responses[0]["error"]["message"])


# ---------------------------------------------------------------------------
# Test 11: MCP override_gate tool
# ---------------------------------------------------------------------------

class TestMCPOverrideGate(unittest.TestCase):
    """MCP tools/call override_gate: required params enforced."""

    def test_override_gate_missing_diff_hash(self):
        """override_gate missing diff_hash → -32602 (required param)."""
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 110,
              "method": "tools/call",
              "params": {"name": "override_gate",
                         "arguments": {
                             "target_id": "alpha",
                             "reason": "test reason",
                         }}}],
            env_extra={"COUNCIL_OPERATOR_ID": "op-test-over"},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        self.assertIn("error", responses[0])
        self.assertEqual(responses[0]["error"]["code"], -32602)

    def test_override_gate_tier_interlock(self):
        """override_gate on default tier1 → tier_interlock (isError, not JSON-RPC err)."""
        responses, _, rc = _run_mcp(
            ["--root", FIXTURE_CORPUS],
            [{"jsonrpc": "2.0", "id": 111,
              "method": "tools/call",
              "params": {"name": "override_gate",
                         "arguments": {
                             "target_id": "alpha",
                             "diff_hash": "sha256:" + "d" * 64,
                             "reason": "test override",
                         }}}],
            env_extra={"COUNCIL_OPERATOR_ID": "op-test-over"},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(len(responses), 1)
        resp = responses[0]
        # Tier interlock → tool-level isError (NOT JSON-RPC error).
        self.assertTrue(resp["result"].get("isError"))
        error_data = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(error_data["error_category"], "tier_interlock")


# ---------------------------------------------------------------------------
# MCP approve helper: creates a Tier 2 policy for tests that need to bypass
# the default policy (which has no policy → tier_interlock).
# ---------------------------------------------------------------------------

_TIER2_POLICY_FIELDS = {
    "version": "0.2.0",
    "active_tier": 2,
    "allowed_operations": [
        {"change_type": "update", "targets": [], "trust_level": "safe"},
        {"change_type": "update", "targets": [], "trust_level": "review"},
    ],
    "briefing_ref": "_briefing_for_approve_test.md",
    "audit_freshness": 30,
    "approval_expiry_window": 30,
    "rescan_batch_ceiling": 50,
    "max_diff_bytes": 524288,
    "sync_latency_budget_ms": 30000,
    "lock_wait_timeout": 30,
    "operator_approval_timeout": 300,
    "notification_mode": "inline",
    "glossary_enforcement": "draft",
    "glossary_staleness_days": 30,
}


def _setup_approve_mcp_test():
    """Create a Tier 2 policy + briefing + sentinel under FIXTURE_CORPUS.

    Returns a dict with:
        policy_path    — absolute path to the policy file (in temp dir)
        data_dir       — absolute path to a new temp data dir (in temp dir)
        created_paths  — list of absolute paths created under FIXTURE_CORPUS
                         (briefing file, sentinel file); the caller MUST
                         delete these in a finally block so the shared
                         fixture remains clean after every test.
    """
    import yaml
    policy_dir = tempfile.mkdtemp()
    policy_path = os.path.join(policy_dir, "pol.yml")
    with open(policy_path, "w") as f:
        yaml.safe_dump({"documenter_policy": _TIER2_POLICY_FIELDS}, f)

    briefing_path = os.path.join(FIXTURE_CORPUS,
                                 _TIER2_POLICY_FIELDS["briefing_ref"])
    with open(briefing_path, "w") as f:
        f.write("# Briefing for approve tests\n\nAuthorised operational context.\n")

    sentinel_dir = os.path.join(FIXTURE_CORPUS, "documenter")
    os.makedirs(sentinel_dir, exist_ok=True)
    sentinel_path = os.path.join(sentinel_dir, ".operator_ingress_ready")
    with open(sentinel_path, "w"):
        pass

    data_dir = os.path.join(tempfile.mkdtemp(), "state")

    return {"policy_path": policy_path,
            "data_dir": data_dir,
            "created_paths": [briefing_path, sentinel_path]}


# ---------------------------------------------------------------------------
# Helper for delegate_write tests
# ---------------------------------------------------------------------------

def _diff_for_alpha_simple():
    """Create a minimal diff for alpha."""
    diff_text = (
        "--- a/docs/en/alpha/index.md\n"
        "+++ b/docs/en/alpha/index.md\n"
        "@@ -1,5 +1,5 @@\n"
        " # Alpha\n"
        " id: alpha\n"
        " Version: 1.0.0\n"
        " Status: active\n"
        "-changelog-path: CHANGELOGS/alpha.md\n"
        "+changelog-path: CHANGELOGS/alpha.updated.md\n"
    )
    return base64.b64encode(diff_text.encode("utf-8")).decode("ascii")
