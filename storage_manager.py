"""Atomic JSON storage with file locking — general-purpose utility.

Provides thread/process-safe read/write for JSON files via:
- FileLock for cross-process mutual exclusion
- tempfile + fsync + atomic replace for crash-safe writes
"""

import json
import os
import tempfile

from filelock import FileLock


class StorageManager:
    """Thread/process-safe JSON file storage with atomic writes."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.lock_path = path + ".lock"

    def read(self):
        with FileLock(self.lock_path, timeout=10):
            if not os.path.exists(self.path):
                return [] if "task" in self.path else {}
            try:
                with open(self.path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, ValueError):
                return [] if "task" in self.path else {}

    def write(self, data) -> None:
        """Atomic write: tempfile → fsync → atomic replace."""
        with FileLock(self.lock_path, timeout=10):
            dir_name = os.path.dirname(os.path.abspath(self.path))
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self.path)
            except BaseException:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
