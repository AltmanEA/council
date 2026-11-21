"""Selector dual-run harness — Layer 1 / Layer 2 comparison.

Runs N = PAIRS pairs of queries through Layer 1 and Layer 2 via the adapter,
collects compact results, and produces an audit ledger (JSON).

Public API:
    PAIRS = 20
    DEFAULT_QUERIES: tuple[str, ...]  # 20 frozen queries
    LEDGER_FIELDS: tuple[str, ...]
    run_pair(manifest_path, query, *, call_id, repo_root=None, audit_dir=None) -> dict
    collect(manifest_path, *, queries=None, repo_root=None) -> dict  (ledger)
    write_ledger(ledger, path) -> str
"""

import copy
import hashlib
import importlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

# ── Constants ───────────────────────────────────────────────────────────────

PAIRS: int = 20

DEFAULT_MODE: str = "layer2"

DEFAULT_QUERIES: tuple[str, ...] = (
    "selector specification",
    "documentation rules",
    "documenter service audit contract",
    "fallback mode procedure",
    "manifest integrity sha256",
    "budget ceiling and truncation",
    "injection defence",
    "provenance and references",
    "draft and archive labels",
    "Layer 2 contract",
    "translation policy",
    "operator approval",
    "moderator runtime",
    "execution runtime",
    "project concept",
    "protocol core",
    "glossary terminology",
    "audit artifact",
    "read-only guarantees",
    "gap reporting",
)

LEDGER_FIELDS: tuple[str, ...] = (
    "kind",
    "contract_version",
    "form_scope",
    "pairs",
    "manifest_sha256",
    "manifest_sha256_unchanged",
    "default_mode",
    "results",
    "metrics",
    "observational_only",
    "gates",
)

# ── Path helpers ────────────────────────────────────────────────────────────

_DUALRUN_DIR: Path = Path(__file__).resolve().parent
_SELECTORS_DIR: Path = _DUALRUN_DIR.parent  # .agents/skills/selector
_RUNTIME_PATH: str = str(_DUALRUN_DIR / "selector_runtime.py")
_ADAPTER_PATH: str = str(_DUALRUN_DIR / "layer2_adapter.py")
_LAYER2_DIR: Path = _SELECTORS_DIR / "layer2"
_LAYER2_PATH: str = str(_LAYER2_DIR / "selector_layer2.py")

# ── Lazy import helpers ─────────────────────────────────────────────────────

_adapter = None


def _load_adapter():
    """Load (or reuse) the layer2_adapter module."""
    global _adapter
    if _adapter is None:
        if "selector_layer2_adapter" in sys.modules:
            _adapter = sys.modules["selector_layer2_adapter"]
        else:
            _adapter = _load_module("selector_layer2_adapter", _ADAPTER_PATH)
    return _adapter


