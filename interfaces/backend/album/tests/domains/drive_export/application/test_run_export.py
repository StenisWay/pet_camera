import pytest

from app.domains.drive_export.application.dtos import ExportJob
from app.domains.drive_export.application.use_cases.run_export import RunExport
from tests.domains.drive_export.builders import CAPTURED_AT, OWNER, a_connection, exportable

FOLDER_NAME = "寵物攝影機"


@pytest.fixture
def use_case(uow, album, oauth, drive) -> RunExport:
    return RunExport(uow, album, oauth, drive, folder_name=FOLDER_NAME)


def a_job(media=None) -> ExportJob:
    media = media or exportable()
    return ExportJob(
        media_item_id=media.id,
        owner_id=OWNER,
        object_key=media.object_key,
        media_type=media.media_type,
        captured_at=CAPTURED_AT,
    )


async def test_upload_goes_into_the_pet_camera_folder(use_case, uow, album, drive):
    """12_spec 第 2.3.3 節驗收:上傳至固定資料夾「寵物攝影機」。"""
    uow.given(a_connection())
    job = a_job(exportable(media_type="clip"))

    await use_case.execute(job)

    upload = drive.uploads[0]
    assert upload["folder_id"] == drive.folders[FOLDER_NAME]
    assert upload["mime_type"] == "video/mp4"
    assert album.completed[job.media_item_id] == upload["file_id"]


async def test_folder_id_is_remembered_for_later_exports(use_case, uow, drive):
    """資料夾只建一次,之後直接重用,不必每次匯出都去 Drive 找。"""
    uow.given(a_connection())

    await use_case.execute(a_job())
    assert (await uow.connections.get_by_owner(OWNER)).folder_id == drive.folders[FOLDER_NAME]

    await use_case.execute(a_job())
    assert drive.ensure_folder_calls == 1


async def test_quota_exceeded_marks_the_item_failed(use_case, uow, album, drive):
    """DRIVE_002 驗收:匯出失敗不影響該項目在相簿內的正常瀏覽。"""
    uow.given(a_connection())
    drive.quota_exceeded = True
    job = a_job()

    await use_case.execute(job)

    assert album.failed == [job.media_item_id]
    assert job.media_item_id not in album.completed


async def test_revoked_refresh_token_clears_the_connection(use_case, uow, oauth, album):
    """DRIVE_003:授權過期後連結要清掉,使用者下次匯出才會拿到 DRIVE_001 並被導回授權頁。"""
    uow.given(a_connection(refresh_token="rt-1"))
    oauth.revoked_refresh_tokens.add("rt-1")
    job = a_job()

    await use_case.execute(job)

    assert album.failed == [job.media_item_id]
    assert await uow.connections.get_by_owner(OWNER) is None


async def test_connection_removed_mid_flight_marks_failed(use_case, album):
    """受理後、實際上傳前使用者解除了授權:背景任務不能爆掉。"""
    job = a_job()

    await use_case.execute(job)

    assert album.failed == [job.media_item_id]


async def test_item_deleted_mid_flight_does_not_raise(use_case, uow, album, drive):
    """規格審查 #10:匯出中仍可刪除,背景任務要能安靜收尾。"""
    uow.given(a_connection())
    job = a_job()
    album.missing_items.add(job.media_item_id)
    drive.quota_exceeded = True

    await use_case.execute(job)  # 不得拋出例外
