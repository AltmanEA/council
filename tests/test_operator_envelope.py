"""Unit tests for operator_ingress.core.envelope (Step 2 — Error envelope + lookup table + deferred stubs).

Acceptance criteria (target-task.md, plan Step 2):
  - 12 registry codes each have CODE_TABLE entry with non-empty str message AND
    non-empty str action (at least one space-separated word — human text);
  - error_envelope returns dict with exactly {code, message, action} keys
    (superset-of-three when overrides add fields; no overrides → exactly those three);
  - unknown code → ValueError; canary secret via overrides never in envelope values;
  - 6 deferred-tool stubs: valid envelope, code class CONFIG., message+action free
    of banned plan terms, action names ≥1 available tool;
  - deferred_response("council.status") → ValueError; deferred_response("bogus") → ValueError;
  - is_envelope: True for valid, False for missing key / non-str value / non-dict.
"""
from __future__ import annotations

import unittest

# ---------------------------------------------------------------------------
# Canary for leakage test
# ---------------------------------------------------------------------------

_CANARY_SECRET = "CANARY_SECRET_DO_NOT_LEAK_9f8e7d6c5b4a3"

# ---------------------------------------------------------------------------
# Registry codes expected in CODE_TABLE
# ---------------------------------------------------------------------------

_REGISTRY_CODES = [
    "VAL.001",
    "VAL.002",
    "VAL.003",
    "VAL.004",
    "VAL.005",
    "IO.001",
    "IO.002",
    "IO.003",
    "IO.004",
    "IO.999",
    "CONFIG.001",
    "CONFIG.002",
]

# ---------------------------------------------------------------------------
# Available tools that deferred-action text must reference (substring check)
# ---------------------------------------------------------------------------

_AVAILABLE_TOOLS = [
    "council.submit_task",
    "council.status",
    "council.list_sessions",
    "documenter.audit",
]

# ---------------------------------------------------------------------------
# Banned plan terms (case-insensitive) in deferred message+action
# ---------------------------------------------------------------------------

_BANNED_TERMS = ["phase 2", "p3", "step "]

# ---------------------------------------------------------------------------
# 6 deferred tools
# ---------------------------------------------------------------------------

_DEFERRED_TOOLS = [
    "council.get_artifacts",
    "council.resolve_escalation",
    "council.override_precheck",
    "documenter.delegate",
    "documenter.approve",
    "documenter.override_gate",
]

# ---------------------------------------------------------------------------
# Import the module under test — must fail before implementation exists
# ---------------------------------------------------------------------------

try:
    from operator_ingress.core.envelope import (  # noqa: F401
        CODE_TABLE,
        deferred_response,
        error_envelope,
        is_envelope,
    )
except ImportError as _import_err:
    _import_err  # silence unused-variable


class TestCodeTableCompleteness(unittest.TestCase):
    """Every registry code has a CODE_TABLE entry with non-empty message and action."""

    def test_all_codes_registered(self):
        for code in _REGISTRY_CODES:
            self.assertIn(code, CODE_TABLE)

    def test_all_codes_non_empty_message(self):
        for code in _REGISTRY_CODES:
            msg, _ = CODE_TABLE[code]
            self.assertIsInstance(msg, str, f"{code} message not str")
            self.assertGreater(len(msg.strip()), 0, f"{code} message empty")

    def test_all_codes_non_empty_action(self):
        for code in _REGISTRY_CODES:
            _, action = CODE_TABLE[code]
            self.assertIsInstance(action, str, f"{code} action not str")
            self.assertGreater(len(action.strip()), 0, f"{code} action empty")

    def test_all_actions_have_human_words(self):
        for code in _REGISTRY_CODES:
            _, action = CODE_TABLE[code]
            words = action.split()
            self.assertGreaterEqual(len(words), 2,
                                    f"{code} action must contain ≥2 words")


