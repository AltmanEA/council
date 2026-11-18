"""CLI tests for --verify-activation, status, and activation_helper.

Covers subprocess-level tests for the activation overlay CLI interface.

Run with: python3 -m unittest tests.test_activation_cli -v
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SERVICE_CMD = [sys.executable, "-m", "documenter_service"]
HELPER_CMD = [sys.executable, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tools", "activation_helper.py")]

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "documenter")


def _write_policy_yaml(tmpdir, fields):
    """Write a policy YAML file in tmpdir. Returns path."""
    import yaml
    p = os.path.join(tmpdir, "documenter_policy.yml")
    with open(p, "w") as f:
        yaml.safe_dump({"documenter_policy": fields}, f)
    return p


def _write_minimal_manifest(tmpdir, doc_ids):
    """Create minimal docs/en/<id>/index.md files with frontmatter.

    gen_manifest.build_entries walks docs/en/ and parses frontmatter, so
    we need actual .md files — not a manifest file — for rule 5 validation.
    """
    for doc_id in doc_ids:
        doc_dir = os.path.join(tmpdir, "docs", "en", doc_id)
        os.makedirs(doc_dir, exist_ok=True)
        fpath = os.path.join(doc_dir, "index.md")
        with open(fpath, "w") as f:
            f.write("---\n")
            f.write(f"id: {doc_id}\n")
            f.write("title: test\n")
            f.write("version: 0.1.0\n")
            f.write("status: draft\n")
            f.write("abstraction: specification\n")
            f.write("---\n")
            f.write("# Test doc\n")
    return os.path.join(tmpdir, "docs", "en")


def _cli(args, root, env_override=None, timeout=30):
    """Run a CLI subprocess and return (returncode, stdout, stderr)."""
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    env["DOCUMENTER_POLICY_PATH"] = os.path.join(root,
                                                 "documenter_policy.yml")
    cmd = args + ["--root", root]
    result = subprocess.run(
        cmd, capture_output=True, text=True, env=env, timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def _run_service(args, root, env_override=None, timeout=30, root_before=False):
    """Run the documenter_service CLI.

    root_before=True: place --root before the subcommand.
    """
    env = os.environ.copy()
    env["DOCUMENTER_POLICY_PATH"] = os.path.join(root,
                                                 "documenter_policy.yml")
    if root_before:
        cmd = SERVICE_CMD + list(args)
    else:
        cmd = SERVICE_CMD + list(args) + ["--root", root]
    if env_override:
        env.update(env_override)
    result = subprocess.run(
        cmd, capture_output=True, text=True, env=env, timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def _run_helper(args, root, env_override=None, timeout=30):
    """Run the activation_helper script.

    Global options (--root, --json) must come before the subcommand in argparse.
    This helper repositions --json from the args list to the global position.
    """
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    # Separate --json flag from subcommand args
    has_json = "--json" in args
    if has_json:
        subargs = [a for a in args if a != "--json"]
    else:
        subargs = list(args)
    cmd = HELPER_CMD + ["--root", root]
    if has_json:
        cmd.append("--json")
    cmd.extend(subargs)
    result = subprocess.run(
        cmd, capture_output=True, text=True, env=env, timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# --verify-activation tests
# ---------------------------------------------------------------------------

class TestVerifyActivationBaseline(unittest.TestCase):
    """--verify-activation in baseline state (no overlay)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _policy(self, **over):
        base = {
            "documenter_policy": {
                "version": "0.2.0",
                "active_tier": 1,
                "allowed_operations": [],
                "briefing_ref": None,
            }
        }
        base["documenter_policy"].update(over)
        return base

    def test_baseline_exit_code(self):
        """Baseline state returns exit code 0."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        rc, out, _ = _run_service(["--verify-activation"], self.tmpdir)
        self.assertEqual(rc, 0)
        self.assertIn("State: baseline", out)

    def test_baseline_json(self):
        """Baseline state in JSON output."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        rc, out, _ = _run_service(
            ["--verify-activation", "--json"], self.tmpdir)
        self.assertEqual(rc, 0)
        data = json.loads(out.strip())
        self.assertEqual(data["state"], "baseline")
        self.assertTrue(data["ok"])

    def test_baseline_overlay_present_false(self):
        """Overlay present is false in baseline."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        rc, out, _ = _run_service(
            ["--verify-activation", "--json"], self.tmpdir)
        self.assertEqual(rc, 0)
        data = json.loads(out.strip())
        self.assertFalse(data["overlay"]["present"])
        self.assertEqual(data["effective"]["source"], "base")

    def test_baseline_interlock(self):
        """Interlock shows locked in baseline."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        rc, out, _ = _run_service(
            ["--verify-activation", "--json"], self.tmpdir)
        self.assertEqual(rc, 0)
        data = json.loads(out.strip())
        interlock = data["interlock"]
        self.assertFalse(interlock["tier2_authorized"])


