#!/usr/bin/env python3
"""Claude Code hook entrypoint for agent-qq notifications."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config import Settings  # noqa: E402
from notifications.events import ClaudeHookEvent, parse_hook_event, read_stdin_json  # noqa: E402
from notifications.limiter import NotificationLimiter  # noqa: E402
from notifications.sender import QQNotificationSender  # noqa: E402
from notifications.service import ClaudeNotifyService  # noqa: E402
from notifications.state import NotificationStateStore  # noqa: E402


def _project_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def build_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    return Settings()


def build_service(settings: Settings) -> ClaudeNotifyService:
    state_dir = _project_path(settings.claude_notify_state_dir)
    store = NotificationStateStore(state_dir, settings.claude_notify_state_ttl_seconds)
    limiter = NotificationLimiter(
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
    sender = QQNotificationSender(settings, sorted(settings.notification_recipients()))
    return ClaudeNotifyService(settings, store, limiter, sender, Path(__file__).resolve())


async def async_main(args: argparse.Namespace) -> int:
    settings = build_settings()
    service = build_service(settings)
    if args.command == "send":
        await service.send_manual(" ".join(args.message))
        return 0
    if args.command == "cleanup":
        service.store.cleanup_expired()
        return 0
    if args.command == "monitor":
        await service.handle(ClaudeHookEvent(command="monitor", session_id=args.session_id))
        return 0
    payload = read_stdin_json()
    event = parse_hook_event(args.command, payload)
    await service.handle(event)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Claude Code QQ notification hook for agent-qq.")
    sub = parser.add_subparsers(dest="command", required=True)
    send_p = sub.add_parser("send")
    send_p.add_argument("message", nargs="+")
    for name in ("start", "stage", "success", "failure", "stop", "cleanup"):
        sub.add_parser(name)
    monitor_p = sub.add_parser("monitor")
    monitor_p.add_argument("--session-id", required=True)
    args = parser.parse_args()
    try:
        return asyncio.run(async_main(args))
    except Exception as exc:
        if os.getenv("CLAUDE_NOTIFY_DEBUG"):
            print(f"claude_notify_hook failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
