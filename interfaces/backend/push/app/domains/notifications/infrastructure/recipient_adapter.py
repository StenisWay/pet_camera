"""RecipientDirectory → push_tokens.api。跨領域只在這裡發生。"""

import uuid

from app.domains.notifications.application.ports import Channel, Recipient, RecipientDirectory
from app.domains.push_tokens.api import PushTokensApi


class PushTokensRecipientDirectory(RecipientDirectory):
    def __init__(self, api: PushTokensApi) -> None:
        self._api = api

    async def list_for_user(self, user_id: uuid.UUID) -> list[Recipient]:
        return [
            Recipient(id=e.id, channel=Channel(e.platform), token=e.token)
            for e in await self._api.list_endpoints(user_id)
        ]

    async def remove(self, recipient_id: uuid.UUID) -> None:
        await self._api.remove(recipient_id)
