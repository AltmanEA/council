"""Selector Layer 2 adapter — thin in-process routing between Layer 1 and Layer 2.

Public API:

    MODE_LAYER1 = "layer1"
    MODE_LAYER2 = "layer2"
    DEFAULT_MODE = MODE_LAYER2

    resolve_mode(mode) -> "layer1" | "layer2"
        None / "" / "layer2" -> "layer2" (default)
        "layer1"             -> "layer1" (explicit opt-out)
        anything else        -> ValueError (fail-closed)

    run(mode, manifest_path, query, *, hints=None, reveal_code=False,
        audit_dir=None, call_id=None, repo_root=None) -> {
            "output": dict, "audit": dict, "audit_path": str
        }

The adapter performs zero I/O of its own — it only dispatches to the
underlying runtime modules.  All paths are computed relative to __file__.
"""

import importlib.util
import sys
from pathlib import Path

# ── Module-level constants ──────────────────────────────────────────────────

MODE_LAYER1: str = "layer1"
MODE_LAYER2: str = "layer2"
DEFAULT_MODE: str = MODE_LAYER2

# ── Path helpers ────────────────────────────────────────────────────────────

_SELECTOR: Path = Path(__file__).resolve().parents[1]  # .agents/skills/selector
_RUNTIME_DIR: Path = _SELECTOR / "runtime"
_LAYER2_DIR: Path = _SELECTOR / "layer2"

# ── Lazy module loader ─────────────────────────────────────────────────────

def _load_module(name: str, file_path: str, subs=None):
    """Load (or re-use) a module from an absolute file path.

    1. If *name* is already in ``sys.modules``, return it (tests preload
       ``selector_runtime`` and ``selector_layer2`` there).
    2. Otherwise create an importlib spec with ``submodule_search_locations``
       when *subs* is given, instantiate and execute it, then register in
       ``sys.modules``.
    3. On failure raise ``ImportError`` with a clear path.
    """
    if name in sys.modules:
        return sys.modules[name]

    spec = importlib.util.spec_from_file_location(name, file_path, submodule_search_locations=subs)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create spec for {name} at {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Deferred references (resolved on first call)
_runtime_mod = None
_layer2_mod = None


def _ensure_modules():
    global _runtime_mod, _layer2_mod
    if _runtime_mod is None:
        _runtime_mod = _load_module(
            "selector_runtime",
            str(_RUNTIME_DIR / "selector_runtime.py"),
        )
    if _layer2_mod is None:
        _layer2_mod = _load_module(
            "selector_layer2",
            str(_LAYER2_DIR / "selector_layer2.py"),
            subs=[str(_LAYER2_DIR)],
        )


# ── Public API ──────────────────────────────────────────────────────────────

def resolve_mode(mode):
    """Normalise a mode token to ``'layer1'`` or ``'layer2'``.

    Args:
        mode: ``None``, ``""`` (default), ``"layer2"``, ``"layer1"`` (opt-out),
            or anything else.

    Returns:
        ``"layer2"`` for unset/default calls, ``"layer1"`` on explicit opt-out.

    Raises:
        ValueError for any value other than None, empty string,
        ``"layer1"``, or ``"layer2"``.
    """
    if mode is None or mode == "" or mode == MODE_LAYER2:
        return MODE_LAYER2
    if mode == MODE_LAYER1:
        return MODE_LAYER1
    raise ValueError(f"Unknown mode: {mode!r} — expected 'layer1' or 'layer2'")


def run(mode, manifest_path, query, *, hints=None, reveal_code=False,
        audit_dir=None, call_id=None, repo_root=None):
    """Dispatch *query* through the selected Selector layer.

    Args:
        mode:     Layer selector (see ``resolve_mode``).
        manifest_path: Path to ``docs-manifest.yaml``.
        query:    Natural-language query string.
        hints:    Optional budget hints {max_files, max_tokens, excluded_paths}.
        reveal_code: Whether to include code search results (Layer 2 only).
        audit_dir: Directory to write audit markdown (``None`` = skip).
        call_id:   Opaque call identifier used in audit filenames.
        repo_root: Absolute path to the repository root (Layer 2 only).

    Returns:
        ``{"output": dict, "audit": dict, "audit_path": str}``

    Raises:
        ValueError if *mode* is not ``"layer1"`` or ``"layer2"``.
    """
    mode = resolve_mode(mode)
    _ensure_modules()

    if mode == "layer1":
        # Layer 1 does not understand reveal_code / repo_root.
        return _runtime_mod.run_query(
            manifest_path, query,
            hints=hints, audit_dir=audit_dir, call_id=call_id,
        )

    # Layer 2
    return _layer2_mod.run_query(
        manifest_path, query,
        hints=hints, reveal_code=reveal_code,
        audit_dir=audit_dir, call_id=call_id, repo_root=repo_root,
    )
