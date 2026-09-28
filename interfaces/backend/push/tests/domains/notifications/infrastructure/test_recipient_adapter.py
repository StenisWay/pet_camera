import uuid

from app.domains.notifications.application.ports import Channel, Recipient
from app.domains.notifications.infrastructure.recipient_adapter import (
    PushTokensRecipientDirectory,
)
from app.domains.push_tokens.api import PushTokensApi
from app.domains.push_tokens.domain.entities import ClientPlatform
from tests.domains.push_tokens.builders import ALICE, a_push_token
from tests.domains.push_tokens.fakes import FakePushTokensUnitOfWork


async def test_maps_push_token_endpoints_to_recipients_and_removes_through_the_api():
    uow = FakePushTokensUnitOfWork()
    web = uow.given(a_push_token(id=uuid.uuid4(), platform=ClientPlatform.WEB, token="{}"))
    directory = PushTokensRecipientDirectory(PushTokensApi(lambda: uow))

    assert await directory.list_for_user(ALICE) == [
        Recipient(id=web.id, channel=Channel.WEB, token="{}")
    ]

    await directory.remove(web.id)
    assert await directory.list_for_user(ALICE) == []
