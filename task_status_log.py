"""Independent task status log — zero token consumption.

Writes task_id, status, and trigger_time to task_status_log.json
whenever a task command (e.g. /plan-start) is received.
Background monitor reads this file to detect anomalies.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

TaskStatus = Literal["pending", "running", "completed", "cancelled", "exception"]


@dataclass
class TaskStatusEntry:
    task_id: str
    status: TaskStatus
    trigger_time: float = field(default_factory=time.time)
    update_time: float = field(default_factory=time.time)
    kind: str = ""
    description: str = ""
    user_id: int = 0
    error_reason: str = ""


class TaskStatusLog:
    """Append-only status log file with cleanup of terminal records."""

    def __init__(self, data_dir: Path, max_age_hours: int = 24) -> None:
        self._path = data_dir / "task_status_log.json"
        self._max_age_hours = max_age_hours
        data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------
    def write_entry(self, entry: TaskStatusEntry) -> None:
        entries = self._read_all()
        entries.append(self._entry_to_dict(entry))
        self._write_all(entries)
        logger.debug("TaskStatusLog: %s → %s", entry.task_id, entry.status)

    def update_status(self, task_id: str, status: TaskStatus, error_reason: str = "") -> None:
        entries = self._read_all()
        now = time.time()
        for e in entries:
            if e.get("task_id") == task_id:
                e["status"] = status
                e["update_time"] = now
                if error_reason:
                    e["error_reason"] = error_reason
                self._write_all(entries)
                logger.info("TaskStatusLog updated: %s → %s", task_id, status)
                return
        # Not found — create new entry
        logger.debug("TaskStatusLog: task %s not found, creating new entry", task_id)
        self.write_entry(TaskStatusEntry(
            task_id=task_id,
            status=status,
            error_reason=error_reason,
        ))

    # ------------------------------------------------------------------
    # Read operations (for monitor — zero AI token)
    # ------------------------------------------------------------------
    def get_active_tasks(self) -> list[dict]:
        """Return tasks that are NOT in a terminal state."""
        return [
            e for e in self._read_all()
            if e.get("status") in ("pending", "running")
        ]

    def get_task(self, task_id: str) -> dict | None:
        for e in self._read_all():
            if e.get("task_id") == task_id:
                return e
        return None

    def read_all(self) -> list[dict]:
        """Full log dump — for /plan-log and /status."""
        return self._read_all()

    # ------------------------------------------------------------------
    # Cleanup — called by log rotator or on startup
    # ------------------------------------------------------------------
    def cleanup_terminal(self) -> int:
        """Remove completed/cancelled entries older than max_age_hours.
        Returns count of removed entries.
        """
        entries = self._read_all()
        now = time.time()
        cutoff = now - self._max_age_hours * 3600
        kept = []
        removed = 0
        for e in entries:
            status = e.get("status", "")
            update_time = e.get("update_time", e.get("trigger_time", 0))
            if status in ("completed", "cancelled") and update_time < cutoff:
                removed += 1
            else:
                kept.append(e)
        if removed:
            self._write_all(kept)
            logger.info("TaskStatusLog cleanup: removed %d terminal entries", removed)
        return removed

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _read_all(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read task_status_log: %s", exc)
            return []

    def _write_all(self, entries: list[dict]) -> None:
        self._path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _entry_to_dict(entry: TaskStatusEntry) -> dict:
        return {
            "task_id": entry.task_id,
            "status": entry.status,
            "trigger_time": entry.trigger_time,
            "update_time": entry.update_time,
            "kind": entry.kind,
            "description": entry.description,
            "user_id": entry.user_id,
            "error_reason": entry.error_reason,
        }
