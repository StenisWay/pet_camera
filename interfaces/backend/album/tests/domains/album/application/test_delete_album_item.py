import uuid

import pytest

from app.domains.album.application.use_cases.delete_album_item import DeleteAlbumItem
from app.domains.album.domain.entities import DriveExportStatus
from app.domains.album.domain.exceptions import AlbumItemNotFound
from tests.domains.album.builders import OWNER, an_item


@pytest.fixture
def use_case(uow, storage) -> DeleteAlbumItem:
    return DeleteAlbumItem(uow, storage)


async def test_deleting_own_item_removes_record_and_r2_objects(use_case, uow, storage):
    """12_spec 第 2.2 節驗收:刪除後對應 R2 物件(內容 + 縮圖)一併移除。"""
    item = uow.given(
        an_item(object_key="media/a.mp4", thumbnail_object_key="media-thumbnails/a.jpg")
    )

    await use_case.execute(item.id, OWNER)

    assert await uow.items.get(item.id) is None
    assert storage.deleted == ["media/a.mp4", "media-thumbnails/a.jpg"]


async def test_deleting_other_users_item_raises_not_found_and_keeps_data(use_case, uow, storage):
    """規格審查 #4:非本人項目回 not found,不洩漏存在性,也不得真的刪掉。"""
    item = uow.given(an_item(owner_id=uuid.uuid4()))

    with pytest.raises(AlbumItemNotFound):
        await use_case.execute(item.id, OWNER)

    assert await uow.items.get(item.id) is not None
    assert storage.deleted == []


async def test_deleting_unknown_item_raises_the_same_error(use_case):
    with pytest.raises(AlbumItemNotFound):
        await use_case.execute(uuid.uuid4(), OWNER)


async def test_item_being_exported_can_still_be_deleted(use_case, uow):
    """規格審查 #10:匯出中仍可刪除,背景任務發現紀錄消失即中止。"""
    item = uow.given(an_item(drive_export_status=DriveExportStatus.EXPORTING))

    await use_case.execute(item.id, OWNER)

    assert await uow.items.get(item.id) is None


async def test_delete_succeeds_and_logs_when_r2_delete_fails(use_case, uow, storage, caplog):
    """R2 刪不掉時不讓使用者卡住:DB 紀錄已移除(使用者看到的相簿是對的),
    孤兒物件寫 WARNING 供後續清理——media/ 沒有 lifecycle rule,不會自己過期。"""
    item = uow.given(an_item(object_key="media/a.jpg"))
    storage.fail_delete_keys = {"media/a.jpg"}

    with caplog.at_level("WARNING"):
        await use_case.execute(item.id, OWNER)

    assert await uow.items.get(item.id) is None
    assert "media/a.jpg" in caplog.text


async def test_failed_ownership_check_does_not_commit(use_case, uow):
    item = uow.given(an_item(owner_id=uuid.uuid4()))

    with pytest.raises(AlbumItemNotFound):
        await use_case.execute(item.id, OWNER)

    assert uow.commit_count == 0
