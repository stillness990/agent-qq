#!/usr/bin/env python3
"""Send one private message through the configured OneBot WebSocket."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(PROJECT_ROOT))

from config import Settings  # noqa: E402
from qq_client import OneBotClient  # noqa: E402


async def send_message(user_id: int, message: str, ws_url: str | None, token: str | None) -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    settings = Settings(
        ONEBOT_WS_URL=ws_url or os.getenv("ONEBOT_WS_URL", "ws://127.0.0.1:3001"),
        ONEBOT_ACCESS_TOKEN=token if token is not None else os.getenv("ONEBOT_ACCESS_TOKEN", ""),
    )
    client = OneBotClient(settings)
    await client.connect()
    try:
        await client.send_private_msg(user_id, message)
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a OneBot private test message.")
    parser.add_argument("--to", type=int, required=True, help="Target QQ user_id")
    parser.add_argument("--message", default="agent-qq 测试消息：OneBot 私聊推送成功。", help="Message text")
    parser.add_argument("--url", default=None, help="Override ONEBOT_WS_URL")
    parser.add_argument("--token", default=None, help="Override ONEBOT_ACCESS_TOKEN")
    args = parser.parse_args()
    try:
        asyncio.run(send_message(args.to, args.message, args.url, args.token))
    except Exception as exc:
        print(f"failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print("sent")


if __name__ == "__main__":
    main()
