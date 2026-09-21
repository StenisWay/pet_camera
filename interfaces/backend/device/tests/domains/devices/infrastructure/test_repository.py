"""資料存取層特有的正確性:mapping 精度、資料庫約束、併發。

全部標記 integration,需要真實 PostgreSQL(testcontainers 或 TEST_DATABASE_URL)。
**不用 SQLite 代替**:本服務靠的正是 SQLite 沒有或行為不同的東西——部分唯一索引、
CHECK 約束、timestamptz、SELECT ... FOR UPDATE。用 SQLite 測等於什麼都沒測到。

跑法:uv run pytest -m integration
"""

import asyncio
import uuid
from datetime import UTC, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.devices.domain.entities import DeviceStatus
from app.domains.devices.domain.exceptions import PairingCodeInvalid
from app.domains.devices.domain.pairing_code import PairingCode
from app.domains.devices.infrastructure.orm import DeviceRow
from app.domains.devices.infrastructure.unit_of_work import SqlAlchemyDevicesUnitOfWork
from tests.domains.devices.builders import (
    ALICE,
    BOB,
    NOW,
    VALID_CODE,
    a_paired_device,
    a_pairing_code,
    a_pending_device,
)

pytestmark = pytest.mark.integration


# --- mapping 往返 -------------------------------------------------------------


async def test_pending_device_round_trips_without_loss(session_factory):
    device = a_pending_device()

    async with SqlAlchemyDevicesUnitOfWork(session_factory) as uow:
        await uow.devices.save(device)
        await uow.commit()

    async with SqlAlchemyDevicesUnitOfWork(session_factory) as uow:
        loaded = await uow.devices.get(device.id)

    assert loaded == device


async def test_paired_device_round_trips_without_loss(session_factory):
    device = a_paired_device(last_seen_at=NOW)

    async with SqlAlchemyDevicesUnitOfWork(session_factory) as uow:
        await uow.devices.save(device)
        await uow.commit()

    async with SqlAlchemyDevicesUnitOfWork(session_factory) as uow:
        loaded = await uow.devices.get(device.id)

    assert loaded == device
    assert loaded.pairing_code is None
    assert loaded.user_id == ALICE


async def test_timestamps_come_back_timezone_aware(session_factory):
    """01_資料模型 第 2.0 節:時間一律 timestamptz,以 UTC 儲存。"""
    device = a_paired_device(last_seen_at=NOW)

    async with SqlAlchemyDevicesUnitOfWork(session_factory) as uow:
        await uow.devices.save(device)
        await uow.commit()

    async with SqlAlchemyDevicesUnitOfWork(session_factory) as uow:
        loaded = await uow.devices.get(device.id)

    assert loaded.created_at.tzinfo is not None
    assert loaded.last_seen_at.tzinfo is not None
    assert loaded.last_seen_at.astimezone(UTC) == NOW


async def test_pairing_code_and_expiry_round_trip_together(session_factory):
    code = PairingCode(code="QQQQ7777", expires_at=NOW + timedelta(minutes=10))
    device = a_pending_device(pairing_code=code)

    async with SqlAlchemyDevicesUnitOfWork(session_factory) as uow:
        await uow.devices.save(device)
        await uow.commit()

    async with SqlAlchemyDevicesUnitOfWork(session_factory) as uow:
        loaded = await uow.devices.get(device.id)

    assert loaded.pairing_code == code


# --- 資料庫約束:最後一道防線,繞過 domain 也擋得下來 --------------------------


async def test_database_rejects_an_unknown_status(session_factory):
    """審查 #6:status 值域已縮小為 pending / paired,offline 不落盤。"""
    async with session_factory() as session:
        session.add(
            DeviceRow(
                id=uuid.uuid4(),
                hardware_id="hw-bad-status",
                name="x",
                device_secret_hash="h",
                status="offline",
                user_id=ALICE,
                created_at=NOW,
            )
        )
        with pytest.raises(IntegrityError, match="ck_devices_status_valid"):
            await session.flush()


