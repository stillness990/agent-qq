import asyncio
import logging
import os
import shlex
import signal
from contextlib import suppress
from pathlib import Path

from config import Settings
from task_registry import TaskRegistry

logger = logging.getLogger(__name__)


class ClaudeCodeClient:
    """Run intelligent tasks through the local Claude Code CLI."""

    def __init__(self, settings: Settings, registry: TaskRegistry | None = None) -> None:
        self._settings = settings
        self._registry = registry

    async def ask(self, prompt: str, task_id: str | None = None) -> str:
        return await self._run_claude(prompt, task_id=task_id)

    async def code(self, prompt: str, task_id: str | None = None) -> str:
        code_prompt = (
            "你是一个谨慎的代码助手。请根据用户需求生成或修改代码。"
            "如果需要执行命令，请先解释风险；不要访问未授权外部系统。\n\n"
            f"用户需求：{prompt}"
        )
        return await self._run_claude(code_prompt, task_id=task_id)

    async def shell(self, command: str, user_id: int, task_id: str | None = None) -> str:
        if not self._settings.enable_shell_command:
            return "当前未启用 /shell 命令。"
        if not self._settings.is_admin(user_id):
            return "权限不足：/shell 仅管理员可用。"
        if not self._is_allowed_shell(command):
            allowed = ", ".join(self._settings.shell_allowed_prefixes)
            return f"命令不在白名单内。允许前缀：{allowed}"

        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=self._safe_workdir(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        if self._registry is not None:
            self._registry.attach_process(task_id, proc.pid)
        try:
            stdout, stderr = await self._communicate(proc, task_id)
        except asyncio.TimeoutError:
            return "命令执行超时，已终止。"

        output = stdout.decode("utf-8", errors="replace")
        error = stderr.decode("utf-8", errors="replace")
        parts = []
        if output:
            parts.append(f"stdout:\n{output}")
        if error:
            parts.append(f"stderr:\n{error}")
        parts.append(f"exit_code: {proc.returncode}")
        return "\n".join(parts)

    async def status(self) -> str:
        command = f"{shlex.quote(self._settings.claude_cli_command)} --version"
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        version = stdout.decode("utf-8", errors="replace").strip()
        error = stderr.decode("utf-8", errors="replace").strip()
        if proc.returncode == 0:
            return f"Claude Code CLI 可用：{version}"
        return f"Claude Code CLI 检查失败：{error or version}"

    async def _run_claude(self, prompt: str, task_id: str | None = None) -> str:
        command = self._build_claude_command(prompt)
        logger.info("Running Claude Code CLI command")

        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=self._safe_workdir(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        if self._registry is not None:
            self._registry.attach_process(task_id, proc.pid)
        try:
            stdout, stderr = await self._communicate(proc, task_id)
        except asyncio.TimeoutError:
            logger.warning("Claude Code CLI timed out")
            return "Claude Code 执行超时，请稍后重试或缩短问题。"

        output = stdout.decode("utf-8", errors="replace").strip()
        error = stderr.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            logger.error("Claude Code CLI failed: %s", error)
            return f"Claude Code 执行失败：{error or output or proc.returncode}"
        return output or "Claude Code 没有返回内容。"

    async def _communicate(self, proc: asyncio.subprocess.Process, task_id: str | None) -> tuple[bytes, bytes]:
        try:
            return await asyncio.wait_for(
                proc.communicate(),
                timeout=self._settings.claude_timeout_seconds,
            )
        except asyncio.TimeoutError:
            await self._terminate_process_group(proc)
            raise
        except asyncio.CancelledError:
            await self._terminate_process_group(proc)
            raise
        finally:
            if self._registry is not None:
                self._registry.clear_process(task_id)

    async def _terminate_process_group(self, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        with suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
            return
        except asyncio.TimeoutError:
            pass
        if proc.returncode is None:
            with suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            with suppress(Exception):
                await proc.wait()

    def _build_claude_command(self, prompt: str) -> str:
        executable = shlex.quote(self._settings.claude_cli_command)
        quoted_prompt = shlex.quote(prompt)
        return f"{executable} -p {quoted_prompt}"

    def _safe_workdir(self) -> Path:
        workdir = self._settings.claude_workdir
        workdir.mkdir(parents=True, exist_ok=True)
        return workdir

    def _is_allowed_shell(self, command: str) -> bool:
        normalized = command.strip()
        return any(
            normalized == prefix or normalized.startswith(f"{prefix} ")
            for prefix in self._settings.shell_allowed_prefixes
        )
