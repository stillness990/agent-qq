import asyncio

from task_registry import TaskRegistry, task_name


def test_registry_lists_running_tasks() -> None:
    registry = TaskRegistry()

    record = registry.create("ask", "问答：你好", 1)

    assert registry.list_running(1) == [record]
    assert registry.format_status(1) != "运行中任务：无"
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


def test_task_name_trims_text() -> None:
    name = task_name("问答", "a" * 80, max_len=10)

    assert name == "问答：aaaaaaaaa…"
