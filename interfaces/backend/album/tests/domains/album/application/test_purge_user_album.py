import uuid

import pytest

from app.domains.album.application.use_cases.purge_user_album import PurgeUserAlbum
from tests.domains.album.builders import OWNER, an_item


@pytest.fixture
def use_case(uow, storage) -> PurgeUserAlbum:
    return PurgeUserAlbum(uow, storage)


async def test_removes_only_that_users_items_and_objects(use_case, uow, storage):
    """01_資料模型與儲存規格.md 第 6 節:刪除帳號時刪光該帳號所有 media_items
    與對應 R2 物件;其他使用者的資料不得受影響。"""
    mine = [uow.given(an_item(object_key=f"media/{n}.jpg")) for n in range(3)]
    theirs = uow.given(an_item(owner_id=uuid.uuid4()))

    deleted = await use_case.execute(OWNER)

    assert deleted == 3
    for item in mine:
        assert await uow.items.get(item.id) is None
    assert await uow.items.get(theirs.id) is not None
    assert set(storage.deleted) == {f"media/{n}.jpg" for n in range(3)}


async def test_purging_an_empty_album_is_a_no_op(use_case):
    assert await use_case.execute(uuid.uuid4()) == 0
