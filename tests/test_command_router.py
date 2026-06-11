import pytest

from claude_client import ClaudeCodeClient
from command_router import CommandRouter, IncomingMessage, MessageDeduplicator, parse_onebot_private_message
from config import Settings


class FakeClaude(ClaudeCodeClient):
    def __init__(self) -> None:
        pass

    async def ask(self, prompt: str) -> str:
        return f"ask:{prompt}"

    async def code(self, prompt: str) -> str:
        return f"code:{prompt}"

    async def shell(self, command: str, user_id: int) -> str:
        return f"shell:{user_id}:{command}"

    async def status(self) -> str:
        return "claude-ok"


@pytest.mark.asyncio
async def test_help_command() -> None:
    settings = Settings(ADMIN_QQ_IDS="1")
    router = CommandRouter(settings, FakeClaude())
    message = IncomingMessage(1, 1, "private", "/help", {})

    reply = await router.route(message)

    assert reply is not None
    assert "/ask" in reply


@pytest.mark.asyncio
async def test_plain_text_routes_to_ask() -> None:
    settings = Settings(ADMIN_QQ_IDS="1")
    router = CommandRouter(settings, FakeClaude())
    message = IncomingMessage(1, 1, "private", "你好", {})

    reply = await router.route(message)

    assert reply == "ask:你好"


@pytest.mark.asyncio
async def test_code_requires_admin() -> None:
    settings = Settings(ADMIN_QQ_IDS="1")
    router = CommandRouter(settings, FakeClaude())
    message = IncomingMessage(1, 2, "private", "/code 写脚本", {})

    reply = await router.route(message)

    assert reply == "权限不足：/code 仅管理员可用。"


def test_deduplicator() -> None:
    dedupe = MessageDeduplicator(ttl_seconds=300)

    assert dedupe.seen_before("a") is False
    assert dedupe.seen_before("a") is True


def test_parse_onebot_private_message() -> None:
    payload = {
        "post_type": "message",
        "message_type": "private",
        "message_id": 123,
        "user_id": 456,
        "message": [{"type": "text", "data": {"text": "/help"}}],
    }

    message = parse_onebot_private_message(payload)

    assert message is not None
    assert message.message_id == 123
    assert message.user_id == 456
    assert message.text == "/help"
