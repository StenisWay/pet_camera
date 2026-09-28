import pytest

from app.domains.push_tokens.application.dtos import RegisterPushTokenCommand
from app.domains.push_tokens.application.use_cases.register_push_token import RegisterPushToken
from app.domains.push_tokens.domain.entities import ClientPlatform
from app.domains.push_tokens.domain.exceptions import BlankPushToken
from tests.domains.push_tokens.builders import ALICE, BOB, FCM_TOKEN, NOW, a_push_token


@pytest.fixture
def use_case(uow, ids, clock) -> RegisterPushToken:
    return RegisterPushToken(uow, ids, clock)


def _command(user_id=ALICE, token=FCM_TOKEN, platform=ClientPlatform.APP):
    return RegisterPushTokenCommand(user_id=user_id, platform=platform, token=token)


async def test_first_registration_creates_a_record_for_the_caller(use_case, uow, clock):
    result = await use_case.execute(_command())

    stored = await uow.tokens.get(result.id)
    assert stored.user_id == ALICE
    assert stored.token == FCM_TOKEN
    assert result.created_at == clock.now()
    assert uow.commit_count == 1


async def test_result_does_not_carry_the_token(use_case):
    """審查 #10:token 等同可對該裝置發推播的憑證,回應不含 token 本身。"""
    result = await use_case.execute(_command())

    assert not hasattr(result, "token")


async def test_re_registering_the_same_endpoint_is_idempotent(use_case, uow):
    """App 每次啟動都會 PUT 一次:不可因此長出重複的登記。"""
    first = await use_case.execute(_command())
    second = await use_case.execute(_command())

    assert second.id == first.id
    assert len(await uow.tokens.list_by_user(ALICE)) == 1


async def test_same_phone_logging_into_another_account_rebinds_the_endpoint(use_case, uow):
    """審查 #4 / 驗收:B 帳號登入後,A 帳號的事件不再推播到該裝置。"""
    existing = uow.given(a_push_token(user_id=ALICE))

    result = await use_case.execute(_command(user_id=BOB))

    assert result.id == existing.id
    assert result.created_at == NOW
    assert await uow.tokens.list_by_user(ALICE) == []
    assert [t.id for t in await uow.tokens.list_by_user(BOB)] == [existing.id]


async def test_same_token_on_another_platform_is_a_separate_endpoint(use_case, uow):
    await use_case.execute(_command(platform=ClientPlatform.APP))
    await use_case.execute(_command(platform=ClientPlatform.WEB))

    assert len(await uow.tokens.list_by_user(ALICE)) == 2


async def test_blank_token_is_rejected_without_writing(use_case, uow):
    with pytest.raises(BlankPushToken):
        await use_case.execute(_command(token="  "))

    assert uow.commit_count == 0
