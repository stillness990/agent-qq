"""Startup recovery — fix orphaned tasks and workers.

Called synchronously on bot startup.  Detects:
- Tasks marked "running" whose assigned worker no longer exists
- Workers pointing to tasks that no longer exist

Resets orphaned tasks to "pending" and orphaned workers to "idle".
"""

import logging

from storage_manager import StorageManager

logger = logging.getLogger(__name__)


def run_recovery(
    task_store: StorageManager,
    worker_store: StorageManager,
) -> int:
    """Fix orphaned tasks and workers on startup.

    Returns count of repaired items.
    """
    tasks = task_store.read()
    workers = worker_store.read()

    valid_task_ids = {t.get("id") for t in tasks if isinstance(t, dict)}
    valid_workers = set(workers.keys())
    repaired = 0

    # ── Fix orphaned running tasks ──
    for task in tasks:
        if not isinstance(task, dict):
            continue
        worker = task.get("worker")
        if task.get("status") == "running" and (worker is None or worker not in valid_workers):
            task["status"] = "pending"
            task["worker"] = None
            repaired += 1
            logger.info("Recovery: reset orphan task %s → pending", task.get("id"))

    # ── Fix orphaned workers ──
    for wid, wdata in workers.items():
        if not isinstance(wdata, dict):
            continue
        if wdata.get("task") and wdata["task"] not in valid_task_ids:
            wdata["task"] = None
            wdata["status"] = "idle"
            repaired += 1
            logger.info("Recovery: reset orphan worker %s → idle", wid)

    if repaired:
        task_store.write(tasks)
        worker_store.write(workers)
        logger.info("Recovery complete: %d orphan(s) repaired", repaired)
    else:
        logger.info("Recovery: no orphans found")

    return repaired
