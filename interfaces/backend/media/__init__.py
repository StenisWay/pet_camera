"""Media 服務——涵蓋 F5(剪輯與截圖)。擁有 media_items 表(負責寫入/建立)。

media_items 表同時被 Album 服務讀取/管理(見 album/__init__.py),是本專案唯一沒有
做到「一服務一資料表」的例外——理由見
rule_doc/功能需求/13_ADR_微服務與三節點部署.md 第 1 節。Album 服務不匯入這裡的
MediaItem 型別,而是自行定義一份唯讀視圖,兩服務可各自獨立部署替換。

本檔是**對外契約**;實作在 app/domains/media/,tests/test_contract.py 驗證兩者不會走樣。

規格審查後對原始介面的修改(見 README 的「規格審查結論」,使用者已確認「都照建議」):
- object_key 改為 Optional:資料模型第 2.4 節明定 processing 期間尚未產生檔案,
  原契約寫成必填,連 processing 狀態的項目都建不出來。
- MediaItem 新增 updated_at:processing 逾時判定要用它(審查 #9),
  與 album 的唯讀視圖一致。
- get_by_id 改為 get(item_id, owner_id):原介面無法在查詢前驗證擁有者(IDOR,審查 #6)。
- create_processing 改為 add(item):建立時就要帶 id(R2 key 含 media_item_id,
  必須先有 id 才算得出 key),由應用程式產生 UUIDv7,不靠資料庫預設值。
- mark_ready / mark_failed 併入 save(item):狀態轉移是實體的職責,repository 只負責
  保存整個聚合,不提供繞過業務規則的欄位級更新。
- 新增 find_active_clip:剪輯的冪等判定(審查 #10)。不新增欄位存起訖秒數——
  captured_at 已是「事件開始時間 + start_sec」、duration_sec 已是長度,兩者即可唯一
  識別同一段剪輯範圍。
- 新增 list_stale_processing:讓卡住的 processing 有終止保證(審查 #9)。

本服務對其他服務的依賴(都走 VCN 私有網路、不經 Load Balancer):
- Event 服務 `GET /internal/events/{id}`:取得剪輯/回放截圖的來源事件(審查 #7)。
  回應需包含 owner_id——events 表本身沒有 user_id,Media 無法自行判斷擁有者。
- Device 服務:確認鏡頭擁有者與線上狀態(比照 stream/__init__.py 的先例)。
- VM-3 worker `POST /internal/frames`、`POST /internal/clips`:擷幀與轉碼(審查 #2、#3)。
  worker 完成後回呼本服務的 `POST /internal/media/{id}/ready` 或 `/failed`。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, Protocol
from uuid import UUID

from pydantic import BaseModel


class MediaItemType(str, Enum):
    PHOTO = "photo"
    CLIP = "clip"


class MediaItemStatus(str, Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class MediaItem(BaseModel):
    id: UUID
    user_id: UUID
    device_id: UUID
    source_event_id: Optional[UUID] = None
    type: MediaItemType
    object_key: Optional[str] = None  # processing 期間尚未產生(資料模型 §2.4)
    thumbnail_object_key: Optional[str] = None
    duration_sec: Optional[int] = None  # clip 才有
    status: MediaItemStatus
    captured_at: datetime
    created_at: datetime
    updated_at: Optional[datetime] = None


class MediaItemRepository(Protocol):
    """本服務只負責建立與寫入生命週期,不負責列表查詢/刪除/匯出——那些是
    Album 服務的職責(見 album/__init__.py 的 AlbumRepository)。"""

    async def get(self, item_id: UUID, *, owner_id: UUID) -> Optional[MediaItem]:
        """取回本人的項目;不存在或不屬於該使用者時一律回 None。

        兩種情況不可區分,否則會洩漏資源存在性(審查 #6)。
        """
        ...

    async def add(self, item: MediaItem) -> None:
        """新增一筆 processing 項目。id 由應用程式產生(UUIDv7)。"""
        ...

    async def save(self, item: MediaItem) -> None:
        """保存整個聚合(狀態、object key、長度)。實際寫入在 commit 時生效。"""
        ...

    async def find_active_clip(
        self,
        *,
        owner_id: UUID,
        source_event_id: UUID,
        captured_at: datetime,
        duration_sec: int,
    ) -> Optional[MediaItem]:
        """找出同一使用者對同一段範圍、仍在 processing 或已 ready 的剪輯(審查 #10)。

        failed 的不算——使用者重送就是要重試。
        """
        ...

    async def list_stale_processing(self, *, changed_before: datetime) -> list[MediaItem]:
        """取出停留在 processing 且 updated_at 早於指定時點的項目(審查 #9)。"""
        ...
