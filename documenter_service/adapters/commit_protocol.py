"""Multi-file commit protocol — Documenter §Safety Protocol #9.

Public API (all docstrings reference index.md §Safety Protocol #9):

  * commit_rank(rel_path)          → int     (priority rank)
  * sort_for_commit(rel_paths)     → list    (ordered paths)
  * allowed_changeset_paths(manifest) → set  (manifest-tracked roots)
  * validate_changeset_paths(rel_paths, manifest) → None  (R2: manifest-tracked)
  * validate_changeset_scope(rel_paths, manifest, target_id) → None  (R3: target-scope)
  * stage_bytes(root, rel_path, data, tx_id)   → str  (absolute .tmp path)
  * write_intent(data_dir, tx_id, record)       → str  (atomic temp+rename)
  * read_intent(data_dir, tx_id)                → dict|None
  * scan_intents(data_dir)                        → list[dict]
  * _valid_intent(record)                         → bool  (accepts "missing" sentinel)
  * delete_intent(data_dir, tx_id)                → None
  * ordered_renames(root, entries, sha_func)      → list[str]
  * _hash_matches(value, expected)                → bool
"""
from __future__ import annotations

import json
import os
import re
import uuid
from hashlib import sha256 as _sha256

from ..core.errors import StructuredError

__all__ = [
    "commit_rank",
    "sort_for_commit",
    "allowed_changeset_paths",
    "validate_changeset_paths",
    "validate_changeset_scope",
    "stage_bytes",
    "write_intent",
    "read_intent",
    "scan_intents",
    "delete_intent",
    "ordered_renames",
    "_hash_matches",
]

# ---------------------------------------------------------------------------
# Rank constants (index.md #9c — ordered renames)
# ---------------------------------------------------------------------------

RANK_DOCUMENT = 0
RANK_RU = 1
RANK_CHANGELOG = 2
RANK_MANIFEST = 3
RANK_HASHES = 4


def commit_rank(rel_path: str) -> int:
    """Return the commit-priority rank for *rel_path*.

    Per index.md §Safety Protocol #9c the fixed order is:

        0  document content (primary index.md or any non-RU / non-changelog file)
        1  index-RU.md (relative path contains 'index-RU.md')
        2  changelog  (path contains 'CHANGELOGS/' AND ends with '.changes.md')
        3  docs-manifest.yaml
        4  documenter/hashes.json

    Unknown paths (not matching any of the above) return rank 0 (document
    content category).  Ranks are compared lexicographically (stable sort).
    """
    # Normalise to POSIX for consistent matching (spec uses /).
    norm = rel_path.replace("\\", "/")

    # Rank 3 — manifest
    if norm == "docs-manifest.yaml":
        return RANK_MANIFEST

    # Rank 4 — hash store
    if norm == "documenter/hashes.json":
        return RANK_HASHES

    # Rank 1 — RU translation
    if "index-RU.md" in norm:
        return RANK_RU

    # Rank 2 — changelog
    if "CHANGELOGS/" in norm and norm.endswith(".changes.md"):
        return RANK_CHANGELOG

    # Everything else falls into rank 0 (document content).
    return RANK_DOCUMENT


def sort_for_commit(rel_paths):
    """Return *rel_paths* sorted by (commit_rank, path), stable.

    Accepts either strings (raw rel_paths) or dicts with a ``path`` key
    (entries from an intent record).  The returned list has the same
    element type as the input.
    """
    def _key(item):
        p = item if isinstance(item, str) else item.get("path", "")
        return (commit_rank(p), p)
    return sorted(rel_paths, key=_key)