class TestErrorEnvelopeBasic(unittest.TestCase):
    """error_envelope returns dict with code/message/action."""

    def test_envelope_has_code(self):
        env = error_envelope("VAL.001")
        self.assertIn("code", env)
        self.assertEqual(env["code"], "VAL.001")

    def test_envelope_has_message(self):
        env = error_envelope("VAL.001")
        self.assertIn("message", env)
        self.assertIsInstance(env["message"], str)

    def test_envelope_has_action(self):
        env = error_envelope("VAL.001")
        self.assertIn("action", env)
        self.assertIsInstance(env["action"], str)

    def test_envelope_exactly_three_keys_no_overrides(self):
        env = error_envelope("VAL.001")
        self.assertEqual(set(env.keys()), {"code", "message", "action"})


class TestErrorEnvelopeOverrides(unittest.TestCase):
    """Overrides add fields; code/message/action always present."""

    def test_override_adds_extra_field(self):
        env = error_envelope("VAL.001", extra="value")
        self.assertIn("code", env)
        self.assertIn("message", env)
        self.assertIn("action", env)
        self.assertIn("extra", env)
        self.assertEqual(env["extra"], "value")

    def test_override_does_not_remove_standard(self):
        env = error_envelope("VAL.001", foo="bar")
        self.assertEqual(env["code"], "VAL.001")
        self.assertIsInstance(env["message"], str)
        self.assertIsInstance(env["action"], str)

    def test_cannot_override_code(self):
        """Overrides that try to replace code/message/action are ignored or rejected."""
        env = error_envelope("VAL.001", code="OVERRIDE")
        self.assertEqual(env["code"], "VAL.001")

    def test_envelope_superset_of_three(self):
        env = error_envelope("VAL.001", a=1, b=2, c=3)
        self.assertTrue({"code", "message", "action"}.issubset(set(env.keys())))


class TestErrorEnvelopeUnknownCode(unittest.TestCase):
    """Unknown code → ValueError."""

    def test_unknown_code_raises_value_error(self):
        with self.assertRaises(ValueError):
            error_envelope("FAKE.999")

    def test_unknown_code_canary(self):
        with self.assertRaises(ValueError):
            error_envelope("FAKE.999", secret=_CANARY_SECRET)


class TestErrorEnvelopeCanaryLeakage(unittest.TestCase):
    """Canary secret never appears in any envelope value."""

    def test_canary_not_in_envelope_values(self):
        env = error_envelope("VAL.001", canary=_CANARY_SECRET)
        for value in env.values():
            self.assertNotIn(_CANARY_SECRET, str(value))

    def test_canary_not_in_envelope_keys(self):
        env = error_envelope("VAL.001", canary=_CANARY_SECRET)
        for key in env.keys():
            self.assertNotIn(_CANARY_SECRET, str(key))


class TestDeferredResponseValidTools(unittest.TestCase):
    """All 6 deferred tools return valid CONFIG.001 envelopes."""

    def test_all_deferred_tools_return_valid_envelope(self):
        for tool in _DEFERRED_TOOLS:
            env = deferred_response(tool)
            self.assertIsInstance(env, dict)
            self.assertIn("code", env)
            self.assertIn("message", env)
            self.assertIn("action", env)
            self.assertTrue(env["code"].startswith("CONFIG."))

    def test_all_deferred_messages_no_banned_terms(self):
        for tool in _DEFERRED_TOOLS:
            env = deferred_response(tool)
            combined = (env["message"] + " " + env["action"]).lower()
            for term in _BANNED_TERMS:
                self.assertNotIn(term, combined,
                                 f"{tool}: banned term {term!r} found")

    def test_all_deferred_actions_name_available_tool(self):
        """Each deferred action text names at least one available tool (substring)."""
        for tool in _DEFERRED_TOOLS:
            env = deferred_response(tool)
            action = env["action"]
            found = any(name in action for name in _AVAILABLE_TOOLS)
            self.assertTrue(found,
                            f"{tool} action must name an available tool; "
                            f"got: {action!r}")

    def test_canary_not_in_deferred_envelope(self):
        """Defensive: canary secret via overrides never leaks."""
        env = deferred_response(_DEFERRED_TOOLS[0], secret=_CANARY_SECRET)
        for value in env.values():
            self.assertNotIn(_CANARY_SECRET, str(value))


