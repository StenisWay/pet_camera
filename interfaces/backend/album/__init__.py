"""Album 服務——涵蓋 F6(相簿與 Google Drive 匯出)。

讀取/管理 media_items 表(Media 服務負責寫入,見 media/__init__.py),
並擁有 google_drive_credentials 表。

AlbumItem 是本服務自行定義的唯讀視圖,刻意不匯入 media 服務的 MediaItem 型別——
兩服務對應到同一張表但不同的程式碼邊界,理由見
rule_doc/功能需求/13_ADR_微服務與三節點部署.md 第 1 節。

**本檔是對外契約**:給其他服務與規格書讀的。實作採 Clean Architecture,每個領域分為
domain / application / infrastructure / presentation 四層:

    app/domains/album/           相簿瀏覽與刪除(12_spec 第 2.1、2.2 節)
    app/domains/drive_export/    Google Drive 授權與匯出(第 2.3 節)

這裡的型別與介面對應實作的 **domain 層**(entities.py、repositories.py);
tests/test_contract.py 驗證兩者不會走樣。實體是純 dataclass,與 SQLAlchemy 的
資料列(infrastructure/orm.py)分開,由 mapper 轉換——資料表可以依
01_資料模型與儲存規格.md 自由演進而不牽動業務規則。

規格審查後對原始介面的修改(理由見 README 的「規格審查結論」):
- 介面一律改用 ABC + @abstractmethod,實作明確繼承(漏實作時建立實例當下就失敗)。
- 新增 get / get_many:原介面無法在刪除/匯出前驗證擁有者(IDOR)。
- delete_all_owned_by 回傳被刪項目的 R2 object key,呼叫端才清得掉物件。
- 新增 list_stale_exports:讓卡住的 exporting 有終止保證。
- 匯出狀態機(start/complete/fail)收進 AlbumItem 實體,不再散在服務層。
- 列表查詢移出 repository,改由 application 的 AlbumQueries 讀取端負責
  (純查詢、沒有業務規則,直接回傳 DTO)。
- 新增 google_drive_credentials 對應的 DriveConnection 與其 repository。
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

# 12_spec 第 2.3.2 節:僅申請 drive.file,不要求存取使用者既有雲端硬碟內容。
DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"


class MediaItemStatus(StrEnum):
    """01_資料模型與儲存規格.md 第 5 節的相簿項目狀態機(由 Media 服務推進)。"""

    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class MediaItemType(StrEnum):
    PHOTO = "photo"
    CLIP = "clip"


class DriveExportStatus(StrEnum):
    """12_spec 第 2.3 節的匯出狀態機(由 Album 服務推進)。"""

    NOT_EXPORTED = "not_exported"
    EXPORTING = "exporting"
    EXPORTED = "exported"
    FAILED = "failed"


@dataclass
class AlbumItem:
    """media_items 的唯讀視圖,僅含相簿瀏覽/匯出需要的欄位。"""

    id: uuid.UUID
    owner_id: uuid.UUID
    device_id: uuid.UUID
    type: MediaItemType
    status: MediaItemStatus
    captured_at: datetime
    # processing 期間尚未產生檔案(資料模型第 2.4 節)
    object_key: str | None = None
    thumbnail_object_key: str | None = None
    duration_sec: int | None = None
    drive_export_status: DriveExportStatus = DriveExportStatus.NOT_EXPORTED
    drive_file_id: str | None = None
    # 匯出狀態最後一次變更的時間,對應資料列的 updated_at(第 2.0 節)
    export_state_changed_at: datetime | None = None

    def is_owned_by(self, user_id: uuid.UUID) -> bool: ...

    @property
    def is_ready(self) -> bool: ...

    @property
    def object_keys(self) -> list[str]:
        """刪除項目時要一併清掉的 R2 物件(12_spec 第 2.2 節)。"""

    @property
    def is_exporting(self) -> bool: ...

    def is_export_stale(self, *, now: datetime, after: timedelta) -> bool:
        """匯出是否卡住(停在 exporting 超過時限),需改判為 failed。"""

    def start_export(self, now: datetime) -> None:
        """受理匯出,狀態轉 exporting;非 ready 的項目丟 MediaItemNotReady。"""

    def complete_export(self, *, drive_file_id: str, now: datetime) -> None: ...

    def fail_export(self, now: datetime) -> None:
        """DRIVE_002:只改匯出狀態,項目本身仍可正常瀏覽。"""


@dataclass
class DriveConnection:
    """google_drive_credentials 表(本服務擁有,見規格審查 #2)。

    與 Auth 服務的 oauth_identities 不同:那是「用 Google 登入」的身分綁定,
    這是「把相簿匯出到 Google Drive」的 drive.file 授權。
    """

    id: uuid.UUID
    owner_id: uuid.UUID
    refresh_token: str
    connected_at: datetime
    folder_id: str | None = None

    def reauthorize(self, refresh_token: str, now: datetime) -> None:
        """重新授權只換 refresh token;已建立的資料夾 id 保留。"""

    def remember_folder(self, folder_id: str) -> None:
        """「寵物攝影機」資料夾只建一次,之後直接重用。"""


class AlbumItemRepository(ABC):
    """以聚合為單位的資料存取。列表查詢不在這裡,見下方說明。"""

    @abstractmethod
    async def get(self, item_id: uuid.UUID) -> AlbumItem | None:
        """取回單一項目;不存在時回傳 None。修改後必須 save 才會保存。"""

    @abstractmethod
    async def get_many(self, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, AlbumItem]:
        """一次取回多個項目,以 id 為鍵;查不到的 id 不會出現在結果中。"""

    @abstractmethod
    async def save(self, item: AlbumItem) -> None:
        """更新由 Album 服務負責的欄位(匯出狀態)。

        Album 不建立 media_items(那是 Media 服務的職責),所以只更新不新增。
        實際寫入在 UnitOfWork.commit() 時生效。
        """

    @abstractmethod
    async def delete(self, item_id: uuid.UUID) -> None:
        """刪除單一項目;R2 物件由呼叫端另行清除。"""

    @abstractmethod
    async def delete_all_owned_by(self, owner_id: uuid.UUID) -> list[str]:
        """刪除該使用者所有項目,回傳被刪項目對應的 R2 object key(含縮圖)。

        由 Auth 服務在刪除帳號時透過 DELETE /internal/users/{user_id}/media 觸發
        (01_資料模型與儲存規格.md 第 6 節)。
        """

    @abstractmethod
    async def list_stale_exports(self, *, changed_before: datetime) -> list[AlbumItem]:
        """取出停留在 exporting 且狀態變更時間早於指定時點的項目。"""


class DriveConnectionRepository(ABC):
    @abstractmethod
    async def get_by_owner(self, owner_id: uuid.UUID) -> DriveConnection | None:
        """取回該使用者的 Drive 連結;未連結時回傳 None。"""

    @abstractmethod
    async def save(self, connection: DriveConnection) -> None:
        """新增或更新連結。一個使用者最多一份。"""

    @abstractmethod
    async def delete_by_owner(self, owner_id: uuid.UUID) -> None:
        """授權失效(DRIVE_003)或刪除帳號時清除;不存在時不視為錯誤。"""
