"""Tests for the refactored CommandRouter with full command interception."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from command_router import (
    CommandRouter,
    IncomingMessage,
    MessageDeduplicator,
    parse_onebot_private_message,
)
from plan_state import PlanStateMachine
from task_registry import TaskRegistry


# ── Helpers ───────────────────────────────────────────────────


def _make_settings(**overrides):
    from config import Settings
    defaults = {
        "ADMIN_QQ_IDS": "12345",
        "ENABLE_PRIVATE_CHAT": "true",
        "ENABLE_SHELL_COMMAND": "true",
        "SHELL_ALLOWED_PREFIXES": "pwd,ls",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _make_msg(text: str, user_id: int = 12345) -> IncomingMessage:
    return IncomingMessage(
        message_id=1, user_id=user_id,
        message_type="private", text=text, raw={},
    )


def _make_fake_claude():
    c = MagicMock()
    c.ask = AsyncMock(return_value="Claude response")
    c.shell = AsyncMock(return_value="stdout: ok\nexit_code: 0")
    c.code = AsyncMock(return_value="Code generated")
    c.status = AsyncMock(return_value="Claude Code CLI 可用：v1.0.0")
    c._is_allowed_shell = MagicMock(return_value=True)
    return c


def _make_plan_state():
    tmp = Path(tempfile.mkdtemp(prefix="test-plan-"))
    from config import Settings
    s = Settings(plan_data_dir=str(tmp))
    return PlanStateMachine(s)


def _make_breaker(plan_state):
    config = CircuitBreakerConfig(enabled=True, max_retries=3, task_timeout_minutes=30)
    return CircuitBreaker(config=config, plan_state=plan_state)


def _make_router(settings=None, claude=None, registry=None, plan_state=None, breaker=None):
    settings = settings or _make_settings()
    claude = claude or _make_fake_claude()
    registry = registry or TaskRegistry()
    plan_state = plan_state or _make_plan_state()
    breaker = breaker or _make_breaker(plan_state)
    return CommandRouter(settings, claude, registry, plan_state, breaker)


# ── Message parsing ───────────────────────────────────────────


class TestParseOnebotPrivateMessage:
    def test_private_text_message(self):
        payload = {
            "post_type": "message", "message_type": "private",
            "user_id": 123, "message_id": 1, "message": "hello",
        }
        msg = parse_onebot_private_message(payload)
        assert msg is not None
        assert msg.user_id == 123
        assert msg.text == "hello"

    def test_self_message_ignored(self):
        payload = {
            "post_type": "message", "message_type": "private",
            "self_id": 999, "user_id": 999, "message_id": 1,
            "message": "self msg",
        }
        assert parse_onebot_private_message(payload) is None

    def test_non_message_event_ignored(self):
        assert parse_onebot_private_message({"post_type": "notice"}) is None

    def test_claude_notification_ignored(self):
        payload = {
            "post_type": "message", "message_type": "private",
            "user_id": 123, "message_id": 1,
            "message": "【Claude】 任务完成",
        }
        assert parse_onebot_private_message(payload) is None

    def test_array_message_extraction(self):
        payload = {
            "post_type": "message", "message_type": "private",
            "user_id": 123, "message_id": 1,
            "message": [
                {"type": "text", "data": {"text": "hello "}},
                {"type": "text", "data": {"text": "world"}},
            ],
        }
        msg = parse_onebot_private_message(payload)
        assert msg is not None
        assert msg.text == "hello world"


# ── Deduplicator ──────────────────────────────────────────────


class TestMessageDeduplicator:
    def test_first_message_passes(self):
        d = MessageDeduplicator(ttl_seconds=60)
        assert not d.seen_before("a:1:100")

    def test_duplicate_blocked(self):
        d = MessageDeduplicator(ttl_seconds=60)
        d.seen_before("a:1:100")
        assert d.seen_before("a:1:100")

    def test_ttl_expires(self):
        d = MessageDeduplicator(ttl_seconds=0)
        d.seen_before("a:1:100")
        d._cleanup(100.0)
        assert not d.seen_before("a:1:100")


# ── Command routing — zero token fallback ─────────────────────


class TestCommandRouter:
    @pytest.mark.asyncio
    async def test_help_lists_all_commands(self):
        router = _make_router()
        result = await router.route(_make_msg("/help"))
        assert "QQ AI Agent 命令列表" in result
        assert "/plan" in result
        assert "/ping" in result
        assert "/weather" in result
        assert "/network" in result
        # /ask and /code must NOT appear in help
        assert "/ask" not in result
        assert "/code" not in result
        # Only /plan can interact with AI
        assert "唯一 AI 交互入口" in result
        assert "零 AI Token 消耗" in result

    @pytest.mark.asyncio
    async def test_unknown_command_no_ai_fallback(self):
        """CRITICAL: Unknown commands must NOT call AI. Return help prompt."""
        router = _make_router()
        result = await router.route(_make_msg("random gibberish text"))
        assert "未知指令" in result
        assert "/help" in result
        router._claude.ask.assert_not_called()

    @pytest.mark.asyncio
    async def test_ping(self):
        router = _make_router()
        result = await router.route(_make_msg("/ping"))
        assert "pong" in result
        assert "在线" in result

    @pytest.mark.asyncio
    async def test_network(self):
        router = _make_router()
        with patch("command_router.TaskMonitor.check_network", return_value=("优", 50.0, 0.0)):
            result = await router.route(_make_msg("/network"))
            assert "优" in result

    @pytest.mark.asyncio
    async def test_clear(self):
        router = _make_router()
        result = await router.route(_make_msg("/clear"))
        assert "重置" in result

    @pytest.mark.asyncio
    async def test_token(self):
        router = _make_router()
        result = await router.route(_make_msg("/token"))
        assert "Token" in result

    @pytest.mark.asyncio
    async def test_empty_message_returns_none(self):
        router = _make_router()
        result = await router.route(_make_msg("   "))
        assert result is None

    @pytest.mark.asyncio
    async def test_ask_removed_treated_as_unknown(self):
        """/ask is removed — must be treated as unknown command, not call AI."""
        router = _make_router()
        result = await router.route(_make_msg("/ask 什么是 Python"))
        assert "未知指令" in result
        router._claude.ask.assert_not_called()

    @pytest.mark.asyncio
    async def test_code_removed_treated_as_unknown(self):
        """/code is removed — must be treated as unknown command, not call AI."""
        router = _make_router()
        result = await router.route(_make_msg("/code 写脚本"))
        assert "未知指令" in result
        router._claude.ask.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_no_params_shows_usage(self):
        router = _make_router()
        result = await router.route(_make_msg("/stop"))
        assert "用法" in result

    @pytest.mark.asyncio
    async def test_kill_is_stop_alias(self):
        router = _make_router()
        result = await router.route(_make_msg("/kill"))
        assert "用法" in result

    @pytest.mark.asyncio
    async def test_reserved_commands(self):
        router = _make_router()
        for cmd in ["/search", "/agent", "/mcp", "/rag", "/workflow"]:
            result = await router.route(_make_msg(cmd))
            assert "尚未实现" in result or "预留" in result

    @pytest.mark.asyncio
    async def test_non_private_message_ignored(self):
        router = _make_router()
        msg = IncomingMessage(1, 123, "group", "/help", {})
        assert await router.route(msg) is None

    @pytest.mark.asyncio
    async def test_shell_admin_only(self):
        router = _make_router()
        msg = _make_msg("/shell pwd", user_id=99999)
        result = await router.route(msg)
        assert "权限不足" in result

    @pytest.mark.asyncio
    async def test_status_lists_running_task(self):
        registry = TaskRegistry()
        record = registry.create("ask", "问答：长任务", 12345)
        router = _make_router(registry=registry)
        result = await router.route(_make_msg("/status"))
        assert record.id in result
        assert "问答：长任务" in result

    @pytest.mark.asyncio
    async def test_stop_running_task_by_id(self):
        registry = TaskRegistry()
        record = registry.create("ask", "问答：长任务", 12345)

        async def wait_forever():
            await asyncio.Event().wait()

        task = asyncio.create_task(wait_forever())
        registry.attach_asyncio_task(record.id, task)
        router = _make_router(registry=registry)
        result = await router.route(_make_msg(f"/stop {record.id}"))
        assert "已请求停止任务" in result
        assert task.cancelled() or task.cancelling()
        task.cancel()


# ── Plan state machine commands ────────────────────────────────


class TestPlanCommands:
    @pytest.fixture(autouse=True)
    def _cleanup_plan_data(self):
        """Ensure each test starts with a clean plan state."""
        import shutil, tempfile
        self._plan_tmp = Path(tempfile.mkdtemp(prefix="test-plan-"))
        yield
        shutil.rmtree(self._plan_tmp, ignore_errors=True)

    def _fresh_router(self):
        """Create a router with a guaranteed-fresh plan state."""
        from config import Settings
        s = Settings(PLAN_DATA_DIR=str(self._plan_tmp))
        ps = PlanStateMachine(s)
        return _make_router(settings=s, plan_state=ps)

    @pytest.mark.asyncio
    async def test_plan_create_requires_description(self):
        router = self._fresh_router()
        result = await router.route(_make_msg("/plan"))
        assert "用法" in result

    @pytest.mark.asyncio
    async def test_plan_create_generates_outline(self):
        router = self._fresh_router()
        result = await router.route(_make_msg("/plan 添加登录功能"))
        assert "计划已生成" in result
        assert "plan-start" in result or "/plan-start" in result

    @pytest.mark.asyncio
    async def test_plan_status_when_empty(self):
        router = self._fresh_router()
        result = await router.route(_make_msg("/plan-status"))
        assert "没有待确认的计划" in result

    @pytest.mark.asyncio
    async def test_plan_status_shows_pending(self):
        router = self._fresh_router()
        await router.route(_make_msg("/plan 添加搜索功能"))
        result = await router.route(_make_msg("/plan-status"))
        assert "待确认计划" in result
        assert "添加搜索功能" in result

    @pytest.mark.asyncio
    async def test_plan_start_without_pending(self):
        router = self._fresh_router()
        result = await router.route(_make_msg("/plan-start"))
        assert "没有待确认的计划" in result

    @pytest.mark.asyncio
    async def test_plan_cancel_without_pending(self):
        router = self._fresh_router()
        result = await router.route(_make_msg("/plan-cancel"))
        assert "没有待确认的计划" in result

    @pytest.mark.asyncio
    async def test_plan_log(self):
        router = self._fresh_router()
        result = await router.route(_make_msg("/plan-log"))
        assert "暂无历史计划记录" in result or "计划历史" in result

    @pytest.mark.asyncio
    async def test_plan_duplicate_pending_blocked(self):
        router = self._fresh_router()
        await router.route(_make_msg("/plan 任务A"))
        router._claude.ask.reset_mock()
        result = await router.route(_make_msg("/plan 任务B"))
        assert "已有待确认的计划" in result
        router._claude.ask.assert_not_called()

    @pytest.mark.asyncio
    async def test_plan_cancel_then_log_shows_cancelled(self):
        router = self._fresh_router()
        await router.route(_make_msg("/plan 测试取消"))
        result = await router.route(_make_msg("/plan-cancel"))
        assert "已取消" in result
        log = await router.route(_make_msg("/plan-log"))
        assert "CANCELLED" in log or "🚫" in log
