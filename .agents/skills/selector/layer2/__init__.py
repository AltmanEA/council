"""Selector Layer 2 — facts + references (deterministic, versioned, injection-safe).

This package is the Layer 2 core of the Selector.  It extends Layer 1 with:
  - verifiable references (sources[] with sha256),
  - evidence facts (facts[] with claim + source links),
  - injection detection / sanitisation,
  - budget-aware truncation,
  - additive Layer 2 fields (modes, integrity, contract_version, form).

Public API (entry-point `selector_layer2`):
  - run_query(manifest_path, query, *, …) -> {output, audit, audit_path}
  - validate_output_v2(output) -> list[str]
  - sanitize.scrub(text) -> (cleaned, count)
  - sources.resolve_doc(entry, repo_root) -> str
  - code.search(repo_root, query, excluded_paths) -> list[str]
  - constants: CONTRACT_VERSION, DEFAULT_CODE_MODE, CEILING_FILES/TOKENS, …
"""

# ── Submodule imports (relative + absolute fallback for importlib compatibility) ──

try:
    from . import sources
    from . import code
    from . import evidence
    from . import sanitize
    from . import budget
    from . import contract
    from . import manifest
except ImportError:
    import importlib, sys

    _layer2_dir = __path__[0]

    sources = importlib.import_module("selector_layer2.sources")
    code = importlib.import_module("selector_layer2.code")
    evidence = importlib.import_module("selector_layer2.evidence")
    sanitize = importlib.import_module("selector_layer2.sanitize")
    budget = importlib.import_module("selector_layer2.budget")
    contract = importlib.import_module("selector_layer2.contract")
    manifest = importlib.import_module("selector_layer2.manifest")

# ── Re-export submodules as attributes (required by tests) ──

__all__ = [
    "run_query",
    "validate_output_v2",
    "CONTRACT_VERSION",
    "DEFAULT_CODE_MODE",
    "CEILING_FILES",
    "CEILING_TOKENS",
    "DEFAULT_FILES",
    "DEFAULT_TOKENS",
]
