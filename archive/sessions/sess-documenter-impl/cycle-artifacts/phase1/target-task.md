# Target Task — Phase 1: `phase4-*` write-gates in `check_drift.py` + displacement of `check_parity.py` + Contract column

Run: impl-run-2026-11-19T14-30-02
Source: `docs/en/documenter-service/impl-guide.md` §Deterministic core (check_drift entry),
§OP-2 ceiling compliance (Recorded displacement), §Phasing Phase 1, §Translation pipeline split.

## Goal

1. Extend `tools/check_drift.py` with a deterministic Phase-4 translation write-gate mode:
   four rule IDs evaluated in code — `phase4-fail`, `phase4-parity`, `phase4-identity`,
   `phase4-glossary`. Gate outcomes are produced by code; the agent never re-derives them.
2. Delete `tools/check_parity.py` (29 LOC) — displacement per the recorded decision in the
   guide. Zero code references exist (verified: no py/prose references except docs — handled
   by Documentation Worker separately).
3. `tools/README.md`: remove the `check_parity.py` table row; add a **Contract** column to
   the tool table (prose-contract registry: canonical anchor per tool — README section,
   skill section, or spec clause). Trace note: check_parity displaced-by check_drift
   phase4 rules, date 2026-11-19, reason: guide Phase 1.

## Binding behavioral decisions (tests MUST encode exactly these)

### CLI (new mode, existing drift mode unchanged)
```
python3 tools/check_drift.py --phase4 <en_path> <ru_candidate_path> \
    --report <run_report.json> [--glossary <glossary.md>] [--json]
```
- `--phase4` runs ONLY the four gate rules (not the 13 structural drift rules).
- `--report` is REQUIRED in phase4 mode (missing/absent file → internal error, exit 2).
- `--glossary` default: `<repo_root>/docs/en/glossary/index.md` (repo root = parent of
  the tools/ dir). `--json` same shape as existing: {"rule","severity","file","description"}.
- Exit codes keep this tool's documented convention (unchanged from current drift mode):
  `0` = no findings (all gates pass), `1` = findings present, `2` = internal error
  (unreadable files, malformed report JSON, missing --report). The frozen audit contract
  belongs to check_all.py; check_drift keeps its own documented codes.
- Human rendering: keep current style — one finding line `rule=<id> severity=<sev>
  file=<path> <description>`, then the `coverage:` footer lines. The coverage footer in
  phase4 mode lists the four gate rule IDs under deterministic.
- Existing drift mode (no --phase4) and its exit/rendering behavior MUST NOT change.

### Run report contract (docs/en/translation-project/contract.md §Run report)
JSON object with integer `fail` field (number of lines that failed translation).

### Rule: phase4-fail  (severity high)
- Parse report JSON. `fail` missing/not-int → internal error (exit 2, stderr ERROR).
- `fail > 0` → finding: `rule=phase4-fail ... fail=<n> (expected 0)`.

### Rule: phase4-parity  (severity high)
- 1:1 line parity between EN and RU candidate: `len(en_lines) == len(ru_lines)`; otherwise
  ONE finding `phase4-parity` with `line count: EN=<n>, RU=<m>` and STOP further parity checks
  (no positional comparisons when lengths differ).
- If lengths equal: for every line index i (0-based, both files read whole): line is blank
  or structural in EN **iff** in RU; any
  mismatch → ONE finding `phase4-parity` naming the first 5 divergent 1-based line numbers
  (`structural divergence at lines: ...`). Do not emit per-line findings.
  **AMENDED (iteration 1 live-corpus finding):** structural here is a STRICT notion, not
  `_is_structural` as-is: blank, heading (`#`), hr (`-{3,}`), code-fence line, or TABLE
  SEPARATOR row (`s.startswith('|')` and set(s) ⊆ `{|, -, :, space}`) only. A table BODY
  row (prose cells, possibly containing hyphens in text like "Controlled-file") is NOT
  structural. (Root cause of the live false positive: `_is_structural`'s
  `startswith('|') and '-' in s` heuristic flagged the EN row with hyphenated prose as
  structural while the hyphen-free RU counterpart was not.)

### Rule: phase4-identity  (severity high)
- Body lines = non-blank, non-structural, not metadata (existing `_is_meta_line` with
  docmeta KNOWN_KEYS + `has_translation:`), outside code fences, and not matching Council
  skip-patterns (the five from the skill: `^has_translation:`, `^changelog-path:`,
  `^Abstraction:`, `^references:`, `^allow_non_index_paths:` — treat as metadata anyway;
  keep it simple: exclusion set = structural ∪ metadata).
