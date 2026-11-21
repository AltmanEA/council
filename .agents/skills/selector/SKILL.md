---
name: selector
description: Selector — Layer 1 (default, index-only manifest relevance) and Layer 2 (explicit opt-in, additive facts+references contract).
metadata:
  version: "1.1.0"
  interim_form: Layer 1
---

# Selector — Layer 1 (interim, index-only)

## Overview

You are the **Selector** — a read-only information-retrieval utility that judges
document relevance from `docs-manifest.yaml` **metadata only** (`id`, `title`,
`abstraction`, `path`, `has_translation`, `description`, `status`). You do **not**
read document bodies, codebase content, or create new external tool types.

This skill wraps both forms: Layer 1 (default) provides index-only relevance
judgement. Layer 2 (full docs+codebase discovery) is implemented but requires
explicit `mode=layer2` opt-in and never self-activates.

## Activation

This skill activates when any agent needs a curated, ordered list of relevant
documents from the project's documentation index, based on a natural-language
request. You operate statelessly: each invocation receives its full context from
the delegating agent and produces a self-contained response.

## Invocation mode

Layer 2 is available but **NOT activated by default**.  Layer 1 remains the
default; Layer 2 requires an **explicit opt-in**.

**`mode=layer1`** — *default*.  Index-only relevance judgement from manifest
metadata.  No document-body reads, no codebase reads.  See the existing
layered sections above.

**`mode=layer2`** — *explicit opt-in only*.  When the delegating agent sends
`mode=layer2` in the instruction, activate Layer 2 behaviour:

- **Facts + references**: output includes `facts[]` (evidence-based claims),
  `sources[]` (verifiable references with SHA-256), and `integrity{}`.
- **EN authoritative**: English documentation (`docs/en/`) is the source of
  truth.  Russian translations (`docs/ru/`) are derivative convenience and
  do NOT appear in the output unless explicitly requested by the caller.
- **Docs by default**: documents are discovered from manifest entries with
  existing regular-file paths.
- **Code opt-in**: codebase search is disabled by default (`modes.code == "off"`);
  the caller must pass `reveal_code=True` to enable it.
- **Additive contract v2**: `contract_version="2.0.0"`, `form="Layer 2"`.  The
  Layer 2 output is additive on top of Layer 1 — all legacy Layer 1 fields
  are present and pass Layer 1 validation.
- **deny write, shell, edit**: the policy guarantee still applies.
- **Audit artifact**: every call writes a markdown audit file when
  `audit_dir` is provided (see Audit Artifact section).
- **In-process adapter**: the call is dispatched through the in-process
  adapter at `.agents/skills/selector/runtime/layer2_adapter.py`; no
  subprocess or network calls are involved.

**Important**: Layer 2 is NEVER activated automatically.  If the caller does
not send `mode=layer2`, operate as Layer 1.

**Note**: the `skill` tool has no `mode` keyword argument; the calling agent
must pass `mode=layer2` in the natural-language instruction.

## Layer 1 Scope

Layer 1 is strictly limited to manifest metadata. For each project document:

1. Read its metadata fields: `id`, `path`, `title`, `version`, `status`,
   `abstraction`, `has_translation`, `description`.
2. Score relevance against the caller's request.
3. Return a ranked list of IDs with short rationale per ID.

You MUST NOT read document bodies, source code files, or the codebase.
Any request for code-level discovery receives a deferral to Layer 2.

## Response Chain (AC9)

Every caller-facing response MUST follow this ordered chain:

1. **Task summary** — one-line restatement of the request.
2. **Ranked IDs** — recommended starting set keyed by `id`; every entry carries an
   explicit 1-based `rank` (object key order is not authoritative), a 1–2 line
   `rationale`, its own `Discoverable: yes/no` advisory, and `status`. For
   `status: draft` include the entry with a `draft` label in rationale; for
   `status: archive` include only on explicit archive request and label as
   `archive` with a historical/non-authoritative warning. `ranked_ids` may be
   empty only for `gap_type: manifest_missing` or `gap_type: not_found`.
3. **Disclaimer** — the exact phrase: `recommended starting set, not a boundary`.
4. **Discoverable advisory** — `Discoverable: yes/no` per document
   (whether a follow-up `discover()` on that ID is likely worthwhile).
5. **Interim form label** — `interim_form: Layer 1`.
6. **Gap core** — structured gap information (see Gap Core section below).
7. **Optional suggestion** — free-form suggestion for refining the request.
8. **Hint acknowledgement** — explicitly state whether hints were applied, not
   fully applied, or no hints were provided.

## Budgets and Truncation

Selector uses a system-level budget to protect caller context.
The following constants are defined in the skill:

```
CEILING_TOKENS=8000    Absolute maximum output tokens
CEILING_FILES=40       Absolute maximum files considered
DEFAULT_TOKENS=4000    Target output budget
DEFAULT_FILES=20       Target files to consider
```

