import asyncio
import logging
from dataclasses import dataclass
from time import monotonic
from typing import Any, Awaitable, Callable

from claude_client import ClaudeCodeClient
from config import Settings
from task_registry import TaskRegistry, task_name

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IncomingMessage:
    message_id: int
    user_id: int
    message_type: str
    text: str
    raw: dict[str, Any]


class MessageDeduplicator:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._seen: dict[str, float] = {}

    def seen_before(self, key: str) -> bool:
        now = monotonic()
        self._cleanup(now)
        if key in self._seen:
            return True
        self._seen[key] = now
        return False

    def _cleanup(self, now: float) -> None:
        expired = [
            key
            for key, created_at in self._seen.items()
            if now - created_at > self._ttl_seconds
        ]
        for key in expired:
            self._seen.pop(key, None)


class CommandRouter:
    def __init__(self, settings: Settings, claude: ClaudeCodeClient, registry: TaskRegistry | None = None) -> None:
        self._settings = settings
        self._claude = claude
        self._registry = registry or TaskRegistry()

    async def route(self, message: IncomingMessage) -> str | None:
        if message.message_type != "private" or not self._settings.enable_private_chat:
            return None

        text = message.text.strip()
        if not text:
            return None

        if text == "/help":
            return self._help()
        if text == "/status":
            return await self._status(message.user_id)
        if text == "/stop":
            return "用法：/stop <任务ID或关键词>\n可先发送 /status 查看任务 ID。"
        if text.startswith("/stop "):
            return self._stop(text.removeprefix("/stop ").strip(), message.user_id)
        if text == "/log":
            return self._log(message.user_id)
        if text.startswith("/ask "):
            prompt = text.removeprefix("/ask ").strip()
            return await self._run_tracked("ask", task_name("问答", prompt), message.user_id, lambda task_id: self._claude.ask(prompt, task_id=task_id))
        if text.startswith("/shell "):
            command = text.removeprefix("/shell ").strip()
            if not self._settings.enable_shell_command:
                return "当前未启用 /shell 命令。"
            if not self._settings.is_admin(message.user_id):
                return "权限不足：/shell 仅管理员可用。"
            if not self._claude._is_allowed_shell(command):
                allowed = ", ".join(self._settings.shell_allowed_prefixes)
                return f"命令不在白名单内。允许前缀：{allowed}"
            return await self._run_tracked("shell", task_name("Shell", command), message.user_id, lambda task_id: self._claude.shell(command, message.user_id, task_id=task_id))
        if text.startswith("/code "):
            prompt = text.removeprefix("/code ").strip()
            if not self._settings.is_admin(message.user_id):
                return "权限不足：/code 仅管理员可用。"
            return await self._run_tracked("code", task_name("代码", prompt), message.user_id, lambda task_id: self._claude.code(prompt, task_id=task_id))
        if text.startswith(("/search", "/agent", "/mcp", "/rag", "/workflow")):
            return "该命令接口已预留，当前版本尚未实现。"

        return await self._run_tracked("ask", task_name("问答", text), message.user_id, lambda task_id: self._claude.ask(text, task_id=task_id))

    async def _run_tracked(
        self,
        kind: str,
        name: str,
        user_id: int,
        runner: Callable[[str], Awaitable[str]],
    ) -> str:
        record = self._registry.create(kind, name, user_id)
        current_task = asyncio.current_task()
        self._registry.attach_asyncio_task(record.id, current_task)
        try:
            return await runner(record.id)
        except asyncio.CancelledError:
            raise
        finally:
            self._registry.finish(record.id)

    async def _status(self, user_id: int) -> str:
        is_admin = self._settings.is_admin(user_id)
        admin = "是" if is_admin else "否"
        claude_status = await self._claude.status()
        task_status = self._registry.format_status(user_id, is_admin)
        return (
            "agent-qq 正常运行\n"
            f"当前用户是否管理员：{admin}\n"
            f"私聊支持：{self._settings.enable_private_chat}\n"
            f"Shell 命令启用：{self._settings.enable_shell_command}\n"
            f"{claude_status}\n"
            f"{task_status}"
        )

    def _stop(self, selector: str, user_id: int) -> str:
        result = self._registry.stop(selector, user_id, self._settings.is_admin(user_id))
        return result.message

    def _log(self, user_id: int) -> str:
        if not self._settings.is_admin(user_id):
            return "权限不足：/log 仅管理员可用。"
        return "日志文件位于 logs/agent-qq.log。Docker 部署可用：docker compose logs -f agent-qq"

    def _help(self) -> str:
        return """QQ AI Agent 命令：
/help 查看帮助
/status 查看运行状态和运行中任务
/stop <任务ID或关键词> 停止运行中的任务
/ask 你好 调用 Claude Code 回答
/log 查看日志位置（管理员）
/shell pwd 执行白名单 Shell 命令（管理员）
/code 创建一个 Python 脚本 调用 Claude Code 处理代码任务（管理员）

预留命令：
/search /agent /mcp /rag /workflow"""


def parse_onebot_private_message(payload: dict[str, Any]) -> IncomingMessage | None:
    if payload.get("post_type") != "message":
        return None
    if payload.get("message_type") != "private":
        return None
    if payload.get("self_id") and str(payload.get("self_id")) == str(payload.get("user_id")):
        return None

    text = _extract_text(payload.get("message"))
    if text is None:
        text = str(payload.get("raw_message", ""))
    if text.strip().startswith("【Claude】"):
        return None

    return IncomingMessage(
        message_id=int(payload.get("message_id", 0)),
        user_id=int(payload.get("user_id", 0)),
        message_type=str(payload.get("message_type", "")),
        text=text,
        raw=payload,
    )


def _extract_text(message: object) -> str | None:
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        parts = []
        for segment in message:
            if not isinstance(segment, dict):
                continue
            if segment.get("type") == "text":
                data = segment.get("data") or {}
                if isinstance(data, dict):
                    parts.append(str(data.get("text", "")))
        return "".join(parts)
    return None
