"""計數窗的 Redis 指令形狀(01_資料模型與儲存規格.md 第 7.1 節)。真正的 Redis 行為
(INCR 原子性、TTL)由 Redis 保證,這裡確認送出的指令與 key 正確。"""

from app.domains.notifications.infrastructure.redis_window import RedisNotificationWindow
from tests.domains.notifications.builders import DEVICE_ID


class RecordingPipeline:
    def __init__(self, log: list, count: int) -> None:
        self.log = log
        self.count = count

    def incr(self, key):
        self.log.append(("incr", key))

    def expire(self, key, seconds, nx=False):
        self.log.append(("expire", key, seconds, nx))

    async def execute(self):
        return [self.count, True]


class RecordingRedis:
    def __init__(self, count: int = 1) -> None:
        self.log: list = []
        self.count = count

    def pipeline(self, transaction=True):
        self.log.append(("pipeline", transaction))
        return RecordingPipeline(self.log, self.count)


async def test_increments_the_device_key_and_starts_a_5_minute_ttl_once():
    redis = RecordingRedis(count=2)
    window = RedisNotificationWindow.with_client(redis, window_seconds=300)

    assert await window.register(DEVICE_ID) == 2
    key = f"push:window:{DEVICE_ID}"
    assert redis.log == [
        ("pipeline", True),
        ("incr", key),
        # nx:只在 key 還沒有 TTL 時設定,窗口從第一個事件起算,不被後續事件延長
        ("expire", key, 300, True),
    ]
