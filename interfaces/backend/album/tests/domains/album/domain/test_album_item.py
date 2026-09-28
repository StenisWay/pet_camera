"""相簿項目的業務規則。完全不碰資料庫、HTTP 或任何框架——這是最快的一層測試。"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.domains.album.domain.entities import DriveExportStatus, MediaItemStatus
from app.domains.album.domain.exceptions import MediaItemNotReady
from tests.domains.album.builders import OWNER, an_item

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
STALE_AFTER = timedelta(minutes=15)


def test_item_is_owned_by_its_owner_only():
    """IDOR 的第一道防線:擁有權判斷是業務規則,不是查詢條件(規格審查 #4)。"""
    item = an_item(owner_id=OWNER)

    assert item.is_owned_by(OWNER)
    assert not item.is_owned_by(uuid.uuid4())


def test_object_keys_include_thumbnail_when_present():
    """12_spec 第 2.2 節驗收:刪除時對應 R2 物件(內容 + 縮圖)一併移除。"""
    item = an_item(object_key="media/a.mp4", thumbnail_object_key="media-thumbnails/a.jpg")

    assert item.object_keys == ["media/a.mp4", "media-thumbnails/a.jpg"]


def test_processing_item_has_no_object_to_delete():
    """processing 期間還沒產生檔案(資料模型第 2.4 節),沒有東西可刪。"""
    assert an_item(status=MediaItemStatus.PROCESSING).object_keys == []


@pytest.mark.parametrize("status", [MediaItemStatus.PROCESSING, MediaItemStatus.FAILED])
def test_starting_export_on_not_ready_item_is_rejected(status):
    """規格審查 #10:只有 ready 的項目有檔案可上傳。"""
    item = an_item(status=status)

    with pytest.raises(MediaItemNotReady):
        item.start_export(NOW)


def test_starting_export_marks_exporting_with_timestamp():
    item = an_item()

    item.start_export(NOW)

    assert item.drive_export_status is DriveExportStatus.EXPORTING
    assert item.export_state_changed_at == NOW


def test_already_exported_item_can_be_exported_again():
    """12_spec 第 2.3.4 節:已 exported 的項目仍可再次觸發匯出。"""
    item = an_item(drive_export_status=DriveExportStatus.EXPORTED, drive_file_id="old")

    item.start_export(NOW)

    assert item.drive_export_status is DriveExportStatus.EXPORTING


def test_completing_export_records_drive_file_id():
    item = an_item()
    item.start_export(NOW)

    item.complete_export(drive_file_id="drive-1", now=NOW)

    assert item.drive_export_status is DriveExportStatus.EXPORTED
    assert item.drive_file_id == "drive-1"


def test_failing_export_does_not_touch_browsing_status():
    """DRIVE_002 驗收:匯出失敗不影響該項目在相簿內的正常瀏覽。"""
    item = an_item()
    item.start_export(NOW)

    item.fail_export(NOW)

    assert item.drive_export_status is DriveExportStatus.FAILED
    assert item.status is MediaItemStatus.READY


def test_export_is_stale_after_the_time_limit():
    """規格審查 #7:匯出狀態機需要終止保證。"""
    item = an_item(
        drive_export_status=DriveExportStatus.EXPORTING,
        export_state_changed_at=NOW - timedelta(minutes=16),
    )

    assert item.is_export_stale(now=NOW, after=STALE_AFTER)


def test_export_within_the_time_limit_is_not_stale():
    item = an_item(
        drive_export_status=DriveExportStatus.EXPORTING,
        export_state_changed_at=NOW - timedelta(minutes=5),
    )

    assert not item.is_export_stale(now=NOW, after=STALE_AFTER)


@pytest.mark.parametrize(
    "status",
    [DriveExportStatus.NOT_EXPORTED, DriveExportStatus.EXPORTED, DriveExportStatus.FAILED],
)
def test_only_exporting_items_can_be_stale(status):
    item = an_item(drive_export_status=status, export_state_changed_at=NOW - timedelta(days=1))

    assert not item.is_export_stale(now=NOW, after=STALE_AFTER)


def test_export_without_a_timestamp_is_treated_as_stale():
    """舊資料或異常寫入留下沒有時間戳的 exporting:視為卡住,讓它有機會被收斂。"""
    item = an_item(drive_export_status=DriveExportStatus.EXPORTING, export_state_changed_at=None)

    assert item.is_export_stale(now=NOW, after=STALE_AFTER)


def test_re_exporting_clears_the_previous_drive_file_id():
    """12_spec 第 2.3.4 節允許重複匯出,而每次匯出都會在 Drive 建立一個新檔案。

    舊的 drive_file_id 在重新匯出的當下就失效了,必須清掉:
    db/models.py 的 ck_media_items_drive_file_id_presence 要求
    「exported 且有 file id」或「非 exported 且沒有 file id」,留著舊值會直接違反約束。
    """
    item = an_item(drive_export_status=DriveExportStatus.EXPORTED, drive_file_id="old-file")

    item.start_export(NOW)

    assert item.drive_file_id is None


def test_failed_export_leaves_no_drive_file_id():
    item = an_item(drive_export_status=DriveExportStatus.EXPORTED, drive_file_id="old-file")

    item.fail_export(NOW)

    assert item.drive_file_id is None