def _load_module(name, file_path, subs=None):
    """Load a module from *file_path* (reuse sys.modules cache)."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, file_path, submodule_search_locations=subs
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create spec for {name} at {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# ── SHA-256 helper ──────────────────────────────────────────────────────────

def _sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


# ── run_pair ────────────────────────────────────────────────────────────────

def run_pair(manifest_path, query, *, call_id, repo_root=None, audit_dir=None):
    """Run one query through both layers and return a compact pair dict."""
    import uuid
    if call_id is None:
        call_id = uuid.uuid4().hex[:8]

    adapter = _load_adapter()

    # ── Layer 1 ─────────────────────────────────────────────────────────
    l1_result = adapter.run(
        "layer1", manifest_path, query,
        call_id=call_id + "-l1", audit_dir=audit_dir, repo_root=repo_root,
    )
    l1_output = l1_result["output"]

    l1_gap = l1_output.get("gap", {})
    l1_ranked_ids = l1_output.get("ranked_ids", {})

    # ranked_ids is dict[str, item]; extract IDs in rank order
    if isinstance(l1_ranked_ids, dict):
        l1_ids_list = [
            k for k, v in sorted(l1_ranked_ids.items(),
                                  key=lambda kv: (kv[1].get("rank"), kv[0]))
        ] if l1_ranked_ids else []
    else:
        l1_ids_list = list(l1_ranked_ids) if l1_ranked_ids else []

    l1_data = {
        "ranked_ids": l1_ids_list,
        "gap_type": l1_gap.get("gap_type", "none") if isinstance(l1_gap, dict) else "none",
        "truncated": l1_output.get("truncated", False),
    }

    # ── Layer 2 ─────────────────────────────────────────────────────────
    l2_result = adapter.run(
        "layer2", manifest_path, query,
        call_id=call_id + "-l2",
        audit_dir=audit_dir, repo_root=repo_root,
    )
    l2_output = l2_result["output"]

    l2_gap = l2_output.get("gap", {})
    l2_ranked_ids = l2_output.get("ranked_ids", {})

    if isinstance(l2_ranked_ids, dict):
        l2_ids_list = [
            k for k, v in sorted(l2_ranked_ids.items(),
                                  key=lambda kv: (kv[1].get("rank"), kv[0]))
        ] if l2_ranked_ids else []
    else:
        l2_ids_list = list(l2_ranked_ids) if l2_ranked_ids else []

    l2_data = {
        "ranked_ids": l2_ids_list,
        "gap_type": l2_gap.get("gap_type", "none") if isinstance(l2_gap, dict) else "none",
        "truncated": l2_output.get("truncated", False),
        "sources_count": len(l2_output.get("sources", [])) if isinstance(l2_output.get("sources"), list) else 0,
        "code_mode": l2_output.get("modes", {}).get("code", "off"),
        "injection_detected": (
            l2_output.get("integrity", {}).get("injection_detected", False)
            if isinstance(l2_output.get("integrity"), dict)
            else False
        ),
    }

    # ── Jaccard similarity ──────────────────────────────────────────────
    s1 = set(l1_ids_list) if l1_ids_list else set()
    s2 = set(l2_ids_list) if l2_ids_list else set()
    if s1 or s2:
        intersection = len(s1 & s2)
        union = len(s1 | s2)
        rank_overlap = intersection / union
    else:
        rank_overlap = 1.0  # both empty → perfect overlap

    return {
        "index": 0,  # placeholder — filled by collect()
        "query": query,
        "layer1": l1_data,
        "layer2": l2_data,
        "rank_overlap": rank_overlap,
        # Preserve full output for validator tests (stripped before JSON write)
        "_l1_output": l1_output,
        "_l2_output": l2_output,
    }


# ── collect ─────────────────────────────────────────────────────────────────

def collect(manifest_path, *, queries=None, repo_root=None):
    """Run all pairs and return the full ledger dict."""
    if queries is None:
        queries = DEFAULT_QUERIES

    # Read #1: SHA-256 BEFORE the 40 runs (real read, not a local ref)
    sha_before = _sha256_of(manifest_path)

    # Use TemporaryDirectory() as context manager — dir is removed on exit.
    with tempfile.TemporaryDirectory() as tmpdir:
        pairs = []
        audit_files_written = 0

        for i, query in enumerate(queries):
            audit_dir = os.path.join(tmpdir, f"pair_{i:02d}")
            pair = run_pair(
                manifest_path, query,
                call_id=f"dual-{i:02d}",
                repo_root=repo_root,
                audit_dir=audit_dir,
            )
            pair["index"] = i
            pairs.append(pair)

            # Count written audit files
            if os.path.isdir(audit_dir):
                audit_files_written += len(os.listdir(audit_dir))

    # Read #2: SHA-256 AFTER the 40 runs (real read)
    sha_after = _sha256_of(manifest_path)
    manifest_sha_unchanged = (sha_before == sha_after)
    manifest_sha = sha_before  # keep original for ledger

    # ── Aggregate metrics ───────────────────────────────────────────────
    overlaps = [p["rank_overlap"] for p in pairs]
    rank_overlap_mean = sum(overlaps) / len(overlaps) if overlaps else 0.0
    rank_overlap_min = min(overlaps) if overlaps else 0.0
    rank_overlap_max = max(overlaps) if overlaps else 0.0
    exact_rank_match_count = sum(
        1 for p in pairs
        if p["layer1"]["ranked_ids"] == p["layer2"]["ranked_ids"]
    )

    gap_dist_l1 = {}
    gap_dist_l2 = {}
    for p in pairs:
        gt1 = p["layer1"]["gap_type"]
        gap_dist_l1[gt1] = gap_dist_l1.get(gt1, 0) + 1
        gt2 = p["layer2"]["gap_type"]
        gap_dist_l2[gt2] = gap_dist_l2.get(gt2, 0) + 1

    trunc_l1 = sum(1 for p in pairs if p["layer1"]["truncated"])
    trunc_l2 = sum(1 for p in pairs if p["layer2"]["truncated"])

    inj_count = sum(
        1 for p in pairs if p["layer2"].get("injection_detected", False)
    )

    code_mode_dist = {"off": 0, "on": 0}
    for p in pairs:
        cm = p["layer2"].get("code_mode", "off")
        if cm in code_mode_dist:
            code_mode_dist[cm] += 1
        else:
            code_mode_dist[cm] = code_mode_dist.get(cm, 0) + 1

    # ── Count validation errors (via runtime + layer2 validators) ──────
    runtime_mod = _load_module("selector_runtime", _RUNTIME_PATH)
    layer2_mod = _load_module("selector_layer2", _LAYER2_PATH,
                              subs=[str(_LAYER2_DIR)])

    validation_error_count = 0

    for p in pairs:
        l1_out = p["_l1_output"]
        l1_errors = runtime_mod.validate_output(l1_out) if isinstance(l1_out, dict) else []
        validation_error_count += len(l1_errors)

        l2_out = p["_l2_output"]
        if isinstance(l2_out, dict):
            l2_errors = runtime_mod.validate_output(l2_out)
            validation_error_count += len(l2_errors)
            if hasattr(layer2_mod, "validate_output_v2"):
                validation_error_count += len(layer2_mod.validate_output_v2(l2_out))

    # ── Build compact results with redaction ────────────────────────────
    # Deep-copy outputs, redact facts[].claim, strip request_intent.
    compact_results = []
    for p in pairs:
        layer1_out = copy.deepcopy(p["_l1_output"]) if isinstance(p["_l1_output"], dict) else {}
        layer2_out = copy.deepcopy(p["_l2_output"]) if isinstance(p["_l2_output"], dict) else {}

        # Strip request_intent from both
        layer1_out.pop("request_intent", None)
        layer2_out.pop("request_intent", None)

        # Redact facts[].claim in layer2 (keep sources/status for v2 validation)
        if "facts" in layer2_out and isinstance(layer2_out["facts"], list):
            for fact in layer2_out["facts"]:
                if isinstance(fact, dict) and "claim" in fact:
                    fact["claim"] = "[redacted]"

        # Layer 1 compact: add top-level gap_type for test compat
        layer1_out["gap_type"] = (
            layer1_out.get("gap", {}).get("gap_type", "none")
            if isinstance(layer1_out.get("gap"), dict) else "none"
        )

        # Layer 2 compact: include all v2 fields + top-level helpers
        layer2_out["sources_count"] = len(layer2_out.get("sources", []))
        layer2_out["code_mode"] = layer2_out.get("modes", {}).get("code", "off")
        layer2_out["gap_type"] = (
            layer2_out.get("gap", {}).get("gap_type", "none")
            if isinstance(layer2_out.get("gap"), dict) else "none"
        )
        layer2_out["injection_detected"] = (
            layer2_out.get("integrity", {}).get("injection_detected", False)
            if isinstance(layer2_out.get("integrity"), dict) else False
        )

        compact_results.append({
            "index": p["index"],
            "query": p["query"],
            "layer1": layer1_out,
            "layer2": layer2_out,
            "rank_overlap": p["rank_overlap"],
        })

    # Clean up internal data from pairs
    for p in pairs:
        if "_l1_output" in p:
            del p["_l1_output"]
        if "_l2_output" in p:
            del p["_l2_output"]

    # ── Ledger ──────────────────────────────────────────────────────────
    ledger = {
        "kind": "selector-dual-run-ledger",
        "contract_version": "2.0.0",
        "form_scope": "Layer 2 default / Layer 1 opt-out",
        "pairs": PAIRS,
        "manifest_sha256": manifest_sha,
        "manifest_sha256_unchanged": manifest_sha_unchanged,
        "default_mode": DEFAULT_MODE,
        "results": compact_results,
        "metrics": {
            "rank_overlap_mean": rank_overlap_mean,
            "rank_overlap_min": rank_overlap_min,
            "rank_overlap_max": rank_overlap_max,
            "exact_rank_match_count": exact_rank_match_count,
            "gap_type_distribution": {
                "layer1": gap_dist_l1,
                "layer2": gap_dist_l2,
            },
            "truncated_count": {
                "layer1": trunc_l1,
                "layer2": trunc_l2,
            },
            "injection_detected_count": inj_count,
            "code_mode_distribution": code_mode_dist,
            "validation_error_count": validation_error_count,
        },
        "observational_only": True,
        "gates": [],
    }

    ledger["audit_files_written"] = audit_files_written

    return ledger


# ── write_ledger ────────────────────────────────────────────────────────────

def write_ledger(ledger, path):
    """Write ledger to JSON. Env var SELECTOR_DUALRUN_LEDGER takes priority."""
    env_path = os.environ.get("SELECTOR_DUALRUN_LEDGER")
    if env_path is not None:
        path = env_path

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(ledger, f, sort_keys=True, indent=2)

    return path
