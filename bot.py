import asyncio
import logging
import signal as _signal
from logging.handlers import RotatingFileHandler
from multiprocessing import Process
from pathlib import Path
from threading import Thread

from circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from claude_client import ClaudeCodeClient
from command_router import CommandRouter, MessageDeduplicator, parse_onebot_private_message
from config import get_settings
from log_rotator import LogRotator
from plan_state import PlanStateMachine
from qq_client import OneBotClient
from storage_manager import StorageManager
from task_cleaner import TaskCleaner
from task_monitor import TaskMonitor
from task_recovery import run_recovery
from task_registry import TaskRegistry
from task_scheduler import TaskScheduler
from task_status_log import TaskStatusLog
from worker_pool import WorkerPool


def setup_logging(level: str) -> None:
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    root = logging.getLogger()
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(log_format))
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        "logs/agent-qq.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(log_format))
    root.addHandler(file_handler)


async def handle_event(
    event: dict,
    router: CommandRouter,
    deduplicator: MessageDeduplicator,
    qq: OneBotClient,
    breaker: CircuitBreaker,
) -> None:
    message = parse_onebot_private_message(event)
    if message is None:
        return

    dedupe_key = f"{message.message_type}:{message.user_id}:{message.message_id}"
    if deduplicator.seen_before(dedupe_key):
        logging.getLogger(__name__).info("Duplicate message ignored: %s", dedupe_key)
        return

    try:
        reply = await router.route(message)
        if reply:
            await qq.send_private_msg_chunked(message.user_id, reply)
    except asyncio.CancelledError:
        logging.getLogger(__name__).info("Message task cancelled: %s", dedupe_key)
    except Exception:
        logging.getLogger(__name__).exception("Failed to handle message")
        await qq.send_private_msg_chunked(message.user_id, "处理消息时发生错误，请查看日志。")


async def run_forever() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    # ── Initialize all new components ──
    status_log = TaskStatusLog(
        data_dir=settings.plan_data_dir,
        max_age_hours=settings.plan_status_log_max_age_hours,
    )
    registry = TaskRegistry(status_log=status_log)
    claude = ClaudeCodeClient(settings, registry)
    plan_state = PlanStateMachine(settings)

    # Circuit breaker
    breaker_config = CircuitBreakerConfig(
        enabled=settings.circuit_breaker_enabled,
        max_retries=settings.circuit_breaker_max_retries,
        task_timeout_minutes=settings.circuit_breaker_task_timeout_minutes,
    )
    breaker = CircuitBreaker(
        config=breaker_config,
        plan_state=plan_state,
        notification_callback=None,  # will be set after QQ client connects
    )

    # Router (with all dependencies)
    router = CommandRouter(settings, claude, registry, plan_state, breaker)
    deduplicator = MessageDeduplicator(settings.message_dedupe_ttl_seconds)

    # Log rotator — clean up on startup
    rotator = LogRotator(settings)
    rotator.cleanup_on_startup()

    # Background monitor
    monitor = TaskMonitor(settings, status_log, breaker)
    await monitor.start()

    # ── Storage managers for scheduler / worker pool ──
    data_dir = Path(settings.plan_data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    task_store = StorageManager(str(data_dir / "task_queue.json"))
    worker_store = StorageManager(str(data_dir / "worker_state.json"))

    # Initialise worker state if empty
    if not worker_store.read():
        worker_store.write({
            f"W{i}": {"status": "idle", "task": None}
            for i in range(1, settings.worker_pool_size + 1)
        })

    # ── Startup recovery ──
    logger.info("Running startup recovery...")
    run_recovery(task_store, worker_store)

    # ── Start worker pool (separate process for true parallelism) ──
    worker_proc: Process | None = None
    if settings.worker_pool_enabled:
        workers = WorkerPool(
            task_store=task_store,
            worker_store=worker_store,
            claude_command=settings.claude_cli_command,
            num_workers=settings.worker_pool_size,
        )
        worker_proc = Process(target=workers.start, name="WorkerPool", daemon=True)
        worker_proc.start()
        logger.info("WorkerPool started (%d workers)", settings.worker_pool_size)

    # ── Start scheduler (daemon thread) ──
    if settings.worker_pool_enabled:
        scheduler = TaskScheduler(task_store=task_store, worker_store=worker_store)
        sched_thread = Thread(target=scheduler.start, daemon=True, name="TaskScheduler")
        sched_thread.start()
        logger.info("TaskScheduler started")

    # ── Start cleaner (daemon thread) ──
    cleaner = TaskCleaner(
        task_store=task_store,
        max_age_hours=settings.task_max_age_hours,
    )
    cleaner_thread = Thread(target=cleaner.start, daemon=True, name="TaskCleaner")
    cleaner_thread.start()
    logger.info("TaskCleaner started (%dh max age)", settings.task_max_age_hours)

    # ── Main loop ──
    reconnect_delay = settings.reconnect_initial_seconds
    try:
        while True:
            qq = OneBotClient(settings)
            try:
                await qq.connect()
                reconnect_delay = settings.reconnect_initial_seconds

                # Wire breaker notification callback to QQ sender
                breaker._notify = lambda msg: asyncio.create_task(
                    qq.send_private_msg_chunked(
                        next(iter(settings.notification_recipients()), 0), msg
                    )
                )

                async for event in qq.events():
                    asyncio.create_task(
                        handle_event(event, router, deduplicator, qq, breaker)
                    )
            except asyncio.CancelledError:
                await qq.close()
                raise
            except Exception:
                logger.exception(
                    "OneBot connection failed, reconnecting in %ss", reconnect_delay
                )
                await qq.close()
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(
                    reconnect_delay * 2, settings.reconnect_max_seconds
                )
    finally:
        # ── Graceful shutdown ──
        logger.info("Shutting down worker pool...")
        if worker_proc is not None:
            worker_proc.terminate()
            worker_proc.join(timeout=5)
            if worker_proc.is_alive():
                worker_proc.kill()
        logger.info("bot.py shutdown complete")


def main() -> None:
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
