import time
from pathlib import Path

import pytest

from config import Settings
from notifications.events import ClaudeHookEvent, parse_hook_event
from notifications.formatter import classify_stage, failure_hash, format_stop, summarize_prompt
from notifications.limiter import NotificationLimiter
from notifications.service import ClaudeNotifyService
from notifications.state import NotificationStateStore


class FakeSender:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, message: str) -> None:
        self.messages.append(message)


def make_limiter(**overrides) -> NotificationLimiter:
    values = {
        "stage_cooldown_seconds": 60,
        "failure_cooldown_seconds": 180,
        "min_interval_seconds": 0,
        "max_per_10_minutes": 20,
        "max_per_hour": 60,
        "session_budget": 25,
        "start_dedupe_seconds": 30,
        "stop_dedupe_seconds": 30,
        "success_mode": "important",
    }
    values.update(overrides)
    return NotificationLimiter(**values)


def make_service(tmp_path: Path, sender: FakeSender | None = None, **settings_overrides) -> tuple[ClaudeNotifyService, FakeSender]:
    settings = Settings(
        ADMIN_QQ_IDS="12345",
        CLAUDE_NOTIFY_STATE_DIR=tmp_path / "notify-state",
        **settings_overrides,
    )
    store = NotificationStateStore(settings.claude_notify_state_dir, settings.claude_notify_state_ttl_seconds)
    limiter = make_limiter(
        stage_cooldown_seconds=settings.claude_notify_stage_cooldown_seconds,
        failure_cooldown_seconds=settings.claude_notify_failure_cooldown_seconds,
        min_interval_seconds=settings.claude_notify_min_interval_seconds,
        max_per_10_minutes=settings.claude_notify_max_per_10_minutes,
        max_per_hour=settings.claude_notify_max_per_hour,
        session_budget=settings.claude_notify_session_budget,
        start_dedupe_seconds=settings.claude_notify_start_dedupe_seconds,
        stop_dedupe_seconds=settings.claude_notify_stop_dedupe_seconds,
        success_mode=settings.claude_notify_success_mode,
    )
    fake = sender or FakeSender()
    return ClaudeNotifyService(settings, store, limiter, fake), fake


def test_classify_stage_for_common_tools() -> None:
    assert classify_stage("Read", {"file_path": "/tmp/a.md"})[0] == "正在分析资料：a.md"
    assert classify_stage("WebSearch", {})[0] == "正在搜索资料"
    assert classify_stage("Edit", {"file_path": "/tmp/a.py"})[0] == "正在修改文件：a.py"
    assert classify_stage("Bash", {"command": "pytest -q"}) == ("正在运行测试", "test")
    assert classify_stage("Bash", {"command": "git push origin main"}) == ("正在推送代码", "git-push")
    assert classify_stage("Agent", {}) == ("正在调度 Agent 任务", "agent")


def test_prompt_summary_and_stop_format() -> None:
    assert summarize_prompt("\n  hello   world  ") == "hello world"
    state = {
        "started_at": time.time() - 62,
        "tool_count": 3,
        "success_count": 2,
        "failure_count": 1,
        "suppressed_count": 4,
        "recent_stages": ["分析", "修改", "测试"],
    }
    message = format_stop("【Claude】", state, time.time())
    assert "本轮完成" in message
    assert "工具 3 次" in message
    assert "已合并 4 条高频通知" in message


def test_limiter_stage_cooldown_and_failure_hash() -> None:
    limiter = make_limiter()
    now = time.time()
    state = {"last_notified_stage": "正在分析资料", "last_stage_at": now, "sent_count": 0}
    assert not limiter.should_send_stage(state, "正在分析资料", now + 10).allowed
    assert limiter.should_send_stage(state, "正在修改文件", now + 10).allowed
    digest = failure_hash("Bash", "exit 1")
    state = {"last_failure_hash": digest, "last_failure_at": now}
    assert not limiter.should_send_failure(state, digest, now + 10).allowed


def test_state_store_sanitizes_session_and_cleans_expired(tmp_path: Path) -> None:
    store = NotificationStateStore(tmp_path, ttl_seconds=1)
    store.write_session("bad/session:id", {"updated_at": time.time() - 5})
    assert store.session_path("bad/session:id").name == "bad_session_id.json"
    assert store.cleanup_expired(time.time()) == 1


@pytest.mark.asyncio
async def test_service_start_stage_stop_with_anti_spam(tmp_path: Path) -> None:
    service, sender = make_service(tmp_path, CLAUDE_NOTIFY_MIN_INTERVAL_SECONDS=0)
    await service.handle_start(ClaudeHookEvent(command="start", session_id="s1", prompt="测试通知"))
    await service.handle_stage(ClaudeHookEvent(command="stage", session_id="s1", tool_name="Read", tool_input={}))
    await service.handle_stage(ClaudeHookEvent(command="stage", session_id="s1", tool_name="Read", tool_input={}))
    await service.handle_stop(ClaudeHookEvent(command="stop", session_id="s1"))
    assert len(sender.messages) == 3
    assert sender.messages[0].startswith("【Claude】开始")
    assert "阶段" in sender.messages[1]
    assert "本轮完成" in sender.messages[-1]
    state = service.store.read_session("s1")
    assert state["suppressed_count"] >= 1


@pytest.mark.asyncio
async def test_service_allowed_cwd_prefix(tmp_path: Path) -> None:
    service, sender = make_service(tmp_path, CLAUDE_NOTIFY_ALLOWED_CWD_PREFIXES="/allowed")
    await service.handle(ClaudeHookEvent(command="start", session_id="s1", cwd="/blocked", prompt="x"))
    assert sender.messages == []


def test_parse_hook_event_defaults() -> None:
    event = parse_hook_event("stage", {"tool_name": "Bash", "tool_input": {"command": "pytest"}})
    assert event.command == "stage"
    assert event.session_id == "default"
    assert event.tool_name == "Bash"
