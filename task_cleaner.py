"""Task cleaner — periodically remove expired completed/cancelled tasks.

Runs as a daemon thread.  Defaults:
- Cycle: every 300 seconds (5 minutes)
- Max age: 24 hours for completed/cancelled/exception tasks
"""

import logging
import time
from datetime import datetime, timedelta, timezone

from storage_manager import StorageManager

logger = logging.getLogger(__name__)


class TaskCleaner:
    """Periodically remove terminal tasks older than max_age_hours."""

    SAFE_STATES = {"completed", "cancelled", "exception"}
    CYCLE_SECONDS = 300   # 5 minutes
    MAX_AGE_HOURS = 24

    def __init__(
        self,
        task_store: StorageManager,
        cycle_seconds: int = CYCLE_SECONDS,
        max_age_hours: int = MAX_AGE_HOURS,
    ) -> None:
        self._task_store = task_store
        self._cycle_seconds = cycle_seconds
        self._max_age_hours = max_age_hours

    def start(self) -> None:
        """Run forever as a daemon thread."""
        while True:
            try:
                self._clean()
            except Exception:
                logger.exception("TaskCleaner error")
            time.sleep(self._cycle_seconds)

    def _clean(self) -> None:
        tasks = self._task_store.read()
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=self._max_age_hours)

        kept = []
        removed = 0
        for t in tasks:
            if not isinstance(t, dict):
                kept.append(t)
                continue
            if t.get("status") in self.SAFE_STATES:
                try:
                    created_str = t.get("created_at") or t.get("trigger_time", "")
                    if created_str:
                        created = datetime.fromisoformat(str(created_str))
                        if created.tzinfo is None:
                            created = created.replace(tzinfo=timezone.utc)
                        if created < cutoff:
                            removed += 1
                            continue
                except (ValueError, KeyError, TypeError):
                    pass
            kept.append(t)

        if removed > 0:
            self._task_store.write(kept)
            logger.info("TaskCleaner: removed %d expired tasks", removed)
