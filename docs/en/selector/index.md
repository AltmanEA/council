# Selector

id: selector
Version: 0.1.0
Status: draft
Abstraction: conceptual
has_translation: docs/ru/selector/index-RU.md
changelog-path: CHANGELOGS/selector.changes.md

---

## Purpose and Scope

Selector is a read-only information-retrieval utility invoked by other agents when they need relevant information from project documentation and the codebase. It is **not** a Council participant and does not take part in consensus, voting, or phase advancement. Its purpose is to reduce the calling agent's context load by performing discovery and reading on the caller's behalf and returning only necessary, relevant facts with references for possible clarification.

Selector is **independent** of the built-in OpenCode `explore` subagent/capability. Architectural responsibility differs: `explore` is a harness-native general navigation/search capability (where available), while Selector is a project-defined utility with a stable contract for locating and summarizing relevant docs/code with traceable references across environments where `explore` may not exist.

## Non-goals

- Participation in Council roles, discussion, consensus, or escalation as an agent role.
- Writing, modifying, or committing project artifacts (including `docs/`, `docs-manifest.yaml`, `CHANGELOGS/`); Selector is read-only.
- Replacing the Documentation Worker skill, Documenter audit, or the Operator's approval authority.
- Acting as a general-purpose autonomous coding or execution agent.

## Deployment and Invocation Contexts

Selector is intended to work in:
1. **Current fallback mode** — invoked during manual/fallback Council workflows (subagent/skill-assisted), producing outputs consumable as session artifacts or direct responses.
2. **Current coding/development tasks** — invoked by agents working on implementation to gather focused context without broad exploratory reads.
3. **Future Council runtime** — as a Supporting Service/module integrated with the Moderator/Execution Runtime under the project's layered architecture (design target; exact runtime/MCP/event wiring specified when runtime contracts are finalized).

### Interim and Final Forms

- **Interim (development):** implemented as an independent **skill + subagent** form, packaged separately from OpenCode `explore`. The interim form MUST implement the Selector contract defined here and record consulted sources for auditability in fallback sessions.
- **Final (target):** a separate module/service analogous in role to Documenter (utility, non-participant), with a versioned interface compatible with the interim contract. Transition is an operator-approved milestone with a documented checklist; compatibility guarantees: the contract/schema may evolve by addition but MUST NOT silently drop provenance, safety, or traceability fields relied upon by callers.

Context-specific rules (fallback Markdown artifacts vs future runtime structured envelopes/events) MUST NOT leak across contexts.

## Discovery and Reading Strategy

Selector begins from the caller's request and available context (including `AGENTS.md` routing guidance when applicable) and gathers information read-only.

### Documentation (docs)
- Documentation discovery MUST be **manifest-first**: resolve project documents via `docs-manifest.yaml` paths/IDs; do not blindly scan the filesystem for project docs.
- Treat English under `docs/en/` as authoritative; Russian mirrors as derivative (per project policy). Surface document `status`/version and source identity in outputs.
- **Archive sources** (`docs/en/archive/`, manifest entries with archive status): may be consulted when relevant but MUST be reported with explicit status/provenance and a warning that they are historical/non-authoritative; never present archived content as current authority. If a caller explicitly requests archive material, include it with the same warnings.

### Codebase
- Code discovery uses targeted, scoped search/read operations appropriate to the request (paths, symbols, patterns). Selector MUST remain read-only.
- Default exclusions SHOULD include non-source/session/operational noise where not relevant (e.g. `.git/`, large vendored dirs if present, and session workspaces) unless explicitly in scope; exact boundary policy is implementation-defined but MUST be reported via `searched_sources`/gaps when it materially affects results.
- The strategy is designed to be extensible so that, in future, separate rules/policies for documentation and code discovery can be applied without changing the caller-facing contract.

### Boundaries and Safety
- Selector MUST NOT write or modify files, persist caches across calls by default in the interim form, or perform actions outside read-only discovery/summarization.
- Selector MUST NOT claim Council authority or act as `explore`. Out-of-scope or disallowed reads MUST NOT be performed; limitations are reported explicitly.

## Input Contract

- **Required:** a free-form request describing the information need (question, goal, entities, or task context).
- **Optional (soft hints):** caller may include hints such as desired depth/scope (`overview` | `targeted` | `deep`), preferred source areas (docs/code), known identifiers/paths/subjects, or output emphasis. Hints guide effort and presentation but do not override safety boundaries or guarantees.
- Selector MAY ask for clarification when the request is insufficient, but when invoked non-interactively it MUST return best-effort results with explicit gaps/assumptions.

## Output Contract

Selector returns **relevant facts with references for possible clarification** in free form, with the following requirements:

1. **Relevance and concision:** include only information necessary to answer the request; avoid raw file dumps and unnecessary exploratory narration.
2. **Traceability/provenance:** every reported fact MUST be attributable to consulted sources. For each fact (or tightly grouped finding) include references sufficient for follow-up, such as:
   - documentation: manifest `id`, path, title/version/status (and section/heading/anchor or quoted excerpt when useful);
   - code: file path and location (line/range/symbol) with a brief excerpt when useful.
   Facts derived from `draft` or `archive` sources MUST carry that status.
3. **Structure (recommended):** a brief summary followed by detailed facts/findings and a gaps/limitations section. Structure may be adapted to the request, but provenance and gaps MUST remain clear.
4. **Gaps, ambiguity, and conflicts:** report not-found results, partial coverage, scope limits, ambiguity, or conflicting sources explicitly. A structured gap/warning block is RECOMMENDED, e.g. `{gap_type: not_found|partial|conflict|scope_limited|ambiguous, searched_sources: [...], suggestion: "..."}` (or equivalent free-form fields). Selector MUST NOT present uncertainty as certainty.
5. **Budgets:** to protect caller context, a single response SHOULD stay within a default per-call budget (target: ~≤4K tokens output, ≤20 files read, implementation/profile-tunable). On budget/limit hit, Selector MUST stop gracefully and report what was covered, what was omitted, and how to refine the request.

## Operational Behavior and Observability

- **Read-only and stateless by default:** no writes, no cross-call persistent cache in the interim form. Any future optimization MUST NOT serve stale results without source-state awareness.
- **Repeatability:** for the same request and unchanged relevant sources, output structure and cited references SHOULD be stable; exact wording may vary when LLM-assisted summarization is used.
- **Auditability:** Selector SHOULD make consulted sources inspectable. In fallback/interim contexts, record a summary of request intent, searched/consulted sources, and outcome/limits in the session artifacts or invocation result. In future runtime, emit an equivalent structured event/log (design target, e.g. `selector.query` with request/result metadata and consulted sources) when available.
- **Failure handling:** on missing sources, access/parse issues, or tool errors, return partial results when safe with explicit errors/gaps; never fabricate sources or facts.

## Cross-References

- `docs/en/documenter-service/index.md` — analogous non-participant utility/service pattern and thin-concept principles
- `AGENTS.md` — context routing and documentation read rules
- `docs-manifest.yaml` — authoritative index for project documentation paths/IDs
- `fallback/index.md` — fallback-mode session procedure and artifact conventions
- `docs/en/execution-runtime/index.md` — future runtime/layering design target (Selector as Supporting Service direction)
- `docs/en/glossary/index.md` — project terminology (e.g. Supporting Service, Primary/Subagent)
