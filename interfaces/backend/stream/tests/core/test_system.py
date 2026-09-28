"""shared_kernel.ports 的正式實作。"""

import uuid
from datetime import UTC, datetime

from app.core.system import SystemClock, Uuid7Generator


def test_clock_is_timezone_aware_utc() -> None:
    """時間一律帶時區:session 的 TTL 比較、TURN 憑證的 expiry 都靠它,
    naive datetime 相減會在跨時區部署時悄悄算錯。"""
    now = SystemClock().now()

    assert now.tzinfo is not None
    assert now.utcoffset() == datetime.now(UTC).utcoffset()


def test_generated_ids_are_uuid_v7() -> None:
    generated = Uuid7Generator().new_id()

    assert isinstance(generated, uuid.UUID)
    assert generated.version == 7


def test_generated_ids_are_unique_and_time_ordered() -> None:
    """UUIDv7 的時間排序讓 session_id 在 log 與 Redis key 裡天然照時間排。"""
    generator = Uuid7Generator()
    ids = [generator.new_id() for _ in range(50)]

    assert len(set(ids)) == 50
    assert [str(i) for i in ids] == sorted(str(i) for i in ids)