# ---------------------------------------------------------------------------
# --verify-activation — active state
# ---------------------------------------------------------------------------

class TestVerifyActivationActive(unittest.TestCase):
    """--verify-activation with active overlay."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_active_exit_code(self):
        """Active state returns exit code 0."""
        import yaml
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        _write_minimal_manifest(self.tmpdir, [
            "documenter-service-configuration-guide", "operator-ingress"])
        outside = tempfile.mkdtemp()
        try:
            p = os.path.join(outside, "overlay.yml")
            with open(p, "w") as f:
                yaml.safe_dump({"scope": "pilot-safe-v1", "active_tier": 2,
                                "briefing_ref": os.path.join(outside, "briefing.md")}, f)
            env = {"DOCUMENTER_ACTIVATION_PATH": p}
            rc, out, _ = _run_service(
                ["--verify-activation"], self.tmpdir, env_override=env)
            self.assertEqual(rc, 0)
            self.assertIn("State: active", out)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_active_json(self):
        """Active state in JSON output."""
        import yaml
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        _write_minimal_manifest(self.tmpdir, [
            "documenter-service-configuration-guide", "operator-ingress"])
        outside = tempfile.mkdtemp()
        try:
            p = os.path.join(outside, "overlay.yml")
            with open(p, "w") as f:
                yaml.safe_dump({"scope": "pilot-safe-v1", "active_tier": 2,
                                "briefing_ref": os.path.join(outside, "briefing.md")}, f)
            env = {"DOCUMENTER_ACTIVATION_PATH": p}
            rc, out, _ = _run_service(
                ["--verify-activation", "--json"], self.tmpdir,
                env_override=env)
            self.assertEqual(rc, 0)
            data = json.loads(out.strip())
            self.assertEqual(data["state"], "active")
            self.assertTrue(data["ok"])
            self.assertTrue(data["overlay"]["present"])
            self.assertEqual(data["effective"]["source"], "overlay")
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_active_scope_in_output(self):
        """Scope shown in active state."""
        import yaml
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        _write_minimal_manifest(self.tmpdir, [
            "documenter-service-configuration-guide", "operator-ingress"])
        outside = tempfile.mkdtemp()
        try:
            p = os.path.join(outside, "overlay.yml")
            with open(p, "w") as f:
                yaml.safe_dump({"scope": "pilot-safe-v1", "active_tier": 2,
                                "briefing_ref": os.path.join(outside, "briefing.md")}, f)
            env = {"DOCUMENTER_ACTIVATION_PATH": p}
            rc, out, _ = _run_service(
                ["--verify-activation", "--json"], self.tmpdir,
                env_override=env)
            self.assertEqual(rc, 0)
            data = json.loads(out.strip())
            self.assertEqual(data["overlay"]["scope"], "pilot-safe-v1")
            self.assertEqual(data["overlay"]["mode"], "scope")
            self.assertEqual(data["effective"]["allowed_operations_count"], 1)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_active_scope_summary(self):
        """Scope summary included for active scope."""
        import yaml
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        _write_minimal_manifest(self.tmpdir, [
            "documenter-service-configuration-guide", "operator-ingress"])
        outside = tempfile.mkdtemp()
        try:
            p = os.path.join(outside, "overlay.yml")
            with open(p, "w") as f:
                yaml.safe_dump({"scope": "pilot-safe-v1", "active_tier": 2,
                                "briefing_ref": os.path.join(outside, "briefing.md")}, f)
            env = {"DOCUMENTER_ACTIVATION_PATH": p}
            rc, out, _ = _run_service(
                ["--verify-activation", "--json"], self.tmpdir,
                env_override=env)
            self.assertEqual(rc, 0)
            data = json.loads(out.strip())
            self.assertIn("scope_summary", data)
            self.assertEqual(data["scope_summary"]["scope_id"],
                             "pilot-safe-v1")
            self.assertEqual(data["scope_summary"]["target_count"], 2)
        finally:
            shutil.rmtree(outside, ignore_errors=True)


# ---------------------------------------------------------------------------
# --verify-activation — invalid state
# ---------------------------------------------------------------------------

class TestVerifyActivationInvalid(unittest.TestCase):
    """--verify-activation with invalid overlay."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_invalid_yaml_exit_code(self):
        """Invalid overlay YAML returns exit code 2."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        outside = tempfile.mkdtemp()
        try:
            p = os.path.join(outside, "overlay.yml")
            with open(p, "w") as f:
                f.write("invalid: yaml: {broken\n")
            env = {"DOCUMENTER_ACTIVATION_PATH": p}
            rc, out, _ = _run_service(
                ["--verify-activation"], self.tmpdir, env_override=env)
            self.assertEqual(rc, 2)
            self.assertIn("State: invalid", out)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_invalid_non_mapping(self):
        """Scalar overlay YAML => invalid state."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        outside = tempfile.mkdtemp()
        try:
            p = os.path.join(outside, "overlay.yml")
            with open(p, "w") as f:
                f.write("just a string\n")
            env = {"DOCUMENTER_ACTIVATION_PATH": p}
            rc, out, _ = _run_service(
                ["--verify-activation", "--json"], self.tmpdir,
                env_override=env)
            self.assertEqual(rc, 2)
            data = json.loads(out.strip())
            self.assertEqual(data["state"], "invalid")
            self.assertFalse(data["ok"])
            self.assertTrue(len(data.get("errors", [])) > 0)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_invalid_empty_overlay(self):
        """Empty overlay (no scope/ops) => invalid state."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        outside = tempfile.mkdtemp()
        try:
            p = os.path.join(outside, "overlay.yml")
            with open(p, "w") as f:
                f.write("{}\n")
            env = {"DOCUMENTER_ACTIVATION_PATH": p}
            rc, out, _ = _run_service(
                ["--verify-activation"], self.tmpdir, env_override=env)
            self.assertEqual(rc, 2)
            self.assertIn("State: invalid", out)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_errors_in_json(self):
        """Error messages included in invalid state JSON."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        outside = tempfile.mkdtemp()
        try:
            p = os.path.join(outside, "overlay.yml")
            with open(p, "w") as f:
                f.write("bad yaml {\n")
            env = {"DOCUMENTER_ACTIVATION_PATH": p}
            rc, out, _ = _run_service(
                ["--verify-activation", "--json"], self.tmpdir,
                env_override=env)
            self.assertEqual(rc, 2)
            data = json.loads(out.strip())
            self.assertTrue(len(data.get("errors", [])) > 0)
        finally:
            shutil.rmtree(outside, ignore_errors=True)


