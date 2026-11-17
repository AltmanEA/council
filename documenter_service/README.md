# documenter_service — Documenter Service MVP (Tier 0–1 operational; Tier 2+ implemented, dormant behind the dual interlock — policy gate + Operator Surface not built, ADR-013)

Stage 4 scaffold (plan `sess-doc-reliability-algo`, session
`sess-doc-reliability-algo`). Contract documents (normative, under `docs/`):

- `docs/en/documenter-service/mvp-contract.md` — stack, Ports & Adapters,
  Safety Protocol §2.1, Testing Strategy §3.1–3.3, Tier 2+ Reserved §4
- `docs/en/documenter-service/mvp-interfaces.md` — `audit()` /
  `delegate(preview: true)` / `documenter.status()`, severity semantics,
  `next_action` enum, error categories, Common Constraints §5
- `docs/en/documenter-service/mvp-data-models.md` — registry envelope and
  record types, token model, Policy File + 7 fail-closed rules, Event
  Channel (redaction), Directory Layout §4, ENV §5

## Operational (this build)

| Surface | Entry | Notes |
| --- | --- | --- |
| `audit()` | `python3 -m documenter_service --audit --target "*" --json` | Pure reuse of `tools/check_all.scan(root)` + `docmeta.validate` — **no rule fork** (documentation-rules §8). Pagination via policy `rescan_batch_ceiling`; single-use `scan_cursor` bound to `(audit_id, target_id)`; partial reports carry the mandatory write-decision-impossible header. |
| `documenter.status()` | `python3 -m documenter_service --status` | Registry health (`healthy/degraded/corrupt`), last audit + freshness, `staged_files`/`override_counter` derived from registry records (unresolved intent leftovers; override_gate token count), pending scan visibility, Tier interlock. Never crashes on a corrupt registry — degradation is REPORTED. |
| `delegate(preview: true)` | `python3 -m documenter_service --delegate-preview --target <id> --change-type update --trust-level review --diff-file -` | Canonical diff: decode base64 → normalize (CRLF→LF, trailing whitespace, final newline) → `diff_hash=sha256:<hex>` over normalized bytes → render `diff_text`. `diff_text` appears ONLY in the response — never in events or the registry. |
| Audit registry | `documenter/audit_registry.jsonl` | Append-only JSONL, envelope `{record_type, prev_hash, data}`, `prev_hash` chain (corruption aid per conflict C5). Token records for scan cursors. Retention 10,000; truncation only with a trailing `checkpoint_record`. |
| Events | stdout (+ persisted `documenter/corpus-audit/events.jsonl`) | One structured JSON line per event (`documenter.issue`, `precheck.passed/failed`) — the operator-approved MVP carrier (conflict C4). Payloads are schema-checked (VAL.001) and redacted (no document text). The default Service sink also appends each event as `{event_id, emitted_at, event_type, payload}` to `documenter/corpus-audit/events.jsonl` (append-only, fsynced) for operator replay per configuration-guide §Delivery Semantics; `event_id` is journal metadata, not a payload key. Callers passing an explicit sink (CLI stderr, MCP) keep the stdout/stderr-only behavior. |
| Hash store | `documenter/hashes.json` (+ `hashes.json.bak`) | Rebuildable cache (ADR-010) per configuration-guide §Hash Store: `{version: 1, entries: {rel_path: {last_hash, last_modified, history[]}}}` — snapshot updated after each `audit()` cycle, history append-only. Self-healing: atomic write (temp+fsync+rename) + `.bak` rotation; any corruption or structural invalidity is a cache miss → rebuild-and-continue, never a crash. Rebuild on demand: `python3 -m documenter_service --rebuild-hashes --json`. |

Rule coverage: deterministic rules **1, 2, 4, 6** plus naming/schema are
covered because audit() invokes the tools checker. **Rules 3 (glossary terms)
and 5 (abstraction consistency) are skill/AI-reserved and not implemented
here** — this package never claims "rules 1–6" coverage (documentation-rules §8).

## Tier 2+ (implemented; dormant behind the dual interlock — policy gate + Operator Surface not built)

- **Write branch** — `--delegate-write` / MCP `delegate_write`: full guard
  chain (tier authorization → registry health → `audit_id` gate rules 1–5 →
  scope → `allowed_operations` → trust invariant), single-use `approval_id`
  bound to `(target_id, diff_hash, proposer_id)`, apply under the
  mvp-contract §2.2 sequence (`core/write.py`, `adapters/lock.py`,
  `adapters/applier.py`): fcntl advisory lock, stage+fsync in the target dir,
  durable intent file, pre-change git snapshot (`git status` + `HEAD`
  captured into the intent record, fail-closed: writes outside a git
  repository are denied — rollback safety per ADR-007), apply-time sha256
  verification (C2), atomic rename,
  `fsync(dir)`, `intent_record` lifecycle, cold-start `reconcile()`.
