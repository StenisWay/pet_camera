"""Google Drive 匯出領域的實體與值物件。純 Python。"""

import uuid
from dataclasses import dataclass
from datetime import datetime

# 12_spec 第 2.3.2 節:僅申請 drive.file,不要求存取使用者既有雲端硬碟內容。
DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"

_EXTENSIONS = {"clip": "mp4", "photo": "jpg"}
_MIME_TYPES = {"clip": "video/mp4", "photo": "image/jpeg"}


@dataclass
class DriveConnection:
    """使用者與自己 Google Drive 的連結(google_drive_credentials,規格審查 #2)。

    與 Auth 服務的 oauth_identities 不同:那是「用 Google 登入」的身分綁定,
    這是「把相簿匯出到 Google Drive」的 drive.file 授權。
    """

    id: uuid.UUID
    owner_id: uuid.UUID
    refresh_token: str
    connected_at: datetime
    folder_id: str | None = None

    @classmethod
    def connect(
        cls, *, id: uuid.UUID, owner_id: uuid.UUID, refresh_token: str, now: datetime
    ) -> "DriveConnection":
        if not refresh_token:
            raise ValueError("refresh_token must not be empty")
        return cls(id=id, owner_id=owner_id, refresh_token=refresh_token, connected_at=now)

    def reauthorize(self, refresh_token: str, now: datetime) -> None:
        """重新授權只換 refresh token;已建立的資料夾 id 保留,不讓它失聯。"""
        if not refresh_token:
            raise ValueError("refresh_token must not be empty")
        self.refresh_token = refresh_token
        self.connected_at = now

    def remember_folder(self, folder_id: str) -> None:
        """「寵物攝影機」資料夾只建一次,之後直接重用。"""
        self.folder_id = folder_id


@dataclass(frozen=True)
class DriveFile:
    """要上傳到 Drive 的一個檔案。檔名與 MIME 是 Drive 的事,不是相簿的事。"""

    object_key: str
    filename: str
    mime_type: str

    @classmethod
    def for_media(cls, *, object_key: str, media_type: str, captured_at: datetime) -> "DriveFile":
        # 用拍攝時間當檔名,使用者在 Drive 裡才認得出是哪一段
        stamp = captured_at.strftime("%Y%m%d_%H%M%S")
        extension = _EXTENSIONS.get(media_type, "bin")
        return cls(
            object_key=object_key,
            filename=f"{media_type}_{stamp}.{extension}",
            mime_type=_MIME_TYPES.get(media_type, "application/octet-stream"),
        )