# ---------------------------------------------------------------------------
# --status — activation block
# ---------------------------------------------------------------------------

class TestStatusActivation(unittest.TestCase):
    """--status includes activation block."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_status_baseline_activation(self):
        """Status shows activation block with baseline."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        rc, out, _ = _run_service(
            ["--status", "--json"], self.tmpdir)
        self.assertEqual(rc, 0)
        data = json.loads(out.strip())
        self.assertIn("activation", data)
        act = data["activation"]
        self.assertFalse(act["overlay_present"])
        self.assertEqual(act["source"], "base")

    def test_status_active_activation(self):
        """Status shows activation block with active overlay."""
        import yaml
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        _write_minimal_manifest(self.tmpdir, [
            "documenter-service-configuration-guide", "operator-ingress"])
        outside = tempfile.mkdtemp()
        try:
            p = os.path.join(outside, "overlay.yml")
            with open(p, "w") as f:
                yaml.safe_dump({"scope": "pilot-safe-v1", "active_tier": 2,
                                "briefing_ref": os.path.join(outside, "briefing.md")}, f)
            env = {"DOCUMENTER_ACTIVATION_PATH": p}
            rc, out, _ = _run_service(
                ["--status", "--json"], self.tmpdir, env_override=env)
            self.assertEqual(rc, 0)
            data = json.loads(out.strip())
            act = data["activation"]
            self.assertTrue(act["overlay_present"])
            self.assertEqual(act["source"], "overlay")
            self.assertEqual(act["scope"], "pilot-safe-v1")
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_status_human_activation(self):
        """Status human output includes activation section."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        rc, out, _ = _run_service(["--status"], self.tmpdir)
        self.assertEqual(rc, 0)
        self.assertIn("activation.overlay_present", out)
        self.assertIn("activation.source", out)
        self.assertIn("activation.allowed_operations_count", out)


# ---------------------------------------------------------------------------
# activation_helper — verify command
# ---------------------------------------------------------------------------

class TestHelperVerify(unittest.TestCase):
    """activation_helper.py verify subcommand."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_helper_verify_baseline(self):
        """Helper verify in baseline state."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        rc, out, _ = _run_helper(["verify"], self.tmpdir)
        self.assertEqual(rc, 0)
        self.assertIn("State: baseline", out)

    def test_helper_verify_active(self):
        """Helper verify with active overlay."""
        import yaml
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        _write_minimal_manifest(self.tmpdir, [
            "documenter-service-configuration-guide", "operator-ingress"])
        outside = tempfile.mkdtemp()
        try:
            p = os.path.join(outside, "overlay.yml")
            with open(p, "w") as f:
                yaml.safe_dump({"scope": "pilot-safe-v1", "active_tier": 2,
                                "briefing_ref": os.path.join(outside, "briefing.md")}, f)
            env = {"DOCUMENTER_ACTIVATION_PATH": p}
            rc, out, _ = _run_helper(
                ["verify"], self.tmpdir, env_override=env)
            self.assertEqual(rc, 0)
            self.assertIn("State: active", out)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_helper_verify_json(self):
        """Helper verify --json produces valid JSON."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        rc, out, _ = _run_helper(["verify", "--json"], self.tmpdir)
        self.assertEqual(rc, 0)
        data = json.loads(out.strip())
        self.assertEqual(data["mode"], "verify-activation")
        self.assertEqual(data["state"], "baseline")