class TestDeferredResponseInvalid(unittest.TestCase):
    """Unknown tool_name or known non-deferred tool → ValueError."""

    def test_unknown_tool_raises_value_error(self):
        with self.assertRaises(ValueError):
            deferred_response("bogus.tool")

    def test_council_status_not_deferred(self):
        """council.status is an MVP tool, NOT deferred."""
        with self.assertRaises(ValueError):
            deferred_response("council.status")


class TestIsEnvelope(unittest.TestCase):
    """is_envelope returns True for valid, False otherwise."""

    def test_valid_envelope_is_envelope(self):
        env = error_envelope("VAL.001")
        self.assertTrue(is_envelope(env))

    def test_missing_code_key(self):
        self.assertFalse(is_envelope({"message": "x", "action": "y"}))

    def test_missing_message_key(self):
        self.assertFalse(is_envelope({"code": "VAL.001", "action": "y"}))

    def test_missing_action_key(self):
        self.assertFalse(is_envelope({"code": "VAL.001", "message": "x"}))

    def test_non_str_message(self):
        self.assertFalse(is_envelope({"code": "VAL.001",
                                       "message": 42,
                                       "action": "y"}))

    def test_non_str_action(self):
        self.assertFalse(is_envelope({"code": "VAL.001",
                                       "message": "x",
                                       "action": None}))

    def test_non_str_code(self):
        self.assertFalse(is_envelope({"code": None,
                                       "message": "x",
                                       "action": "y"}))

    def test_non_dict(self):
        self.assertFalse(is_envelope("not a dict"))
        self.assertFalse(is_envelope(["code", "message", "action"]))
        self.assertFalse(is_envelope(None))


# ---------------------------------------------------------------------------
# Coverage-gap (iter 2): deferred message must be honest, not CONFIG.001 leak
# ---------------------------------------------------------------------------


class TestDeferredMessageHonesty(unittest.TestCase):
    """Each deferred tool's message must mention the tool, state non-availability,
    and must NOT claim a config/credential problem."""

    _CONFIG_LEAK_TERMS = ["api key", "credential", "configuration"]

    def test_message_mentions_tool_name(self):
        """Message must contain the tool's short name (part after dot)."""
        for tool in _DEFERRED_TOOLS:
            env = deferred_response(tool)
            short_name = tool.rsplit(".", 1)[-1]
            self.assertIn(short_name, env["message"].lower(),
                          f"{tool}: message must mention '{short_name}'")

    def test_message_states_non_availability(self):
        """Message must honestly say the tool is not available / not implemented."""
        phrases = ["not available", "not yet available", "not implemented"]
        for tool in _DEFERRED_TOOLS:
            env = deferred_response(tool)
            lower_msg = env["message"].lower()
            found = any(ph in lower_msg for ph in phrases)
            self.assertTrue(found,
                            f"{tool}: message must state non-availability; "
                            f"got: {env['message']!r}")

    def test_message_no_config_leak(self):
        """Message must NOT claim a config/credential problem (the old CONFIG.001 leak)."""
        for tool in _DEFERRED_TOOLS:
            env = deferred_response(tool)
            lower_msg = env["message"].lower()
            for term in self._CONFIG_LEAK_TERMS:
                self.assertNotIn(term, lower_msg,
                                 f"{tool}: message must not contain '{term}'; "
                                 f"got: {env['message']!r}")

    def test_deferred_invariants_still_hold(self):
        """Re-assert: CONFIG. prefix, envelope shape, banned terms, action names."""
        for tool in _DEFERRED_TOOLS:
            env = deferred_response(tool)
            self.assertIsInstance(env, dict)
            self.assertIn("code", env)
            self.assertIn("message", env)
            self.assertIn("action", env)
            self.assertTrue(env["code"].startswith("CONFIG."))
            combined = (env["message"] + " " + env["action"]).lower()
            for term in _BANNED_TERMS:
                self.assertNotIn(term, combined,
                                 f"{tool}: banned term {term!r} in message+action")
            found_tool = any(name in env["action"] for name in _AVAILABLE_TOOLS)
            self.assertTrue(found_tool,
                            f"{tool}: action must name an available tool; "
                            f"got: {env['action']!r}")


if __name__ == "__main__":
    unittest.main()
