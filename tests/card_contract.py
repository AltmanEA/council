"""Approval Card template contract — pure-Python library.

Canonical template constants and a deterministic parser/validator for
rendered Approval Card blocks.  No network, subprocess, or filesystem access.

Rule IDs and their meanings:
  card-line-limit      — block exceeds 10 lines
  card-unknown-field   — a Label: value line with Label outside CARD_FIELDS
  card-missing-required — a required field absent
  card-field-order     — present fields not in CARD_FIELDS relative order
  card-empty-value     — a present field with empty value
  card-category        — Category not in {create, update, delete, split, translation}
  card-classification  — Classification head not mechanical/semantic, or
                         bracket suffix not matching [agent proposed: <non-empty>]
  card-delta           — Delta not matching the required format (see below)
  card-translations    — Translations not matching the required format
  card-state           — State not in {final, intermediate}
  card-audit           — Audit line present with clean-ish value (silent-when-clean)

Unicode literals (copy-paste, do NOT substitute):
  U+2212 (−) — minus sign used in Delta (−<int>), NOT ASCII hyphen-minus
  U+00B7 (·) — middle dot used in Translations separators, NOT ASCII asterisk
  U+00B1 (±) — plus-minus sign allowed as net sign in Delta

Parser tolerance (negative/robustness):
  - Lines outside the block that are not Label: value form (prose) are ignored.
  - A colon inside the value (e.g. "agent proposed: ...") does not create a second field.
  - Labels are exact-match, case-sensitive.
  - Leading/trailing blank lines are stripped before counting.

Approved Grammar (check_approve):
  - classification mechanical: bare "approve" → True; "approve: anything" → True.
  - classification semantic: bare "approve" → False; "approve: <non-empty noun phrase>" → True.
  - Boundary rulings (agent-judgment guidance, not code):
      version bump + changelog = mechanical
      glossary term addition = semantic
"""
import re

# ---------------------------------------------------------------------------
# Canonical template constants
# ---------------------------------------------------------------------------

CARD_FIELDS = [
    "Files",
    "Category",
    "Delta",
    "Classification",
    "Audit",
    "Translations",
    "State",
]

REQUIRED_FIELDS = ["Files", "Category", "Delta", "Classification"]

MAX_CARD_LINES = 10

# Set of all allowed field labels
_ALLOWED_FIELDS = frozenset(CARD_FIELDS)

_VALID_CATEGORIES = frozenset(["create", "update", "delete", "split", "translation"])

_VALID_STATES = frozenset(["final", "intermediate"])

# Classification heads (without optional bracket suffix)
_VALID_CLASS_HEADS = frozenset(["mechanical", "semantic"])

# Clean-ish patterns that indicate no audit finding (silent-when-clean).
# When present, the Audit line MUST be omitted, not rendered with these values.
_CLEAN_AUDIT_RE = re.compile(
    r"^(?:none|clean|0|\u2014)$",  # \u2014 = em dash —
    re.IGNORECASE,
)

# Delta pattern:
#   +<int> / \u2212<int> / net <sign><int>
# where \u2212 (U+2212, MINUS SIGN) is mandatory before M,
# and the net sign is \u00b1 (U+00B1, PLUS-MINUS) or ASCII + or -.
_DELTA_RE = re.compile(
    r"^\+\d+ / \u2212\d+ / net [\u00b1+-]\d+$"
)

