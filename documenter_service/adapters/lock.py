"""fcntl advisory lock for the delegate write branch.

DelegateLock — context manager that acquires fcntl.flock(LOCK_EX | LOCK_NB) on
a lock file inside the data directory, with a poll loop (0.1 s sleep) up to
wait_timeout seconds.  On success writes {pid, acquired_at} to the file.

On timeout → StructuredError("lock_conflict", ..., next_action="preview_denied").

On unexpected OSError (e.g. EBADF, ENOSPC) → StructuredError("unknown", …,
next_action="escalate").  Only BlockingIOError / EWOULDBLOCK / EAGAIN is
treated as "already locked" (retry).

On release: truncate lock file, unlock, close.  NEVER raises from release.

Create data_dir if missing.
"""
from __future__ import annotations

import errno
import fcntl
import json
import os
import time
import uuid
from typing import Any, Callable, Optional

from ..core.errors import StructuredError

__all__ = ["DelegateLock"]

_LOCK_FILENAME = ".delegate.lock"


class DelegateLock:
    """Advisory lock context manager for the write branch.

    Parameters
    ----------
    data_dir : str
        Directory where the lock file will live (``.delegate.lock``).
    wait_timeout : int
        Maximum seconds to poll for the lock (default 30).
    clock : callable, optional
        Injected clock (returns int/float seconds); defaults to ``time.time``.
    """

    def __init__(
        self,
        data_dir: str,
        wait_timeout: int = 30,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._data_dir = os.path.abspath(data_dir)
        self._wait_timeout = wait_timeout
        self._clock = clock or time.time
        self._lock_path: Optional[str] = None
        self._fd: Optional[int] = None
        self._owner_info: dict = {}

    # -- context manager protocol -------------------------------------------

    def __enter__(self) -> "DelegateLock":
        self._lock_path = os.path.join(self._data_dir, _LOCK_FILENAME)
        os.makedirs(self._data_dir, exist_ok=True)
        self._fd = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, 0o644)

        deadline = self._clock() + self._wait_timeout
        while True:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break  # acquired
            except BlockingIOError:
                # Normal retry: lock is held by another process.
                if self._clock() >= deadline:
                    owner = self._read_owner_info()
                    self._unlock_no_raise()
                    raise StructuredError(
                        "lock_conflict",
                        "Another agent holds an advisory lock on "
                        f"{self._lock_path!r}. "
                        f"Lock owner: pid {owner.get('pid', '?')}, "
                        f"acquired at {owner.get('acquired_at', '?')}. "
                        f"Wait? (yes/no) — Default: no after {self._wait_timeout}s.",
                        next_action="preview_denied",
                    )
                time.sleep(0.1)
            except OSError as exc:
                # Only EWOULDBLOCK / EAGAIN counts as "already locked"; all
                # other OS errors (EBADF, ENOSPC, …) are unexpected.
                if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                    if self._clock() >= deadline:
                        owner = self._read_owner_info()
                        self._unlock_no_raise()
                        raise StructuredError(
                            "lock_conflict",
                            "Another agent holds an advisory lock on "
                            f"{self._lock_path!r}. "
                            f"Lock owner: pid {owner.get('pid', '?')}, "
                            f"acquired at {owner.get('acquired_at', '?')}. "
                            f"Wait? (yes/no) — Default: no after "
                            f"{self._wait_timeout}s.",
                            next_action="preview_denied",
                        )
                    time.sleep(0.1)
                else:
                    # Unexpected OS error (EBADF, ENOSPC, …) — close fd and
                    # escalate; treating it as "locked" would loop forever.
                    self._unlock_no_raise()
                    raise StructuredError(
                        "unknown",
                        f"unexpected error acquiring lock: {exc}",
                        next_action="escalate",
                    )

        # Write owner info to the lock file (truncate then write).
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        owner = {"pid": os.getpid(), "acquired_at": now_iso}
        self._owner_info = owner
        os.lseek(self._fd, 0, os.SEEK_SET)
        os.truncate(self._fd, 0)
        os.write(self._fd, json.dumps(owner).encode("utf-8"))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._unlock_no_raise()

    # -- internals ----------------------------------------------------------

    def _read_owner_info(self) -> dict:
        """Best-effort read of the current lock holder's owner JSON."""
        try:
            with open(self._lock_path, encoding="utf-8") as fh:
                info = json.loads(fh.read() or "{}")
            return info if isinstance(info, dict) else {}
        except (OSError, ValueError):
            return {}

    def _unlock_no_raise(self) -> None:
        """Release the lock.  NEVER raises (crash-safety)."""
        try:
            if self._fd is not None:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.lseek(self._fd, 0, os.SEEK_SET)
                os.truncate(self._fd, 0)
                os.close(self._fd)
                self._fd = None
        except BaseException:
            pass  # NEVER raise from release
