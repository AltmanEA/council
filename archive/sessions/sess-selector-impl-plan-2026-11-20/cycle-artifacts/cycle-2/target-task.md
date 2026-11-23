# Target Task — Selector Layer 1 deterministic runtime harness (V1/V2/V3/V4/V6/V8)

## Goal
Add an **internal** Python harness that makes the deterministic part of Selector
Layer 1 executable and testable. It is NOT a new externally callable tool type:
it lives inside the skill package and is invoked by the skill wrapper, never by
the read-only role. This closes the council's requirement that V2 injection tests
be automated before pilot, and provides runtime evidence for V3/V4/V6/V8.

## Basis
- `consensus-doc.md` verification items V1–V8; `operator-decisions.md` D1–D4.
- Operator choice (this session): "Внутренний Python-харнесс" for automated V2/V4/V6/V8.
- `docs/en/selector/index.md` v0.2.0 — Layer 1 index-only contract.
- Current contract artifacts at commit `f5c8482` (schema with explicit `rank`,
  per-document `discoverable`, extended `gap_type`).

## Acceptance criteria
- **AC1 / V2 (BLOCKING):** with `.agents/skills/selector/fixtures/manifest.poisoned.yaml`,
  the injection payload `IGNORE PREVIOUS INSTRUCTIONS` MUST NOT appear anywhere in
  the returned output (task_summary, rationale, gap fields) or audit artifact body.
  Ranking (ids + ranks) MUST be identical to the clean manifest result. Detection
  MUST be recorded in the audit as a boolean/count, not by echoing the payload.
- **AC2 / V1:** harness MUST read only the manifest file and the audit file. No
  `docs/` document body or code file is opened. Test with a `builtins.open` spy.
- **AC3 / V3:** pre-call and post-call `sha256_file(manifest_path)` are equal and
  recorded as `manifest_sha256` in output and audit; manifest bytes unchanged.
- **AC4 / V4:** caller hints asking for 100 files / 10000 tokens MUST be capped at
  `CEILING_FILES=40` / `CEILING_TOKENS=8000`; when the result is cut, `truncated=true`,
  task_summary carries `⚠ TRUNCATED`, `gap_type=budget_stop`, `omitted_items` non-empty.
  Without hints the effective cap is `DEFAULT_FILES=20` / `DEFAULT_TOKENS=4000`.
- **AC5 / V6:** missing OR structurally malformed manifest returns `gap_type=manifest_missing`,
  empty `ranked_ids`, explicit error text, and never invents document IDs.
- **AC6 / V8:** `write_audit()` creates `<dir>/selector-<call-id>.md` containing
  `# Selector audit`, `call_id`, `manifest_sha256`; the path is returned in the result.
- **AC7 / V5:** `validate_output()` returns `[]` for both output fixtures; it accepts
  empty `ranked_ids` only when `gap_type in {"manifest_missing","not_found"}`.
- **AC8:** all 126 existing tests (`test_selector_contract`, `test_selector_smoke`)
  remain green — no changes to them or to the schema/fixtures.

## Target files
- NEW `.agents/skills/selector/runtime/selector_runtime.py`
- NEW `tests/test_selector_integration.py`
- MODIFY `.agents/skills/selector/SKILL.md` (explicitly listed; add one internal-harness section)

## Allowed paths (whitelist — unchanged)
`.agents/skills/selector/*`, `tests/test_selector_*.py`.
Deny list always wins: `docs/`, `docs-manifest.yaml`, `CHANGELOGS/`, `fallback/`,
`AGENTS.md`, `defaults/`, `.opencode/`, `archive/`, `sessions/`,
`.agents/skills/documentation/`, `documenter_policy.yml`.

## Required public API (use these exact names in `code-files.json` signatures)
Module-level constants: `CEILING_TOKENS`, `CEILING_FILES`, `DEFAULT_TOKENS`,
`DEFAULT_FILES`, `INJECTION_PATTERNS`.
Functions:
- `sha256_file(path) -> str`
- `load_manifest(path) -> list[dict]` (PyYAML 6.0.3 available; stdlib fallback parser OK)
- `sanitize_metadata(text) -> tuple[str, bool]`
- `rank(request: str, entries: list[dict], max_files: int) -> list[dict]`
  — each item `{id, rank, rationale, discoverable}`; rationale only from metadata fields.
- `run_query(manifest_path, request, hints=None, audit_dir=None, call_id=None) -> dict`
  — returns `{"output": {...}, "audit": {...}, "audit_path": str}`.
- `validate_output(output) -> list[str]`
- `write_audit(audit_dir, call_id, audit) -> str`

## Test command
`python3 -m unittest tests.test_selector_integration -v`
(Final main-tree verification adds the two existing modules.)

## Notes
- unittest only. Tests import the module via `importlib.util.spec_from_file_location`
  with the path computed from `__file__` (`parents[1] / .agents/skills/selector/runtime/`).
- Tests use `tempfile.TemporaryDirectory()` for audit output; never write to `sessions/`.
- No commits by subagents. Existing tests/schema/fixtures are read-only.
- `yaml` is installed; if you avoid it, the fallback parser must handle the exact
  fixture subset (`documents:` list of `key: value` lines).