async def test_database_rejects_a_paired_device_without_an_owner(session_factory):
    """01_資料模型 第 2.2 節:status='pending' 與 user_id is null 必須同時成立。"""
    async with session_factory() as session:
        session.add(
            DeviceRow(
                id=uuid.uuid4(),
                hardware_id="hw-orphan",
                name="x",
                device_secret_hash="h",
                status="paired",
                user_id=None,
                created_at=NOW,
            )
        )
        with pytest.raises(IntegrityError, match="ck_devices_pending_iff_unowned"):
            await session.flush()


async def test_database_rejects_an_empty_name(session_factory):
    async with session_factory() as session:
        session.add(
            DeviceRow(
                id=uuid.uuid4(),
                hardware_id="hw-empty-name",
                name="",
                device_secret_hash="h",
                status="pending",
                user_id=None,
                created_at=NOW,
            )
        )
        with pytest.raises(IntegrityError, match="ck_devices_name_length"):
            await session.flush()


async def test_database_rejects_a_duplicate_hardware_id(session_factory):
    """審查 #3:hardware_id 是冪等鍵,重複等於同一台鏡頭長出兩列。"""
    async with SqlAlchemyDevicesUnitOfWork(session_factory) as uow:
        await uow.devices.save(a_pending_device(id=uuid.uuid4(), hardware_id="same-hw"))
        await uow.commit()

    with pytest.raises(IntegrityError, match="uq_devices_hardware_id"):
        async with SqlAlchemyDevicesUnitOfWork(session_factory) as uow:
            await uow.devices.save(
                a_pending_device(
                    id=uuid.uuid4(), hardware_id="same-hw", pairing_code=a_pairing_code("ZZZZ9999")
                )
            )
            await uow.commit()


async def test_database_rejects_two_devices_sharing_a_pairing_code(session_factory):
    """01_資料模型 第 2.2 節的部分唯一索引。這正是 issue_unique_code 要重試的原因。"""
    async with SqlAlchemyDevicesUnitOfWork(session_factory) as uow:
        await uow.devices.save(a_pending_device(id=uuid.uuid4(), hardware_id="hw-1"))
        await uow.commit()

    with pytest.raises(IntegrityError, match="uq_devices_pairing_code"):
        async with SqlAlchemyDevicesUnitOfWork(session_factory) as uow:
            await uow.devices.save(a_pending_device(id=uuid.uuid4(), hardware_id="hw-2"))
            await uow.commit()


async def test_many_paired_devices_can_coexist_with_null_pairing_codes(session_factory):
    """部分唯一索引只約束非 null 的值,否則第二台配對完成的裝置就存不進去。"""
    async with SqlAlchemyDevicesUnitOfWork(session_factory) as uow:
        await uow.devices.save(a_paired_device(id=uuid.uuid4(), hardware_id="hw-1"))
        await uow.devices.save(a_paired_device(id=uuid.uuid4(), hardware_id="hw-2"))
        await uow.commit()

    async with SqlAlchemyDevicesUnitOfWork(session_factory) as uow:
        assert await uow.devices.count_by_user(ALICE) == 2


# --- 併發(審查 #10) ---------------------------------------------------------


async def test_two_users_pairing_with_the_same_code_serialize(session_factory):
    """只有一個人能配對成功,另一個得到 DEVICE_002。

    這是 get_by_pairing_code 的 with_for_update() 在做的事:沒有它,兩個交易會
    雙雙讀到 pending 狀態,後寫入的那個靜悄悄覆蓋前一個的 user_id。
    """
    device = a_pending_device()
    async with SqlAlchemyDevicesUnitOfWork(session_factory) as uow:
        await uow.devices.save(device)
        await uow.commit()

    async def pair_as(user_id: uuid.UUID) -> bool:
        async with SqlAlchemyDevicesUnitOfWork(session_factory) as uow:
            found = await uow.devices.get_by_pairing_code(VALID_CODE)
            if found is None:
                return False
            try:
                found.pair(user_id=user_id, typed_code=VALID_CODE, now=NOW)
            except PairingCodeInvalid:
                return False
            await uow.devices.save(found)
            await uow.commit()
            return True

    results = await asyncio.gather(pair_as(ALICE), pair_as(BOB))

    assert sum(results) == 1

    async with SqlAlchemyDevicesUnitOfWork(session_factory) as uow:
        final = await uow.devices.get(device.id)

    assert final.status is DeviceStatus.PAIRED
    assert final.user_id in (ALICE, BOB)
    assert final.pairing_code is None
