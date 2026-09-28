import uuid

from app.domains.push_tokens.application.use_cases.list_push_tokens import ListPushTokens
from tests.domains.push_tokens.builders import ALICE, BOB, a_push_token


async def test_lists_only_the_callers_registrations_without_tokens(uow):
    """審查 #11:設定頁據此還原開關狀態;審查 #10:不回 token 明碼。"""
    mine = uow.given(a_push_token(id=uuid.uuid4(), token="a"))
    uow.given(a_push_token(id=uuid.uuid4(), token="b", user_id=BOB))

    results = await ListPushTokens(uow).execute(ALICE)

    assert [r.id for r in results] == [mine.id]
    assert not hasattr(results[0], "token")


async def test_user_without_registrations_gets_an_empty_list(uow):
    assert await ListPushTokens(uow).execute(ALICE) == []
