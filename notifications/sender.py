from collections.abc import Sequence

from config import Settings
from qq_client import OneBotClient


class QQNotificationSender:
    def __init__(self, settings: Settings, recipients: Sequence[int]) -> None:
        self.settings = settings
        self.recipients = tuple(recipients)

    async def send(self, message: str) -> None:
        if not self.recipients:
            raise RuntimeError("notification recipients are empty")
        client = OneBotClient(self.settings)
        await client.connect()
        try:
            for recipient in self.recipients:
                await client.send_private_msg(recipient, message)
        finally:
            await client.close()