# ---------------------------------------------------------------------------
# activation_helper — template command
# ---------------------------------------------------------------------------

class TestHelperTemplate(unittest.TestCase):
    """activation_helper.py template subcommand."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_template_default_scope(self):
        """Template with default scope (pilot-safe-v1)."""
        rc, out, _ = _run_helper(
            ["template"], self.tmpdir, env_override={})
        self.assertEqual(rc, 0)
        self.assertIn("scope:", out)
        self.assertIn("pilot-safe-v1", out)

    def test_template_custom_scope(self):
        """Template with custom scope."""
        rc, out, _ = _run_helper(
            ["template", "--scope", "ru-sync-review"], self.tmpdir)
        self.assertEqual(rc, 0)
        self.assertIn("scope:", out)
        self.assertIn("ru-sync-review", out)

    def test_template_solo(self):
        """Template with solo approval fields."""
        rc, out, _ = _run_helper(
            ["template", "--solo"], self.tmpdir)
        self.assertEqual(rc, 0)
        self.assertIn("allow_solo_approval:", out)
        self.assertIn("min_approval_delay_seconds:", out)

    def test_template_no_solo(self):
        """Template without solo fields (default)."""
        rc, out, _ = _run_helper(
            ["template", "--no-solo"], self.tmpdir)
        self.assertEqual(rc, 0)
        self.assertNotIn("allow_solo_approval:", out)
        self.assertNotIn("min_approval_delay_seconds:", out)

    def test_template_custom_tier(self):
        """Template with custom active tier."""
        rc, out, _ = _run_helper(
            ["template", "--active-tier", "3"], self.tmpdir)
        self.assertEqual(rc, 0)
        self.assertIn("active_tier: 3", out)


# ---------------------------------------------------------------------------
# activation_helper — deactivate-hints command
# ---------------------------------------------------------------------------

class TestHelperDeactivateHints(unittest.TestCase):
    """activation_helper.py deactivate-hints subcommand."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_deactivate_hints_output(self):
        """deactivate-hints produces step-by-step guidance."""
        rc, out, _ = _run_helper(["deactivate-hints"], self.tmpdir)
        self.assertEqual(rc, 0)
        self.assertIn("Deactivation Hints", out)
        self.assertIn("Step 1:", out)
        self.assertIn("Step 2:", out)
        self.assertIn("Step 3:", out)

    def test_deactivate_hints_json(self):
        """deactivate-hints --json produces valid JSON."""
        rc, out, _ = _run_helper(
            ["deactivate-hints", "--json"], self.tmpdir)
        self.assertEqual(rc, 0)
        data = json.loads(out.strip())
        self.assertEqual(data["action"], "deactivate-tier-2-activation")
        self.assertIn("steps", data)
        self.assertEqual(len(data["steps"]), 3)
        self.assertIn("guarantees", data)


