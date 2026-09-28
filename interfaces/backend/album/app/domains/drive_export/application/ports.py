"""application 層需要、但由外層實作的介面。

跨領域的需求(相簿)也定義在這裡,以 drive_export 自己的語言命名;實際接到
album.api 是 infrastructure 層 adapter 的事。
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Self

from app.domains.drive_export.application.dtos import ExportJob
from app.domains.drive_export.domain.repositories import DriveConnectionRepository


class DriveExportUnitOfWork(ABC):
    """交易邊界。use case 以 `async with uow:` 開啟,明確 commit;未 commit 即回滾。"""

    connections: DriveConnectionRepository

    @abstractmethod
    async def __aenter__(self) -> Self: ...

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """未 commit 的變更一律回滾。"""

    @abstractmethod
    async def commit(self) -> None: ...


@dataclass(frozen=True)
class ExportableMedia:
    """相簿願意讓本領域匯出的一個項目。"""

    id: uuid.UUID
    object_key: str
    media_type: str
    captured_at: datetime


@dataclass(frozen=True)
class PreparedExport:
    accepted: list[ExportableMedia]
    skipped_ids: list[uuid.UUID]


class AlbumContent(ABC):
    """drive_export 對 album 領域的需求,以本領域的語言定義。"""

    @abstractmethod
    async def prepare_export(
        self, owner_id: uuid.UUID, item_ids: list[uuid.UUID]
    ) -> PreparedExport:
        """檢核擁有權與狀態,把通過的項目轉成「匯出中」並回傳上傳所需資訊。

        任何一個 id 不存在或不屬於該使用者時丟出錯誤,整批不受理;
        已在匯出中的項目列在 skipped_ids,不重複送。
        """

    @abstractmethod
    async def complete_export(self, item_id: uuid.UUID, *, drive_file_id: str) -> None:
        """記錄匯出成功與 Drive 檔案 id。"""

    @abstractmethod
    async def fail_export(self, item_id: uuid.UUID) -> None:
        """記錄匯出失敗(DRIVE_002);項目本身仍可正常瀏覽。"""

    @abstractmethod
    async def read_object(self, object_key: str) -> bytes:
        """取出要上傳的檔案內容。"""


@dataclass(frozen=True)
class OAuthTokens:
    access_token: str
    refresh_token: str | None


class GoogleOAuth(ABC):
    @abstractmethod
    def authorization_url(self, *, state: str) -> str:
        """產生 Google 授權連結,scope 僅 drive.file(12_spec 第 2.3.2 節)。"""

    @abstractmethod
    async def exchange_code(self, code: str) -> OAuthTokens:
        """以授權碼換取 token;授權碼無效或已使用時丟 DriveAuthorizationExpired。

        使用者先前已授權過時,Google 可能不再回傳 refresh_token(此時為 None)。
        """

    @abstractmethod
    async def refresh_access_token(self, refresh_token: str) -> str:
        """換取短效 access token;refresh token 已撤銷/過期時丟 DriveAuthorizationExpired。"""


class GoogleDrive(ABC):
    @abstractmethod
    async def ensure_folder(self, *, access_token: str, name: str) -> str:
        """取得(必要時建立)指定名稱的資料夾,回傳其 id。"""

    @abstractmethod
    async def upload_file(
        self,
        *,
        access_token: str,
        folder_id: str,
        filename: str,
        content: bytes,
        mime_type: str,
    ) -> str:
        """上傳檔案並回傳 Drive 檔案 id;額度不足等失敗丟 DriveExportFailed。"""


class OAuthStateStore(ABC):
    """OAuth state 的暫存(規格審查 #8,存於共用 Redis)。"""

    @abstractmethod
    async def issue(self, state: str, owner_id: uuid.UUID, *, ttl_seconds: int) -> None:
        """記下這個 state 是發給誰的。儲存失敗時丟出例外——這裡刻意 fail-closed。"""

    @abstractmethod
    async def consume(self, state: str) -> uuid.UUID | None:
        """取出並作廢(一次性);不存在或已過期時回傳 None。"""


class ExportScheduler(ABC):
    """匯出是非同步的(12_spec 第 2.3.3 節)。"""

    @abstractmethod
    def schedule(self, job: ExportJob) -> None:
        """安排一個背景匯出工作。"""
