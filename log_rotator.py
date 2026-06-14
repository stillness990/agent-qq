"""Log rotation and cleanup — prevents unlimited log growth.

- plan_history.json: keep at most N entries (configurable, default 50)
- task_status_log.json: remove terminal (completed/cancelled) entries
  older than N hours (configurable, default 24)
"""

import logging

from config import Settings
from task_status_log import TaskStatusLog

logger = logging.getLogger(__name__)


class LogRotator:
    """Handles automatic log cleanup on startup and periodically."""

    def __init__(self, settings: Settings) -> None:
        self._status_log = TaskStatusLog(
            data_dir=settings.plan_data_dir,
            max_age_hours=settings.plan_status_log_max_age_hours,
        )
        self._history_max = settings.plan_history_max
        self._max_age_hours = settings.plan_status_log_max_age_hours

    def cleanup_on_startup(self) -> dict[str, int]:
        """Run all cleanup tasks. Returns counts per cleanup type."""
        result: dict[str, int] = {}

        # Cleanup task_status_log.json
        removed = self._status_log.cleanup_terminal()
        result["status_log_terminal_removed"] = removed

        logger.info(
            "Log rotator startup cleanup: removed %d terminal status entries",
            removed,
        )
        return result

    def rotate_plan_history(self, entries: list[dict]) -> list[dict]:
        """Enforce max entries limit on plan history."""
        if len(entries) > self._history_max:
            trimmed = len(entries) - self._history_max
            logger.info("Plan history rotated: trimmed %d oldest entries", trimmed)
            return entries[-self._history_max :]
        return entries
