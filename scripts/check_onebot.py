#!/usr/bin/env python3
"""Check whether the configured OneBot WebSocket is reachable."""

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


async def check(ws_url: str | None, token: str | None) -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    settings = Settings(
        ONEBOT_WS_URL=ws_url or os.getenv("ONEBOT_WS_URL", "ws://127.0.0.1:3001"),
        ONEBOT_ACCESS_TOKEN=token if token is not None else os.getenv("ONEBOT_ACCESS_TOKEN", ""),
    )
    client = OneBotClient(settings)
    await client.connect()
    await client.close()
    print(f"ok: connected to {settings.onebot_ws_url}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check OneBot WebSocket connectivity.")
    parser.add_argument("--url", default=None, help="Override ONEBOT_WS_URL")
    parser.add_argument("--token", default=None, help="Override ONEBOT_ACCESS_TOKEN")
    args = parser.parse_args()
    try:
        asyncio.run(check(args.url, args.token))
    except Exception as exc:
        print(f"failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
