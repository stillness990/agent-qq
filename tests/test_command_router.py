import asyncio

import pytest

from claude_client import ClaudeCodeClient
from command_router import CommandRouter, IncomingMessage, MessageDeduplicator, parse_onebot_private_message
from config import Settings
from task_registry import TaskRegistry


class FakeClaude(ClaudeCodeClient):
    def __init__(self) -> None:
        pass

    async def ask(self, prompt: str, task_id: str | None = None) -> str:
        return f"ask:{task_id}:{prompt}"

    async def code(self, prompt: str, task_id: str | None = None) -> str:
        return f"code:{task_id}:{prompt}"

    async def shell(self, command: str, user_id: int, task_id: str | None = None) -> str:
        return f"shell:{task_id}:{user_id}:{command}"

    async def status(self) -> str:
        return "claude-ok"

    def _is_allowed_shell(self, command: str) -> bool:
        return True


@pytest.mark.asyncio
async def test_help_command() -> None:
    settings = Settings(ADMIN_QQ_IDS="1")
    router = CommandRouter(settings, FakeClaude())
    message = IncomingMessage(1, 1, "private", "/help", {})

    reply = await router.route(message)

    assert reply is not None
    assert "/ask" in reply
    assert "/stop" in reply


@pytest.mark.asyncio
async def test_plain_text_routes_to_ask() -> None:
    settings = Settings(ADMIN_QQ_IDS="1")
    router = CommandRouter(settings, FakeClaude())
    message = IncomingMessage(1, 1, "private", "你好", {})

    reply = await router.route(message)

    assert reply == "ask:t1:你好"


@pytest.mark.asyncio
async def test_code_requires_admin() -> None:
    settings = Settings(ADMIN_QQ_IDS="1")
    registry = TaskRegistry()
    router = CommandRouter(settings, FakeClaude(), registry)
    message = IncomingMessage(1, 2, "private", "/code 写脚本", {})

    reply = await router.route(message)

    assert reply == "权限不足：/code 仅管理员可用。"
    assert registry.format_status(2) == "运行中任务：无"


@pytest.mark.asyncio
async def test_status_lists_no_running_tasks() -> None:
    settings = Settings(ADMIN_QQ_IDS="1")
    router = CommandRouter(settings, FakeClaude())
    message = IncomingMessage(1, 1, "private", "/status", {})

    reply = await router.route(message)

    assert reply is not None
    assert "agent-qq 正常运行" in reply
    assert "运行中任务：无" in reply


@pytest.mark.asyncio
async def test_status_lists_running_task_name() -> None:
    settings = Settings(ADMIN_QQ_IDS="1")
    registry = TaskRegistry()
    record = registry.create("ask", "问答：长任务", 1)
    router = CommandRouter(settings, FakeClaude(), registry)
    message = IncomingMessage(1, 1, "private", "/status", {})

    reply = await router.route(message)

    assert reply is not None
    assert record.id in reply
    assert "问答：长任务" in reply


@pytest.mark.asyncio
async def test_stop_without_selector_returns_usage() -> None:
    settings = Settings(ADMIN_QQ_IDS="1")
    router = CommandRouter(settings, FakeClaude())
    message = IncomingMessage(1, 1, "private", "/stop", {})

    reply = await router.route(message)

    assert reply is not None
    assert "用法：/stop" in reply


@pytest.mark.asyncio
async def test_stop_running_task_by_id() -> None:
    settings = Settings(ADMIN_QQ_IDS="1")
    registry = TaskRegistry()
    record = registry.create("ask", "问答：长任务", 1)

    async def wait_forever() -> None:
        await asyncio.Event().wait()

    task = asyncio.create_task(wait_forever())
    registry.attach_asyncio_task(record.id, task)
    router = CommandRouter(settings, FakeClaude(), registry)
    message = IncomingMessage(1, 1, "private", f"/stop {record.id}", {})

    reply = await router.route(message)

    assert reply is not None
    assert "已请求停止任务" in reply
    assert task.cancelled() or task.cancelling()
    task.cancel()


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


def test_parse_ignores_claude_notification_prefix() -> None:
    payload = {
        "post_type": "message",
        "message_type": "private",
        "message_id": 123,
        "user_id": 456,
        "message": "【Claude】本轮完成",
    }

    assert parse_onebot_private_message(payload) is None


def test_parse_ignores_self_message() -> None:
    payload = {
        "post_type": "message",
        "message_type": "private",
        "message_id": 123,
        "self_id": 456,
        "user_id": 456,
        "message": "/help",
    }

    assert parse_onebot_private_message(payload) is None
