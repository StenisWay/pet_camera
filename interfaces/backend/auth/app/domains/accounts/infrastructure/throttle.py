"""忘記密碼的限流(02_spec 第 2.4 節)。

email 與來源 IP 各 5 次/小時。全站預設的 120 次/分鐘對一個「會寄信到第三人信箱」
的端點太寬鬆——拿它轟炸別人的信箱不需要任何帳號。

限流後端不可用時 fail-open,與 10_錯誤處理與狀態規範.md 第 3 節一致:
限流是保護機制,不該讓它自己的故障變成阻斷服務的原因。
"""

from app.core.rate_limit import RateLimiter
from app.domains.accounts.application.ports import PasswordResetThrottle

ENDPOINT = "password_forgot"


class RateLimiterThrottle(PasswordResetThrottle):
    def __init__(self, limiter: RateLimiter) -> None:
        self._limiter = limiter

    async def check(self, *identities: str) -> None:
        for identity in identities:
            if not identity:
                # 取不到來源 IP 時不要用空字串當 key,否則所有無 IP 的請求
                # 會共用同一個計數,互相把對方限流掉
                continue
            await self._limiter.check(identity, endpoint=ENDPOINT)