def allowed_changeset_paths(manifest):
    """Return the set of manifest-tracked paths allowed in a changeset.

    Per index.md #9b — intent record entries MUST reference only
    manifest-tracked file paths.

    The returned set contains:

      - Every manifest entry's ``path`` (POSIX-normalised).
      - Every manifest entry's ``has_translation`` path (when present,
        POSIX-normalised).
      - The literal strings ``"docs-manifest.yaml"`` and
        ``"documenter/hashes.json"``.
      - Changelog paths from manifest entries that carry a
        ``changelog-path`` field (POSIX-normalised).
    """
    allowed = set()
    allowed.add("docs-manifest.yaml")
    allowed.add("documenter/hashes.json")

    for entry in manifest.entries():
        # Main path
        p = entry.get("path", "")
        if p:
            allowed.add(p.replace("\\", "/"))

        # RU translation (has_translation is relative path from manifest
        # location to the RU file — AGENTS.md §2.2).
        ru = entry.get("has_translation")
        if ru:
            allowed.add(ru.replace("\\", "/"))

        # Changelog (from frontmatter changelog-path when present).
        chlog = entry.get("changelog-path")
        if chlog:
            allowed.add(chlog.replace("\\", "/"))

    return allowed


def validate_changeset_paths(rel_paths, manifest):
    """Raise StructuredError when any *rel_path* is not manifest-tracked.

    Per index.md #9b: "Any attempt to stage a non-manifest path during a
    changeset causes delegate() to reject with error_category: unknown and
    no writes proceed."
    """
    allowed = allowed_changeset_paths(manifest)
    for p in rel_paths:
        norm = p.replace("\\", "/")
        if norm not in allowed:
            raise StructuredError(
                "unknown",
                f"changeset path {p!r} is not manifest-tracked — "
                "no writes proceed (index.md §Safety Protocol #9b)")


def validate_changeset_scope(rel_paths, manifest, target_id, policy_entry=None):
    """Second-level scope guard (fix plan p.15, R3): changeset paths may
    only touch the target's own file-set plus commit bookkeeping.

    Allowed (exact paths only — no directory prefixes, so a changeset
    can never write sibling documents or foreign changelogs):

      - <target path> (the target document itself, when repeated in the
        changeset — still checked for duplication elsewhere),
      - <target changelog> (manifest ``changelog-path`` of the target),
      - <target translation> (manifest ``has_translation`` of the target),
      - ``docs-manifest.yaml`` and ``documenter/hashes.json`` (bookkeeping).

    Anything else → StructuredError("unknown", ...) before any writes.

    This is distinct from validate_changeset_paths: that function checks
    manifest-tracked inclusion (R2), while this function checks that the
    changeset only modifies the target document's own scope (R3).  Both
    guards must pass before any writes proceed.

    Parameters
    ----------
    rel_paths : list[str]
        Normalized path strings from the changeset.
    manifest : ManifestSource
        Manifest source to resolve target entry.
    target_id : str
        Target document identifier.
    policy_entry : dict, optional
        Reserved for policy-declared extra scope (post-MVP).  Unused in
        the MVP implementation; kept to preserve the planned interface.
    """
    entry = manifest.resolve(target_id) or {}
    allowed = set()

    # Exact target file-set paths.
    for key in ("path", "changelog-path", "has_translation"):
        v = entry.get(key)
        if v:
            allowed.add(str(v).replace("\\", "/"))

    # Always allowed bookkeeping paths
    allowed.add("docs-manifest.yaml")
    allowed.add("documenter/hashes.json")

    for p in rel_paths:
        norm = p.replace("\\", "/")
        if norm in allowed:
            continue
        raise StructuredError(
            "unknown",
            f"changeset path {p!r} is outside the target scope of "
            f"{target_id!r} (only target file, its changelog, its "
            "translation, docs-manifest.yaml, documenter/hashes.json "
            "are permitted)")


# ---------------------------------------------------------------------------
# Staging (index.md #9a)
# ---------------------------------------------------------------------------


def stage_bytes(root, rel_path, data: bytes, tx_id: str) -> str:
    """Write *data* to a staging temp file in the target directory.

    Per index.md #9a: all new content is staged to ``.tmp`` paths in their
    target directories.  Temp files MUST NOT be placed in ``/tmp``.

    Naming convention: ``.<basename>.<tx16>.tmp`` where tx16 is the first
    16 hex characters of *tx_id*.  Written via ``os.open`` (O_WRONLY |
    O_CREAT | O_TRUNC, 0o644) with fsync.

    Returns the absolute path of the created temp file.
    """
    target_abs = os.path.join(root, rel_path)
    target_dir = os.path.dirname(target_abs)
    basename = os.path.basename(target_abs)
    tx16 = tx_id[:16]
    staged_name = f".{basename}.{tx16}.tmp"
    tmp_path = os.path.join(target_dir, staged_name)

    # Ensure parent directory exists (e.g. staging a file in a new dir).
    os.makedirs(target_dir, exist_ok=True)

    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)

    return os.path.abspath(tmp_path)