# ---------------------------------------------------------------------------
# activation_helper — --help
# ---------------------------------------------------------------------------

class TestHelperHelp(unittest.TestCase):
    """activation_helper.py --help."""

    def test_helper_help_exits_zero(self):
        """--help exits with code 0."""
        tmp = tempfile.mkdtemp()
        try:
            rc, out, _ = _run_helper(["--help"], tmp)
            self.assertEqual(rc, 0)
            self.assertIn("activation_helper", out.lower())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_helper_help_shows_subcommands(self):
        """--help shows all subcommands."""
        tmp = tempfile.mkdtemp()
        try:
            rc, out, _ = _run_helper(["--help"], tmp)
            self.assertEqual(rc, 0)
            self.assertIn("verify", out)
            self.assertIn("print-effective", out)
            self.assertIn("template", out)
            self.assertIn("deactivate-hints", out)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Global options placement
# ---------------------------------------------------------------------------

class TestGlobalOptions(unittest.TestCase):
    """Tests that global options work before/after subcommand where applicable."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_json_flag_before_subcommand_service(self):
        """--json before subcommand works for service."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        rc, out, _ = _run_service(
            ["--json", "--verify-activation"], self.tmpdir)
        self.assertEqual(rc, 0)
        data = json.loads(out.strip())
        self.assertIn("state", data)

    def test_root_before_subcommand(self):
        """--root before subcommand works."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        rc, out, _ = _run_service(
            ["--verify-activation"], self.tmpdir, root_before=True)
        self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# No-overlay in existing environments
# ---------------------------------------------------------------------------

class TestNoOverlayExistingEnvironments(unittest.TestCase):
    """Ensure existing environments without overlay work correctly."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_existing_data_dir_no_overlay(self):
        """Existing data dir with no overlay => baseline."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        # Create a data dir like the service would expect
        data_dir = os.path.join(self.tmpdir, "documenter")
        os.makedirs(data_dir, exist_ok=True)
        rc, out, _ = _run_service(
            ["--verify-activation", "--json"], self.tmpdir)
        self.assertEqual(rc, 0)
        data = json.loads(out.strip())
        self.assertEqual(data["state"], "baseline")

    def test_existing_status_no_overlay(self):
        """--status with no overlay => baseline activation."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        data_dir = os.path.join(self.tmpdir, "documenter")
        os.makedirs(data_dir, exist_ok=True)
        rc, out, _ = _run_service(
            ["--status", "--json"], self.tmpdir)
        self.assertEqual(rc, 0)
        data = json.loads(out.strip())
        self.assertFalse(data["activation"]["overlay_present"])


