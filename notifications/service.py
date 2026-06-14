import asyncio
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from config import Settings
from notifications.events import ClaudeHookEvent
from notifications.formatter import (
    classify_stage,
    extract_failure_reason,
    failure_hash,
    format_failure,
    format_heartbeat,
    format_stage,
    format_start,
    format_stop,
    format_success,
    summarize_prompt,
    trim_message,
)
from notifications.limiter import NotificationLimiter
from notifications.sender import QQNotificationSender
from notifications.state import NotificationStateStore


class ClaudeNotifyService:
    def __init__(
        self,
        settings: Settings,
        store: NotificationStateStore,
        limiter: NotificationLimiter,
        sender: QQNotificationSender,
        script_path: Path | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.limiter = limiter
        self.sender = sender
        self.script_path = script_path

    async def handle(self, event: ClaudeHookEvent) -> None:
        if not self.settings.claude_notify_enabled:
            return
        if not self._cwd_allowed(event.cwd):
            return
        self.store.cleanup_expired()
        if event.command == "start":
            await self.handle_start(event)
        elif event.command == "stage":
            await self.handle_stage(event)
        elif event.command == "success":
            await self.handle_success(event)
        elif event.command == "failure":
            await self.handle_failure(event)
        elif event.command == "stop":
            await self.handle_stop(event)
        elif event.command == "monitor":
            await self.handle_monitor(event.session_id)

    async def send_manual(self, message: str) -> None:
        await self._send(trim_message(message, self.settings.claude_notify_message_max_len), None, force=True)

    async def handle_start(self, event: ClaudeHookEvent) -> None:
        now = time.time()
        state = self.store.read_session(event.session_id)
        title = summarize_prompt(event.prompt, 60)
        state.update(
            {
                "session_id": event.session_id,
                "title": title,
                "started_at": state.get("started_at") or now,
                "updated_at": now,
                "done": False,
                "last_stage": "开始执行任务",
                "long_notice_sent": state.get("long_notice_sent", False),
            }
        )
        decision = self.limiter.should_send_start(state, now)
        if decision.allowed:
            state["start_sent_at"] = now
            await self._send(format_start(self.settings.claude_notify_prefix, title), state)
        else:
            self._suppress(state)
        self.store.write_session(event.session_id, state)
        self._spawn_monitor(event.session_id)

    async def handle_stage(self, event: ClaudeHookEvent) -> None:
        now = time.time()
        state = self._ensure_state(event.session_id, now)
        stage, kind = classify_stage(event.tool_name, event.tool_input)
        state["tool_count"] = int(state.get("tool_count", 0) or 0) + 1
        state["updated_at"] = now
        state["last_stage"] = stage
        state["last_tool"] = event.tool_name or ""
        state["last_kind"] = kind
        self._append_stage(state, stage)
        decision = self.limiter.should_send_stage(state, stage, now)
        if decision.allowed:
            state["last_stage_at"] = now
            state["last_notified_stage"] = stage
            await self._send(format_stage(self.settings.claude_notify_prefix, stage), state)
        else:
            self._suppress(state)
        self.store.write_session(event.session_id, state)

    async def handle_success(self, event: ClaudeHookEvent) -> None:
        now = time.time()
        state = self._ensure_state(event.session_id, now)
        stage, kind = classify_stage(event.tool_name, event.tool_input)
        state["success_count"] = int(state.get("success_count", 0) or 0) + 1
        state["last_success_at"] = now
        state["updated_at"] = now
        decision = self.limiter.should_send_success(state, kind, now)
        if decision.allowed:
            await self._send(format_success(self.settings.claude_notify_prefix, stage), state)
        else:
            self._suppress(state)
        self.store.write_session(event.session_id, state)

    async def handle_failure(self, event: ClaudeHookEvent) -> None:
        now = time.time()
        state = self._ensure_state(event.session_id, now)
        reason = extract_failure_reason(event.tool_name, event.tool_response, self.settings.claude_notify_message_max_len)
        digest = failure_hash(event.tool_name, reason)
        state["failure_count"] = int(state.get("failure_count", 0) or 0) + 1
        state["updated_at"] = now
        decision = self.limiter.should_send_failure(state, digest, now)
        if decision.allowed:
            state["last_failure_hash"] = digest
            state["last_failure_at"] = now
            await self._send(format_failure(self.settings.claude_notify_prefix, reason), state, force=True)
        else:
            self._suppress(state)
        self.store.write_session(event.session_id, state)

    async def handle_stop(self, event: ClaudeHookEvent) -> None:
        now = time.time()
        state = self._ensure_state(event.session_id, now)
        decision = self.limiter.should_send_stop(state, now)
        state["updated_at"] = now
        if decision.allowed:
            state["stop_sent_at"] = now
            await self._send(format_stop(self.settings.claude_notify_prefix, state, now), state, force=True)
        else:
            self._suppress(state)
        state["done"] = True
        state["last_stage"] = "本轮完成"
        self.store.write_session(event.session_id, state)
        self.store.release_monitor_lock(event.session_id)

    async def handle_monitor(self, session_id: str) -> None:
        if not self.store.acquire_monitor_lock(session_id, self.settings.claude_notify_monitor_lock_ttl_seconds):
            return
        try:
            while True:
                await asyncio.sleep(self.settings.claude_notify_monitor_interval_seconds)
                now = time.time()
                state = self.store.read_session(session_id)
                if not state or state.get("done"):
                    return
                self.store.refresh_monitor_lock(session_id, now)
                started_at = float(state.get("started_at", now) or now)
                last_heartbeat_at = float(state.get("last_heartbeat_at", started_at) or started_at)
                elapsed = now - started_at
                if elapsed >= self.settings.claude_notify_long_task_seconds and not state.get("long_notice_sent"):
                    state["long_notice_sent"] = True
                    state["last_heartbeat_at"] = now
                    await self._send(format_heartbeat(self.settings.claude_notify_prefix, state, now), state)
                    self._write_if_not_done(session_id, state)
                    continue
                if elapsed >= self.settings.claude_notify_heartbeat_seconds and now - last_heartbeat_at >= self.settings.claude_notify_heartbeat_seconds:
                    state["last_heartbeat_at"] = now
                    await self._send(format_heartbeat(self.settings.claude_notify_prefix, state, now), state)
                    self._write_if_not_done(session_id, state)
        finally:
            self.store.release_monitor_lock(session_id)

    def _write_if_not_done(self, session_id: str, state: dict[str, Any]) -> None:
        """Re-check done flag before writing to avoid race with handle_stop."""
        latest = self.store.read_session(session_id)
        if latest and latest.get("done"):
            return
        self.store.write_session(session_id, state)

    def _ensure_state(self, session_id: str, now: float) -> dict[str, Any]:
        state = self.store.read_session(session_id)
        if not state:
            state = {"session_id": session_id, "title": "未命名任务", "started_at": now}
        state.setdefault("sent_count", 0)
        state.setdefault("suppressed_count", 0)
        state.setdefault("success_count", 0)
        state.setdefault("failure_count", 0)
        state.setdefault("tool_count", 0)
        state.setdefault("recent_stages", [])
        return state

    async def _send(self, message: str, state: dict[str, Any] | None, force: bool = False) -> None:
        recipients = self.settings.notification_recipients()
        if not recipients:
            return
        global_state = self.store.read_global()
        now = time.time()
        allowed = True
        if not force:
            for recipient in recipients:
                decision = self.limiter.should_send_global(global_state, recipient, now)
                if not decision.allowed:
                    allowed = False
                    break
        if not allowed:
            if state is not None:
                self._suppress(state)
            self.store.write_global(global_state)
            return
        await self.sender.send(trim_message(message, self.settings.claude_notify_message_max_len))
        for recipient in recipients:
            self.limiter.record_global_send(global_state, recipient, now)
        self.store.write_global(global_state)
        if state is not None:
            state["sent_count"] = int(state.get("sent_count", 0) or 0) + 1

    def _spawn_monitor(self, session_id: str) -> None:
        if self.script_path is None:
            return
        if not self.store.acquire_monitor_lock(session_id, self.settings.claude_notify_monitor_lock_ttl_seconds):
            return
        self.store.release_monitor_lock(session_id)
        subprocess.Popen(
            [sys.executable, str(self.script_path), "monitor", "--session-id", session_id],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def _cwd_allowed(self, cwd: str | None) -> bool:
        prefixes = self.settings.claude_notify_allowed_cwd_prefixes
        if not prefixes or not cwd:
            return True
        return any(str(cwd).startswith(prefix) for prefix in prefixes)

    def _append_stage(self, state: dict[str, Any], stage: str) -> None:
        recent = state.setdefault("recent_stages", [])
        if not isinstance(recent, list):
            recent = []
            state["recent_stages"] = recent
        if not recent or recent[-1] != stage:
            recent.append(stage)
        del recent[:-8]

    def _suppress(self, state: dict[str, Any]) -> None:
        state["suppressed_count"] = int(state.get("suppressed_count", 0) or 0) + 1
