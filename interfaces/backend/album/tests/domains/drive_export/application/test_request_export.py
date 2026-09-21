import uuid

import pytest

from app.domains.drive_export.application.dtos import ExportRequestCommand
from app.domains.drive_export.application.ports import PreparedExport
from app.domains.drive_export.application.use_cases.request_export import RequestExport
from app.domains.drive_export.domain.exceptions import (
    DriveNotConnected,
    EmptyExportRequest,
    ExportBatchTooLarge,
)
from tests.domains.drive_export.builders import OWNER, a_connection, exportable


@pytest.fixture
def use_case(uow, album, scheduler) -> RequestExport:
    return RequestExport(uow, album, scheduler, batch_limit=50)


async def test_export_without_google_connection_raises_drive_001(use_case, album):
    """12_spec 第 5 節 DRIVE_001:前端阻斷式導向 OAuth 授權頁。"""
    album.will_prepare(exportable())

    with pytest.raises(DriveNotConnected):
        await use_case.execute(ExportRequestCommand(owner_id=OWNER, media_item_ids=[uuid.uuid4()]))


async def test_empty_selection_is_rejected(use_case, uow):
    uow.given(a_connection())

    with pytest.raises(EmptyExportRequest):
        await use_case.execute(ExportRequestCommand(owner_id=OWNER, media_item_ids=[]))


async def test_batch_over_the_limit_is_rejected(use_case, uow):
    """規格審查 #6:單次匯出上限 50 筆。"""
    uow.given(a_connection())

    with pytest.raises(ExportBatchTooLarge):
        await use_case.execute(
            ExportRequestCommand(owner_id=OWNER, media_item_ids=[uuid.uuid4() for _ in range(51)])
        )


async def test_accepted_items_are_scheduled_as_background_jobs(use_case, uow, album, scheduler):
    """12_spec 第 2.3.3 節:後端非同步上傳。"""
    uow.given(a_connection())
    media = exportable(media_type="clip")
    album.will_prepare(media)

    result = await use_case.execute(
        ExportRequestCommand(owner_id=OWNER, media_item_ids=[media.id])
    )

    assert result.accepted_ids == [media.id]
    assert [j.media_item_id for j in scheduler.jobs] == [media.id]
    assert scheduler.jobs[0].media_type == "clip"


async def test_skipped_items_are_reported_and_not_scheduled(use_case, uow, album, scheduler):
    """已在 exporting 的項目不重送,但要讓前端知道它們被跳過了。"""
    uow.given(a_connection())
    skipped = uuid.uuid4()
    album.prepared = PreparedExport(accepted=[], skipped_ids=[skipped])

    result = await use_case.execute(ExportRequestCommand(owner_id=OWNER, media_item_ids=[skipped]))

    assert result.accepted_ids == []
    assert result.skipped_ids == [skipped]
    assert scheduler.jobs == []


async def test_connection_check_happens_before_touching_the_album(use_case, album):
    """未連結 Google 時不該先去動相簿的狀態。"""
    album.prepare_error = AssertionError("album must not be touched")

    with pytest.raises(DriveNotConnected):
        await use_case.execute(ExportRequestCommand(owner_id=OWNER, media_item_ids=[uuid.uuid4()]))
