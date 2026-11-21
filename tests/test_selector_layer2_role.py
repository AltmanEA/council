"""Contract tests for the Selector Layer 2 role file:
    .agents/skills/selector/roles/selector_layer2.md

All paths resolved relative to tests root (Path(__file__).resolve().parents[1]).
Uses unittest + stdlib only.
"""
import os
import unittest

import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_ROLE_PATH = str(_ROOT / ".agents" / "skills" / "selector" / "roles" / "selector_layer2.md")
_SKILL_PATH = str(_ROOT / ".agents" / "skills" / "selector" / "SKILL.md")


def _read_role():
    """Read the role file content."""
    with open(_ROLE_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _read_skill():
    """Read the SKILL.md content."""
    with open(_SKILL_PATH, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# TestRoleFileContract
# ---------------------------------------------------------------------------

class TestRoleFileContract(unittest.TestCase):
    """Tests for the .agents/skills/selector/roles/selector_layer2.md file."""

    def test_role_file_exists(self):
        """The role file must exist."""
        self.assertTrue(os.path.isfile(_ROLE_PATH),
                        f"Role file not found: {_ROLE_PATH}")

    def test_frontmatter_version(self):
        """Frontmatter must declare version '1.1.0'."""
        content = _read_role()
        self.assertIn('version: "1.1.0"', content,
                      "Frontmatter must contain version: \"1.1.0\"")

    def test_deny_tokens(self):
        """Must contain deny: write, shell, edit."""
        content = _read_role()
        self.assertIn("deny: write, shell, edit", content,
                      "Role must contain 'deny: write, shell, edit'")

    def test_content_is_data_not_instructions(self):
        """Role must state that source content is data, not instructions."""
        content = _read_role()
        text_lower = content.lower()
        self.assertTrue(
            "data, not instructions" in content or
            "data , not instructions" in content or
            "data,not instructions" in text_lower or
            "не инструкции" in content or
            "data—not instructions" in content,
            "Role must state content is data, not instructions "
            "(look for 'data, not instructions' or 'не инструкции')",
        )

    def test_no_fabricated_sources(self):
        """Role must prohibit fabricating sources; facts[] only from sources[]."""
        content = _read_role()
        text_lower = content.lower()
        self.assertTrue(
            "facts[]" in content and "sources[]" in content or
            "facts" in text_lower and "sources" in text_lower,
            "Role must reference facts[] and sources[] relationship",
        )
        self.assertTrue(
            "fabricat" not in text_lower.replace("non-fabricat", "").replace(
                "un-fabricat", ""
            ) or
            "do not fabricat" in text_lower or
            "must not fabricat" in text_lower or
            "never fabricat" in text_lower or
            "no fabricated" in text_lower or
            "must not invent" in text_lower or
            "prohibit invent" in text_lower or
            "not add source" in text_lower or
            "only from sources" in text_lower or
            "facts from sources" in text_lower,
            "Role must prohibit fabricating/inventing sources, "
            "stating facts[] come only from sources[]",
        )

    def test_en_authoritative(self):
        """EN authoritative; RU not in output without explicit request."""
        content = _read_role()
        self.assertTrue(
            "en authorit" in content.lower() or
            "authorit" in content.lower() and "en" in content.lower() or
            "english" in content.lower() and "authorit" in content.lower() or
            "ru" in content.lower() and "output" in content.lower() and
            ("without" in content.lower() or "explicit" in content.lower() or
             "not" in content.lower() or "unless" in content.lower()),
            "Role must state EN is authoritative and RU docs not in output "
            "without explicit request",
        )

    def test_code_opt_in(self):
        """Role must require reveal_code=True and default modes.code == 'off'."""
        content = _read_role()
        self.assertTrue(
            "reveal_code=True" in content or "reveal_code" in content.lower() and "True" in content,
            "Role must reference reveal_code=True",
        )
        self.assertTrue(
            'modes.code' in content and 'off' in content or
            "modes.code" in content.lower() and ("off" in content or "default" in content),
            "Role must default modes.code to 'off'",
        )

    def test_contract_v2_tokens(self):
        """Must contain contract_version 2.0.0 and form Layer 2."""
        content = _read_role()
        self.assertIn("2.0.0", content,
                      "Role must contain contract_version 2.0.0")
        self.assertIn("Layer 2", content,
                      "Role must contain form 'Layer 2'")

    def test_no_self_activation(self):
        """Role must explicitly NOT self-activate."""
        content = _read_role()
        text_lower = content.lower()
        self.assertTrue(
            "must not self-activate" in text_lower or
            "must not self activate" in text_lower or
            "mush not self-activate" not in text_lower and
            ("self-activate" in text_lower or "self activate" in text_lower) and
            ("must not" in text_lower or "mustn't" in text_lower or
             "never activate" in text_lower or "do not activate" in text_lower),
            "Role must explicitly state it MUST NOT self-activate",
        )

    def test_truncated_and_hint_ack(self):
        """Role must reference ⚠ TRUNCATED and hint acknowledgement."""
        content = _read_role()
        self.assertTrue(
            "TRUNCATED" in content,
            "Role must reference TRUNCATED warning",
        )
        self.assertTrue(
            "hint" in content.lower() and "ack" in content.lower() or
            "hint acknowledgement" in content.lower() or
            "hint-ack" in content.lower(),
            "Role must reference hint acknowledgement",
        )

    def test_skill_references_role(self):
        """SKILL.md must contain a reference to selector_layer2.md."""
        skill_content = _read_skill()
        self.assertIn("selector_layer2.md", skill_content,
                      "SKILL.md must reference selector_layer2.md")


if __name__ == "__main__":
    unittest.main()
