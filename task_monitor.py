"""Background task monitor — pure script, zero AI token consumption.

Reads task_status_log.json on a high-frequency timer.  Detects:
- Stale running tasks (no update in N seconds)
- Exception states needing circuit breaker trip
- Network health degradation

All monitoring logic is pure script — no AI calls.
"""

import asyncio
import contextlib
import logging
import subprocess
import sys
import time
from pathlib import Path

from circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from config import Settings
from task_status_log import TaskStatusLog

logger = logging.getLogger(__name__)


class TaskMonitor:
    """High-frequency poller that watches task_status_log.json for anomalies."""

    def __init__(
        self,
        settings: Settings,
        status_log: TaskStatusLog,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._settings = settings
        self._status_log = status_log
        self._breaker = breaker
        self._poll_interval = settings.monitor_poll_interval_seconds
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not self._settings.monitor_enabled:
            logger.info("TaskMonitor disabled by config")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "TaskMonitor started (poll every %ds)",
            self._poll_interval,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("TaskMonitor stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("TaskMonitor tick error")
            await asyncio.sleep(self._poll_interval)

    async def _tick(self) -> None:
        """One monitoring cycle — pure script, zero token."""
        now = time.time()
        active_tasks = self._status_log.get_active_tasks()

        for entry in active_tasks:
            task_id = entry.get("task_id", "unknown")
            status = entry.get("status", "")
            trigger_time = entry.get("trigger_time", now)
            elapsed = now - trigger_time

            # Check if the task itself is healthy (circuit breaker)
            if self._breaker and status == "running":
                reason = self._breaker.check_health(task_id, elapsed)
                if reason:
                    self._status_log.update_status(task_id, "exception", error_reason=reason)
                    logger.error("Monitor flagged exception: %s — %s", task_id, reason)

    @staticmethod
    def check_network() -> tuple[str, float, float]:
        """Test network quality via ping. Returns (grade, latency_ms, loss_pct).

        Grades: 优 (excellent), 良 (good), 差 (poor)
        """
        hosts = ["github.com", "baidu.com"]
        total_latency = 0.0
        total_loss = 0.0
        success = 0

        for host in hosts:
            try:
                result = subprocess.run(
                    ["ping", "-c", "3", "-W", "5", host],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                if result.returncode == 0:
                    # Parse latency from last line
                    for line in result.stdout.splitlines():
                        if "avg" in line or "rtt" in line:
                            # e.g. "rtt min/avg/max/mdev = 50.0/60.0/70.0/8.0 ms"
                            parts = line.split("=")[-1].strip().split("/")
                            if len(parts) >= 2:
                                total_latency += float(parts[1])
                            break
                    success += 1
                else:
                    total_loss += 100
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.warning("Ping %s failed: %s", host, exc)
                total_loss += 100

        avg_latency = total_latency / max(success, 1)
        avg_loss = total_loss / len(hosts)

        if avg_loss > 50:
            grade = "差"
        elif avg_loss > 10 or avg_latency > 300:
            grade = "良"
        else:
            grade = "优"

        return grade, avg_latency, avg_loss


# Allow running as standalone script for manual network check
if __name__ == "__main__":
    grade, latency, loss = TaskMonitor.check_network()
    print(f"网络状态：{grade}")
    print(f"平均延迟：{latency:.0f}ms")
    print(f"丢包率：{loss:.0f}%")
