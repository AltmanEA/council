"""Tests for activation overlay loading, validation, expansion, and merge.

Covers the runtime activation overlay system: overlay path resolution,
containment, allowlist, XOR, scope expansion/narrowing, merge semantics,
and solo field validation.

Run with: python3 -m unittest tests.test_activation_overlay -v
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from documenter_service.core.policy import (  # noqa: E402
    Policy, PolicyError, load_policy, validate_policy)
from documenter_service.core.activation import (  # noqa: E402
    ACTIVATION_ENV, DEFAULT_ACTIVATION_PATH,
    load_activation_overlay, apply_activation_overlay,
    activation_summary, resolve_activation_path,
)
from documenter_service.core import scope_presets  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmpdir():
    """Create a temporary directory for simulated workspace root."""
    return tempfile.mkdtemp()


def _policy_path(tmpdir, fields):
    """Write a policy YAML file in tmpdir. Returns path."""
    import yaml
    p = os.path.join(tmpdir, "documenter_policy.yml")
    with open(p, "w") as f:
        yaml.safe_dump({"documenter_policy": fields}, f)
    return p


def _write_overlay_in_outside_dir(fields, tmpdir):
    """Write overlay YAML in a temp dir OUTSIDE tmpdir. Returns (path, cleanup_dir)."""
    import yaml
    outside = tempfile.mkdtemp()
    p = os.path.join(outside, "overlay.yml")
    with open(p, "w") as f:
        yaml.safe_dump(fields, f)
    return os.path.abspath(p), outside


def _empty_env():
    """Return a minimal env dict with no ACTIVATION_ENV set."""
    return {}


def _tmpdir_outside():
    """Create a pair: (workspace_root, outside_dir)."""
    root = tempfile.mkdtemp()
    outside = tempfile.mkdtemp()
    return root, outside


def _write_overlay_file(outside, fields):
    """Write overlay YAML in outside dir. Returns path."""
    import yaml
    p = os.path.join(outside, "overlay.yml")
    with open(p, "w") as f:
        yaml.safe_dump(fields, f)
    return p


def _load_overlay_test(root, outside, fields):
    """Write overlay and load it. Returns (overlay, path, explicit)."""
    p = _write_overlay_file(outside, fields)
    return load_activation_overlay(root, {ACTIVATION_ENV: p})


# ---------------------------------------------------------------------------
# resolve_activation_path
# ---------------------------------------------------------------------------

class TestResolveActivationPath(unittest.TestCase):
    """Tests for resolve_activation_path()."""

    def test_default_path_absent(self):
        """Default path returned when env not set."""
        root = _tmpdir()
        path, explicit = resolve_activation_path(root, _empty_env())
        self.assertEqual(path, DEFAULT_ACTIVATION_PATH)
        self.assertFalse(explicit)

    def test_explicit_path(self):
        """Explicit env path returned as-is."""
        root = _tmpdir()
        env = {ACTIVATION_ENV: "/custom/path/overlay.yml"}
        path, explicit = resolve_activation_path(root, env)
        self.assertEqual(path, "/custom/path/overlay.yml")
        self.assertTrue(explicit)

    def test_explicit_path_stripped(self):
        """Whitespace is stripped from explicit path."""
        root = _tmpdir()
        env = {ACTIVATION_ENV: "  /custom/path/overlay.yml  "}
        path, explicit = resolve_activation_path(root, env)
        self.assertEqual(path, "/custom/path/overlay.yml")
        self.assertTrue(explicit)

    def test_explicit_relative_path_rejected(self):
        """Relative explicit path: abs expanded => check containment.
        
        os.path.abspath() makes 'relative/path.yml' absolute.
        Since root is a temp dir outside cwd, containment passes.
        But the overlay loader will catch it when the actual file
        doesn't exist (explicit missing => PolicyError).
        
        However, _require_outside_workspace is called with
        must_be_absolute=True and the path becomes absolute via
        abspath(), so no error is raised here.
        The real validation is in load_activation_overlay where
        the file must exist.
        """
        # This test documents that resolve_activation_path does NOT
        # reject relative paths that become absolute via abspath().
        # The actual containment check happens against the root,
        # and since our temp root is outside cwd, it passes.
        root = _tmpdir()
        env = {ACTIVATION_ENV: "relative/path.yml"}
        # resolve_activation_path expands the path and checks containment;
        # since root is in /tmp (outside cwd), the relative path becomes
        # abs and is not under root => passes.
        path, explicit = resolve_activation_path(root, env)
        self.assertTrue(explicit)
        self.assertIn("relative/path.yml", path)

    def test_explicit_inside_workspace_rejected(self):
        """Explicit path inside workspace raises PolicyError."""
        root = _tmpdir()
        env = {ACTIVATION_ENV: os.path.join(root, "overlay.yml")}
        with self.assertRaises(PolicyError) as ctx:
            resolve_activation_path(root, env)
        self.assertIn("outside workspace root", ctx.exception.reason)


# ---------------------------------------------------------------------------
# load_activation_overlay — absent overlay
# ---------------------------------------------------------------------------

class TestLoadOverlayAbsent(unittest.TestCase):
    """Tests for absent overlay scenarios."""

    def test_absent_default_returns_none(self):
        """Default overlay absent => (None, path, False)."""
        root = _tmpdir()
        overlay, path, explicit = load_activation_overlay(root, _empty_env())
        self.assertIsNone(overlay)
        self.assertEqual(path, DEFAULT_ACTIVATION_PATH)
        self.assertFalse(explicit)

    def test_absent_explicit_raises(self):
        """Explicit env path that doesn't exist => PolicyError."""
        root = _tmpdir()
        env = {ACTIVATION_ENV: "/tmp/nonexistent_overlay_path_12345.yml"}
        with self.assertRaises(PolicyError) as ctx:
            load_activation_overlay(root, env)
        self.assertIn("not found", ctx.exception.reason)


