"""Task scheduler — assigns pending tasks to idle workers.

Polls task_status_log.json periodically.  When a task is in "pending" or
"running" state and no worker has claimed it, assigns it to an idle worker
by writing to worker_state.json.  Uses StorageManager for atomic file ops.

Runs as a daemon thread — no asyncio dependency.
"""

import logging
import time

from storage_manager import StorageManager

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Poll task_status_log and assign unclaimed tasks to idle workers."""

    POLL_INTERVAL = 1.0  # seconds

    def __init__(
        self,
        task_store: StorageManager,
        worker_store: StorageManager,
    ) -> None:
        self._task_store = task_store
        self._worker_store = worker_store

    def start(self) -> None:
        """Run forever as a daemon thread."""
        while True:
            try:
                self._schedule()
            except Exception:
                logger.exception("TaskScheduler error")
            time.sleep(self.POLL_INTERVAL)

    def _schedule(self) -> None:
        tasks = self._task_store.read()
        workers = self._worker_store.read()

        # Find pending tasks that are not yet assigned
        pending = [
            t for t in tasks
            if t.get("status") in ("pending", "running")
            and t.get("worker") is None
        ]
        if not pending:
            return

        # Find idle workers
        idle_workers = sorted([
            wid for wid, w in workers.items()
            if w.get("status") == "idle"
        ])
        if not idle_workers:
            return

        assigned = False
        for task in pending:
            if not idle_workers:
                break
            wid = idle_workers.pop(0)
            task["worker"] = wid
            task["status"] = "running"
            workers[wid]["status"] = "busy"
            workers[wid]["task"] = task["id"]
            logger.info("Scheduler: %s → %s", task["id"], wid)
            assigned = True

        if assigned:
            self._task_store.write(tasks)
            self._worker_store.write(workers)
