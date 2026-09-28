import uuid

import pytest

from app.domains.push_tokens.application.use_cases.unregister_push_token import (
    UnregisterPushToken,
)
from app.domains.push_tokens.domain.exceptions import PushTokenNotFound
from tests.domains.push_tokens.builders import ALICE, BOB, a_push_token


async def test_owner_can_unregister(uow):
    registration = uow.given(a_push_token(user_id=ALICE))

    await UnregisterPushToken(uow).execute(registration.id, ALICE)

    assert await uow.tokens.get(registration.id) is None
    assert uow.commit_count == 1


async def test_someone_elses_registration_is_reported_as_not_found_and_kept(uow):
    """審查 #5:非本人一律 404,不回 403(不洩漏存在性),也不得真的刪掉——
    否則任何登入者都能讓別人靜默收不到通知。"""
    registration = uow.given(a_push_token(user_id=BOB))

    with pytest.raises(PushTokenNotFound):
        await UnregisterPushToken(uow).execute(registration.id, ALICE)

    assert await uow.tokens.get(registration.id) is not None
    assert uow.commit_count == 0


async def test_unknown_registration_raises_the_same_error(uow):
    with pytest.raises(PushTokenNotFound):
        await UnregisterPushToken(uow).execute(uuid.uuid4(), ALICE)