- **Multi-file commit protocol** — `adapters/commit_protocol.py` + the
  `changeset` parameter of `core/write.propose_write`/`apply_write`
  (index.md §Safety Protocol #9, mvp-contract §2.2.5): changesets spanning
  document + `index-RU.md` + changelog + `docs-manifest.yaml` +
  `documenter/hashes.json` commit through stage-all (`.tmp` in target dirs,
  `/tmp` staging prohibited) → intent record
  `documenter/intent/<tx_id>.json` (atomic, entries carry
  `path/tmp_path/before_hash/after_hash`) → ordered renames (document → RU →
  changelog → manifest → hash store; manifest last so a crash leaves
  orphaned-but-readable files) → cleanup in #9d order with the intent record
  deleted LAST. Non-manifest paths in a changeset are rejected with
  `unknown` before any write. `reconcile()` implements the three-branch
  cold-start recovery (after_hash → skip; before_hash → roll-forward from
  staged tmp; neither → `needs_attention` without force). The core API is
  wired for changesets; the CLI/MCP surfaces expose the single-document
  flow (changeset wiring is a reserved follow-up).
  Synchronous calls respect `sync_latency_budget_ms` (policy, default
  30000): an over-budget call returns `gate_failure` instead of blocking
  (mvp-interfaces §5); `audit()` additionally enforces read-before-use
  (mvp-contract §2.1.3): scope-file hashes are taken before and after each
  pass and an unstable pass is discarded and re-run.
- **Approval** — `--approve` / MCP `approve`: out-of-band, approver ≠
  proposer, single-use (consumed on apply; second apply → `token_replay`),
  expiry per `approval_expiry_window`. `operator_id` comes from
  `COUNCIL_OPERATOR_ID` only — never a CLI/MCP parameter. Solo self-approval
  (ADR-017) additionally requires the acknowledgment token: CLI
  `--acknowledge CONFIRMED_SOLE_REVIEWER` / MCP `approve {"acknowledge": …}`;
  it is permitted only for a `safe`-trust matched operation, after
  `min_approval_delay_seconds`, and the approve response carries a
  `bias_warning` banner. Missing or wrong token → `gate_failure`.
- **Override gate** — `--override-gate` / MCP `override_gate`: one-shot per
  `(target_id, diff_hash)` within the window, emits the canonical event,
  unavailable for `critical` findings (§4 wins over §2.2.6; the
  post-mortem writer in `core/override.py` stays as the durable mechanism).
- **Tier 3** — `core/patterns.py`: policy-enumerated `type: pattern`
  entries, viewed-diffs metric (≥90%), quarantine (first N per-item
  approval), application limit/expiry, batch digest; every path requires
  `active_tier >= 3`.
- **Still absent (deferred):** CLI/MCP changeset surface (the commit
  protocol is core-level; transports expose the single-document flow),
  Layer 1 `WorkerPort` adapter (`worker_stub` → interlock),
  Layer 2 surface. With `documenter_policy.yml` at Tier 0–1 and
  `briefing_ref: null`, every non-preview call fails closed
  (`tier_interlock`). Per ADR-013 the runtime policy gate is only the first
  interlock level: Tier 2+ is **not activatable** until the Operator Surface
  exists as code providing authenticated ingress — a policy edit alone is
  prohibited as an activation act (AGENTS.md §1.7; operator out-of-session
  action per policy-reference §Authorization Workflow and
  `briefings/tier2-delegation.md`). The readiness precondition is enforced
  in `check_tier2_authorized` via the readiness sentinel
  `documenter/.operator_surface_ready` (absent by default; created by the
  surface installation); `status()` reports the blocking level.

## MCP stdio transport

The MVP includes an MCP stdio JSON-RPC 2.0 server. Run it with:

```bash
python3 -m documenter_service --mcp --root <repo-root>
```

The server exposes six tools: read-only `audit`, `status`,
`delegate_preview` plus Tier 2+ `delegate_write`, `approve`,
`override_gate` (policy-gated; operator identity from `COUNCIL_OPERATOR_ID`
only). Stdout carries ONLY JSON-RPC messages (one per line); the Service's
event sink writes to stderr so events and logs never interleave with RPC
output.

**Not registered in workspace config.** Per AGENTS.md §1.7 (prohibition),
the Documenter is NOT registered as an MCP server in the workspace
configuration — registration is an explicit operator decision, out of
scope for this MVP build.

## Critical producers

By contract (mvp-interfaces §1 severity semantics, mvp-contract MVP
boundary) the MVP has **no producers of `critical` findings**: read-only
diagnostics cannot establish data-integrity compromise, so the severity
enum keeps `critical` but nothing emits it. This absence is intentional
(not an oversight); introducing a critical-producer rule is a separate
change that activates blocking + post-mortem semantics belonging to the
write path. Do not fabricate example critical findings in tests or fixtures.

## Running

```bash
python3 -m documenter_service --status
python3 -m documenter_service --audit --target "*" --json
python3 -m documenter_service --audit --target <id> --severity-min medium
python3 -m documenter_service --audit --target "*" --scan-cursor <token>  # resume
python3 -m documenter_service --delegate-preview --target <id> \
    --change-type update --trust-level review --diff-file -                # b64 on stdin
python3 -m documenter_service --delegate-write --target <id> --change-type update \
    --trust-level review --diff-file - --audit-id <id>                     # propose
python3 -m documenter_service --approve --approval-id <id>                 # op: COUNCIL_OPERATOR_ID
python3 -m documenter_service --delegate-write --target <id> --change-type update \
    --trust-level review --diff-file - --audit-id <id> --approval-id <id>  # apply
python3 -m documenter_service --override-gate --target <id> \
    --diff-hash sha256:<hex> --reason "..."                                 # gated
python3 -m documenter_service --reconcile                                   # cold-start recovery, exit 0
python3 -m documenter_service --rebuild-hashes --json                       # rebuild hash cache
```

Exit codes (also in the `__main__` docstring):
**0** success (findings do NOT flip the code — audit is diagnostics, not a
gate); **2** structured refusal (StructuredError: JSON on stdout with
`error_category` + `next_action`); **3** internal error (fail loud, traceback
on stderr — a bug, not operator action).

Configuration (ENV, mvp-data-models §5): `DOCUMENTER_POLICY_PATH` (default
`documenter_policy.yml`), `DOCUMENTER_DATA_DIR` (default `documenter/`),
`DOCUMENTER_LOG_LEVEL` (stderr warning filter). The policy loader is
fail-closed (7 rules of mvp-data-models §2); a broken policy never blocks
audit()/status() and never blocks `preview: true` (preview exemption) — it
only downgrades `max_diff_bytes` to the documented 512 KiB default with a
stderr warning. A missing/unreadable policy at Tier 2+ fails closed: every
non-preview call returns `tier_interlock` (via `check_tier2_authorized`).

## Safety

The service never runs `git commit` / `git add` / any mutating git command;
the only git invocations are the read-only `git rev-parse HEAD` and
`git status --porcelain` inside the write branch's pre-change snapshot
(`adapters/git_snapshot.py`, argv-list subprocess, no shell). Those are
capture-only: they never mutate the repo or the index, and a failure to
capture fails the write closed (no snapshot → no write — ADR-007 rollback
relies on git). Corpus mutation happens ONLY through the
policy-gated write branch (§2.2 durability sequence; one document per
single-document invocation, multi-file changesets only through the
Multi-file Commit Protocol with an intent record; every step recorded in
the registry); every applied change is a
plain unstaged working-tree edit reversible by `git restore`. Read-only
operations touch nothing outside `documenter/audit_registry.jsonl` appends,
`documenter/corpus-audit/events.jsonl` appends, and the rebuildable
`documenter/hashes.json` cache (plus creation of the
`documenter/` state directory). The checkpoint-governed `truncate()` compaction path is
explicit and never runs implicitly. Imports are stdlib + PyYAML (via
`tools/docmeta` / `yaml.safe_load`); the only subprocess use is the
read-only git snapshot above; no LLM clients, no
network libraries.

## Resolved: policy validation rule 3 direction

`mvp-data-models.md` §2 rule 3 originally read "allowed_operations **empty**
while `active_tier < 2` → load fails", contradicting the validator rule it
cites (`policy-reference.md` §Policy File: reject when **non-empty** while
active_tier < 2) and making any legal Tier 0/1 policy (empty
`allowed_operations`) unparsable. Fixed in the contract at v0.3.2-draft
(rule 3 now reads "non-empty while `active_tier < 2`", operator-approved).
The scaffold always followed the cited validator rule (fail on non-empty ops
below Tier 2) and additionally requires non-empty ops at Tier ≥2
(mvp-contract §4); no code change was needed.