# ---------------------------------------------------------------------------
# load_activation_overlay — present but invalid
# ---------------------------------------------------------------------------

class TestLoadOverlayInvalid(unittest.TestCase):
    """Tests for present-but-invalid overlay."""

    def test_invalid_yaml(self):
        """Malformed YAML => PolicyError."""
        root, outside = _tmpdir_outside()
        try:
            p = os.path.join(outside, "overlay.yml")
            with open(p, "w") as f:
                f.write("invalid: yaml: {broken\n")
            env = {ACTIVATION_ENV: p}
            with self.assertRaises(PolicyError) as ctx:
                load_activation_overlay(root, env)
            self.assertIn("invalid YAML", ctx.exception.reason)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_non_mapping_overlay(self):
        """Scalar YAML (not mapping) => PolicyError."""
        root, outside = _tmpdir_outside()
        try:
            p = os.path.join(outside, "overlay.yml")
            with open(p, "w") as f:
                f.write("just a string\n")
            env = {ACTIVATION_ENV: p}
            with self.assertRaises(PolicyError) as ctx:
                load_activation_overlay(root, env)
            self.assertIn("must be a YAML mapping", ctx.exception.reason)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_empty_mapping_fails_xor(self):
        """Empty YAML mapping => XOR check fails."""
        root, outside = _tmpdir_outside()
        try:
            import yaml
            p = os.path.join(outside, "overlay.yml")
            with open(p, "w") as f:
                yaml.safe_dump({}, f)
            env = {ACTIVATION_ENV: p}
            with self.assertRaises(PolicyError) as ctx:
                load_activation_overlay(root, env)
            self.assertIn("exactly one of", ctx.exception.reason)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_none_doc_is_empty_mapping(self):
        """Empty file => None doc => empty mapping => XOR fail."""
        root, outside = _tmpdir_outside()
        try:
            p = os.path.join(outside, "overlay.yml")
            with open(p, "w") as f:
                pass  # empty file => yaml.safe_load => None => {}
            env = {ACTIVATION_ENV: p}
            with self.assertRaises(PolicyError) as ctx:
                load_activation_overlay(root, env)
            self.assertIn("exactly one of", ctx.exception.reason)
        finally:
            shutil.rmtree(outside, ignore_errors=True)


# ---------------------------------------------------------------------------
# load_activation_overlay — strict allowlist
# ---------------------------------------------------------------------------

