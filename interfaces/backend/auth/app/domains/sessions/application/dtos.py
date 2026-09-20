"""sessions 的輸入輸出 DTO。"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.shared_kernel.platform import Platform


@dataclass(frozen=True)
class SessionTokens:
    """簽發結果。refresh_token 是**明碼**,只在這一刻存在,之後只剩指紋。"""

    access_token: str
    # App 平台為 None(02_spec 第 2.3 節)
    refresh_token: str | None


@dataclass(frozen=True)
class ExtendTokenCommand:
    """來自呼叫端已驗證過的 access token claims(02_spec 第 2.8 節)。

    application 不解 JWT:解碼與簽章驗證是 presentation/infrastructure 的事,
    這裡只拿到「這個 token 是誰的、什麼平台、什麼時候發的」。
    """

    user_id: uuid.UUID
    platform: Platform
    issued_at: datetime
