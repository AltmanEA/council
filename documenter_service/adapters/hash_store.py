"""Hash Store — content-hash cache for the Documenter Service.

File: ``<data_dir>/hashes.json`` (default ``documenter/hashes.json``).
Managed exclusively by Documenter; hidden from operator.

Provides optimistic concurrency control via per-file SHA-256 snapshot
tokens.  History entries form an append-only audit trail that accumulates
indefinitely — each time a file's hash changes, the previous hash (with
timestamp) is appended; this never truncates.

Self-healing (chosen combination: atomic write + .bak rotation):
  1. Before writing, copy the existing hashes.json → hashes.json.bak
  2. Write to a temp file, fsync, then os.rename → hashes.json (atomic)
  3. fsync the directory to ensure the rename is durable

Load fallback: if hashes.json is missing, has invalid JSON, or fails
structural validation, hashes.json.bak is tried next.  If both fail,
an empty structure is returned (cache miss).

Cold-start integrity: on any parse/structure error the store is treated as a
cache miss — rebuilt from scratch (ADR-010: rebuildable cache).

AGENTS.md §8: tool-prose contract must match implementation; this module's
behaviour (atomic write + .bak + rebuild-on-corruption + append-only
history) is the canonical specification.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone

__all__ = ["HashStore"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HASH_RE = "sha256:[0-9a-f]{64}"


def _sha256_file(path: str) -> str:
    """Return ``sha256:<64-hex>`` for the file at *path*."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _utc_now() -> str:
    """ISO 8601 UTC timestamp ending with ``Z``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_entry(data: dict) -> bool:
    """Return True when *data* has a valid hashes.json structure."""
    if not isinstance(data, dict):
        return False
    if data.get("version") != 1:
        return False
    entries = data.get("entries")
    if not isinstance(entries, dict):
        return False
    for path, entry in entries.items():
        if not isinstance(entry, dict):
            return False
        lh = entry.get("last_hash")
        if not isinstance(lh, str) or not lh.startswith("sha256:"):
            return False
        hex_part = lh[7:]
        if len(hex_part) != 64 or not all(c in "0123456789abcdef" for c in hex_part):
            return False
        lm = entry.get("last_modified")
        if not isinstance(lm, str):
            return False
        hist = entry.get("history")
        if not isinstance(hist, list):
            return False
        for h in hist:
            if not isinstance(h, dict):
                return False
            if not isinstance(h.get("hash"), str) or not h["hash"].startswith("sha256:"):
                return False
            if not isinstance(h.get("timestamp"), str):
                return False
    return True


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class HashStore:
    """File-backed content-hash cache.

    Parameters
    ----------
    data_dir : str
        Directory that holds ``hashes.json`` (and ``hashes.json.bak``).
    root : str
        Repository root — used to resolve relative paths from the manifest.
    clock : callable, optional
        ``() -> str`` returning an ISO 8601 ``Z`` timestamp.  Defaults to
        the current UTC time.
    """

    def __init__(self, data_dir: str, root: str, clock=None) -> None:
        self.data_dir = os.path.abspath(data_dir)
        self.root = os.path.abspath(root)
        self._clock = clock or _utc_now
        self._path = os.path.join(self.data_dir, "hashes.json")
        self._bak_path = os.path.join(self.data_dir, "hashes.json.bak")

    # -- persistence --------------------------------------------------------

    def _ensure_dir(self) -> None:
        """Create data_dir and parents if missing."""
        os.makedirs(self.data_dir, exist_ok=True)

    def load(self) -> dict:
        """Read and validate ``hashes.json`` with .bak fallback.

        Primary: read ``hashes.json`` and validate it.
        Fallback: when the primary file is missing, has unparsable JSON,
        or fails structural validation, but ``hashes.json.bak`` exists
        and is valid → return the backup data.
        Fail-safe: both files broken → return empty structure.
        """
        if os.path.isfile(self._path):
            try:
                with open(self._path, encoding="utf-8") as fh:
                    data = json.load(fh)
                if _validate_entry(data):
                    return data
            except (json.JSONDecodeError, OSError):
                pass

        # Primary failed: try .bak fallback
        if os.path.isfile(self._bak_path):
            try:
                with open(self._bak_path, encoding="utf-8") as fh:
                    bak_data = json.load(fh)
                if _validate_entry(bak_data):
                    return bak_data
            except (json.JSONDecodeError, OSError):
                pass

        return {"version": 1, "entries": {}}

    def save(self, data: dict) -> None:
        """Atomically write *data* to ``hashes.json``.

        Self-healing:
          1. Rotate existing file → ``.bak``
          2. Write to temp file in the same directory
          3. fsync temp → rename → fsync dir

        Raises nothing — any failure during write is swallowed silently;
        the store is a rebuildable cache (ADR-010).
        """
        try:
            self._ensure_dir()

            # .bak rotation: copy existing file before overwrite
            if os.path.isfile(self._path):
                shutil.copy2(self._path, self._bak_path)

            # Atomic write: temp + rename
            fd, tmp_path = tempfile.mkstemp(dir=self.data_dir, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, sort_keys=True, ensure_ascii=False)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.rename(tmp_path, self._path)
                # fsync the parent directory
                dir_fd = os.open(self.data_dir, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except BaseException:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception:
            # NEVER crash the caller — cache is rebuildable
            pass

    # -- core operations ----------------------------------------------------

    def _file_path(self, manifest_path: str):
        """Absolute path for a manifest-relative path."""
        return os.path.join(self.root, manifest_path)

    def _compute_hash(self, manifest_path: str):
        """Return sha256:hex for a manifest-relative path, or None if absent."""
        abs_path = self._file_path(manifest_path)
        if not os.path.isfile(abs_path):
            return None
        return _sha256_file(abs_path)

    def rebuild(self, manifest) -> dict:
        """Rebuild the hash store from scratch using manifest entries.

        For every manifest entry:
          - Compute SHA-256 for the primary file, RU translation (if present),
            and changelog (if it exists on disk).
          - The entry's path key is the primary file's ``path``.
          - ``last_hash`` is the hash of the primary file.
          - ``history`` is built from previous entries: the old entry's
            existing history is preserved (append-only, indefinite), then
            the old last_hash is appended.

        Calls ``save()`` before returning.

        Parameters
        ----------
        manifest : ManifestSource
            Must provide ``.entries() -> list`` with dicts containing
            ``path``, ``has_translation``, and ``changelog-path``.

        Returns
        -------
        dict
            The rebuilt data (same structure as returned by ``load``).
        """
        data = self.load()  # starts with {version:1, entries:{}}
        old_entries = data.get("entries", {})
        new_entries = {}

        for entry in manifest.entries():
            main_path = entry["path"]
            history: list = []

            # Check if we have a previous entry for this path; preserve
            # existing history (append-only, indefinite accumulation) and
            # append the old last_hash.
            if main_path in old_entries:
                old_entry = old_entries[main_path]
                # Inherit existing history (if any — may come from a
                # .bak fallback where load() returned stale data).
                existing_history: list = list(old_entry.get("history") or [])
                old_last_hash = old_entry.get("last_hash")
                if old_last_hash:
                    history = existing_history + [{
                        "hash": old_last_hash,
                        "timestamp": old_entry.get(
                            "last_modified", _utc_now()),
                    }]

            now = self._clock()

            # Compute hash for the primary file
            main_hash = self._compute_hash(main_path)
            if main_hash is None:
                # File doesn't exist on disk — skip (ADR-010: don't add
                # keys that aren't on disk)
                continue

            record: dict = {
                "last_hash": main_hash,
                "last_modified": now,
                "history": history,
            }
            new_entries[main_path] = record

        data["entries"] = new_entries
        self.save(data)
        return data

    def update(self, manifest, target_ids) -> None:
        """Update snapshot records for the given target IDs.

        For each target_id (looked up in manifest):
          - Compute current hash for the primary file (and RU / changelog).
          - If the hash hasn't changed since the last recorded snapshot → skip.
          - If hash changed (or entry is new) → preserve existing history
            (append-only, indefinite), append old last_hash, update
            last_hash and last_modified.

        History is append-only and accumulates indefinitely: every time a
        file's hash changes, the previous hash (with its timestamp) is
        appended to the history list. This never truncates.

        Parameters
        ----------
        manifest : ManifestSource
            Must provide ``.entries()`` and ``.resolve(target_id)``.
        target_ids : list[str]
            Manifest IDs whose hash records to update.
        """
        data = self.load()
        entries_list = manifest.entries()
        now = self._clock()

        for entry in entries_list:
            if entry["id"] not in target_ids:
                continue

            main_path = entry["path"]
            old_entry = data["entries"].get(main_path)
            current_hash = self._compute_hash(main_path)

            if current_hash is None:
                # File missing — skip silently
                continue

            if old_entry is not None and old_entry.get("last_hash") == current_hash:
                # No change — do NOT update last_modified or append to history
                continue

            # Hash changed or entry is new: preserve existing history
            # (append-only, indefinite accumulation), then add the old hash.
            existing_history: list = list(old_entry.get("history") or []) if old_entry else []
            if old_entry is not None:
                history = existing_history + [{
                    "hash": old_entry["last_hash"],
                    "timestamp": old_entry.get("last_modified", _utc_now()),
                }]
            else:
                history = existing_history  # new entry — no prior hash to record

            data["entries"][main_path] = {
                "last_hash": current_hash,
                "last_modified": now,
                "history": history,
            }

        self.save(data)

    def verify(self, manifest, target_id: str):
        """Verify hash integrity for a manifest entry.

        Returns
        -------
        None — hash matches, file exists.
        "stale" — file exists but hash differs, or file is missing
                  while a record exists.
        "missing" — no record in the store (cache miss).
        """
        data = self.load()
        entries_list = manifest.entries()

        # Find the manifest entry
        manifest_entry = None
        for e in entries_list:
            if e["id"] == target_id:
                manifest_entry = e
                break

        if manifest_entry is None:
            return "missing"

        main_path = manifest_entry["path"]
        record = data["entries"].get(main_path)

        if record is None:
            return "missing"

        current_hash = self._compute_hash(main_path)
        if current_hash is None:
            # File missing on disk but record exists → stale
            return "stale"

        if current_hash != record.get("last_hash"):
            return "stale"

        return None
