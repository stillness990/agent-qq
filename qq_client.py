import asyncio
import json
import logging
from collections.abc import AsyncIterator
from itertools import count
from typing import Any

import aiohttp

from config import Settings

logger = logging.getLogger(__name__)


class OneBotClient:
    """OneBot v11 WebSocket client for NapCat QQ."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._echo_counter = count(1)

    async def connect(self) -> None:
        headers = {}
        if self._settings.onebot_access_token:
            headers["Authorization"] = f"Bearer {self._settings.onebot_access_token}"
        self._session = aiohttp.ClientSession(headers=headers)
        try:
            self._ws = await self._session.ws_connect(self._settings.onebot_ws_url, heartbeat=30)
        except Exception:
            await self.close()
            raise
        logger.info("Connected to OneBot: %s", self._settings.onebot_ws_url)

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
        if self._session is not None:
            await self._session.close()
        self._ws = None
        self._session = None

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        if self._ws is None:
            raise RuntimeError("OneBot WebSocket is not connected")

        async for message in self._ws:
            if message.type == aiohttp.WSMsgType.TEXT:
                try:
                    payload = json.loads(message.data)
                except json.JSONDecodeError:
                    logger.warning("Invalid OneBot JSON: %s", message.data)
                    continue
                yield payload
            elif message.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                raise ConnectionError("OneBot WebSocket closed")

    async def send_private_msg(self, user_id: int, message: str) -> None:
        await self._call_api(
            "send_private_msg",
            {
                "user_id": user_id,
                "message": message,
            },
        )

    async def send_private_msg_chunked(self, user_id: int, message: str) -> None:
        chunk_size = self._settings.qq_reply_chunk_size
        chunks = [message[i : i + chunk_size] for i in range(0, len(message), chunk_size)] or [""]
        for chunk in chunks:
            await self.send_private_msg(user_id, chunk)
            await asyncio.sleep(0.2)

    async def _call_api(self, action: str, params: dict[str, Any]) -> None:
        if self._ws is None:
            raise RuntimeError("OneBot WebSocket is not connected")
        payload = {
            "action": action,
            "params": params,
            "echo": f"agent-qq-{next(self._echo_counter)}",
        }
        await self._ws.send_json(payload)