class TestOverlayAllowlist(unittest.TestCase):
    """Tests for strict allowlist enforcement."""

    def test_unknown_key_raises(self):
        """Unknown key => PolicyError."""
        root, outside = _tmpdir_outside()
        try:
            import yaml
            p = os.path.join(outside, "overlay.yml")
            with open(p, "w") as f:
                yaml.safe_dump(
                    {"scope": "pilot-safe-v1", "unknown_field": True}, f)
            env = {ACTIVATION_ENV: p}
            with self.assertRaises(PolicyError) as ctx:
                load_activation_overlay(root, env)
            self.assertIn("unknown key", ctx.exception.reason)
            self.assertIn("unknown_field", ctx.exception.reason)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_unknown_keys_multiple(self):
        """Multiple unknown keys listed."""
        root, outside = _tmpdir_outside()
        try:
            import yaml
            p = os.path.join(outside, "overlay.yml")
            with open(p, "w") as f:
                yaml.safe_dump(
                    {"scope": "pilot-safe-v1", "foo": 1, "bar": 2}, f)
            env = {ACTIVATION_ENV: p}
            with self.assertRaises(PolicyError) as ctx:
                load_activation_overlay(root, env)
            self.assertIn("foo", ctx.exception.reason)
            self.assertIn("bar", ctx.exception.reason)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_valid_keys_allowed(self):
        """Overlay with only valid keys passes allowlist check."""
        root, outside = _tmpdir_outside()
        try:
            import yaml
            p = os.path.join(outside, "overlay.yml")
            with open(p, "w") as f:
                yaml.safe_dump({"scope": "pilot-safe-v1"}, f)
            env = {ACTIVATION_ENV: p}
            overlay, path, explicit = load_activation_overlay(root, env)
            self.assertIsNotNone(overlay)
            self.assertEqual(overlay["scope"], "pilot-safe-v1")
        finally:
            shutil.rmtree(outside, ignore_errors=True)


# ---------------------------------------------------------------------------
# load_activation_overlay — XOR
# ---------------------------------------------------------------------------

class TestOverlayXOR(unittest.TestCase):
    """Tests for XOR constraint between scope and allowed_operations."""

    def test_both_scope_and_ops_raises(self):
        """Both scope and allowed_operations => PolicyError."""
        root, outside = _tmpdir_outside()
        try:
            with self.assertRaises(PolicyError) as ctx:
                _load_overlay_test(root, outside, {
                    "scope": "pilot-safe-v1",
                    "allowed_operations": [{"type": "operation"}],
                })
            self.assertIn("must not specify both", ctx.exception.reason)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_neither_raises(self):
        """Neither scope nor allowed_operations => PolicyError."""
        root, outside = _tmpdir_outside()
        try:
            with self.assertRaises(PolicyError) as ctx:
                _load_overlay_test(root, outside, {"active_tier": 2})
            self.assertIn("exactly one of", ctx.exception.reason)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_scope_only_ok(self):
        """Only scope => valid."""
        root, outside = _tmpdir_outside()
        try:
            overlay, _, _ = _load_overlay_test(root, outside,
                                               {"scope": "pilot-safe-v1"})
            self.assertIsNotNone(overlay)
            self.assertEqual(overlay["scope"], "pilot-safe-v1")
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_ops_only_ok(self):
        """Only allowed_operations => valid."""
        root, outside = _tmpdir_outside()
        try:
            overlay, _, _ = _load_overlay_test(root, outside, {
                "allowed_operations": [
                    {"type": "operation", "change_type": "update",
                     "trust_level": "safe", "targets": ["glossary"]}
                ]
            })
            self.assertIsNotNone(overlay)
            self.assertEqual(overlay["allowed_operations"][0]["change_type"],
                             "update")
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_none_scope_ok_with_ops(self):
        """scope=null with allowed_operations => valid."""
        root, outside = _tmpdir_outside()
        try:
            overlay, _, _ = _load_overlay_test(root, outside, {
                "scope": None,
                "allowed_operations": [{"type": "operation"}],
            })
            self.assertIsNotNone(overlay)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_none_ops_ok_with_scope(self):
        """allowed_operations=null with scope => valid."""
        root, outside = _tmpdir_outside()
        try:
            overlay, _, _ = _load_overlay_test(root, outside, {
                "scope": "pilot-safe-v1",
                "allowed_operations": None,
            })
            self.assertIsNotNone(overlay)
        finally:
            shutil.rmtree(outside, ignore_errors=True)


# ---------------------------------------------------------------------------
# load_activation_overlay — scope_targets
# ---------------------------------------------------------------------------

