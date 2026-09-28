import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ExportRequestCommand:
    owner_id: uuid.UUID
    media_item_ids: list[uuid.UUID]


@dataclass(frozen=True)
class ExportAcceptedResult:
    """12_spec 第 2.3 節:回應只代表「已受理」。

    成功與否由 drive_export_status 反映,前端在相簿縮圖上呈現(第 4、5 節)。
    """

    accepted_ids: list[uuid.UUID]
    skipped_ids: list[uuid.UUID]  # 已在匯出中,未重複送出


@dataclass(frozen=True)
class ExportJob:
    """一個待執行的背景匯出工作。"""

    media_item_id: uuid.UUID
    owner_id: uuid.UUID
    object_key: str
    media_type: str
    captured_at: datetime


@dataclass(frozen=True)
class AuthorizationUrlResult:
    authorization_url: str


@dataclass(frozen=True)
class CompleteAuthorizationCommand:
    owner_id: uuid.UUID
    code: str
    state: str
