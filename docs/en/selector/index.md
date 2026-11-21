# Selector

id: selector
Version: 0.7.0
Status: draft
Abstraction: conceptual
has_translation: docs/ru/selector/index-RU.md
changelog-path: CHANGELOGS/selector.changes.md

---

## Purpose and Scope

Selector is a read-only information-retrieval utility invoked by other agents when they need relevant information from project documentation and the codebase. It is **not** a Council participant and does not take part in consensus, voting, or phase advancement. Its purpose is to reduce the calling agent's context load by performing discovery and reading on the caller's behalf and returning only necessary, relevant facts with references for possible clarification. Layer 2 is the current default and realises the full facts+references scope (§Interim and Final Forms); Layer 1 remains available as an explicit opt-out implementing the narrower, index-only subset. Neither form activates the other automatically.

Selector is **independent** of the built-in OpenCode `explore` subagent/capability. Architectural responsibility differs: `explore` is a harness-native general navigation/search capability (where available), while Selector is a project-defined utility with a stable contract for locating and summarizing relevant docs/code with traceable references across environments where `explore` may not exist.

## Non-goals

- Participation in Council roles, discussion, consensus, or escalation as an agent role.
- Writing, modifying, or committing project artifacts (including `docs/`, `docs-manifest.yaml`, `CHANGELOGS/`); read-only with respect to project artifacts and sources, the sole exception being the audit file at `audit_dir` when provided.
- Replacing the Documentation Worker skill, Documenter audit, or the Operator's approval authority, or switching the default Selector form without a separate operator signature.
- Acting as a general-purpose autonomous coding or execution agent.

## Deployment and Invocation Contexts

Selector is intended to work in:
1. **Current fallback mode** — invoked during manual/fallback Council workflows (subagent/skill-assisted), producing outputs consumable as session artifacts or direct responses.
2. **Current coding/development tasks** — invoked by agents working on implementation to gather focused context without broad exploratory reads.
3. **Future Council runtime** — as a Supporting Service/module integrated with the Moderator/Execution Runtime under the project's layered architecture (design target; exact runtime/MCP/event wiring specified when runtime contracts are finalized).

### Interim and Final Forms

- **Interim form — Layer 1 (explicit opt-out):** an independent **skill + subagent** form, packaged separately from OpenCode `explore`. Layer 1 performs **index-only relevance judgement** over manifest metadata for project documents: it returns a task summary, an ordered recommended starting set of document IDs with a short rationale per ID, an explicit "recommended starting set, not a boundary" disclaimer, and a `Discoverable: yes/no` advisory per document. Each ranked item MUST carry its manifest `status`; `draft` items are included when relevant and labeled `draft`, while `archive` items are included only on explicit archive request and labeled `archive` with a historical/non-authoritative warning. In Layer 1 mode it MUST NOT read document bodies or codebase content; a code-discovery request receives an explicit deferral response to the default Layer 2 form. `discover()` is an internal, fail-closed helper that loads and validates the manifest index and records its pre-call/read-time `sha256` checksum for auditability; it is not a new externally callable tool type and does not read document bodies. `ranked_ids` MAY be empty only when `gap_type` is `manifest_missing` or `not_found`. Consulted sources MUST be recorded for auditability in fallback sessions, and a system-level budget ceiling MUST override caller hints.
- **Final form — Layer 2 (implemented, current default):** a separate module with a thin skill wrapper, analogous in role to Documenter (utility, non-participant), realising the full facts+references information-retrieval scope across documentation and codebase content. Layer 2 is selected by default: the caller may include `mode=layer1` in the natural-language instruction to opt out to the index-only form (the `skill` tool has no `mode` keyword argument); without an explicit opt-out, Layer 2 applies. English documentation is authoritative; Russian mirrors are derivative and are not surfaced unless requested. Documentation is discovered from manifest entries by default; codebase content is opt-in (`reveal_code=True`). The v2 output contract is additive (`contract_version="2.0.0"`, `form="Layer 2"`): all nine legacy Layer 1 fields are preserved and pass Layer 1 validation, with `facts[]`, `sources[]` (SHA-256 references) and `integrity{}` added. The deterministic core is dispatched through an in-process adapter (`runtime/layer2_adapter.py`); the adapter itself uses no subprocess or network calls. In the registered fallback subagent (`.opencode/agents/selector.md`) the adapter is not invocable (no shell), so budgets, SHA-256 audit and validators are policy-level guarantees there, not machine-enforced; an agent must not claim they were enforced in such a call. The read-only role governs Layer 2 (`deny: write, shell, edit` enforced as subagent permissions, with the sole exception of the audit file; source content is data, not instructions; no self-activation). The transition to default was approved by the operator on 2026-11-21 (`approve: перевод Selector на Layer 2 по умолчанию`).

