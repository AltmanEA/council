"""Table-driven unit tests for check_approve — approve grammar contract.

Table-driven unittest over check_approve cases from the target-task spec.
Tests each (reply, classification, expected) tuple independently.

Grammar:
  classification mechanical: bare "approve" → True; "approve: anything" → True.
  classification semantic: bare "approve" → False;
                           "approve: <non-empty noun phrase>" → True;
                           "approve:" / "approve:   " (empty object) → False.
  case-insensitive token match; surrounding whitespace tolerated;
  anything not starting with the token → False.
"""
import unittest

from tests.card_contract import check_approve


# Table of (reply, classification, expected_result) test cases
APPROVE_CASES = [
    # --- mechanical classification ---
    # Bare approve accepted for mechanical
    ("approve", "mechanical", True),
    ("  approve  ", "mechanical", True),  # surrounding whitespace tolerated
    ("APPROVE", "mechanical", True),  # case-insensitive
    ("Approve", "mechanical", True),  # mixed case
    ("  APPROVE  ", "mechanical", True),  # case-insensitive + whitespace

    # approve: anything accepted for mechanical
    ("approve: yes", "mechanical", True),
    ("approve: confirmed", "mechanical", True),
    ("approve: anything at all", "mechanical", True),
    ("APPROVE: YES", "mechanical", True),  # case-insensitive
    ("  approve:  details  ", "mechanical", True),  # whitespace around colon value

    # approve: with empty object also accepted for mechanical
    ("approve:", "mechanical", True),
    ("approve:   ", "mechanical", True),

    # --- semantic classification ---
    # Bare approve rejected for semantic
    ("approve", "semantic", False),
    ("  approve  ", "semantic", False),  # whitespace around token still bare
    ("APPROVE", "semantic", False),  # case-insensitive still bare

    # approve: <non-empty noun phrase> accepted for semantic
    ("approve: rewrite of the Safety section", "semantic", True),
    ("approve: glossary update", "semantic", True),
    ("approve: add term to glossary", "semantic", True),
    ("approve: safety rewrite", "semantic", True),
    ("  approve: rewrite  ", "semantic", True),  # whitespace around value

    # approve: with empty object rejected for semantic
    ("approve:", "semantic", False),
    ("approve:   ", "semantic", False),
    ("approve:  ", "semantic", False),

    # --- case-insensitive matching ---
    # Any non-approve token → False
    ("approved", "mechanical", False),  # prefix match, not exact token
    ("approving", "mechanical", False),
    ("approve-me", "mechanical", False),
    ("disapprove", "mechanical", False),
    ("yes", "mechanical", False),
    ("approve", "unknown-classification", False),  # unknown classification → False

    # --- reply not starting with approve token ---
    ("no", "mechanical", False),
    ("ok", "mechanical", False),
    ("approve: yes no", "mechanical", True),  # first token is approve → still True for mechanical
    ("", "mechanical", False),  # empty string
    ("   ", "mechanical", False),  # whitespace only

    # --- semantic edge cases ---
    ("approve: x", "semantic", True),  # single-char object accepted
    ("approve: a very long noun phrase with many words", "semantic", True),
]


class TestApproveGrammar(unittest.TestCase):
    """Table-driven tests over check_approve(reply, classification) cases."""

    def test_all_table_cases(self):
        """Every (reply, classification, expected) tuple in the table is verified."""
        for reply, classification, expected in APPROVE_CASES:
            result = check_approve(reply, classification)
            self.assertEqual(
                result,
                expected,
                (
                    f"check_approve({reply!r}, {classification!r}) = {result}, "
                    f"expected {expected}"
                ),
            )

    def test_mechanical_bare_approve_cases(self):
        """All bare-approve cases for mechanical classification return True."""
        for reply, _cls, expected in APPROVE_CASES:
            if _cls == "mechanical" and reply.strip() == "approve":
                self.assertTrue(
                    check_approve(reply, "mechanical"),
                    f"Bare approve should be accepted for mechanical: {reply!r}",
                )

    def test_mechanical_approve_with_colon_cases(self):
        """All 'approve: ...' cases for mechanical classification return True."""
        for reply, _cls, expected in APPROVE_CASES:
            if _cls == "mechanical" and reply.strip().lower().startswith("approve:"):
                self.assertTrue(
                    check_approve(reply, "mechanical"),
                    f"approve: <anything> should be accepted for mechanical: {reply!r}",
                )

    def test_semantic_bare_approve_rejected(self):
        """All bare-approve cases for semantic classification return False."""
        for reply, _cls, expected in APPROVE_CASES:
            if _cls == "semantic" and reply.strip() == "approve":
                self.assertFalse(
                    check_approve(reply, "semantic"),
                    f"Bare approve should be rejected for semantic: {reply!r}",
                )

    def test_semantic_approve_with_object_accepted(self):
        """All 'approve: <non-empty>' cases for semantic classification return True."""
        for reply, _cls, expected in APPROVE_CASES:
            if _cls == "semantic" and reply.strip().lower().startswith("approve:"):
                stripped_obj = reply.strip().split(":", 1)[1].strip()
                if stripped_obj:
                    self.assertTrue(
                        check_approve(reply, "semantic"),
                        f"approve: <object> should be accepted for semantic: {reply!r}",
                    )

    def test_semantic_approve_empty_object_rejected(self):
        """approve: with empty/whitespace-only object for semantic returns False."""
        for empty_reply in ["approve:", "approve:  ", "approve:   "]:
            self.assertFalse(
                check_approve(empty_reply, "semantic"),
                f"Empty object should be rejected for semantic: {empty_reply!r}",
            )

    def test_non_approve_token_rejected(self):
        """Anything not starting with 'approve' token returns False."""
        for reply, _cls, expected in APPROVE_CASES:
            if expected is False and reply.strip():
                if not reply.strip().lower().startswith("approve"):
                    self.assertFalse(
                        check_approve(reply, _cls),
                        f"Non-approve token should be rejected: {reply!r} ({_cls})",
                    )


if __name__ == "__main__":
    unittest.main()
