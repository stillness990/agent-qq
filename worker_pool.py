"""Worker pool — parallel task execution via subprocess workers.

Manages N worker slots, each running one task at a time via Claude Code CLI.
Monitors worker processes for completion, cancellation, and failure.
Runs in a dedicated Process for true parallelism (bypasses GIL).

Uses StorageManager for atomic reads/writes to task_status_log.json and
worker_state.json.
"""

import logging
import os
import signal
import subprocess
import sys
import time

from storage_manager import StorageManager

logger = logging.getLogger(__name__)


class WorkerPool:
    """Manage N parallel worker slots for task execution."""

    CHECK_INTERVAL = 0.5  # seconds
    KILL_TIMEOUT = 5      # seconds before SIGKILL

    def __init__(
        self,
        task_store: StorageManager,
        worker_store: StorageManager,
        claude_command: str = "claude",
        num_workers: int = 4,
    ) -> None:
        self._task_store = task_store
        self._worker_store = worker_store
        self._claude_command = claude_command
        self._num_workers = num_workers
        self._processes: dict[str, dict] = {}

    def start(self) -> None:
        """Run forever (called from a dedicated Process)."""
        while True:
            try:
                self._tick()
            except Exception:
                logger.exception("WorkerPool error")
            time.sleep(self.CHECK_INTERVAL)

    def _tick(self) -> None:
        """One check cycle."""
        workers = self._worker_store.read()

        for wid in [f"W{i}" for i in range(1, self._num_workers + 1)]:
            wdata = workers.get(wid, {})
            if wdata.get("status") == "busy" and wdata.get("task"):
                if wid not in self._processes:
                    self._spawn(wid, wdata["task"])
            elif wid in self._processes:
                self._cleanup_worker(wid)

        self._check_cancellations()

    # ------------------------------------------------------------------
    # Spawn
    # ------------------------------------------------------------------
    def _spawn(self, wid: str, task_id: str) -> None:
        tasks = self._task_store.read()
        task = next((t for t in tasks if t.get("id") == task_id), None)
        if not task:
            logger.warning("Worker %s: task %s not found", wid, task_id)
            return

        description = task.get("description", task.get("cmd", ""))
        cmd = f"{self._claude_command} -p {_shell_quote(description)}"

        try:
            proc = subprocess.Popen(
                cmd, shell=True,
                preexec_fn=os.setpgrp,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._processes[wid] = {"proc": proc, "task_id": task_id}
            logger.info("Worker %s spawned PID %d for %s", wid, proc.pid, task_id)
        except Exception:
            logger.exception("Worker %s spawn failed for %s", wid, task_id)
            self._finalize_task(task_id, "exception")
            self._release_worker(wid)

    # ------------------------------------------------------------------
    # Cleanup completed worker
    # ------------------------------------------------------------------
    def _cleanup_worker(self, wid: str) -> None:
        if wid not in self._processes:
            return
        info = self._processes[wid]
        ret = info["proc"].poll()
        if ret is not None:
            status = "completed" if ret == 0 else "exception"
            self._finalize_task(info["task_id"], status)
            self._release_worker(wid)
            del self._processes[wid]
            logger.info("Worker %s finished: %s (exit %d)", wid, info["task_id"], ret)

    # ------------------------------------------------------------------
    # Cancellation handling
    # ------------------------------------------------------------------
    def _check_cancellations(self) -> None:
        tasks = self._task_store.read()
        cancel_ids = {
            t["id"] for t in tasks
            if t.get("status") in ("cancelled", "stopping")
        }

        for wid, info in list(self._processes.items()):
            if info["task_id"] in cancel_ids:
                self._kill_process_group(info["proc"])
                self._finalize_task(info["task_id"], "cancelled")
                self._release_worker(wid)
                del self._processes[wid]
                logger.info("Worker %s cancelled: %s", wid, info["task_id"])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _kill_process_group(self, proc: subprocess.Popen) -> None:
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
            try:
                proc.wait(timeout=self.KILL_TIMEOUT)
            except subprocess.TimeoutExpired:
                os.killpg(pgid, signal.SIGKILL)
                proc.wait()
        except ProcessLookupError:
            pass

    def _finalize_task(self, task_id: str, status: str) -> None:
        tasks = self._task_store.read()
        for t in tasks:
            if t.get("id") == task_id:
                t["status"] = status
                t["worker"] = None
                break
        self._task_store.write(tasks)

    def _release_worker(self, wid: str) -> None:
        workers = self._worker_store.read()
        if wid in workers:
            workers[wid]["status"] = "idle"
            workers[wid]["task"] = None
            self._worker_store.write(workers)


def _shell_quote(s: str) -> str:
    """Minimal shell quoting for Claude CLI prompts."""
    return "'" + s.replace("'", "'\\''") + "'"