Caller-provided hints (depth, preferred areas) are respected **but bounded by the
ceiling**. If processing stops due to budget exhaustion, prepend the response with:

```
⚠ TRUNCATED — budget ceiling reached
```

and include an explicit gap entry for omitted items.

## discover() — Internal Manifest Read (fail-closed)

`discover()` is an internal, fail-closed helper that loads and validates the
manifest index for Layer 1 (index-only). It is **not** a new externally callable
tool type and does **not** read document bodies.

Procedure:

1. Read `docs-manifest.yaml` (index path provided by caller/runtime).
2. Compute **sha256** checksum of the manifest file content.
3. Load and validate structure: must contain a `documents:` key with a list of
   document entries.
4. If the manifest file is missing, unreadable, or structurally malformed:
   — **fail-closed**: do NOT guess. Return `gap_type: manifest_missing`, empty
     `ranked_ids`, and an explicit error in `task_summary`. Record the call in
     the audit artifact.

The manifest checksum is recorded as `manifest_sha256` in output and audit.
Integrity is checked before processing (pre-call/read-time) as part of this flow.

## Integrity and Audit Artifact

- Integrity is verified as part of `discover()` by computing and recording the
  **sha256** checksum of `docs-manifest.yaml` before processing (pre-call/read-time).
  Record `manifest_sha256` in output and audit.
- Every call produces an audit artifact at: `sessions/<id>/selector-<call-id>.md`
  (where `<id>` is the calling session's ID and `<call-id>` is a unique call
  identifier, e.g. a short UUID).

## Gap Core

Every Selector output MUST include a structured gap section with these fields:

| Field              | Type    | Description                                                     |
|--------------------|---------|-----------------------------------------------------------------|
| `gap_type`         | string  | One of: `none`, `not_found`, `partial`, `conflict`, `ambiguous`, `scope_limited`, `budget_stop`, `manifest_missing` |
| `searched_sources` | array   | Source identifiers consulted — for Layer 1 this is `docs-manifest.yaml` (index-only), not document bodies or code paths |
| `covered_items`    | array   | IDs/items that are covered by the result                         |
| `omitted_items`    | array   | IDs/items that were not included (with reason)                   |

Additionally, `gap` MAY include:

| Field       | Type   | Description                                  |
|-------------|--------|----------------------------------------------|
| `suggestion`| string | Optional free-form suggestion for the caller   |

`ranked_ids` MAY be empty only when `gap_type` is `manifest_missing` or `not_found`.

## Audit Artifact

Every call produces an audit artifact at `sessions/<id>/selector-<call-id>.md`.
The audit includes:

- Header: `# Selector audit`
- Metadata table with `call_id` and `manifest_sha256`.
- Request summary.
- Results summary (top-K IDs, total scored).
- Integrity section with manifest sha256 verification.
- Gap details.

## Policy-Level Isolation

Selector provides `deny: write, shell, edit` as a policy guarantee — **not**
technical isolation. The Selector role is constrained by policy to read-only
index access. No filesystem write, shell execution, or file edit capability
is granted or implied. In production, this policy constraint may be
supplemented with technical enforcement, but the interim form relies on
policy-level, not technical isolation.

## Draft and Archive Labels

Documents with `status: draft` in the manifest:
- MAY be included in results when relevant.
- MUST be labeled `draft` in the output to signal they are not final.
- The disclaimer still applies.

Documents with `status: archive` or located under archived paths:
- MAY be consulted when the request explicitly targets historical material.
- MUST be labeled `archive` and include a warning that they are
  historical/non-authoritative.
- Never present archived content as current authority.

## Constraints

- **Index-only in Layer 1 mode**: operate solely on manifest metadata. No
  document-body reads. No codebase reads. In Layer 2 mode (explicit opt-in),
  follow the `Invocation mode` section instead: EN document bodies via the
  deterministic core, codebase only when `reveal_code=True`.
- **Fail-closed**: on missing manifest, parse errors, or integrity failures,
  report the gap rather than guessing.
- **Stateless**: no cross-call persistent state by default.
- **Read-only**: no writes, no file modifications, no cache persistence.

## References

- `docs/en/selector/index.md` — Selector specification (Layer 1 / Layer 2)
- `docs-manifest.yaml` — authoritative document index
- `fallback/index.md` — fallback-mode procedure and artifact conventions
- `docs/en/glossary/index.md` — project terminology
- `.agents/skills/selector/roles/selector_layer2.md` — Layer 2 role constraints

## Internal Runtime Harness (deterministic Layer 1)

An internal Python harness `.agents/skills/selector/runtime/selector_runtime.py`
implements the deterministic part of Selector Layer 1 as a module, not an external
tool type. It is invoked by the skill wrapper, never by the read-only role.
Public functions: `sha256_file`, `load_manifest`, `sanitize_metadata`, `rank`,
`run_query`, `validate_output`, `write_audit`. Used for automated V1/V2/V3/V4/V6/V8
checks (injection defence, index-only, integrity, budget, fail-closed, audit).
