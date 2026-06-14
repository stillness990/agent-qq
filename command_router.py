"""Command router with full command interception — zero AI token fallback.

All QQ messages are intercepted by pure-script parsing.  Only /plan is allowed
to call AI (for generating an execution outline, never for direct execution).
Unknown commands receive a help prompt instead of being passed to AI.

Command dictionary (COMMANDS) is the single source of truth for all routes.
"""

import asyncio
import logging
import sys
from dataclasses import dataclass
from time import monotonic
from typing import Any, Awaitable, Callable

from claude_client import ClaudeCodeClient
from circuit_breaker import CircuitBreaker
from config import Settings
from plan_state import (
    NoPendingPlanError,
    PendingPlanExistsError,
    PlanStateMachine,
)
from task_monitor import TaskMonitor
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
    """Pure command-driven router.  No natural-language fallback."""

    def __init__(
        self,
        settings: Settings,
        claude: ClaudeCodeClient,
        registry: TaskRegistry,
        plan_state: PlanStateMachine,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._settings = settings
        self._claude = claude
        self._registry = registry
        self._plan = plan_state
        self._breaker = breaker

        # ── Command dictionary ──
        # Each entry: (handler, needs_admin, help_text)
        # Only /plan is allowed to touch AI (outline generation only)
        self.COMMANDS: dict[
            str, Callable[[IncomingMessage], Awaitable[str | None]]
        ] = {
            "/help": self._cmd_help,
            "/status": self._cmd_status,
            "/stop": self._cmd_stop,
            "/kill": self._cmd_stop,  # alias
            "/log": self._cmd_log,
            "/shell": self._cmd_shell,
            # ── Plan state machine (ONLY path to AI) ──
            "/plan": self._cmd_plan_create,
            "/plan-status": self._cmd_plan_status,
            "/plan-start": self._cmd_plan_start,
            "/plan-cancel": self._cmd_plan_cancel,
            "/plan-log": self._cmd_plan_log,
            # ── Pure-script commands (zero AI) ──
            "/ping": self._cmd_ping,
            "/network": self._cmd_network,
            "/clear": self._cmd_clear,
            "/token": self._cmd_token,
            "/weather": self._cmd_weather,
            # Reserved
            "/search": self._cmd_reserved,
            "/agent": self._cmd_reserved,
            "/mcp": self._cmd_reserved,
            "/rag": self._cmd_reserved,
            "/workflow": self._cmd_reserved,
        }

    # ──────────────────────────────────────────────────────────
    # Main route entry
    # ──────────────────────────────────────────────────────────
    async def route(self, message: IncomingMessage) -> str | None:
        if message.message_type != "private" or not self._settings.enable_private_chat:
            return None

        text = message.text.strip()
        if not text:
            return None

        # Exact command match (e.g. "/help")
        if text in self.COMMANDS:
            return await self.COMMANDS[text](message) or None

        # Prefix match (e.g. "/ask hello world")
        for cmd, handler in self.COMMANDS.items():
            if text.startswith(cmd + " "):
                return await handler(message) or None

        # ── No AI fallback ──
        # Unknown input: return help prompt instead of calling Claude
        return (
            f"未知指令：「{text[:100]}」\n"
            f"发送 /help 查看可用命令列表。"
        )

    # ──────────────────────────────────────────────────────────
    # /help
    # ──────────────────────────────────────────────────────────
    async def _cmd_help(self, msg: IncomingMessage) -> str:
        is_admin = self._settings.is_admin(msg.user_id)
        lines = [
            "QQ AI Agent 命令列表：",
            "",
            "📋 计划管理（唯一 AI 交互入口）：",
            "  /plan <任务描述>  生成AI执行大纲（不实际执行）",
            "  /plan-status       查看待确认的计划",
            "  /plan-start        确认并执行待确认计划",
            "  /plan-cancel       取消待确认计划",
            "  /plan-log          查看历史计划日志",
            "",
            "🔧 任务控制：",
            "  /status            查看运行状态和任务",
            "  /stop <ID或关键词>  停止运行中的任务",
            "  /kill <ID或关键词>  同 /stop（强制终止）",
        ]
        if is_admin:
            lines.extend([
                "  /shell <命令>       执行白名单 Shell 命令（管理员）",
                "  /log                 查看日志位置（管理员）",
            ])
        lines.extend([
            "",
            "📡 系统工具：",
            "  /ping               心跳检测",
            "  /network            网络环境测试（优/良/差）",
            "  /weather            手动触发天气推送",
            "  /clear              重置对话上下文",
            "  /token              查询当前 Token 预算",
            "",
            "⚠️ 除 /plan 外，所有命令均由纯脚本执行，零 AI Token 消耗。",
        ])
        return "\n".join(lines)

    # ──────────────────────────────────────────────────────────
    # /status  — fixed: reads both memory and persistent log
    # ──────────────────────────────────────────────────────────
    async def _cmd_status(self, msg: IncomingMessage) -> str:
        is_admin = self._settings.is_admin(msg.user_id)
        admin = "是" if is_admin else "否"
        claude_status = await self._claude.status()
        task_status = self._registry.format_status(msg.user_id, is_admin)

        # Also show pending plan if any
        plan_info = ""
        pending = self._plan.read_pending()
        if pending:
            plan_info = (
                f"\n📋 待确认计划：{pending.id}\n"
                f"   描述：{pending.description[:80]}\n"
                f"   发送 /plan-start 执行，/plan-cancel 取消"
            )

        return (
            "agent-qq 正常运行\n"
            f"当前用户是否管理员：{admin}\n"
            f"私聊支持：{self._settings.enable_private_chat}\n"
            f"Shell 命令启用：{self._settings.enable_shell_command}\n"
            f"{claude_status}\n"
            f"{task_status}"
            f"{plan_info}"
        )

    # ──────────────────────────────────────────────────────────
    # /stop  /kill
    # ──────────────────────────────────────────────────────────
    async def _cmd_stop(self, msg: IncomingMessage) -> str:
        text = msg.text.strip()
        for prefix in ("/stop ", "/kill "):
            if text.startswith(prefix):
                selector = text.removeprefix(prefix).strip()
                result = self._registry.stop(
                    selector, msg.user_id,
                    self._settings.is_admin(msg.user_id),
                )
                return result.message
        return "用法：/stop <任务ID或关键词>\n可先发送 /status 查看任务 ID。"

    # ──────────────────────────────────────────────────────────
    # /log
    # ──────────────────────────────────────────────────────────
    async def _cmd_log(self, msg: IncomingMessage) -> str:
        if not self._settings.is_admin(msg.user_id):
            return "权限不足：/log 仅管理员可用。"
        return (
            "日志文件位于 logs/agent-qq.log。\n"
            "计划历史：data/plan_history.json\n"
            "状态日志：data/task_status_log.json\n"
            "Docker 部署可用：docker compose logs -f agent-qq"
        )

    # ──────────────────────────────────────────────────────────
    # /shell  (admin only, whitelist, pure subprocess — no AI)
    # ──────────────────────────────────────────────────────────
    async def _cmd_shell(self, msg: IncomingMessage) -> str:
        command = msg.text.removeprefix("/shell ").strip()
        if not command:
            return "用法：/shell <命令>"
        if not self._settings.enable_shell_command:
            return "当前未启用 /shell 命令。"
        if not self._settings.is_admin(msg.user_id):
            return "权限不足：/shell 仅管理员可用。"
        if not self._claude._is_allowed_shell(command):
            allowed = ", ".join(self._settings.shell_allowed_prefixes)
            return f"命令不在白名单内。允许前缀：{allowed}"
        return await self._run_tracked(
            "shell",
            task_name("Shell", command),
            msg.user_id,
            lambda task_id: self._claude.shell(
                command, msg.user_id, task_id=task_id,
            ),
        )

    # ══════════════════════════════════════════════════════════
    # Plan state machine commands (ONLY path to AI)
    # ══════════════════════════════════════════════════════════

    # ── /plan <description>  — AI outline only, no execution ──
    async def _cmd_plan_create(self, msg: IncomingMessage) -> str:
        text = msg.text.strip()
        if text == "/plan":
            return (
                "用法：/plan <任务描述>\n"
                "示例：/plan 给我的博客添加 RSS 订阅功能\n\n"
                "AI 将返回执行大纲，不会实际执行任何操作。"
            )
        description = text.removeprefix("/plan ").strip()

        # Check for existing pending plan
        if self._plan.has_pending():
            pending = self._plan.read_pending()
            return (
                f"⚠️ 已有待确认的计划（{pending.id}）：\n"
                f"{pending.description[:100]}\n\n"
                f"请先 /plan-start 执行或 /plan-cancel 取消。"
            )

        # Call AI for outline ONLY
        outline_prompt = (
            "你是一个任务规划助手。用户描述了一个任务，请**仅输出执行大纲和计划步骤**，"
            "绝对不要执行任何实际操作、不要修改文件、不要运行命令。\n\n"
            f"用户任务描述：{description}\n\n"
            "请按以下格式输出：\n"
            "1. 任务分析（简要理解）\n"
            "2. 执行步骤（有序列表）\n"
            "3. 涉及文件/模块\n"
            "4. 预估风险点"
        )

        try:
            outline = await self._claude.ask(outline_prompt)
        except Exception as exc:
            logger.exception("Failed to generate plan outline")
            return f"生成计划大纲失败：{exc}"

        try:
            record = self._plan.create_pending(description, outline, msg.user_id)
        except PendingPlanExistsError as exc:
            return str(exc)

        return (
            f"📋 计划已生成（{record.id}）\n\n"
            f"{outline}\n\n"
            f"── 发送 /plan-start 确认执行\n"
            f"── 发送 /plan-cancel 取消计划"
        )

    # ── /plan-status  — read pending plan ──
    async def _cmd_plan_status(self, msg: IncomingMessage) -> str:
        record = self._plan.read_pending()
        if record is None:
            return "当前没有待确认的计划。发送 /plan <描述> 创建新计划。"
        return (
            f"📋 待确认计划：{record.id}\n"
            f"创建时间：{_format_time(record.created_at)}\n"
            f"任务描述：{record.description}\n\n"
            f"执行大纲：\n{record.outline}\n\n"
            f"── 发送 /plan-start 确认执行\n"
            f"── 发送 /plan-cancel 取消计划"
        )

    # ── /plan-start  — confirm and execute ──
    async def _cmd_plan_start(self, msg: IncomingMessage) -> str:
        try:
            record = self._plan.confirm_pending()
        except NoPendingPlanError as exc:
            return str(exc)

        # Execute the plan via AI
        exec_prompt = (
            "你是一个任务执行助手。以下是已确认的执行计划，请按照大纲逐步执行。"
            "如果遇到问题，请报告并等待指示。\n\n"
            f"任务描述：{record.description}\n\n"
            f"执行大纲：\n{record.outline}"
        )

        result = await self._run_tracked(
            "plan-exec",
            task_name("Plan执行", record.description),
            msg.user_id,
            lambda task_id: self._claude.ask(exec_prompt, task_id=task_id),
            plan_id=record.id,
        )

        # Update plan history with result
        self._plan.update_executed_result(record.id, result[:500])

        return (
            f"✅ 计划 {record.id} 执行完成\n\n"
            f"结果摘要：\n{result[:1500]}\n\n"
            f"── 发送 /plan-log 查看历史记录"
        )

    # ── /plan-cancel  — discard pending plan ──
    async def _cmd_plan_cancel(self, msg: IncomingMessage) -> str:
        try:
            record = self._plan.cancel_pending()
        except NoPendingPlanError as exc:
            return str(exc)
        return f"🚫 计划 {record.id} 已取消。"

    # ── /plan-log  — read history ──
    async def _cmd_plan_log(self, msg: IncomingMessage) -> str:
        records = self._plan.read_history(limit=15)
        if not records:
            return "暂无历史计划记录。"
        lines = ["📋 计划历史（最新 15 条）：", ""]
        for r in records:
            status = r.get("status", "?") if isinstance(r, dict) else getattr(r, "status", "?")
            desc = r.get("description", "") if isinstance(r, dict) else getattr(r, "description", "")
            rid = r.get("id", "?") if isinstance(r, dict) else getattr(r, "id", "?")
            created = r.get("created_at", 0) if isinstance(r, dict) else getattr(r, "created_at", 0)
            status_icon = {
                "PENDING": "⏳",
                "EXECUTED": "✅",
                "CANCELLED": "🚫",
                "EXCEPTION": "⚠️",
            }.get(status, "❓")
            lines.append(
                f"{status_icon} {rid}｜{status}｜"
                f"{desc[:60]}｜{_format_time(created)}"
            )
        return "\n".join(lines)

    # ══════════════════════════════════════════════════════════
    # New preset commands (zero token)
    # ══════════════════════════════════════════════════════════

    # ── /ping  — heartbeat ──
    async def _cmd_ping(self, msg: IncomingMessage) -> str:
        import time as _time
        now = _time.strftime("%Y-%m-%d %H:%M:%S")
        running = self._registry.count_running()
        return (
            f"🏓 pong!\n"
            f"服务器时间：{now}\n"
            f"当前运行任务数：{running}\n"
            f"状态：在线 ✅"
        )

    # ── /network  — network quality test (优/良/差) ──
    async def _cmd_network(self, msg: IncomingMessage) -> str:
        grade, latency, loss = TaskMonitor.check_network()
        return (
            f"🌐 网络状态：{grade}\n"
            f"平均延迟：{latency:.0f}ms\n"
            f"丢包率：{loss:.0f}%"
        )

    # ── /clear  — reset conversation context ──
    async def _cmd_clear(self, msg: IncomingMessage) -> str:
        # Clear any pending plans (archive them)
        if self._plan.has_pending():
            try:
                self._plan.cancel_pending()
            except Exception:
                pass
        return "🔄 对话上下文已重置。"

    # ── /token  — query token budget ──
    async def _cmd_token(self, msg: IncomingMessage) -> str:
        try:
            status = await self._claude.status()
        except Exception:
            status = "无法查询 Claude 状态"
        return (
            f"💰 Token 预算信息：\n"
            f"{status}\n\n"
            f"注意：具体 Token 用量需查看 Claude Code 会话。"
        )

    # ── /weather  — trigger weather push script (no AI) ──
    async def _cmd_weather(self, msg: IncomingMessage) -> str:
        """Call the pre-configured weather push script directly. No AI."""
        import subprocess as _subprocess
        weather_script = self._settings.weather_push_script

        if not weather_script.exists():
            return f"天气推送脚本不存在：{weather_script}\n请检查 WEATHER_PUSH_SCRIPT 配置。"

        try:
            result = _subprocess.run(
                [sys.executable, str(weather_script)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(weather_script.parent),
            )
            if result.returncode == 0:
                output = result.stdout.strip() or "天气推送已触发（无输出）"
                return f"🌤️ {output}"
            else:
                error = result.stderr.strip() or "未知错误"
                logger.warning("Weather script failed: %s", error)
                return f"天气推送脚本执行失败：{error}"
        except FileNotFoundError:
            return f"python3 命令不可用"
        except _subprocess.TimeoutExpired:
            return "天气推送脚本执行超时"
        except Exception as exc:
            logger.exception("Weather command error")
            return f"天气推送异常：{exc}"

    # ── Reserved commands ──
    async def _cmd_reserved(self, msg: IncomingMessage) -> str:
        return "该命令接口已预留，当前版本尚未实现。"

    # ══════════════════════════════════════════════════════════
    # Internal helpers
    # ══════════════════════════════════════════════════════════

    async def _run_tracked(
        self,
        kind: str,
        name: str,
        user_id: int,
        runner: Callable[[str], Awaitable[str]],
        plan_id: str = "",
    ) -> str:
        record = self._registry.create(kind, name, user_id, plan_id=plan_id)
        current_task = asyncio.current_task()
        self._registry.attach_asyncio_task(record.id, current_task)
        try:
            result = await runner(record.id)

            # Check for token exhaustion in response
            if self._breaker:
                trip_reason = self._breaker.check_claude_response(record.id, result)
                if trip_reason:
                    self._registry.mark_exception(record.id, trip_reason)
                    return f"⚠️ {trip_reason}\n任务已熔断，请稍后重试。"

            return result
        except asyncio.CancelledError:
            self._registry.finish(record.id, "cancelled")
            raise
        except Exception as exc:
            logger.exception("Task %s failed", record.id)
            error_msg = str(exc)

            # Network error → circuit breaker
            if self._breaker:
                trip_reason = self._breaker.check_network_error(record.id, error_msg)
                if trip_reason:
                    self._registry.mark_exception(record.id, trip_reason)
                    return f"⚠️ {trip_reason}\n任务已熔断。"

            self._registry.finish(record.id, "exception")
            return f"任务执行失败：{error_msg[:300]}"
        finally:
            # Ensure cleanup if not already done
            if record.id in self._registry._tasks:
                self._registry.finish(record.id, "completed")


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


def _format_time(timestamp: float) -> str:
    import time as _time
    return _time.strftime("%Y-%m-%d %H:%M:%S", _time.localtime(timestamp))
