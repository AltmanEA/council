# documenter_service — Documenter Service MVP (Tier 0–1 operational; Tier 2+ implemented, policy-gated)

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
| `audit()` | `python3 -m documenter_service --audit --target "*" --json` | Pure reuse of `tools/check_all.scan(root)` + `docmeta.validate` — **no rule fork** (AGENTS.md §8). Pagination via policy `rescan_batch_ceiling`; single-use `scan_cursor` bound to `(audit_id, target_id)`; partial reports carry the mandatory write-decision-impossible header. |
| `documenter.status()` | `python3 -m documenter_service --status` | Registry health (`healthy/degraded/corrupt`), last audit + freshness, pending scan visibility, Tier interlock. Never crashes on a corrupt registry — degradation is REPORTED. |
| `delegate(preview: true)` | `python3 -m documenter_service --delegate-preview --target <id> --change-type update --trust-level review --diff-file -` | Canonical diff: decode base64 → normalize (CRLF→LF, trailing whitespace, final newline) → `diff_hash=sha256:<hex>` over normalized bytes → render `diff_text`. `diff_text` appears ONLY in the response — never in events or the registry. |
| Audit registry | `documenter/audit_registry.jsonl` | Append-only JSONL, envelope `{record_type, prev_hash, data}`, `prev_hash` chain (corruption aid per conflict C5). Token records for scan cursors. Retention 10,000; truncation only with a trailing `checkpoint_record`. |
| Events | stdout | One structured JSON line per event (`documenter.issue`, `precheck.passed/failed`) — the operator-approved MVP carrier (conflict C4). Payloads are schema-checked (VAL.001) and redacted (no document text). |

Rule coverage: deterministic rules **1, 2, 4, 6** plus naming/schema are
covered because audit() invokes the tools checker. **Rules 3 (glossary terms)
and 5 (abstraction consistency) are skill/AI-reserved and not implemented
here** — this package never claims "rules 1–6" coverage (AGENTS.md §8).

## Tier 2+ (implemented; the policy interlock IS the gate)

- **Write branch** — `--delegate-write` / MCP `delegate_write`: full guard
  chain (tier authorization → registry health → `audit_id` gate rules 1–5 →
  scope → `allowed_operations` → trust invariant), single-use `approval_id`
  bound to `(target_id, diff_hash, proposer_id)`, apply under the
  mvp-contract §2.2 sequence (`core/write.py`, `adapters/lock.py`,
  `adapters/applier.py`): fcntl advisory lock, stage+fsync in the target dir,
  durable intent file, apply-time sha256 verification (C2), atomic rename,
  `fsync(dir)`, `intent_record` lifecycle, cold-start `reconcile()`.
- **Approval** — `--approve` / MCP `approve`: out-of-band, approver ≠
  proposer, single-use (consumed on apply; second apply → `token_replay`),
  expiry per `approval_expiry_window`. `operator_id` comes from
  `COUNCIL_OPERATOR_ID` only — never a CLI/MCP parameter.
- **Override gate** — `--override-gate` / MCP `override_gate`: one-shot per
  `(target_id, diff_hash)` within the window, emits the canonical event,
  unavailable for `critical` findings (§4 wins over §2.2.6; the
  post-mortem writer in `core/override.py` stays as the durable mechanism).
- **Tier 3** — `core/patterns.py`: policy-enumerated `type: pattern`
  entries, viewed-diffs metric (≥90%), quarantine (first N per-item
  approval), application limit/expiry, batch digest; every path requires
  `active_tier >= 3`.
- **Still absent (deferred):** Multi-file Commit Protocol (one document per
  invocation), Layer 1 `WorkerPort` adapter (`worker_stub` → interlock),
  Layer 2 surface. With `documenter_policy.yml` at Tier 0–1 and
  `briefing_ref: null`, every non-preview call fails closed
  (`tier_interlock`) — activation is the operator's explicit edit per
  policy-reference §Authorization Workflow and `briefings/tier2-delegation.md`.

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

**Not registered in workspace config.** Per AGENTS.md §7.5 (prohibition),
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
```

Exit codes (also in the `__main__` docstring):
**0** success (findings do NOT flip the code — audit is diagnostics, not a
gate); **2** structured refusal (StructuredError: JSON on stdout with
`error_category` + `next_action`); **3** internal error (fail loud, traceback
on stderr — a bug, not operator action).

Configuration (ENV, mvp-data-models §5): `DOCUMENTER_POLICY_PATH` (default
`documenter_policy.yml`), `DOCUMENTER_DATA_DIR` (default `documenter/`),
`DOCUMENTER_LOG_LEVEL`. The policy loader is fail-closed (7 rules of
mvp-data-models §2); a broken policy never blocks audit()/status() and never
blocks `preview: true` (preview exemption) — it only downgrades
`max_diff_bytes` to the documented 512 KiB default with a stderr warning. A
missing/unreadable policy at Tier 2+ fails closed: every non-preview call
returns `tier_interlock` (via `check_tier2_authorized`).

## Safety

The service never runs git. Corpus mutation happens ONLY through the
policy-gated write branch (§2.2 durability sequence, one document per
invocation, every step recorded in the registry); every applied change is a
plain unstaged working-tree edit reversible by `git restore`. Read-only
operations touch nothing outside `documenter/audit_registry.jsonl` appends
(plus creation of the `documenter/` state directory). The checkpoint-governed `truncate()` compaction path is
explicit and never runs implicitly. Imports are stdlib + PyYAML (via
`tools/docmeta` / `yaml.safe_load`); no subprocess, no LLM clients, no
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