# Translations format:
#   "<mode> \u00b7 verified <N> \u00b7 unverified <M>"
# mode = non-empty token without whitespace
# U+00B7 separators
_TRANSLATIONS_RE = re.compile(
    r"^[^\s]+ \u00b7 verified \d+ \u00b7 unverified \d+$"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_label_value(line):
    """Return (label, value) for a 'Label: value' line, or None if not matching.

    Only the FIRST colon is used as the separator.  A colon inside the value
    (e.g. "agent proposed: ...") does NOT create a second field.
    Labels are case-sensitive.
    """
    idx = line.find(":")
    if idx <= 0:
        return None
    label = line[:idx]
    value = line[idx + 1:].strip()
    return (label, value)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_card(lines):
    """Validate a rendered Approval Card block.

    Parameters
    ----------
    lines : list[str]
        Lines of the card block (already stripped of leading/trailing blank lines).

    Returns
    -------
    list[str]
        List of finding strings (empty = conformant).  Each element is the rule ID
        of the violation.  Duplicates may appear for multiple violations of the same
        rule (e.g. two required fields missing), but each test case typically triggers
        at most one violation.
    """
    findings = []

    # Strip leading/trailing blank lines before counting (spec: "stripped before counting")
    stripped = list(lines)
    while stripped and stripped[0].strip() == "":
        stripped.pop(0)
    while stripped and stripped[-1].strip() == "":
        stripped.pop()

    # --- card-line-limit (rule ID) ---
    if len(stripped) > MAX_CARD_LINES:
        findings.append("card-line-limit")

    # Parse labels from stripped lines
    parsed = {}  # label -> value (first occurrence wins)
    for line in stripped:
        parsed_line = _parse_label_value(line)
        if parsed_line is None:
            continue  # prose / non-label line, ignored by tolerance rules
        label, value = parsed_line
        if label not in parsed:
            parsed[label] = value

    # --- card-unknown-field (rule ID) ---
    for label in parsed:
        if label not in _ALLOWED_FIELDS:
            findings.append("card-unknown-field")
            break  # report once per card

    # --- card-missing-required (rule ID) ---
    for req in REQUIRED_FIELDS:
        if req not in parsed:
            findings.append("card-missing-required")
            break  # report once per card

    # --- card-field-order (rule ID) ---
    # Check that present required fields appear in CARD_FIELDS order.
    if len(parsed) > 1:
        present_in_order = []
        for field in CARD_FIELDS:
            if field in parsed:
                present_in_order.append(field)
        # Check that present fields don't appear in wrong relative order
        for i in range(len(present_in_order)):
            for j in range(i + 1, len(present_in_order)):
                # present_in_order is already in CARD_FIELDS order by construction
                # We need to check the INPUT order, not CARD_FIELDS order
                pass
        # Actually we need to check the order in the INPUT, not in CARD_FIELDS.
        # Re-check: extract the order from the input lines.
        present_input_order = []
        for line in stripped:
            pl = _parse_label_value(line)
            if pl is None:
                continue
            lbl, _ = pl
            if lbl in _ALLOWED_FIELDS and lbl not in present_input_order:
                present_input_order.append(lbl)
        # Verify relative order
        for i in range(len(present_input_order)):
            for j in range(i + 1, len(present_input_order)):
                idx_i = CARD_FIELDS.index(present_input_order[i])
                idx_j = CARD_FIELDS.index(present_input_order[j])
                if idx_i > idx_j:
                    findings.append("card-field-order")
                    break
            else:
                continue
            break

    # --- card-empty-value (rule ID) ---
    for label, value in parsed.items():
        if label in _ALLOWED_FIELDS and value == "":
            findings.append("card-empty-value")
            break

    # --- card-category (rule ID) ---
    if "Category" in parsed:
        cat_val = parsed["Category"].strip()
        if cat_val not in _VALID_CATEGORIES:
            findings.append("card-category")

    # --- card-classification (rule ID) ---
    if "Classification" in parsed:
        cls_val = parsed["Classification"].strip()
        # Check head (before bracket suffix)
        head = cls_val
        bracket_match = re.match(r"^(mechanical|semantic)(\s+\[.*)?$", cls_val)
        if bracket_match:
            head = bracket_match.group(1)
            bracket_part = bracket_match.group(2)
            if bracket_part:
                # Must match [agent proposed: <non-empty>]
                bm = re.match(r"^\s*\[agent proposed: (.+)\]$", bracket_part)
                if not bm:
                    findings.append("card-classification")
        else:
            findings.append("card-classification")

    # --- card-delta (rule ID) ---
    if "Delta" in parsed:
        delta_val = parsed["Delta"].strip()
        if not _DELTA_RE.match(delta_val):
            findings.append("card-delta")

    # --- card-translations (rule ID) ---
    if "Translations" in parsed:
        trans_val = parsed["Translations"].strip()
        if not _TRANSLATIONS_RE.match(trans_val):
            findings.append("card-translations")
        else:
            # M > 0 is informational only, no finding (per spec)
            pass

    # --- card-state (rule ID) ---
    if "State" in parsed:
        state_val = parsed["State"].strip()
        if state_val not in _VALID_STATES:
            findings.append("card-state")

    # --- card-audit (rule ID) ---
    if "Audit" in parsed:
        audit_val = parsed["Audit"].strip()
        if _CLEAN_AUDIT_RE.match(audit_val):
            findings.append("card-audit")

    return findings


def check_approve(reply, classification):
    """Validate the operator's approval reply against the classify-approve grammar.

    Parameters
    ----------
    reply : str
        The operator's reply text.
    classification : str
        One of "mechanical" or "semantic".

    Returns
    -------
    bool
        True if the reply is a valid approval for the given classification.

    Grammar:
      mechanical — bare "approve" → True; "approve: anything" → True.
      semantic   — bare "approve" → False; "approve: <non-empty noun phrase>" → True.
                   "approve:" or "approve:   " (empty object) → False.
      Case-insensitive token match; surrounding whitespace tolerated.
      Anything not starting with the token "approve" → False.

    Boundary rulings (documented, not encoded — classification itself remains
    agent judgment):
      version bump + changelog = mechanical
      glossary term addition = semantic
    """
    reply_stripped = reply.strip()
    # Tokenize: first word (before colon or whitespace) must be "approve"
    # e.g. "approve: yes" → first word is "approve:" → strip ":" → "approve"
    first_word = reply_stripped.split(None, 1)[0] if reply_stripped else ""
    first_token = first_word.rstrip(":")
    if not first_token or first_token.lower() != "approve":
        return False

    if classification.lower() == "mechanical":
        # Bare approve or approve: anything → True
        return True

    if classification.lower() == "semantic":
        # Must have a non-empty object after the approve token
        if len(reply_stripped.split(None, 1)) < 2:
            return False
        # Extract the rest after the first token
        rest = reply_stripped.split(None, 1)[1]
        obj = rest.lstrip(":").strip()
        if not obj:
            return False
        return True

    # Unknown classification — reject
    return False