# ---------------------------------------------------------------------------
# Intent record I/O (index.md #9b)
# ---------------------------------------------------------------------------


def write_intent(data_dir, tx_id, record) -> str:
    """Atomically write the intent record to ``<data_dir>/intent/<tx_id>.json``.

    Per index.md #9b and configuration-guide.md §Intent Record: write via
    temp-file + fsync + os.replace + fsync(dir).

    Validates the record structure BEFORE writing; an invalid record raises
    StructuredError("unknown", ...) and the file is NOT created.

    Returns the absolute path of the written intent file.
    """
    if not _valid_intent(record):
        raise StructuredError(
            "unknown",
            "intent record validation failed — structure is invalid "
            "(index.md §Safety Protocol #9b)")

    intent_dir = os.path.join(data_dir, "intent")
    os.makedirs(intent_dir, exist_ok=True)

    intent_file = os.path.join(intent_dir, f"{tx_id}.json")
    tmp_file = intent_file + ".tmp"

    fd = os.open(tmp_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, json.dumps(record).encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)

    os.replace(tmp_file, intent_file)

    # fsync the intent directory so the intent file is durable BEFORE
    # any renames begin (crash-safety per §5 pattern).
    dir_fd = os.open(intent_dir, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)

    return os.path.abspath(intent_file)


def read_intent(data_dir, tx_id):
    """Read and validate the intent record for *tx_id*.

    Returns the parsed dict when the file exists and has valid structure,
    otherwise returns None (skip semantics per configuration-guide.md
    §Intent Record: "corrupted or incomplete intent records are logged and
    skipped").

    Also skips if the filename tx_id doesn't match record["tx_id"].
    """
    intent_file = os.path.join(data_dir, "intent", f"{tx_id}.json")
    if not os.path.exists(intent_file):
        return None

    try:
        with open(intent_file, encoding="utf-8") as f:
            record = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    if _valid_intent(record):
        return record
    return None


def scan_intents(data_dir):
    """Return a list of all valid intent records found in ``<data_dir>/intent/*.json``.

    Invalid files are silently skipped (log-and-skip semantics per
    configuration-guide.md §Intent Record).  When the filename tx_id
    does not match record["tx_id"], the record is skipped.
    """
    intent_dir = os.path.join(data_dir, "intent")
    if not os.path.isdir(intent_dir):
        return []

    results = []
    for fname in os.listdir(intent_dir):
        if not fname.endswith(".json"):
            continue
        filepath = os.path.join(intent_dir, fname)
        tx_id_from_file = fname[:-5]  # strip .json

        record = read_intent(data_dir, tx_id_from_file)
        if record is None:
            continue

        # Verify filename tx_id matches record tx_id.
        if record.get("tx_id") != tx_id_from_file:
            continue

        results.append(record)

    return results


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


_SHA256_HEX_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _hash_matches(value, expected):
    """Return True when *value* matches the expected sha256:<hex> format.

    Both must be strings, both must start with ``sha256:`` and have exactly
    64 lowercase hex characters after the prefix.
    """
    if not isinstance(value, str) or not isinstance(expected, str):
        return False
    return value == expected


