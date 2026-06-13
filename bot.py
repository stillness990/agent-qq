import asyncio
import logging
from logging.handlers import RotatingFileHandler

from claude_client import ClaudeCodeClient
from command_router import CommandRouter, MessageDeduplicator, parse_onebot_private_message
from config import get_settings
from qq_client import OneBotClient
from task_registry import TaskRegistry


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

    registry = TaskRegistry()
    claude = ClaudeCodeClient(settings, registry)
    router = CommandRouter(settings, claude, registry)
    deduplicator = MessageDeduplicator(settings.message_dedupe_ttl_seconds)

    reconnect_delay = settings.reconnect_initial_seconds
    while True:
        qq = OneBotClient(settings)
        try:
            await qq.connect()
            reconnect_delay = settings.reconnect_initial_seconds
            async for event in qq.events():
                asyncio.create_task(handle_event(event, router, deduplicator, qq))
        except asyncio.CancelledError:
            await qq.close()
            raise
        except Exception:
            logger.exception("OneBot connection failed, reconnecting in %ss", reconnect_delay)
            await qq.close()
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, settings.reconnect_max_seconds)


def main() -> None:
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
