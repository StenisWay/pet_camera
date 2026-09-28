"""Device 實體的業務規則。

每條規則在這一層窮盡測試;外層(application / presentation)只驗證規則有被接上。
"""

from datetime import timedelta

import pytest

from app.domains.devices.domain.entities import Device, DeviceStatus
from app.domains.devices.domain.exceptions import (
    DeviceAlreadyPaired,
    DeviceNotPaired,
    InvalidDeviceName,
    PairingCodeExpired,
    PairingCodeInvalid,
)
from tests.domains.devices.builders import (
    ALICE,
    BOB,
    DEVICE_ID,
    HARDWARE_ID,
    NOW,
    SECRET_HASH,
    VALID_CODE,
    a_paired_device,
    a_pairing_code,
    a_pending_device,
)

OFFLINE_AFTER = 90  # 03_spec 第 2.3 節
NAME_MAX = 30  # 規格審查 #11


# --- register(03_spec 第 2.1 節、規格審查 #11) ---------------------------------


def test_register_creates_a_pending_unowned_device():
    code = a_pairing_code()

    device = Device.register(
        id=DEVICE_ID,
        hardware_id=HARDWARE_ID,
        secret_hash=SECRET_HASH,
        pairing_code=code,
        name="未命名鏡頭",
        now=NOW,
    )

    assert device.status is DeviceStatus.PENDING
    assert device.user_id is None
    assert device.pairing_code == code
    assert device.last_seen_at is None
    assert device.created_at == NOW
    assert device.name == "未命名鏡頭"


# --- pair(03_spec 第 2.2 節、規格審查 #5) --------------------------------------


def test_pair_binds_owner_and_clears_the_pairing_code():
    device = a_pending_device()

    device.pair(user_id=ALICE, typed_code=VALID_CODE, now=NOW)

    assert device.status is DeviceStatus.PAIRED
    assert device.user_id == ALICE
    assert device.pairing_code is None


def test_pair_accepts_the_code_as_the_user_typed_it():
    """審查 #4:大小寫不敏感、容許連字號,I/L→1、O→0。"""
    device = a_pending_device()

    device.pair(user_id=ALICE, typed_code="abcd-1234", now=NOW)

    assert device.status is DeviceStatus.PAIRED


def test_pair_with_expired_code_raises_device_001():
    device = a_pending_device(pairing_code=a_pairing_code(expires_in=timedelta(minutes=10)))

    with pytest.raises(PairingCodeExpired):
        device.pair(user_id=ALICE, typed_code=VALID_CODE, now=NOW + timedelta(minutes=11))

    assert device.status is DeviceStatus.PENDING
    assert device.user_id is None


def test_pair_with_wrong_code_raises_device_002():
    device = a_pending_device()

    with pytest.raises(PairingCodeInvalid):
        device.pair(user_id=ALICE, typed_code="ZZZZ9999", now=NOW)

    assert device.user_id is None


def test_wrong_code_takes_precedence_over_expiry():
    """碼本身就不對時回 DEVICE_002,不透漏「這組碼存在但過期了」。"""
    device = a_pending_device(pairing_code=a_pairing_code(expires_in=timedelta(minutes=10)))

    with pytest.raises(PairingCodeInvalid):
        device.pair(user_id=ALICE, typed_code="ZZZZ9999", now=NOW + timedelta(minutes=11))


def test_pair_an_already_paired_device_raises_device_002_not_device_003():
    """審查 #5:已配對一律回 DEVICE_002,DEVICE_003 已從規格移除。"""
    device = a_paired_device(user_id=BOB)

    with pytest.raises(PairingCodeInvalid):
        device.pair(user_id=ALICE, typed_code=VALID_CODE, now=NOW)

    assert device.user_id == BOB


# --- reissue_pairing_code(規格審查 #3) -----------------------------------------


def test_reissue_replaces_the_code_on_a_pending_device():
    device = a_pending_device()
    new_code = a_pairing_code("ZZZZ9999", expires_in=timedelta(minutes=10))

    device.reissue_pairing_code(new_code)

    assert device.pairing_code == new_code
    assert device.status is DeviceStatus.PENDING


def test_reissue_on_a_paired_device_is_rejected():
    device = a_paired_device()

    with pytest.raises(DeviceAlreadyPaired):
        device.reissue_pairing_code(a_pairing_code("ZZZZ9999"))

    assert device.pairing_code is None


