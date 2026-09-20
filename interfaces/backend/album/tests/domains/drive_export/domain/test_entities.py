import uuid
from datetime import UTC, datetime

import pytest

from app.domains.drive_export.domain.entities import DRIVE_FILE_SCOPE, DriveConnection, DriveFile
from tests.domains.drive_export.builders import NOW, OWNER, a_connection

LATER = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def test_scope_is_drive_file_only():
    """12_spec 第 2.3.2 節驗收:僅申請 drive.file,不要求存取既有雲端硬碟內容。"""
    assert DRIVE_FILE_SCOPE == "https://www.googleapis.com/auth/drive.file"


def test_connecting_requires_a_refresh_token():
    with pytest.raises(ValueError):
        DriveConnection.connect(id=uuid.uuid4(), owner_id=OWNER, refresh_token="", now=NOW)


def test_reauthorizing_keeps_the_existing_folder():
    """重新授權不該讓已經建好的「寵物攝影機」資料夾失聯。"""
    connection = a_connection(folder_id="folder-1")

    connection.reauthorize("rt-2", LATER)

    assert connection.refresh_token == "rt-2"
    assert connection.folder_id == "folder-1"
    assert connection.connected_at == LATER


@pytest.mark.parametrize(
    ("media_type", "filename", "mime_type"),
    [
        ("photo", "photo_20260920_103015.jpg", "image/jpeg"),
        ("clip", "clip_20260920_103015.mp4", "video/mp4"),
    ],
)
def test_drive_filename_uses_capture_time(media_type, filename, mime_type):
    """用拍攝時間當檔名,使用者在自己的 Drive 裡才認得出是哪一段。"""
    file = DriveFile.for_media(
        object_key="media/a",
        media_type=media_type,
        captured_at=datetime(2026, 9, 20, 10, 30, 15, tzinfo=UTC),
    )

    assert file.filename == filename
    assert file.mime_type == mime_type


def test_reauthorizing_requires_a_refresh_token():
    connection = a_connection()

    with pytest.raises(ValueError):
        connection.reauthorize("", LATER)