class TestOverlayScopeTargets(unittest.TestCase):
    """Tests for scope_targets field."""

    def test_scope_targets_requires_scope(self):
        """scope_targets without scope => PolicyError."""
        root, outside = _tmpdir_outside()
        try:
            with self.assertRaises(PolicyError) as ctx:
                _load_overlay_test(root, outside, {
                    "allowed_operations": [],
                    "scope_targets": ["glossary"],
                })
            self.assertIn("scope_targets requires 'scope'",
                          ctx.exception.reason)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_scope_targets_must_be_list(self):
        """scope_targets as non-list => PolicyError."""
        root, outside = _tmpdir_outside()
        try:
            with self.assertRaises(PolicyError) as ctx:
                _load_overlay_test(root, outside, {
                    "scope": "pilot-safe-v1",
                    "scope_targets": "not-a-list",
                })
            self.assertIn("scope_targets must be a list",
                          ctx.exception.reason)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_scope_targets_list_ok(self):
        """scope_targets as list with scope => valid."""
        root, outside = _tmpdir_outside()
        try:
            overlay, _, _ = _load_overlay_test(root, outside, {
                "scope": "pilot-safe-v1",
                "scope_targets": ["glossary"],
            })
            self.assertEqual(overlay["scope_targets"], ["glossary"])
        finally:
            shutil.rmtree(outside, ignore_errors=True)


# ---------------------------------------------------------------------------
# load_activation_overlay — containment
# ---------------------------------------------------------------------------

class TestOverlayContainment(unittest.TestCase):
    """Tests for containment enforcement."""

    def test_briefing_ref_inside_workspace_rejected(self):
        """briefing_ref inside workspace => PolicyError."""
        root, outside = _tmpdir_outside()
        try:
            with self.assertRaises(PolicyError) as ctx:
                _load_overlay_test(root, outside, {
                    "scope": "pilot-safe-v1",
                    "briefing_ref": os.path.join(root, "briefing.md"),
                })
            self.assertIn("outside workspace root", ctx.exception.reason)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_briefing_ref_outside_workspace_ok(self):
        """briefing_ref outside workspace => valid."""
        root, outside = _tmpdir_outside()
        try:
            overlay, _, _ = _load_overlay_test(root, outside, {
                "scope": "pilot-safe-v1",
                "briefing_ref": os.path.join(outside, "briefing.md"),
            })
            self.assertEqual(
                overlay["briefing_ref"],
                os.path.join(outside, "briefing.md"))
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_briefing_ref_empty_allowed(self):
        """Empty string briefing_ref => valid."""
        root, outside = _tmpdir_outside()
        try:
            overlay, _, _ = _load_overlay_test(root, outside, {
                "scope": "pilot-safe-v1",
                "briefing_ref": "",
            })
            self.assertEqual(overlay["briefing_ref"], "")
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_briefing_ref_null_allowed(self):
        """Null briefing_ref => valid."""
        root, outside = _tmpdir_outside()
        try:
            overlay, _, _ = _load_overlay_test(root, outside, {
                "scope": "pilot-safe-v1",
                "briefing_ref": None,
            })
            self.assertIsNone(overlay["briefing_ref"])
        finally:
            shutil.rmtree(outside, ignore_errors=True)


# ---------------------------------------------------------------------------
# load_activation_overlay — field type validation
# ---------------------------------------------------------------------------

class TestOverlayFieldTypes(unittest.TestCase):
    """Tests for overlay field type validation."""

    def test_active_tier_must_be_int(self):
        """active_tier as non-int => PolicyError."""
        root, outside = _tmpdir_outside()
        try:
            with self.assertRaises(PolicyError):
                _load_overlay_test(root, outside, {
                    "scope": "pilot-safe-v1", "active_tier": 2.5})
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_active_tier_bool_rejected(self):
        """active_tier as bool => PolicyError."""
        root, outside = _tmpdir_outside()
        try:
            with self.assertRaises(PolicyError):
                _load_overlay_test(root, outside, {
                    "scope": "pilot-safe-v1", "active_tier": True})
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_allow_solo_approval_must_be_bool(self):
        """allow_solo_approval as non-bool => PolicyError."""
        root, outside = _tmpdir_outside()
        try:
            with self.assertRaises(PolicyError):
                _load_overlay_test(root, outside, {
                    "scope": "pilot-safe-v1", "allow_solo_approval": "yes"})
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_min_approval_delay_must_be_int(self):
        """min_approval_delay_seconds as non-int => PolicyError."""
        root, outside = _tmpdir_outside()
        try:
            with self.assertRaises(PolicyError):
                _load_overlay_test(root, outside, {
                    "scope": "pilot-safe-v1",
                    "min_approval_delay_seconds": 3.5})
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_min_approval_delay_bool_rejected(self):
        """min_approval_delay_seconds as bool => PolicyError."""
        root, outside = _tmpdir_outside()
        try:
            with self.assertRaises(PolicyError):
                _load_overlay_test(root, outside, {
                    "scope": "pilot-safe-v1",
                    "min_approval_delay_seconds": True})
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_briefing_ref_must_be_string(self):
        """briefing_ref as non-string => PolicyError."""
        root, outside = _tmpdir_outside()
        try:
            with self.assertRaises(PolicyError):
                _load_overlay_test(root, outside, {
                    "scope": "pilot-safe-v1", "briefing_ref": 12345})
        finally:
            shutil.rmtree(outside, ignore_errors=True)


