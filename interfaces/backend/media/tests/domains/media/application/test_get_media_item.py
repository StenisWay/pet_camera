"""GET /media/{id}:查詢處理狀態與內容(11_spec 第 3 節 + 審查 #12)。

路由邊界:單筆內容查詢屬 Media 服務,列表與刪除屬 Album(12_spec 第 3 節)。
"""

import pytest

from app.domains.media.application.use_cases.get_media_item import GetMediaItem
from app.domains.media.domain.entities import MediaItemStatus
from app.domains.media.domain.exceptions import MediaItemNotFound
from tests.domains.media.builders import ITEM, OTHER_USER, OWNER, an_item
from tests.domains.media.fakes import FakeMediaStorage, FakeMediaUnitOfWork


@pytest.fixture
def uow():
    return FakeMediaUnitOfWork()


def build(uow, storage=None):
    return GetMediaItem(uow, storage or FakeMediaStorage())


async def test_ready_item_comes_with_a_presigned_link(uow):
    """資料模型 §3.3:一次性 presigned URL,效期 10 分鐘;不外洩 object key 以外的東西。"""
    uow.given(
        an_item(
            status=MediaItemStatus.READY,
            object_key="media/a/x.jpg",
            thumbnail_object_key="media-thumbnails/a/x.jpg",
        )
    )

    result = await build(uow).execute(ITEM, requester_id=OWNER)

    assert result.status is MediaItemStatus.READY
    assert result.content_url == "https://r2.example/media/a/x.jpg?sig=test"
    assert result.thumbnail_url == "https://r2.example/media-thumbnails/a/x.jpg?sig=test"


@pytest.mark.parametrize("status", [MediaItemStatus.PROCESSING, MediaItemStatus.FAILED])
async def test_unfinished_item_has_no_link(uow, status):
    """12_spec 第 2.1 節:只有 ready 的項目可以播放,非 ready 不提供內容連結。

    前端靠 status 決定顯示 spinner 還是錯誤圖示(11_spec 第 4 節)。
    """
    uow.given(an_item(status=status))

    result = await build(uow).execute(ITEM, requester_id=OWNER)

    assert result.status is status
    assert result.content_url is None
    assert result.thumbnail_url is None


async def test_unknown_item_is_reported_as_not_found(uow):
    with pytest.raises(MediaItemNotFound):
        await build(uow).execute(ITEM, requester_id=OWNER)


async def test_other_users_item_is_reported_as_not_found(uow):
    """審查 #6:IDOR。查不到與無權限回同一個結果。"""
    uow.given(an_item(owner_id=OTHER_USER, status=MediaItemStatus.READY))

    with pytest.raises(MediaItemNotFound):
        await build(uow).execute(ITEM, requester_id=OWNER)


async def test_reading_does_not_write(uow):
    """純查詢不該開交易(ADR 第 4 節:Media 的 C 選擇只約束寫入路徑)。"""
    uow.given(an_item(status=MediaItemStatus.READY, object_key="media/a/x.jpg"))

    await build(uow).execute(ITEM, requester_id=OWNER)

    assert uow.commit_count == 0
