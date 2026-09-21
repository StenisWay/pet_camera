"""push_tokens 對其他領域公開的唯一入口(app/domains/push_tokens/api.py)。"""

import uuid

from app.domains.push_tokens.api import PushTokensApi
from tests.domains.push_tokens.builders import ALICE, BOB, a_push_token
from tests.domains.push_tokens.fakes import FakePushTokensUnitOfWork


async def test_lists_endpoints_with_tokens_for_sending():
    uow = FakePushTokensUnitOfWork()
    mine = uow.given(a_push_token(id=uuid.uuid4(), token="t-1"))
    uow.given(a_push_token(id=uuid.uuid4(), token="t-2", user_id=BOB))

    endpoints = await PushTokensApi(lambda: uow).list_endpoints(ALICE)

    assert [(e.id, e.platform, e.token) for e in endpoints] == [(mine.id, "app", "t-1")]


async def test_remove_deletes_and_is_idempotent():
    uow = FakePushTokensUnitOfWork()
    registration = uow.given(a_push_token())
    api = PushTokensApi(lambda: uow)

    await api.remove(registration.id)
    await api.remove(registration.id)

    assert await uow.tokens.get(registration.id) is None
