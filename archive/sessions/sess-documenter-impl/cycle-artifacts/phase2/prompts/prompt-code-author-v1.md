# Role: Code Author — Phase 2 Approval Card contract cycle (impl-run-2026-11-19T16-00-01)

You are the **Code Author** in a sequential TDD cycle. The Test Author already wrote the contract library and the tests. Your job: make `tests/card_contract.py` FULLY conform to the binding spec — audit it line-by-line against the target task and fix every deviation. The tests (a)/(b) groups are green; the 12 (c) anchor tests are RED BY DESIGN (SKILL.md adoption is operator-handled, out-of-cycle) — you cannot and must not make them pass.

## Inputs (read these)
- Binding spec: `/home/ea/council/sessions/sess-documenter-impl/impl-run-2026-11-19T16-00-01/target-task.md` — FULLY. Especially §Deliverables: exact constant values, validator signature and every rule ID with its exact semantics, parser tolerance rules, and `check_approve` semantics.
- Canonical card content: `/home/ea/council/docs/en/documenter-service/impl-guide.md` lines 101–133 (READ-ONLY).
- Current library: `tests/card_contract.py` (in your worktree). Tests (read-only): `tests/test_card_contract.py`, `tests/test_approve_grammar.py`.

## Output (write EXACTLY this file, plus your artifact)
Working directory: `/home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-19T16-00-01`
1. `tests/card_contract.py` — the ONLY file you may edit. Audit against spec and fix deviations. Checklist you must verify explicitly (fix if wrong):
   - `CARD_FIELDS == ["Files","Category","Delta","Classification","Audit","Translations","State"]` (ordered, exact, case-sensitive matching in validator).
   - `REQUIRED_FIELDS == ["Files","Category","Delta","Classification"]`; `MAX_CARD_LINES == 10`.
   - Delta regex: U+2212 (−) before M (NOT hyphen-minus), exact spaces `+N / −M / net ±K`, K sign `±` or `+` or `-`.
   - Translations regex: `<mode> · verified <int> · unverified <int>` with U+00B7 (·) separators; mode = one token without whitespace.
   - `card-audit`: finding when Audit present and value matches clean-ish (`none|clean|0|—` case-insensitive) → must be OMITTED when clean.
   - `card-classification`: head `mechanical|semantic`; bracket allowed ONLY in exact form `[agent proposed: <non-empty>]`.
   - `card-field-order`: present fields must respect CARD_FIELDS relative order.
   - `card-unknown-field`, `card-missing-required`, `card-empty-value`, `card-line-limit` (after stripping leading/trailing blank lines).
   - Tolerance: non-`Label: value` lines ignored; colon inside value does not split fields; labels case-SENSITIVE (e.g. `files:` → unknown-field finding).
   - `check_approve(reply, classification)`: mechanical → bare `approve` True; semantic → bare False, `approve: <non-empty>` True, `approve:`/`approve:   ` False; case-insensitive token, surrounding whitespace tolerated, non-matching prefix False.
   - Module docstring records the two boundary rulings (version bump + changelog = mechanical; glossary term addition = semantic) as agent-judgment guidance, not code.
2. `artifacts/code-files.json`: `{"files": ["tests/card_contract.py"], "signatures": ["CARD_FIELDS", "REQUIRED_FIELDS", "MAX_CARD_LINES", "validate_card", "check_approve"], "audit_findings": ["<spec deviations you fixed, or 'none found'>"]}`.

## Constraints
- You MUST NOT modify the test files. If a test seems wrong, it is NOT yours to change — leave it failing and record the disagreement in `audit_findings` (orchestrator adjudicates).
- Pure stdlib only, no imports beyond `re`/`typing`-style constants; no I/O, no subprocess.
- Zero-trust: exactly one editable target file. ANY other changed path in `git status` (besides `artifacts/code-files.json`) = TASK FAILED (governance incident).
- No git state changes, no commits. Never touch `docs/`, `.agents/`, `tools/`, `CHANGELOGS/`, manifest.
- Keep the file ≤ 450 LOC.

When done, reply with a short summary: deviations found and fixed (or 'none'), and confirm `(a)/(b)` green re-run result.
