"""Wiring guards for the registered read-only Selector subagent (fix C1)."""
import pathlib
import re
import unittest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_AGENT = _ROOT / ".opencode" / "agents" / "selector.md"
_SKILL = _ROOT / ".agents" / "skills" / "selector" / "SKILL.md"


def _frontmatter(text):
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    return match.group(1) if match else ""


class TestSelectorSubagentWiring(unittest.TestCase):
    def test_agent_file_exists_with_subagent_mode(self):
        self.assertTrue(_AGENT.is_file(), f"missing {_AGENT}")
        fm = _frontmatter(_AGENT.read_text(encoding="utf-8"))
        self.assertIn("mode: subagent", fm)
        self.assertIn("description:", fm)

    def test_read_only_permissions_are_configured(self):
        fm = _frontmatter(_AGENT.read_text(encoding="utf-8"))
        self.assertIn('action: "*"', fm)
        self.assertIn("effect: deny", fm)
        self.assertIn("action: read", fm)
        self.assertIn("action: skill", fm)
        self.assertIn('resource: "selector"', fm)
        # The sole write is the audit file under the session convention.
        self.assertIn('resource: "sessions/*/selector-*.md"', fm)
        self.assertIn("action: edit", fm)
        self.assertNotIn("action: shell\n", fm + "\n")

    def test_skill_activation_matches_layer2_default(self):
        text = _SKILL.read_text(encoding="utf-8")
        self.assertNotIn("a curated, ordered list of relevant documents", text)
        self.assertIn("Execution boundary (policy-level)", text)


if __name__ == "__main__":
    unittest.main()
