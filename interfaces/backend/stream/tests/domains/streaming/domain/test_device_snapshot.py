"""鏡頭是否可串流的判定(06_spec 第 7 節 STREAM_001、03_spec 第 2.3 節心跳)。

這個規則放在 domain 而不是 adapter:90 秒門檻是業務決策,不是 HTTP 細節。
Device 服務只回報原始資料(status、last_seen_at),要不要拒絕串流由本服務判斷。
"""

from datetime import timedelta

import pytest

from app.domains.streaming.domain.value_objects import DeviceSnapshot, DeviceStatus
from tests.domains.streaming.builders import ALICE, DEVICE_A, NOW


def a_device(
    *,
    status: DeviceStatus = DeviceStatus.PAIRED,
    last_seen_ago: timedelta | None = timedelta(seconds=10),
    owner_id=ALICE,
) -> DeviceSnapshot:
    return DeviceSnapshot(
        device_id=DEVICE_A,
        owner_id=owner_id,
        status=status,
        last_seen_at=None if last_seen_ago is None else NOW - last_seen_ago,
    )


@pytest.mark.parametrize(
    ("last_seen_ago", "online"),
    [
        (timedelta(seconds=0), True),
        (timedelta(seconds=89), True),
        (timedelta(seconds=90), False),  # 03_spec 第 2.3 節:超過 90 秒視為 offline
        (timedelta(seconds=300), False),
        (None, False),  # 從未回報過心跳
    ],
)
def test_heartbeat_freshness_decides_online(last_seen_ago: timedelta | None, online: bool) -> None:
    assert a_device(last_seen_ago=last_seen_ago).is_online(NOW) is online


def test_device_marked_offline_is_offline_even_with_fresh_heartbeat() -> None:
    """status 已經是 offline 就不必再看心跳——Device 服務的判斷優先"""
    device = a_device(status=DeviceStatus.OFFLINE, last_seen_ago=timedelta(seconds=1))

    assert device.is_online(NOW) is False


def test_unpaired_device_is_never_streamable() -> None:
    """pending 裝置沒有擁有者,不該能被任何人串流"""
    device = a_device(status=DeviceStatus.PENDING, owner_id=None)

    assert device.is_owned_by(ALICE) is False
    assert device.is_online(NOW) is False
