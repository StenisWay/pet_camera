import uuid
from datetime import timedelta

from app.domains.push_tokens.domain.entities import ClientPlatform
from tests.domains.push_tokens.builders import (
    ALICE,
    BOB,
    FCM_TOKEN,
    NOW,
    WEB_PUSH_SUBSCRIPTION,
    a_push_token,
)


async def _saved(store, **overrides):
    async with store.uow() as uow:
        stored = await uow.tokens.save(a_push_token(**overrides))
        await uow.commit()
    return stored


async def test_get_missing_registration_returns_none(store):
    async with store.uow() as uow:
        assert await uow.tokens.get(uuid.uuid4()) is None


async def test_committed_registration_is_restored_completely(store):
    saved = await _saved(store, platform=ClientPlatform.WEB, token=WEB_PUSH_SUBSCRIPTION)

    async with store.uow() as uow:
        loaded = await uow.tokens.get(saved.id)

    assert loaded == saved
    assert loaded.created_at == NOW
    assert loaded.platform is ClientPlatform.WEB


async def test_uncommitted_save_is_rolled_back(store):
    async with store.uow() as uow:
        await uow.tokens.save(a_push_token())  # 沒有 commit

    async with store.uow() as uow:
        assert await uow.tokens.find_by_endpoint(ClientPlatform.APP, FCM_TOKEN) is None


async def test_modifying_loaded_entity_without_save_is_not_persisted(store):
    saved = await _saved(store, user_id=ALICE)

    async with store.uow() as uow:
        loaded = await uow.tokens.get(saved.id)
        loaded.rebind_to(BOB)
        await uow.commit()  # 沒有 save

    async with store.uow() as uow:
        assert (await uow.tokens.get(saved.id)).user_id == ALICE


async def test_find_by_endpoint_matches_platform_and_token(store):
    saved = await _saved(store)

    async with store.uow() as uow:
        assert (await uow.tokens.find_by_endpoint(ClientPlatform.APP, FCM_TOKEN)).id == saved.id
        assert await uow.tokens.find_by_endpoint(ClientPlatform.WEB, FCM_TOKEN) is None
        assert await uow.tokens.find_by_endpoint(ClientPlatform.APP, "other") is None


async def test_saving_a_rebound_registration_keeps_its_id(store):
    """審查 #4:換帳號登入時改綁,id 不變。"""
    saved = await _saved(store, user_id=ALICE)

    async with store.uow() as uow:
        loaded = await uow.tokens.get(saved.id)
        loaded.rebind_to(BOB)
        await uow.tokens.save(loaded)
        await uow.commit()

    async with store.uow() as uow:
        assert (await uow.tokens.get(saved.id)).user_id == BOB
        assert await uow.tokens.list_by_user(ALICE) == []


async def test_new_registration_for_a_taken_endpoint_rebinds_the_existing_one(store):
    """兩個請求同時登記同一端點:唯一鍵是 (platform, token),不能變成兩筆
    (否則同一則通知會推兩遍,01_資料模型第 2.6 節)。"""
    first = await _saved(store, id=uuid.uuid4(), user_id=ALICE)

    stored = await _saved(store, id=uuid.uuid4(), user_id=BOB, created_at=NOW + timedelta(1))

    assert stored.id == first.id
    assert stored.user_id == BOB
    assert stored.created_at == NOW
    async with store.uow() as uow:
        assert [t.id for t in await uow.tokens.list_by_user(BOB)] == [first.id]
        assert await uow.tokens.list_by_user(ALICE) == []


async def test_list_by_user_returns_only_that_users_registrations_oldest_first(store):
    newer = await _saved(store, id=uuid.uuid4(), token="b", created_at=NOW + timedelta(1))
    older = await _saved(store, id=uuid.uuid4(), token="a", created_at=NOW)
    await _saved(store, id=uuid.uuid4(), token="c", user_id=BOB)

    async with store.uow() as uow:
        found = await uow.tokens.list_by_user(ALICE)

    assert [t.id for t in found] == [older.id, newer.id]


async def test_committed_delete_removes_the_registration(store):
    saved = await _saved(store)

    async with store.uow() as uow:
        await uow.tokens.delete(saved.id)
        await uow.commit()

    async with store.uow() as uow:
        assert await uow.tokens.get(saved.id) is None


async def test_uncommitted_delete_is_rolled_back(store):
    saved = await _saved(store)

    async with store.uow() as uow:
        await uow.tokens.delete(saved.id)

    async with store.uow() as uow:
        assert await uow.tokens.get(saved.id) is not None


async def test_deleting_a_missing_registration_is_not_an_error(store):
    """端點失效的回報可能重複(同一 token 兩則通知同時失敗),刪除必須冪等。"""
    async with store.uow() as uow:
        await uow.tokens.delete(uuid.uuid4())
        await uow.commit()
