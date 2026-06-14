"""Tests for TaskRegistry with persistence and plan integration."""

import asyncio
import tempfile
from pathlib import Path

from task_registry import TaskRegistry, task_name
from task_status_log import TaskStatusLog


def test_registry_lists_running_tasks() -> None:
    registry = TaskRegistry()
    record = registry.create("ask", "问答：你好", 1)
    assert registry.list_running(1) == [record]
    assert record.id in registry.format_status(1)
    assert "问答：你好" in registry.format_status(1)


def test_registry_filters_by_user() -> None:
    registry = TaskRegistry()
    registry.create("ask", "问答：用户1", 1)
    registry.create("ask", "问答：用户2", 2)
    assert len(registry.list_running(1)) == 1
    assert len(registry.list_running(1, is_admin=True)) == 2


def test_stop_by_id_cancels_task() -> None:
    registry = TaskRegistry()
    record = registry.create("ask", "问答：长任务", 1)

    async def wait_forever() -> None:
        await asyncio.Event().wait()

    async def run() -> None:
        task = asyncio.create_task(wait_forever())
        registry.attach_asyncio_task(record.id, task)
        result = registry.stop(record.id, 1)
        assert result.status == "stopped"
        assert task.cancelled() or task.cancelling()
        task.cancel()

    asyncio.run(run())


def test_stop_by_keyword() -> None:
    registry = TaskRegistry()
    record = registry.create("ask", "问答：分析天气推送", 1)
    result = registry.stop("天气", 1)
    assert result.status == "stopped"
    assert record.id in result.message


def test_stop_ambiguous_keyword() -> None:
    registry = TaskRegistry()
    registry.create("ask", "问答：分析天气", 1)
    registry.create("ask", "问答：天气推送", 1)
    result = registry.stop("天气", 1)
    assert result.status == "ambiguous"
    assert "匹配到多个任务" in result.message


def test_finish_removes_task() -> None:
    registry = TaskRegistry()
    record = registry.create("ask", "问答：你好", 1)
    registry.finish(record.id)
    assert registry.format_status(1) == "运行中任务：无"


def test_finish_with_custom_status() -> None:
    registry = TaskRegistry()
    record = registry.create("ask", "test", 1)
    registry.finish(record.id, "completed")
    assert registry.get(record.id) is None


def test_count_running() -> None:
    registry = TaskRegistry()
    assert registry.count_running() == 0
    registry.create("ask", "a", 1)
    registry.create("ask", "b", 1)
    assert registry.count_running() == 2


def test_mark_exception_removes_task() -> None:
    registry = TaskRegistry()
    record = registry.create("ask", "问答：异常任务", 1)
    registry.mark_exception(record.id, "Token 耗尽")
    # Task should be removed from in-memory registry
    assert registry.get(record.id) is None


def test_task_name_trims_text() -> None:
    name = task_name("问答", "a" * 80, max_len=10)
    assert name == "问答：aaaaaaaaa…"


# ── Persistence integration ───────────────────────────────────


def test_registry_with_status_log() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="test-status-log-"))
    status_log = TaskStatusLog(data_dir=tmp)

    registry = TaskRegistry(status_log=status_log)
    record = registry.create("ask", "测试持久化", 1)

    # Should be written to persistent log
    active = status_log.get_active_tasks()
    assert any(e["task_id"] == record.id for e in active)

    # Finish should update status
    registry.finish(record.id, "completed")
    active = status_log.get_active_tasks()
    assert not any(e["task_id"] == record.id for e in active)


def test_format_status_includes_persistent_entries() -> None:
    """Fix: /status should find tasks even if only in persistent log."""
    tmp = Path(tempfile.mkdtemp(prefix="test-status-fix-"))
    status_log = TaskStatusLog(data_dir=tmp)

    from task_status_log import TaskStatusEntry
    status_log.write_entry(TaskStatusEntry(
        task_id="orphan-1",
        status="running",
        description="孤立任务（仅在持久化日志中）",
        user_id=1,
    ))

    registry = TaskRegistry(status_log=status_log)
    result = registry.format_status(1, is_admin=True)
    assert "orphan-1" in result
    assert "孤立任务" in result


def test_create_with_plan_id() -> None:
    registry = TaskRegistry()
    record = registry.create("plan-exec", "Plan执行：测试", 1, plan_id="plan_123")
    assert record.plan_id == "plan_123"