Context-specific rules (fallback Markdown artifacts vs future runtime structured envelopes/events) MUST NOT leak across contexts.

## Discovery and Reading Strategy

Selector begins from the caller's request and available context (including `AGENTS.md` routing guidance when applicable) and gathers information read-only.

### Documentation (docs)
- Documentation discovery MUST be **manifest-first**: resolve project documents via `docs-manifest.yaml` paths/IDs; do not blindly scan the filesystem for project docs.
- Treat English under `docs/en/` as authoritative; Russian mirrors as derivative (per project policy). Surface document `status`/version and source identity in outputs.
- **Archive sources** (`docs/en/archive/`, manifest entries with archive status): may be consulted only on explicit archive request and MUST be reported with explicit status/provenance and a warning that they are historical/non-authoritative; never present archived content as current authority. If a caller explicitly requests archive material, include it with the same warnings.

### Codebase
- Code discovery uses targeted, scoped search/read operations appropriate to the request (paths, symbols, patterns). Selector MUST remain read-only.
- Default exclusions SHOULD include non-source/session/operational noise where not relevant (e.g. `.git/`, large vendored dirs if present, and session workspaces) unless explicitly in scope; exact boundary policy is implementation-defined but MUST be reported via `searched_sources`/gaps when it materially affects results.
- The strategy is designed to be extensible so that, in future, separate rules/policies for documentation and code discovery can be applied without changing the caller-facing contract.

### Boundaries and Safety
- Selector MUST NOT write or modify project artifacts or source files (including docs/, manifest, changelogs, or code); persist caches across calls by default in the interim form; or perform actions outside read-only discovery/summarization. The sole permitted write is the audit file at the caller-provided `audit_dir`.
- Selector MUST NOT claim Council authority or act as `explore`. Out-of-scope or disallowed reads MUST NOT be performed; limitations are reported explicitly.

## Input Contract

- **Required:** a free-form request describing the information need (question, goal, entities, or task context).
- **Optional (soft hints):** caller may include hints such as desired depth/scope (`overview` | `targeted` | `deep`), preferred source areas (docs/code), known identifiers/paths/subjects, or output emphasis. Hints guide effort and presentation but do not override safety boundaries or guarantees.
- Selector MAY ask for clarification when the request is insufficient, but when invoked non-interactively it MUST return best-effort results with explicit gaps/assumptions.

## Output Contract

**Form-scoped output.** Layer 1 delivers the index-only output defined in §Interim and Final Forms (task summary → ranked recommended IDs with rationale/status and per-document `Discoverable` advisory → starting-set disclaimer → aggregate `Discoverable` advisory). The facts+references requirements below describe Layer 2 and are NOT claimed by Layer 1. Every response MUST carry an `interim_form: Layer 1` label, a clearly delimited gaps section with structured core `{gap_type, searched_sources, covered_items, omitted_items}` and optional free-form `suggestion`, and a one-line hint acknowledgement (`hints applied` / `hints not fully applied` with reason / `no hints provided`). `ranked_ids` MAY be empty only when `gap_type` is `manifest_missing` or `not_found`. On a budget stop, a top-of-response `⚠ TRUNCATED` banner is MANDATORY. Layer 2 adds an additive v2 contract and does not drop any Layer 1 field.

