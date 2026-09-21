"""use case 的輸入輸出。純 dataclass,不是 Pydantic——HTTP 形狀在 presentation 決定。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.domains.push_tokens.domain.entities import ClientPlatform, PushToken


@dataclass(frozen=True)
class RegisterPushTokenCommand:
    user_id: uuid.UUID
    platform: ClientPlatform
    token: str


@dataclass(frozen=True)
class PushTokenResult:
    """刻意不含 token:它等同可對該裝置發推播的憑證(審查 #10)。"""

    id: uuid.UUID
    platform: ClientPlatform
    created_at: datetime

    @classmethod
    def from_entity(cls, push_token: PushToken) -> PushTokenResult:
        return cls(id=push_token.id, platform=push_token.platform, created_at=push_token.created_at)
