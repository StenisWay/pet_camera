"""push_tokens API 的 Pydantic 模型。只在 presentation 層使用。

回應刻意不含 token 與 user_id:token 等同可對該裝置發推播的憑證(審查 #10)。
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RegisterPushTokenIn(BaseModel):
    platform: Literal["app", "web"]
    # Web Push subscription 是 JSON 字串,實際約數百字元;上限只為擋掉惡意超大 body
    token: str = Field(min_length=1, max_length=4096)


class PushTokenOut(BaseModel):
    id: uuid.UUID
    platform: str
    created_at: datetime


class PushTokenListOut(BaseModel):
    items: list[PushTokenOut]
