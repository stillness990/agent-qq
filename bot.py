import asyncio
import logging
from logging.handlers import RotatingFileHandler

from circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from claude_client import ClaudeCodeClient
from command_router import CommandRouter, MessageDeduplicator, parse_onebot_private_message
from config import get_settings
from log_rotator import LogRotator
from plan_state import PlanStateMachine
from qq_client import OneBotClient
from task_monitor import TaskMonitor
from task_registry import TaskRegistry
from task_status_log import TaskStatusLog


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

    # ── Main loop ──
    reconnect_delay = settings.reconnect_initial_seconds
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


def main() -> None:
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
