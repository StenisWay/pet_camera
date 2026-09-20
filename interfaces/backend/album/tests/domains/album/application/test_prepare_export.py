import uuid

import pytest

from app.domains.album.application.use_cases.prepare_export import PrepareExport
from app.domains.album.domain.entities import DriveExportStatus, MediaItemStatus
from app.domains.album.domain.exceptions import AlbumItemNotFound, MediaItemNotReady
from tests.domains.album.builders import OWNER, an_item


@pytest.fixture
def use_case(uow, clock) -> PrepareExport:
    return PrepareExport(uow, clock)


async def test_accepted_items_are_marked_exporting(use_case, uow, clock):
    """12_spec 第 2.3.3 節:受理後 drive_export_status 先轉 exporting。"""
    item = uow.given(an_item())

    preparation = await use_case.execute(OWNER, [item.id])

    assert [i.id for i in preparation.accepted] == [item.id]
    stored = await uow.items.get(item.id)
    assert stored.drive_export_status is DriveExportStatus.EXPORTING
    assert stored.export_state_changed_at == clock.now()


async def test_other_users_item_raises_not_found(use_case, uow):
    """IDOR:不能拿別人的 media_item_id 匯出到自己的 Drive。"""
    item = uow.given(an_item(owner_id=uuid.uuid4()))

    with pytest.raises(AlbumItemNotFound):
        await use_case.execute(OWNER, [item.id])


async def test_unknown_item_raises_the_same_error(use_case):
    with pytest.raises(AlbumItemNotFound):
        await use_case.execute(OWNER, [uuid.uuid4()])


@pytest.mark.parametrize("status", [MediaItemStatus.PROCESSING, MediaItemStatus.FAILED])
async def test_not_ready_item_is_rejected(use_case, uow, status):
    """規格審查 #10:只有 ready 的項目有檔案可上傳。"""
    item = uow.given(an_item(status=status))

    with pytest.raises(MediaItemNotReady):
        await use_case.execute(OWNER, [item.id])


async def test_items_already_exporting_are_skipped(use_case, uow):
    """規格審查 #6:重複送出不應在 Drive 產生重複檔案。"""
    running = uow.given(an_item(drive_export_status=DriveExportStatus.EXPORTING))
    pending = uow.given(an_item())

    preparation = await use_case.execute(OWNER, [running.id, pending.id])

    assert [i.id for i in preparation.accepted] == [pending.id]
    assert preparation.skipped_ids == [running.id]


async def test_already_exported_item_is_accepted_again(use_case, uow):
    """12_spec 第 2.3.4 節:已 exported 的項目仍可再次觸發匯出。"""
    item = uow.given(an_item(drive_export_status=DriveExportStatus.EXPORTED, drive_file_id="old"))

    preparation = await use_case.execute(OWNER, [item.id])

    assert [i.id for i in preparation.accepted] == [item.id]


async def test_rejected_batch_leaves_no_item_marked_exporting(use_case, uow):
    """一批裡只要有一個不合法就整批拒絕——不可以留下一半已經轉成 exporting 的項目。"""
    good = uow.given(an_item())
    bad = uow.given(an_item(status=MediaItemStatus.PROCESSING))

    with pytest.raises(MediaItemNotReady):
        await use_case.execute(OWNER, [good.id, bad.id])

    assert (await uow.items.get(good.id)).drive_export_status is DriveExportStatus.NOT_EXPORTED
    assert uow.commit_count == 0