- Compare positional body lines EN[i] vs RU[i] after strip. ZERO body lines → no finding.
  ALL body lines identical → finding `phase4-identity ... candidate is an EN copy`.
  Partial identity (1..n-1) → NO finding (partial is legitimate: inline-code, numbers).

### Rule: phase4-glossary  (severity high)
- Parse glossary markdown entries: lines of form `**<EN Term>** (<RU equiv>) ...`
  (regex `^\*\*([^*]+)\*\*\s*\(([^)]+)\)`). Terms with parenthetical absent are ignored.
- **AMENDED (iteration 1: document-level scope + stem-prefix match).** For each term that
  occurs in the EN document BODY (whole-file scan, outside code fences AND outside inline
  code spans, case-insensitive whole-word): require the RU candidate WHOLE BODY (same
  exclusions) to contain, case-insensitively, a STEM-PREFIX match for EVERY word of the
  term's RU equivalent: stem = lowercased first 4 chars of the word (full word if shorter),
  matched as a word-start occurrence in the lowercased RU body (regex `\b<stem>`; keep
  hyphens inside words). This tolerates Russian declension AND alternating stems:
  «уровень» vs «уровню/уровней» (stem «уров»), «Фаза» vs «фазы/фазе» (stem «фаз»).
  **AMENDED iteration 2→3: stem length 5 → 4 (5 breaks alternating stems «урове»/«уровн»,
  «фаза»/«фазы»).** A term with ANY RU-equivalent word
  lacking a stem hit is offending. Presence of the bare EN term does NOT satisfy the gate.
  Offending terms → ONE finding `phase4-glossary` listing up to 5 terms
  (`glossary terms untranslated: A, B, ...`). Terms not appearing in EN body are irrelevant.
  NOTE: deterministic approximation; supplements (does not replace) skill rule-3 judgment.
- Scope is DOCUMENT-LEVEL (not per-line): the RU term may appear anywhere in the RU body
  (a translated heading, table cell, or prose line all satisfy the term requirement).

### check_parity.py deletion
- `git rm tools/check_parity.py` equivalent: file must not exist after the cycle.
- No imports of it may appear anywhere (tests must not reference it).

### tools/README.md (implementation file; contract registry)
- Tool table gains a 4th column `Contract` — one canonical anchor per row (existing
  `##` section of README, `SKILL.md §…`, or spec clause). check_drift row's Contract cell
  must mention the phase4 gate rules; check_parity row removed with a trace note line under
  the table: displaced-by, date 2026-11-19, reason (guide Phase 1).

## Acceptance criteria

- New fixtures under `tools/tests/fixtures/check_drift/phase4/`: EN, RU (good, bad-parity,
  bad-identity, bad-glossary), report fixtures (fail0.json, fail2.json, malformed.json),
  mini-glossary.md. Fixture data does not count toward OP-2 LOC.
- New test module `tests/test_check_drift.py` (unittest, subprocess CLI + direct import):
  all four gates pass on good fixture (exit 0, no `rule=phase4-` lines); each gate fails
  in isolation with the other three clean; drift mode regression (exit codes unchanged
  0/1/2 as currently documented); --report missing → exit 2; --json schema holds; parity
  lengths-differ emits ONE finding; identity all-identical vs partial-identical branches;
  glossary: term present in EN + absent both forms in RU → finding; EN term retained in
  RU → no finding; `tools/check_parity.py` absent; README has Contract column and no
  check_parity row.
- Full regression: `tests.test_check_drift`, `tests.test_check_all`,
  `tests.test_check_all_hook_contract`, `tests.test_install_hooks`,
  `tests.test_link_integrity` — all green.
- Live run: `check_drift.py --phase4 docs/en/documenter-service/index.md
  docs/ru/documenter-service/index-RU.md --report <any good report> ` → exit 0
  (the RU mirror was just realigned; if the real corpus surfaces a genuine gate finding,
  report it verbatim — do NOT weaken the rule to pass).

## Allowed paths (whitelist)

- `tools/check_drift.py` (existing, explicitly listed)
- `tools/check_parity.py` (existing, explicitly listed — DELETED in this task)
- `tools/README.md` (existing, explicitly listed)
- `tests/test_check_drift.py` (new)
- `tools/tests/fixtures/check_drift/phase4/**` (new fixture data)
- `.impl/*` (cycle artifacts)

## Forbidden

- `docs/`, `CHANGELOGS/`, `fallback/`, `.agents/`, `defaults/`, `sessions/`, `archive/`
- `tools/docmeta.py`, `tools/tests_helpers.py`, `tools/check_all.py` (read-only)
- Existing `tests/test_*.py` (read-only); no commits. No Tier 2+ markers.

## Test command

`cd <worktree> && python3 -m unittest tests.test_check_drift -v`
(regression set per acceptance criteria)
