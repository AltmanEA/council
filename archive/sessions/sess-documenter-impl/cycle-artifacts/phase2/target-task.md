# Target Task — Phase 2: Approval Card template + approve grammar (machine-checkable contract)

Session: sess-documenter-impl · Run: impl-run-2026-11-19T16-00-01
Source: docs/en/documenter-service/impl-guide.md §Approval Card, §Approve grammar, §Phasing (Phase 2), §Definition of done (prompt part).
Operator command (2026-11-19): «Приступай к фазе 2. Используй субагентов на локальной модели последовательно.»

## Scope split (binding)

Phase 2 is a **prompt part** per the impl-guide allocation matrix (card rendering and
approve grammar are agent judgment; "no machine classifier"). Governance: the
documentation Worker skill file (`.agents/skills/documentation/SKILL.md`) is an
unconditional deny-path for subagents ("forbidden; require explicit operator
handling"). Therefore:

1. **Subagent TDD cycle (this task)** builds the *machine-checkable contract* of the
   Approval Card — the deterministic core of Phase 2's "scripted dry-run" DoD —
   entirely under `tests/` (whitelisted). No new script under `tools/` (OP-2:
   tooling at 3560/3600 LOC; guide: "no new tool is created for it"; no machine
   classifier).
2. **Operator-handled prose part (primary agent, main tree, post-cycle):** adopt the
   fixed template + approve grammar verbatim in SKILL.md §Step-(5) Approve. The
   anchor tests written by this cycle verify that adoption; they are EXPECTED RED
   inside the worktree and must go GREEN in the main tree after the prose sync.

## Deliverables (subagent cycle)

### New file `tests/card_contract.py` (library, no tests in it)
Canonical template constants + a pure parser/validator for rendered card blocks
(no network, no subprocess, no filesystem):

```
CARD_FIELDS = ordered field names, exactly 7, no unknown field allowed:
  Files, Category, Delta, Classification, Audit, Translations, State
REQUIRED_FIELDS = [Files, Category, Delta, Classification]
MAX_CARD_LINES = 10
```

Validator signature: `validate_card(lines: list[str]) -> list[str]` returning a list
of finding strings (empty list = conformant). Findings (rule IDs):
- `card-line-limit` — block exceeds 10 lines.
- `card-unknown-field` — a `Label: value` line with Label outside CARD_FIELDS.
- `card-missing-required` — a required field absent.
- `card-field-order` — present fields not in CARD_FIELDS relative order.
- `card-empty-value` — a present field with empty value.
- `card-category` — Category not in {create, update, delete, split, translation}.
- `card-classification` — Classification head not `mechanical|semantic`, or bracket
  suffix present but not matching the exact form `[agent proposed: <non-empty>]`.
- `card-delta` — Delta not matching `+<int> / −<int> / net [±+-]<int>` (exact spaces,
  U+2212 minus in the −M part).
- `card-translations` — Translations not matching
  `<mode> · verified <int> · unverified <int>` (mode = non-empty token without
  whitespace; U+00B7 separators; M>0 means drift attention — informational only, no finding).
- `card-state` — State not in {final, intermediate}.
- `card-audit` — Audit line present but matches clean-ish patterns
  (`none|clean|0|—` case-insensitive) → must be OMITTED, not rendered clean (silent-when-clean).

Parser tolerance (negative/robustness tests): lines outside the block that are not
`Label: value` form (prose) are ignored by the validator; a colon inside the value
(`agent proposed: ...`) does not create a second field; labels are exact-match,
case-sensitive; leading/trailing blank lines are stripped before counting.

### New file `tests/test_card_contract.py` (unittest)
(a) Unit tests of the validator: conformant 6-line card and conformant 10-line full
card (all 7 fields, override bracket, `State: intermediate`) pass; one targeted
failing case per rule ID above; field-order violation; 11-line violation; prose line
ignored; colon-in-value tolerated; case-sensitive labels rejected; clean-audit
rendering flagged.
(b) **Scripted dry-run of the operating loop** (impl-guide DoD "scripted dry-run"):
render a card from a bundle dict (helper in the test file) for a representative
mechanical bundle — e.g. the real Phase 1 tail shape:
`{files: [docs/en/documenter-service/index.md, docs/ru/documenter-service/index-RU.md,
CHANGELOGS/documenter-service.changes.md, docs-manifest.yaml], category: update,
added: 2, removed: 2, classification: mechanical, audit: clean,
translations: {mode: auto_sync, verified: 78, unverified: 0}}` →
validator returns [] AND audit line is absent AND Translations uses U+00B7
AND card is ≤10 lines AND approval grammar accepts it under a bare `approve`
(via `check_approve` with classification=mechanical). Second dry-run: semantic
bundle → `check_approve` requires `approve: <noun phrase>`.
(c) **Prose-anchor tests** against `.agents/skills/documentation/SKILL.md` resolved
from the repository root via `pathlib.Path(__file__).resolve().parents[1]`
(NOT CWD-dependent): the adopted step-(5) procedure must contain, between the
Step-(5) heading and the next `### ` heading: the fenced card template block whose
field lines match CARD_FIELDS order/labels verbatim; the approve-grammar rules
(bare `approve` for mechanical; `approve: <noun phrase>` for semantic; boundary
rulings version bump + changelog = mechanical, glossary term addition = semantic);
`silent when clean`; `State:` / `final` / `intermediate`; `agent proposed:`;
`Карточка согласования`. Use precise literal substrings, one assertPer rule.

### New file `tests/test_approve_grammar.py` (unittest)
`check_approve(reply: str, classification: str) -> bool` — implemented in
`tests/card_contract.py` (test-adjacent helper; NOT tools/, NOT a classifier):
- classification `mechanical`: bare `approve` → True; `approve: anything` → True.
- classification `semantic`: bare `approve` → False; `approve: <non-empty noun
  phrase>` → True; `approve:` / `approve:   ` (empty object) → False.
- case-insensitive token match; surrounding whitespace tolerated; anything not
  starting with the token → False.
Table-driven unittest over these cases + the two boundary rulings documented in
card_contract docstrings (assertion-free ruling cases are not encoded; the
classification itself remains agent judgment — this helper parses the operator
reply only).

## Whitelist (cycle-enforced, mirrors this section)
```
tests/card_contract.py
tests/test_card_contract.py
tests/test_approve_grammar.py
```

## Forbidden
- Any path outside the whitelist; unconditional deny list stands (docs/, CHANGELOGS/,
  docs-manifest.yaml, .agents/skills/documentation/, tools/, fallback/, defaults/,
  archive/, sessions/, .opencode/, AGENTS.md).
- Existing `tests/test_*.py` and `tests/tools_helpers.py` read-only.
- No commits by subagents. Zero-trust: each role writes EXACTLY its named output
  files; any other changed path = TASK FAILED (governance incident).
- No new files under `tools/`. No edits to `.agents/skills/` (either skill).

## Test command (Level 0)
```
python3 -m unittest tests.test_card_contract tests.test_approve_grammar -v
```
Full-suite regression (orchestrator, post-merge, main tree): all 11 modules.

## Anti-reversed-TDD baseline
Before implementation all new tests must FAIL (import error counts). Recorded by
orchestrator.

## Pass verdict
Level 0 script: exit_code == 0 on the cycle test command, pass-count grew across
iterations, signature grep (CARD_FIELDS, validate_card, check_approve, and each
rule ID string present in the code files), path-gate PASS. Anchor tests are the
documented exception: they are allowed to remain red ONLY on SKILL.md content
(reason recorded) while (a)/(b) are green; final green is verified by the
orchestrator in the main tree after the SKILL.md sync.

## Operator-handled part (out of cycle, primary agent, main tree, same changeset)
Rewrite SKILL.md §Step-(5) Approve procedure to adopt verbatim from impl-guide:
- fixed 7-field template block (labels/order exactly as CARD_FIELDS), ≤10 lines;
- override bracket `[agent proposed: <original>]` only on operator override;
- Audit omitted when clean (silent-when-clean); Translations line only when a
  translation is involved; State only for staged work;
- approve grammar (a)–(d) incl. boundary rulings; classification always a labeled
  card field, never buried in prose; operator may override;
- terminology: Approval Card / Карточка согласования; never "Operator Surface".
Then: full tests/ suite green in main tree (anchors green); scripted dry-run re-run;
commit as feat(implementation); docs/ tail (index.md card reference) → Documentation
Worker with operator approve.