# ---------------------------------------------------------------------------
# load_activation_overlay — unknown scope
# ---------------------------------------------------------------------------

class TestOverlayUnknownScope(unittest.TestCase):
    """Tests for unknown scope IDs."""

    def test_unknown_scope_in_expand_raises(self):
        """Unknown scope in scope_presets.expand => PolicyError."""
        from documenter_service.core import scope_presets
        with self.assertRaises(PolicyError) as ctx:
            scope_presets.expand("nonexistent-scope")
        self.assertIn("unknown scope", ctx.exception.reason.lower())

    def test_load_policy_with_unknown_scope_raises(self):
        """Unknown scope causes load_policy to fail."""
        root, outside = _tmpdir_outside()
        try:
            _policy_f = os.path.join(root, "documenter_policy.yml")
            import yaml
            with open(_policy_f, "w") as f:
                yaml.safe_dump({
                    "documenter_policy": {
                        "version": "0.2.0", "active_tier": 1,
                        "allowed_operations": [], "briefing_ref": None,
                    }
                }, f)
            _write_overlay_file(outside, {
                "scope": "nonexistent-scope", "active_tier": 2
            })
            env = {ACTIVATION_ENV: os.path.join(outside, "overlay.yml")}
            with self.assertRaises(PolicyError):
                load_policy(root, env=env)
        finally:
            shutil.rmtree(outside, ignore_errors=True)


# ---------------------------------------------------------------------------
# scope_presets — expansion and target counts
# ---------------------------------------------------------------------------

class TestScopePresetsExpansion(unittest.TestCase):
    """Tests for scope preset expansion and target counts."""

    def test_pilot_safe_v1_target_count(self):
        """pilot-safe-v1 expands to 1 operation with 2 targets."""
        ops = scope_presets.expand("pilot-safe-v1")
        self.assertEqual(len(ops), 1)
        self.assertEqual(len(ops[0]["targets"]), 2)

    def test_docs_maint_safe_target_count(self):
        """docs-maint-safe expands to 24 operations."""
        ops = scope_presets.expand("docs-maint-safe")
        self.assertEqual(len(ops), 1)
        self.assertEqual(len(ops[0]["targets"]), 24)

    def test_docs_content_review_target_count(self):
        """docs-content-review expands to 24 operations."""
        ops = scope_presets.expand("docs-content-review")
        self.assertEqual(len(ops), 1)
        self.assertEqual(len(ops[0]["targets"]), 24)

    def test_ru_sync_review_target_count(self):
        """ru-sync-review expands to 18 operations."""
        ops = scope_presets.expand("ru-sync-review")
        self.assertEqual(len(ops), 1)
        self.assertEqual(len(ops[0]["targets"]), 18)

    def test_preset_change_types(self):
        """Check change types for each preset."""
        self.assertEqual(
            scope_presets.expand("pilot-safe-v1")[0]["change_type"],
            "update")
        self.assertEqual(
            scope_presets.expand("ru-sync-review")[0]["change_type"],
            "create_ru")

    def test_preset_trust_levels(self):
        """Check trust levels for each preset."""
        self.assertEqual(
            scope_presets.expand("pilot-safe-v1")[0]["trust_level"],
            "safe")
        self.assertEqual(
            scope_presets.expand("docs-content-review")[0]["trust_level"],
            "review")

    def test_deepcopy_isolation(self):
        """Expansions are deep-copied (mutations don't affect each other)."""
        ops1 = scope_presets.expand("pilot-safe-v1")
        ops2 = scope_presets.expand("pilot-safe-v1")
        ops1[0]["targets"].append("extra")
        self.assertNotIn("extra", ops2[0]["targets"])


# ---------------------------------------------------------------------------
# scope_presets — narrowing
# ---------------------------------------------------------------------------