# --- rename(規格審查 #11) -----------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "stored"),
    [("客廳", "客廳"), ("  客廳  ", "客廳"), ("A", "A"), ("貓" * 30, "貓" * 30)],
)
def test_rename_trims_and_accepts_names_within_limit(typed, stored):
    device = a_paired_device()

    device.rename(typed, max_length=NAME_MAX)

    assert device.name == stored


@pytest.mark.parametrize("typed", ["", "   ", "貓" * 31])
def test_rename_rejects_empty_or_too_long_names(typed):
    device = a_paired_device(name="客廳")

    with pytest.raises(InvalidDeviceName):
        device.rename(typed, max_length=NAME_MAX)

    assert device.name == "客廳"


# --- record_heartbeat(03_spec 第 2.3 節、規格審查 #14) --------------------------


def test_heartbeat_updates_last_seen_at_on_a_paired_device():
    device = a_paired_device(last_seen_at=None)

    device.record_heartbeat(NOW)

    assert device.last_seen_at == NOW


def test_heartbeat_on_a_pending_device_is_rejected():
    device = a_pending_device()

    with pytest.raises(DeviceNotPaired):
        device.record_heartbeat(NOW)

    assert device.last_seen_at is None


# --- display_status(規格審查 #6:offline 是衍生狀態,不落盤) --------------------


@pytest.mark.parametrize(
    ("seconds_since_heartbeat", "expected"),
    [
        (0, DeviceStatus.PAIRED),
        (89, DeviceStatus.PAIRED),
        (90, DeviceStatus.PAIRED),  # 「超過 90 秒」才算離線,等於 90 秒仍在線
        (91, DeviceStatus.OFFLINE),
        (3600, DeviceStatus.OFFLINE),
    ],
)
def test_display_status_derives_offline_from_last_seen_at(seconds_since_heartbeat, expected):
    device = a_paired_device(last_seen_at=NOW)

    actual = device.display_status(
        NOW + timedelta(seconds=seconds_since_heartbeat), offline_after_seconds=OFFLINE_AFTER
    )

    assert actual is expected


def test_a_paired_device_that_never_reported_is_offline():
    device = a_paired_device(last_seen_at=None)

    assert (
        device.display_status(NOW, offline_after_seconds=OFFLINE_AFTER) is DeviceStatus.OFFLINE
    )


def test_a_pending_device_is_never_offline():
    """offline 的定義是「已配對裝置失聯」(01_資料模型 第 2.2 節),未配對的不適用。"""
    device = a_pending_device()

    assert (
        device.display_status(NOW, offline_after_seconds=OFFLINE_AFTER) is DeviceStatus.PENDING
    )


def test_stored_status_is_never_offline():
    """審查 #6:offline 只由 display_status 產生,不會寫進 status 欄位。"""
    device = a_paired_device(last_seen_at=None)

    device.display_status(NOW, offline_after_seconds=OFFLINE_AFTER)

    assert device.status is DeviceStatus.PAIRED


# --- unpair(04_spec 第 2.3 節、01_資料模型 第 6 節) ----------------------------


def test_unpair_resets_the_device_for_a_new_owner():
    device = a_paired_device(user_id=ALICE, last_seen_at=NOW, name="客廳")
    new_code = a_pairing_code("ZZZZ9999")

    device.unpair(new_code)

    assert device.status is DeviceStatus.PENDING
    assert device.user_id is None
    assert device.pairing_code == new_code
    assert device.last_seen_at is None


def test_unpair_keeps_the_hardware_identity():
    """同一台實體鏡頭重新配對後仍是同一列(審查 #3 的 hardware_id 冪等靠這個)。"""
    device = a_paired_device()

    device.unpair(a_pairing_code("ZZZZ9999"))

    assert device.id == DEVICE_ID
    assert device.hardware_id == HARDWARE_ID
    assert device.secret_hash == SECRET_HASH


# --- is_owned_by(規格審查 #1) -------------------------------------------------


def test_owner_checks():
    device = a_paired_device(user_id=ALICE)

    assert device.is_owned_by(ALICE)
    assert not device.is_owned_by(BOB)


def test_a_pending_device_is_owned_by_nobody():
    device = a_pending_device()

    assert not device.is_owned_by(ALICE)
