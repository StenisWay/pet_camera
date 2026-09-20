"""Backoff 的正式實作:指數退避(07_spec 第 3 節邊界案例)。"""

import asyncio

from app.domains.detection.application.ports import Backoff


class ExponentialBackoff(Backoff):
    def __init__(self, *, base_seconds: float = 1.0) -> None:
        self.base_seconds = base_seconds

    async def wait(self, attempt: int) -> None:
        """第 1 次失敗等 1 秒、第 2 次等 2 秒。

        上傳失敗多半是 R2 暫時性的問題,立刻重試只會再撞一次;
        但 worker 是單例,也不能等太久,所以 3 次以內收斂。
        """
        await asyncio.sleep(self.base_seconds * (2 ** (attempt - 1)))