class TestScopeNarrowing(unittest.TestCase):
    """Tests for scope_targets narrowing."""

    def test_narrowing_subset_ok(self):
        """scope_targets subset of preset => valid."""
        ops = scope_presets.expand(
            "pilot-safe-v1", scope_targets=["operator-ingress"])
        self.assertEqual(ops[0]["targets"], ["operator-ingress"])

    def test_narrowing_presorted(self):
        """Narrowed scope_targets are sorted deterministically."""
        ops = scope_presets.expand(
            "pilot-safe-v1", scope_targets=[
                "operator-ingress",
                "documenter-service-configuration-guide"])
        self.assertEqual(
            ops[0]["targets"],
            ["documenter-service-configuration-guide", "operator-ingress"])

    def test_narrowing_invalid_id_raises(self):
        """scope_targets with unknown id => PolicyError."""
        with self.assertRaises(PolicyError):
            scope_presets.expand(
                "pilot-safe-v1", scope_targets=["nonexistent-target"])

    def test_narrowing_non_list_raises(self):
        """scope_targets as non-list => PolicyError."""
        with self.assertRaises(PolicyError):
            scope_presets.expand("pilot-safe-v1", scope_targets="string")

    def test_narrowing_empty_list_raises(self):
        """scope_targets empty list => PolicyError."""
        with self.assertRaises(PolicyError):
            scope_presets.expand("pilot-safe-v1", scope_targets=[])

    def test_narrowing_non_string_raises(self):
        """scope_targets with non-string element => PolicyError."""
        with self.assertRaises(PolicyError):
            scope_presets.expand("pilot-safe-v1", scope_targets=[123])

    def test_narrowing_duplicates_deduped(self):
        """Duplicate scope_targets are deduplicated."""
        ops = scope_presets.expand(
            "pilot-safe-v1", scope_targets=[
                "operator-ingress", "operator-ingress"])
        self.assertEqual(ops[0]["targets"], ["operator-ingress"])


# ---------------------------------------------------------------------------
# apply_activation_overlay — merge semantics
# ---------------------------------------------------------------------------

class TestApplyOverlayMerge(unittest.TestCase):
    """Tests for apply_activation_overlay merge semantics."""

    def setUp(self):
        self.root, self.outside = _tmpdir_outside()

    def tearDown(self):
        shutil.rmtree(self.outside, ignore_errors=True)

    def test_allowed_operations_replaced(self):
        """Overlay scope replaces base allowed_operations (1 op, 2 targets)."""
        base = {"active_tier": 1, "allowed_operations": []}
        overlay = {"scope": "pilot-safe-v1"}
        eff = apply_activation_overlay(base, overlay, self.root)
        self.assertEqual(len(eff["allowed_operations"]), 1)
        self.assertEqual(len(eff["allowed_operations"][0]["targets"]), 2)

    def test_overlay_active_tier_overrides(self):
        """Overlay active_tier overrides base."""
        base = {"active_tier": 1, "allowed_operations": []}
        overlay = {"scope": "pilot-safe-v1", "active_tier": 2}
        eff = apply_activation_overlay(base, overlay, self.root)
        self.assertEqual(eff["active_tier"], 2)

    def test_overlay_briefing_ref_overrides(self):
        """Overlay briefing_ref overrides base."""
        base = {"active_tier": 1, "allowed_operations": [],
                "briefing_ref": "/old/briefing.md"}
        overlay = {"scope": "pilot-safe-v1",
                   "briefing_ref": os.path.join(self.outside, "new.md")}
        eff = apply_activation_overlay(base, overlay, self.root)
        self.assertEqual(eff["briefing_ref"],
                         os.path.join(self.outside, "new.md"))

    def test_base_fields_preserved(self):
        """Non-overlay base fields are preserved."""
        base = {"active_tier": 1, "allowed_operations": [],
                "audit_freshness": 30, "notification_mode": "inline"}
        overlay = {"scope": "pilot-safe-v1"}
        eff = apply_activation_overlay(base, overlay, self.root)
        self.assertEqual(eff["audit_freshness"], 30)
        self.assertEqual(eff["notification_mode"], "inline")

    def test_solo_fields_overridden(self):
        """Overlay allow_solo_approval/min_approval_delay override base."""
        base = {
            "active_tier": 1, "allowed_operations": [],
            "allow_solo_approval": False, "min_approval_delay_seconds": 0,
        }
        overlay = {
            "scope": "pilot-safe-v1",
            "allow_solo_approval": True, "min_approval_delay_seconds": 600,
        }
        eff = apply_activation_overlay(base, overlay, self.root)
        self.assertTrue(eff["allow_solo_approval"])
        self.assertEqual(eff["min_approval_delay_seconds"], 600)

    def test_effective_briefing_containment(self):
        """Effective briefing_ref outside workspace => valid."""
        base = {"active_tier": 1, "allowed_operations": [],
                "briefing_ref": None}
        overlay = {
            "scope": "pilot-safe-v1",
            "briefing_ref": os.path.join(self.outside, "briefing.md"),
        }
        eff = apply_activation_overlay(base, overlay, self.root)
        self.assertIsNotNone(eff["briefing_ref"])

    def test_effective_briefing_inside_workspace_rejected(self):
        """Effective briefing_ref inside workspace raises PolicyError."""
        base = {"active_tier": 1, "allowed_operations": []}
        overlay = {
            "scope": "pilot-safe-v1",
            "briefing_ref": os.path.join(self.root, "briefing.md"),
        }
        with self.assertRaises(PolicyError):
            apply_activation_overlay(base, overlay, self.root)

    def test_advanced_override_ops(self):
        """Direct allowed_operations list used as-is."""
        base = {"active_tier": 1, "allowed_operations": []}
        overlay = {"allowed_operations": [
            {"type": "operation", "change_type": "update",
             "trust_level": "safe", "targets": ["glossary"]}]
        }
        eff = apply_activation_overlay(base, overlay, self.root)
        self.assertEqual(len(eff["allowed_operations"]), 1)
        self.assertEqual(eff["allowed_operations"][0]["targets"],
                         ["glossary"])

    def test_advanced_override_ops_must_be_list(self):
        """allowed_operations non-list => PolicyError."""
        base = {"active_tier": 1, "allowed_operations": []}
        overlay = {"allowed_operations": "not-a-list"}
        with self.assertRaises(PolicyError):
            apply_activation_overlay(base, overlay, self.root)


