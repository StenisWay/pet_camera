"""建立測試資料的輔助函式與固定 ID。"""

import uuid
from datetime import UTC, datetime

from app.domains.push_tokens.domain.entities import ClientPlatform, PushToken

ALICE = uuid.UUID("00000000-0000-0000-0000-00000000a11c")
BOB = uuid.UUID("00000000-0000-0000-0000-0000000000b0")
TOKEN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 9, 20, 3, 14, tzinfo=UTC)

FCM_TOKEN = "fcm-registration-token-abc"
WEB_PUSH_SUBSCRIPTION = '{"endpoint": "https://fcm.googleapis.com/wp/xyz", "keys": {}}'


def a_push_token(
    *,
    id: uuid.UUID = TOKEN_ID,
    user_id: uuid.UUID = ALICE,
    platform: ClientPlatform = ClientPlatform.APP,
    token: str = FCM_TOKEN,
    created_at: datetime = NOW,
) -> PushToken:
    return PushToken(id=id, user_id=user_id, platform=platform, token=token, created_at=created_at)