def _valid_intent(record) -> bool:
    """Return True when *record* is a well-formed intent record.

    Schema (configuration-guide.md §Intent Record):

        {
            tx_id: uuid-v4 string,
            target_id: string,
            created_at: ISO8601Z string,
            entries: [
                {
                    path: string,
                    tmp_path: string,
                    before_hash: sha256:<64-hex> | "missing",
                    after_hash: sha256:<64-hex>
                },
                ...
            ]
        }

    *before_hash* may be "missing" (sentinel) for create operations where
    the target file does not yet exist on disk.  *after_hash* must always be
    a valid sha256:<64-hex>.

    Returns False when any required field is missing / wrong type, or
    when entries is empty / any entry has malformed hash fields.
    """
    if not isinstance(record, dict):
        return False

    # Top-level fields.
    tx_id = record.get("tx_id")
    target_id = record.get("target_id")
    created_at = record.get("created_at")
    entries = record.get("entries")

    if not isinstance(tx_id, str) or not tx_id:
        return False
    if not isinstance(target_id, str) or not target_id:
        return False
    if not isinstance(created_at, str) or not created_at:
        return False

    # Entries must be a non-empty list.
    if not isinstance(entries, list) or len(entries) == 0:
        return False

    for entry in entries:
        if not isinstance(entry, dict):
            return False
        # Required keys.
        path = entry.get("path")
        tmp_path = entry.get("tmp_path")
        before_hash = entry.get("before_hash")
        after_hash = entry.get("after_hash")

        if not isinstance(path, str) or not path:
            return False
        if not isinstance(tmp_path, str) or not tmp_path:
            return False
        # before_hash: sha256:<64-hex> or the "missing" sentinel (create ops).
        if before_hash not in ("missing",) and not _SHA256_HEX_RE.match(before_hash or ""):
            return False
        if not _SHA256_HEX_RE.match(after_hash or ""):
            return False

    return True


# ---------------------------------------------------------------------------
# Cleanup (index.md #9d)
# ---------------------------------------------------------------------------


def delete_intent(data_dir, tx_id):
    """Best-effort removal of the intent file ``<data_dir>/intent/<tx_id>.json``.

    Per index.md #9d: "The intent record MUST be the last element removed".
    """
    intent_file = os.path.join(data_dir, "intent", f"{tx_id}.json")
    try:
        os.remove(intent_file)
    except OSError:
        pass  # best-effort — file may already be gone


# ---------------------------------------------------------------------------
# Ordered renames (index.md #9c → 9d)
# ---------------------------------------------------------------------------


def ordered_renames(root, entries, sha_func=None):
    """Rename staged files to their final paths in commit order.

    Per index.md #9c: entries are processed in sorted order
    (sort_for_commit).  For each entry:

      1. tmp_path must exist (else StructuredError("hash_mismatch")).
      2. sha256(tmp) == after_hash (else StructuredError("hash_mismatch",
         next_action="resolve_finding")).
      3. os.replace(tmp, root/path).
      4. fsync the target directory.

    Returns the list of successfully renamed relative paths (empty list
    on failure because we stop at the first error *before* doing any
    renames beyond the failing entry — partial renames cannot happen
    before the bad entry because we process in sorted order).
    """
    from ..core.errors import StructuredError

    hasher = sha_func or (lambda b: "sha256:" + _sha256(b).hexdigest())
    ordered = sort_for_commit(entries)

    renamed_paths = []

    for entry in ordered:
        tmp_path = entry.get("tmp_path", "")
        rel_path = entry.get("path", "")

        # Check tmp exists.
        if not os.path.exists(tmp_path):
            raise StructuredError(
                "hash_mismatch",
                f"staged file missing: {tmp_path!r} "
                "(multi-file commit protocol requires all staged files "
                "to exist before rename)",
                next_action="resolve_finding")

        # Verify hash.
        with open(tmp_path, "rb") as f:
            tmp_bytes = f.read()
        actual_hash = hasher(tmp_bytes)
        expected_hash = entry.get("after_hash", "")
        if actual_hash != expected_hash:
            raise StructuredError(
                "hash_mismatch",
                f"hash mismatch for staged file {tmp_path!r}: "
                f"expected {expected_hash}, got {actual_hash} "
                "(next_action: resolve_finding)",
                next_action="resolve_finding")

        # Perform atomic rename.
        target_abs = os.path.join(root, rel_path)
        target_dir = os.path.dirname(target_abs)
        os.makedirs(target_dir, exist_ok=True)
        os.replace(tmp_path, target_abs)

        # fsync the target directory.
        dir_fd = os.open(target_dir, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

        renamed_paths.append(rel_path)

    return renamed_paths