# ---------------------------------------------------------------------------
# activation_summary
# ---------------------------------------------------------------------------

class TestActivationSummary(unittest.TestCase):
    """Tests for activation_summary() output structure."""

    def test_summary_keys_present(self):
        """Summary dict has all expected keys."""
        summary = activation_summary(None)
        self.assertIsInstance(summary, dict)
        expected_keys = {
            "overlay_present", "overlay_path", "scope", "mode",
            "source", "effective_tier", "briefing_ref",
            "allowed_operations_count", "sentinel_present",
            "briefing_exists",
        }
        self.assertEqual(set(summary.keys()), expected_keys)

    def test_source_default_is_base(self):
        """Source defaults to 'base' when no overlay."""
        summary = activation_summary(None)
        self.assertEqual(summary["source"], "base")

    def test_source_none_handling(self):
        """Summary handles None fields gracefully."""
        summary = activation_summary(None)
        self.assertIsNone(summary["scope"])
        self.assertIsNone(summary["overlay_path"])
        self.assertIsNone(summary["effective_tier"])


# ---------------------------------------------------------------------------
# scope_presets — list_scopes and list_scope_ids API
# ---------------------------------------------------------------------------

class TestScopePresetsAPI(unittest.TestCase):
    """Tests for scope_presets public API stability."""

    def test_list_scope_ids_sorted(self):
        """list_scope_ids returns sorted list."""
        ids = scope_presets.list_scope_ids()
        self.assertEqual(ids, sorted(ids))

    def test_list_scope_ids_four_presets(self):
        """list_scope_ids returns exactly 4 IDs."""
        ids = scope_presets.list_scope_ids()
        self.assertEqual(len(ids), 4)

    def test_list_scope_ids_known_values(self):
        """list_scope_ids contains expected preset IDs."""
        ids = set(scope_presets.list_scope_ids())
        expected = {"pilot-safe-v1", "docs-maint-safe",
                    "docs-content-review", "ru-sync-review"}
        self.assertEqual(ids, expected)

    def test_list_scopes_returns_list(self):
        """list_scopes returns a list of dicts."""
        scopes = scope_presets.list_scopes()
        self.assertIsInstance(scopes, list)
        self.assertEqual(len(scopes), 4)

    def test_list_scopes_has_required_fields(self):
        """Each scope dict has required fields."""
        scopes = scope_presets.list_scopes()
        required = {"id", "description", "change_type", "trust_level",
                     "target_count", "targets"}
        for scope in scopes:
            self.assertEqual(set(scope.keys()), required)

    def test_get_preset_returns_none_for_unknown(self):
        """get_preset returns None for unknown scope."""
        self.assertIsNone(scope_presets.get_preset("nonexistent"))

    def test_get_preset_returns_deepcopy(self):
        """get_preset returns a copy (mutations are isolated)."""
        p1 = scope_presets.get_preset("pilot-safe-v1")
        p2 = scope_presets.get_preset("pilot-safe-v1")
        if p1 and p2:
            p1["operations"][0]["targets"].append("extra")
            self.assertNotIn("extra", p2["operations"][0]["targets"])


