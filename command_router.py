import logging
from dataclasses import dataclass
from time import monotonic
from typing import Any

from claude_client import ClaudeCodeClient
from config import Settings

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
    def __init__(self, settings: Settings, claude: ClaudeCodeClient) -> None:
        self._settings = settings
        self._claude = claude

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
        if text == "/log":
            return self._log(message.user_id)
        if text.startswith("/ask "):
            return await self._claude.ask(text.removeprefix("/ask ").strip())
        if text.startswith("/shell "):
            return await self._claude.shell(text.removeprefix("/shell ").strip(), message.user_id)
        if text.startswith("/code "):
            return await self._code(text.removeprefix("/code ").strip(), message.user_id)
        if text.startswith(("/search", "/agent", "/mcp", "/rag", "/workflow")):
            return "该命令接口已预留，当前版本尚未实现。"

        return await self._claude.ask(text)

    async def _status(self, user_id: int) -> str:
        admin = "是" if self._settings.is_admin(user_id) else "否"
        claude_status = await self._claude.status()
        return (
            "agent-qq 正常运行\n"
            f"当前用户是否管理员：{admin}\n"
            f"私聊支持：{self._settings.enable_private_chat}\n"
            f"Shell 命令启用：{self._settings.enable_shell_command}\n"
            f"{claude_status}"
        )

    async def _code(self, prompt: str, user_id: int) -> str:
        if not self._settings.is_admin(user_id):
            return "权限不足：/code 仅管理员可用。"
        return await self._claude.code(prompt)

    def _log(self, user_id: int) -> str:
        if not self._settings.is_admin(user_id):
            return "权限不足：/log 仅管理员可用。"
        return "日志文件位于 logs/agent-qq.log。Docker 部署可用：docker compose logs -f agent-qq"

    def _help(self) -> str:
        return """QQ AI Agent 命令：
/help 查看帮助
/status 查看运行状态
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

    text = _extract_text(payload.get("message"))
    if text is None:
        text = str(payload.get("raw_message", ""))

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
