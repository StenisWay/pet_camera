"""相簿分頁用的組合游標。

純字串運算,沒有框架依賴,所以放 shared_kernel——domain 與 application 都會碰到它。

用 (captured_at, id) 組合游標而不是 offset:相簿會持續有新項目寫入,offset 分頁會讓
使用者往下捲時重複或漏掉項目;captured_at 又可能重複(連續保存),再以 id 決勝。
見 rule_doc/功能需求/12_spec_相簿與雲端匯出.md 第 2.1 節。
"""

import base64
import binascii
import uuid
from dataclasses import dataclass
from datetime import datetime


class InvalidCursor(ValueError):
    """游標不是本服務發出的(被竄改或用了舊格式)。"""


@dataclass(frozen=True)
class Cursor:
    captured_at: datetime
    item_id: uuid.UUID

    def encode(self) -> str:
        raw = f"{self.captured_at.isoformat()}|{self.item_id}"
        return base64.urlsafe_b64encode(raw.encode()).decode()

    @classmethod
    def decode(cls, value: str) -> "Cursor":
        try:
            raw = base64.urlsafe_b64decode(value.encode()).decode()
            captured_at, item_id = raw.split("|", 1)
            return cls(datetime.fromisoformat(captured_at), uuid.UUID(item_id))
        except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
            raise InvalidCursor(value) from exc