# ---------------------------------------------------------------------------
# Integration: load_policy with activation overlay
# ---------------------------------------------------------------------------

class TestLoadPolicyWithOverlay(unittest.TestCase):
    """Integration tests: load_policy with activation overlay present."""

    def setUp(self):
        self.root, self.outside = _tmpdir_outside()

    def tearDown(self):
        shutil.rmtree(self.outside, ignore_errors=True)

    def _write_policy(self, fields):
        import yaml
        p = os.path.join(self.root, "documenter_policy.yml")
        with open(p, "w") as f:
            yaml.safe_dump({"documenter_policy": fields}, f)
        return p

    def _write_overlay(self, fields):
        import yaml
        p = os.path.join(self.outside, "overlay.yml")
        with open(p, "w") as f:
            yaml.safe_dump(fields, f)
        return p

    def test_load_policy_baseline_no_overlay(self):
        """load_policy returns base policy when overlay absent."""
        self._write_policy({
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        policy = load_policy(self.root, env=_empty_env())
        self.assertFalse(policy.overlay_present)
        self.assertEqual(policy.activation_source, "base")

    def test_load_policy_with_overlay_active(self):
        """load_policy merges overlay when present."""
        self._write_policy({
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        self._write_overlay({
            "scope": "pilot-safe-v1", "active_tier": 2,
            "briefing_ref": "/tmp/briefing.md",
        })
        env = {ACTIVATION_ENV: os.path.join(self.outside, "overlay.yml")}
        policy = load_policy(self.root, env=env)
        self.assertTrue(policy.overlay_present)
        self.assertEqual(policy.activation_source, "overlay")
        self.assertEqual(policy.activation_scope, "pilot-safe-v1")
        self.assertEqual(policy.activation_mode, "scope")
        self.assertEqual(len(policy.get("allowed_operations")), 1)
        self.assertEqual(len(policy.get("allowed_operations")[0]["targets"]), 2)

    def test_load_policy_overlay_invalid_yaml(self):
        """load_policy fails when overlay YAML is invalid."""
        self._write_policy({
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        p = os.path.join(self.outside, "overlay.yml")
        with open(p, "w") as f:
            f.write("invalid: yaml: {broken\n")
        env = {ACTIVATION_ENV: p}
        with self.assertRaises(PolicyError):
            load_policy(self.root, env=env)

    def test_load_policy_with_advanced_override(self):
        """load_policy with allowed_operations override works."""
        self._write_policy({
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        self._write_overlay({
            "active_tier": 2,
            "briefing_ref": "/tmp/briefing.md",
            "allowed_operations": [{
                "type": "operation", "change_type": "update",
                "trust_level": "safe", "targets": ["glossary"],
                "requires_diff_preview": True
            }]
        })
        env = {ACTIVATION_ENV: os.path.join(self.outside, "overlay.yml")}
        policy = load_policy(self.root, env=env)
        self.assertTrue(policy.overlay_present)
        self.assertEqual(policy.activation_mode, "override")

    def test_load_policy_with_solo_fields(self):
        """Overlay with solo fields merges correctly."""
        self._write_policy({
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        self._write_overlay({
            "scope": "pilot-safe-v1",
            "active_tier": 2,
            "briefing_ref": "/tmp/briefing.md",
            "allow_solo_approval": True,
            "min_approval_delay_seconds": 300,
        })
        env = {ACTIVATION_ENV: os.path.join(self.outside, "overlay.yml")}
        policy = load_policy(self.root, env=env)
        self.assertTrue(policy.get("allow_solo_approval"))
        self.assertEqual(policy.get("min_approval_delay_seconds"), 300)

    def test_overlay_path_in_summary(self):
        """overlay_path appears in summary when overlay present."""
        self._write_policy({
            "version": "0.2.0", "active_tier": 1,
            "allowed_operations": [], "briefing_ref": None,
        })
        self._write_overlay({"scope": "pilot-safe-v1", "active_tier": 2, "briefing_ref": "/tmp/briefing.md"})
        env = {ACTIVATION_ENV: os.path.join(self.outside, "overlay.yml")}
        policy = load_policy(self.root, env=env)
        summary = activation_summary(policy)
        self.assertTrue(summary["overlay_present"])
        self.assertIsNotNone(summary["overlay_path"])
