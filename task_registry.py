import asyncio
import time
from dataclasses import dataclass
from typing import Literal


TaskStatus = Literal["running", "stopping"]


@dataclass
class TaskRecord:
    id: str
    name: str
    kind: str
    user_id: int
    created_at: float
    updated_at: float
    status: TaskStatus = "running"
    asyncio_task: asyncio.Task | None = None
    pid: int | None = None


@dataclass(frozen=True)
class StopResult:
    status: Literal["stopped", "not_found", "ambiguous"]
    message: str


class TaskRegistry:
    def __init__(self) -> None:
        self._counter = 0
        self._tasks: dict[str, TaskRecord] = {}

    def create(self, kind: str, name: str, user_id: int) -> TaskRecord:
        self._counter += 1
        now = time.time()
        record = TaskRecord(
            id=f"t{self._counter}",
            name=name,
            kind=kind,
            user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        self._tasks[record.id] = record
        return record

    def attach_asyncio_task(self, task_id: str, task: asyncio.Task | None) -> None:
        record = self._tasks.get(task_id)
        if record is None:
            return
        record.asyncio_task = task
        record.updated_at = time.time()

    def attach_process(self, task_id: str | None, pid: int) -> None:
        if task_id is None:
            return
        record = self._tasks.get(task_id)
        if record is None:
            return
        record.pid = pid
        record.updated_at = time.time()

    def clear_process(self, task_id: str | None) -> None:
        if task_id is None:
            return
        record = self._tasks.get(task_id)
        if record is None:
            return
        record.pid = None
        record.updated_at = time.time()

    def finish(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)

    def list_running(self, user_id: int, is_admin: bool = False) -> list[TaskRecord]:
        records = list(self._tasks.values())
        if not is_admin:
            records = [record for record in records if record.user_id == user_id]
        return sorted(records, key=lambda record: record.created_at)

    def format_status(self, user_id: int, is_admin: bool = False) -> str:
        records = self.list_running(user_id, is_admin)
        if not records:
            return "运行中任务：无"

        now = time.time()
        lines = ["运行中任务："]
        for record in records:
            elapsed = _format_elapsed(now - record.created_at)
            pid = f"｜PID {record.pid}" if record.pid else ""
            user = f"｜用户 {record.user_id}" if is_admin else ""
            lines.append(f"- {record.id}｜{record.name}{user}｜{record.status}｜已运行 {elapsed}{pid}")
        return "\n".join(lines)

    def stop(self, selector: str, user_id: int, is_admin: bool = False) -> StopResult:
        selector = selector.strip()
        if not selector:
            return StopResult("not_found", "用法：/stop <任务ID或关键词>\n可先发送 /status 查看任务 ID。")

        records = self.list_running(user_id, is_admin)
        matches = [record for record in records if record.id == selector]
        if not matches:
            matches = [record for record in records if selector in record.name]

        if not matches:
            return StopResult(
                "not_found",
                f"未找到可停止的运行中任务：{selector}\n可用 /status 查看任务 ID。",
            )
        if len(matches) > 1:
            lines = ["匹配到多个任务，请使用任务 ID："]
            lines.extend(f"- {record.id}｜{record.name}" for record in matches)
            return StopResult("ambiguous", "\n".join(lines))

        record = matches[0]
        record.status = "stopping"
        record.updated_at = time.time()
        if record.asyncio_task is not None and not record.asyncio_task.done():
            record.asyncio_task.cancel()
        return StopResult("stopped", f"已请求停止任务 {record.id}：{record.name}\n稍后可用 /status 查看是否已结束。")


def task_name(prefix: str, text: str, max_len: int = 42) -> str:
    compact = " ".join(text.strip().split())
    if len(compact) > max_len:
        compact = compact[: max_len - 1] + "…"
    return f"{prefix}：{compact or '未命名任务'}"


def _format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}时{minutes}分{sec}秒"
    if minutes:
        return f"{minutes}分{sec}秒"
    return f"{sec}秒"