Selector returns **relevant facts with references for possible clarification** in free form, with the following requirements:

1. **Relevance and concision:** include only information necessary to answer the request; avoid raw file dumps and unnecessary exploratory narration.
2. **Traceability/provenance:** every reported fact MUST be attributable to consulted sources. For each fact (or tightly grouped finding) include references sufficient for follow-up, such as:
   - documentation: manifest `id`, path, title/version/status (and section/heading/anchor or quoted excerpt when useful);
   - code: file path and location (line/range/symbol) with a brief excerpt when useful.
   Facts derived from `draft` or `archive` sources MUST carry that status.
3. **Structure (recommended):** a brief summary followed by detailed facts/findings and a gaps/limitations section. Structure may be adapted to the request, but provenance and gaps MUST remain clear.
4. **Gaps, ambiguity, and conflicts:** report not-found results, partial coverage, scope limits, ambiguity, or conflicting sources explicitly. A structured gap/warning block is RECOMMENDED, e.g. `{gap_type: not_found|partial|conflict|scope_limited|ambiguous, searched_sources: [...], suggestion: "..."}` (or equivalent free-form fields). Selector MUST NOT present uncertainty as certainty.
5. **Budgets:** to protect caller context, a single response SHOULD stay within a default per-call budget (target: ~≤4K tokens output, ≤20 files read, implementation/profile-tunable). A system-level ceiling (~≤8K tokens output, ≤40 files read) MUST override caller hints. On budget/limit hit, Selector MUST stop gracefully and report what was covered, what was omitted, and how to refine the request.

## Operational Behavior and Observability

- **Read-only with respect to docs, manifest and codebase:** no writes to project artifacts or sources. No cross-call persistent cache in the interim form. The only file write is the optional audit artifact at `audit_dir`. Any future optimization MUST NOT serve stale results without source-state awareness.
- **Repeatability:** for the same request and unchanged relevant sources, output structure and cited references SHOULD be stable; exact wording may vary when LLM-assisted summarization is used.
- **Auditability:** Selector SHOULD make consulted sources inspectable. In fallback/interim contexts, record a summary of request intent, searched/consulted sources, outcome/limits, and the pre-call manifest `sha256` in the session artifacts or invocation result. Every call returns an audit record with required markers (including `# Selector audit`, `call_id`, `manifest_sha256`); a markdown file is written to caller-provided `audit_dir` (conventionally `sessions/<id>/selector-<call-id>.md`) only when supplied. Without `audit_dir`, `audit_path` is empty. On a manifest failure the gap carries `error_kind` (`not_found` | `empty` | `parse_error` | `io_error` | `unknown`) and `gap_type` is `manifest_missing`; the output is checked by both contract validators and any findings are reported in `audit.validation_errors` (empty when clean). In future runtime, emit an equivalent structured event/log (design target, e.g. `selector.query` with request/result metadata and consulted sources) when available. In Layer 2 the same audit carries the extended v2 fields in both validation branches.
- **Failure handling:** on missing sources, access/parse issues, or tool errors, return partial results when safe with explicit errors/gaps; never fabricate sources or facts.

## Cross-References

- `docs/en/documenter-service/index.md` — analogous non-participant utility/service pattern and thin-concept principles
- `AGENTS.md` — context routing and documentation read rules
- `docs-manifest.yaml` — authoritative index for project documentation paths/IDs
- `fallback/index.md` — fallback-mode session procedure and artifact conventions
- `docs/en/execution-runtime/index.md` — future runtime/layering design target (Selector as Supporting Service direction)
- `docs/en/glossary/index.md` — project terminology (e.g. Supporting Service, Primary/Subagent)