# ---------------------------------------------------------------------------
# activation_helper — print-effective
# ---------------------------------------------------------------------------

class TestHelperPrintEffective(unittest.TestCase):
    """activation_helper.py print-effective subcommand."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_print_effective_baseline(self):
        """print-effective shows base policy."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        rc, out, _ = _run_helper(
            ["print-effective"], self.tmpdir)
        self.assertEqual(rc, 0)
        self.assertIn("Effective fields", out)
        self.assertIn("active_tier: 1", out)

    def test_print_effective_json(self):
        """print-effective --json produces valid JSON."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        rc, out, _ = _run_helper(
            ["print-effective", "--json"], self.tmpdir)
        self.assertEqual(rc, 0)
        data = json.loads(out.strip())
        self.assertIn("activation", data)
        self.assertIn("effective_fields", data)


# ---------------------------------------------------------------------------
# Regression: no-overlay in existing environments
# ---------------------------------------------------------------------------

class TestRegressionNoOverlay(unittest.TestCase):
    """Regression tests: ensure overlay changes don't break existing setups."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_solo_activation_regression(self):
        """Solo activation: base policy without overlay unchanged."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
            "allow_solo_approval": False,
        })
        rc, out, _ = _run_service(
            ["--verify-activation", "--json"], self.tmpdir)
        self.assertEqual(rc, 0)
        data = json.loads(out.strip())
        self.assertEqual(data["state"], "baseline")
        self.assertFalse(data["effective"]["allow_solo_approval"])
        self.assertEqual(data["effective"]["min_approval_delay_seconds"], 0)

    def test_integration_interlock_no_overlay(self):
        """Integration: without overlay, interlock stays locked."""
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        rc, out, _ = _run_service(
            ["--verify-activation", "--json"], self.tmpdir)
        self.assertEqual(rc, 0)
        data = json.loads(out.strip())
        self.assertFalse(data["interlock"]["tier2_authorized"])
        self.assertFalse(data["interlock"]["tier2_policy_ready"])
        self.assertFalse(data["interlock"]["sentinel_present"])
        # The reason should mention the missing components
        self.assertTrue(len(data["interlock"]["reason"]) > 0)

    def test_interlock_with_overlay_scope(self):
        """Integration: overlay present, but sentinel still missing."""
        import yaml
        _write_policy_yaml(self.tmpdir, {
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        _write_minimal_manifest(self.tmpdir, [
            "documenter-service-configuration-guide", "operator-ingress"])
        outside = tempfile.mkdtemp()
        try:
            p = os.path.join(outside, "overlay.yml")
            with open(p, "w") as f:
                yaml.safe_dump({
                    "scope": "pilot-safe-v1",
                    "active_tier": 2,
                    "briefing_ref": os.path.join(outside, "briefing.md"),
                }, f)
            env = {"DOCUMENTER_ACTIVATION_PATH": p}
            rc, out, _ = _run_service(
                ["--verify-activation", "--json"], self.tmpdir,
                env_override=env)
            self.assertEqual(rc, 0)
            data = json.loads(out.strip())
            self.assertEqual(data["state"], "active")
            # Sentinel missing => not authorized
            self.assertFalse(data["interlock"]["tier2_authorized"])
        finally:
            shutil.rmtree(outside, ignore_errors=True)
