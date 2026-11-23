# Target Task — Telemetry control surface (v0.1.0)

Source of authority: `sessions/sess-telemetry-distribution-2026-11-22/consensus-doc.md`,
Action Items 1–8 + «Уточнения оператора» 1–6. Operator request: «Реализация по Action Items»
(2026-11-22) — this explicitly lists the existing files editable in this cycle.

## Goal

Implement the minimal **local, opt-in, manual** diagnostics control surface for the
Council distribution. No automatic collection, no external transmission, no metrics
collection, no science/sampling logic. HCD precondition: disclosure + opt-in must be
really present before any collection can be enabled on a host.

## Allowed paths (whitelist — see `whitelist.cycle`)

NEW:
- `tools/collect_telemetry.sh`
- `tests/test_collect_telemetry.py` (unittest; additional `tests/test_telemetry_*.py` allowed)

EXISTING (explicitly listed by the operator via the Action Items):
- `dist/install.sh`
- `dist/RUNBOOK.md`
- `tools/README.md`

Everything else is read-only. In particular: `dist/build.sh` MUST NOT change
(`copy_core "tools"` already ships the collector); `docs/`, `docs-manifest.yaml`,
`CHANGELOGS/`, `fallback/`, `AGENTS.md`, `defaults/`, `.opencode/`, `archive/`,
`sessions/`, `.agents/` are forbidden. No commits. No Tier 2+ Documenter markers.

## Acceptance criteria

### A. `tools/collect_telemetry.sh` (bash, executable bit set)

CLI (all from the host project root, CWD = host root):
- no args or `--collect` — read JSONL error records from **stdin**, append redacted
  records to `.council/telemetry/diagnostics/<session_id>.jsonl`;
- `--inspect` — print a **summary only** (record count, categories, directory size,
  last-record date) — never record content; exit 0 even with no data;
- `--bundle` — write a gzip tarball to **stdout** containing `manifest.json` plus
  the files it lists (paths relative to host root, all under `.council/telemetry/`);
- `--read <bundle.tgz>` — extract to a temp dir, parse `manifest.json`; wrong or
  unsupported `schema_version` → warning to stderr, skip files, exit 0 (silent
  degrade); valid → print only the file list; never print record contents;
- `--help`.

Consent and safety:
1. Config `.council/telemetry.yml`, minimal `key: value` lines. Keys: `enabled`,
   `project_name`, `redact_symbols`, `max_file_size_mb`, `max_total_dir_mb`,
   `retention_days`, `collect`. Missing config or `enabled: false` → exit 0, write
   nothing. Council never writes the config itself.
2. `.council/opt-out-telemetry` present → `--collect` writes nothing even if enabled.
3. Failure of any kind (bad input, redaction error, permission error) → print a
   warning to stderr and **do not write a partial record**; exit 0. The host must
   never break (fail-closed, silent fallback).
4. Never touch `.git/`, never register hooks, never call curl/wget/network, never
   read env variables into records.

Redaction (every rule enforced in code, not only docs):
- filesystem paths → `./<basename>:<line>` (drop host directories);
- stacktrace: at most 50 lines, fields only `file`, `line`, `function`,
  `exception_type`, `message`; no source lines, no variables, no env, no prompts,
  no file contents;
- `redact_symbols: false` (default) keeps `function`; `true` replaces it with a
  stable short hash;
- API keys / long tokens matching `[A-Za-z0-9]{32,}` → `[REDACTED]`;
- IPv4 → `[local]` for private/loopback, `[external]` otherwise;
- duplicate records (same redacted hash) are skipped;
- record JSON fields: `schema_version` (1), `session_id`, `timestamp`,
  `error_category` (config|tooling|protocol|agent), `stacktrace_hash`,
  `redacted_stack`.

Limits:
- `max_file_size_mb: 10`, `max_total_dir_mb: 50` defaults; oldest-first rotation
  within a file and oldest-first deletion across the diagnostics directory; warning
  to stderr on rotation; no daemon, no background process, flush on write.
- `metrics/` created but never written in v0.1.0.

Bundle manifest: exactly these 5 fields —
`schema_version`, `collector_version`, `project_name`, `generated_at`, `files[]`.
`--read` checks `schema_version` and degrades silently on mismatch.

### B. `dist/install.sh`

- New option `--enable-telemetry`; documented in usage.
- With the flag: create `.council/telemetry.yml` (`enabled: true`, `project_name`
  resolved from `--project-name` or `basename(target)` — reuse existing `PROJECT_NAME`),
  `redact_symbols: false`, limits, `collect`, `retention_days`; create
  `.council/telemetry/diagnostics/`, `.council/telemetry/metrics/`,
  `.council/telemetry/.gitignore`, `.council/telemetry/README.md` (checklist
  «Collected / Not collected» in English, matching the runbook table).
  Overlay mode must not overwrite an existing operator-edited config.
- Without the flag: create **none** of the above; only the disclosure text is printed.
- Always print a post-install disclosure block: off by default, what would be
  collected, what is never collected, «data is never transmitted; export is manual»,
  opt-out path `.council/opt-out-telemetry`.
- No telemetry paths added to core-manifest; `dist/build.sh` untouched.

### C. `dist/RUNBOOK.md`

New section «Telemetry (opt-in)»: enable command, «Collected / Not collected» table,
opt-out flag, `--inspect`, `--bundle`, `--read`, survival across `update.sh` (data in
host-owned `.council/telemetry/`, outside core-manifest), explicit statement that no
data leaves the host and that sampling/scientific validity is the researcher's task.

### D. `tools/README.md`

Add a `collect_telemetry.sh` row and an explicit sentence: «`check_all.py` does not
initiate telemetry collection; the collector is not git-aware — it never touches
`.git/` or registers hooks, and it never transmits data.»

### E. Tests

`tests/test_collect_telemetry.py` — unittest, `python3 -m unittest tests.test_collect_telemetry -v`.
Cover: disabled-by-default silence; opt-out; redaction table; ≤50 lines; hash dedup;
fail-closed; limits/rotation; `--inspect` summary-only; `--bundle` manifest 5 fields;
`--read` schema mismatch silent degrade; installer with/without flag; disclosure
text; docs contract strings. Use `tempfile.TemporaryDirectory` and `subprocess`.
Do not modify other tests.

## Test command

`python3 -m unittest tests.test_collect_telemetry -v`

## Notes for the cycle

- The collector is a thin bash script; avoid new dependencies (python3 stdlib is
  acceptable for JSON/tar if needed; PyYAML is already a core dependency).
- Keep it OP-2 simple: one file, no daemon, no server, no TLS, no push endpoint,
  no sampling thresholds, no signature code.
