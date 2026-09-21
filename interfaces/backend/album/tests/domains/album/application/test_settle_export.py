import uuid

import pytest

from app.domains.album.application.use_cases.settle_export import SettleExport
from app.domains.album.domain.entities import DriveExportStatus, MediaItemStatus
from app.domains.album.domain.exceptions import AlbumItemNotFound
from tests.domains.album.builders import an_item


@pytest.fixture
def use_case(uow, clock) -> SettleExport:
    return SettleExport(uow, clock)


async def test_success_records_drive_file_id(use_case, uow):
    item = uow.given(an_item(drive_export_status=DriveExportStatus.EXPORTING))

    await use_case.succeed(item.id, drive_file_id="drive-1")

    stored = await uow.items.get(item.id)
    assert stored.drive_export_status is DriveExportStatus.EXPORTED
    assert stored.drive_file_id == "drive-1"


async def test_failure_leaves_the_item_browsable(use_case, uow):
    """DRIVE_002 驗收:匯出失敗不影響該項目在相簿內的正常瀏覽。"""
    item = uow.given(an_item(drive_export_status=DriveExportStatus.EXPORTING))

    await use_case.fail(item.id)

    stored = await uow.items.get(item.id)
    assert stored.drive_export_status is DriveExportStatus.FAILED
    assert stored.status is MediaItemStatus.READY


async def test_settling_a_deleted_item_raises_not_found(use_case):
    """受理後、上傳完成前被使用者刪掉(規格審查 #10)。"""
    with pytest.raises(AlbumItemNotFound):
        await use_case.succeed(uuid.uuid4(), drive_file_id="drive-1")
