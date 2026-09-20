"""shared_kernel.ports 的正式實作。"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from uuid6 import uuid7

from app.shared_kernel.ports import Clock, IdGenerator, OpaqueTokenFactory


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)


class Uuid7Generator(IdGenerator):
    def new_id(self) -> uuid.UUID:
        # 01_資料模型與儲存規格.md 第 2.0 節:id 會出現在 R2 key 與 API 路徑上,
        # 用 UUIDv7 取得時間排序與 B-tree 友善的特性
        return uuid.UUID(str(uuid7()))


class Sha256TokenFactory(OpaqueTokenFactory):
    """密碼重設 token 與 refresh token 的產生與指紋計算。

    指紋用**未加鹽的 SHA-256**,而不是 bcrypt:這些 token 是 256 bits 的
    密碼學亂數,沒有字典攻擊的空間,而查詢必須是確定性的(要用 token_hash 當
    索引鍵)。加鹽的雜湊沒辦法拿來查,只能全表掃描後逐一比對。

    這與 users.password_hash 的取捨不同——那裡的輸入是人選的密碼,熵很低,
    非用加鹽的慢雜湊不可。
    """

    def generate(self) -> str:
        # 32 bytes = 256 bits
        return secrets.token_urlsafe(32)

    def fingerprint(self, secret: str) -> str:
        return hashlib.sha256(secret.encode()).hexdigest()
