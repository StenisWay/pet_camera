"""DeviceRepository 的合約測試。

同一組測試跑在**每一個**實作上:fake 與 SQLAlchemy。內容逐條來自
app/domains/devices/domain/repositories.py 各方法 docstring 寫下的行為承諾。

為什麼重要:application 層的測試全部建立在 fake 上。若 fake 的行為與正式實作不同
(例如 get 回傳同一個物件、修改不用 save 就生效),application 測試會綠燈、
正式環境卻出錯。

開發迴圈用 `uv run pytest` 只跑 fake;CI 用 `uv run pytest -m integration` 兩個都跑。
"""

import uuid
from collections.abc import Callable
from datetime import timedelta

import pytest

from app.domains.devices.application.ports import DevicesUnitOfWork
from app.domains.devices.domain.entities import DeviceStatus
from tests.domains.devices.builders import (
    ALICE,
    BOB,
    NOW,
    VALID_CODE,
    a_paired_device,
    a_pairing_code,
    a_pending_device,
)
from tests.domains.devices.fakes import FakeDevicesUnitOfWork

UowFactory = Callable[[], DevicesUnitOfWork]


@pytest.fixture(params=["fake", pytest.param("sqlalchemy", marks=pytest.mark.integration)])
def uow_factory(request: pytest.FixtureRequest) -> UowFactory:
    if request.param == "fake":
        shared = FakeDevicesUnitOfWork()  # 同一個實例 = 同一個「資料庫」
        return lambda: shared
    session_factory = request.getfixturevalue("session_factory")
    from app.domains.devices.infrastructure.unit_of_work import SqlAlchemyDevicesUnitOfWork

    return lambda: SqlAlchemyDevicesUnitOfWork(session_factory)


async def test_get_returns_none_for_an_unknown_id(uow_factory: UowFactory):
    async with uow_factory() as uow:
        assert await uow.devices.get(uuid.uuid4()) is None


async def test_get_by_hardware_id_returns_none_when_never_registered(uow_factory: UowFactory):
    async with uow_factory() as uow:
        assert await uow.devices.get_by_hardware_id("never-seen") is None


async def test_get_by_pairing_code_returns_none_for_an_unknown_code(uow_factory: UowFactory):
    async with uow_factory() as uow:
        assert await uow.devices.get_by_pairing_code("ZZZZ9999") is None


async def test_saved_device_can_be_read_back_after_commit(uow_factory: UowFactory):
    device = a_pending_device()

    async with uow_factory() as uow:
        await uow.devices.save(device)
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.devices.get(device.id) == device


async def test_leaving_the_unit_of_work_without_commit_rolls_back(uow_factory: UowFactory):
    device = a_pending_device()

    async with uow_factory() as uow:
        await uow.devices.save(device)
        # 沒有 commit

    async with uow_factory() as uow:
        assert await uow.devices.get(device.id) is None


async def test_modifying_a_loaded_device_without_save_is_not_persisted(uow_factory: UowFactory):
    device = a_pending_device()
    async with uow_factory() as uow:
        await uow.devices.save(device)
        await uow.commit()

    async with uow_factory() as uow:
        loaded = await uow.devices.get(device.id)
        assert loaded is not None
        loaded.rename("改過但沒存", max_length=30)
        await uow.commit()  # 沒有 save

    async with uow_factory() as uow:
        reloaded = await uow.devices.get(device.id)
        assert reloaded is not None
        assert reloaded.name == device.name


async def test_saving_an_existing_device_updates_it(uow_factory: UowFactory):
    device = a_paired_device(name="客廳")
    async with uow_factory() as uow:
        await uow.devices.save(device)
        await uow.commit()

    async with uow_factory() as uow:
        loaded = await uow.devices.get(device.id)
        assert loaded is not None
        loaded.rename("臥室", max_length=30)
        await uow.devices.save(loaded)
        await uow.commit()

    async with uow_factory() as uow:
        reloaded = await uow.devices.get(device.id)
        assert reloaded is not None
        assert reloaded.name == "臥室"


async def test_get_by_pairing_code_normalizes_user_input(uow_factory: UowFactory):
    """審查 #4:實作必須先正規化再查,否則使用者打小寫或帶連字號就配對不上。"""
    device = a_pending_device(pairing_code=a_pairing_code(VALID_CODE))
    async with uow_factory() as uow:
        await uow.devices.save(device)
        await uow.commit()

    async with uow_factory() as uow:
        found = await uow.devices.get_by_pairing_code("abcd-1234")
        assert found is not None
        assert found.id == device.id


async def test_get_by_pairing_code_returns_none_once_the_device_is_paired(
    uow_factory: UowFactory,
):
    """審查 #5 的前提:配對成功後碼被清空,同一組碼再也查不到。"""
    device = a_pending_device()
    async with uow_factory() as uow:
        await uow.devices.save(device)
        await uow.commit()

    async with uow_factory() as uow:
        loaded = await uow.devices.get_by_pairing_code(VALID_CODE)
        assert loaded is not None
        loaded.pair(user_id=ALICE, typed_code=VALID_CODE, now=NOW)
        await uow.devices.save(loaded)
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.devices.get_by_pairing_code(VALID_CODE) is None


async def test_get_by_hardware_id_finds_the_device_across_reboots(uow_factory: UowFactory):
    """審查 #3:鏡頭重開機靠 hardware_id 找回自己那一列。"""
    device = a_pending_device(hardware_id="pi-abc")
    async with uow_factory() as uow:
        await uow.devices.save(device)
        await uow.commit()

    async with uow_factory() as uow:
        found = await uow.devices.get_by_hardware_id("pi-abc")
        assert found is not None
        assert found.id == device.id


async def test_list_by_user_returns_only_that_users_devices_oldest_first(
    uow_factory: UowFactory,
):
    alice_old = a_paired_device(id=uuid.uuid4(), hardware_id="a1", user_id=ALICE, created_at=NOW)
    alice_new = a_paired_device(
        id=uuid.uuid4(),
        hardware_id="a2",
        user_id=ALICE,
        created_at=NOW + timedelta(days=1),
    )
    bobs = a_paired_device(id=uuid.uuid4(), hardware_id="b1", user_id=BOB)
    unpaired = a_pending_device(id=uuid.uuid4(), hardware_id="p1")

    async with uow_factory() as uow:
        for device in (alice_new, alice_old, bobs, unpaired):
            await uow.devices.save(device)
        await uow.commit()

    async with uow_factory() as uow:
        listed = await uow.devices.list_by_user(ALICE)

    assert [d.id for d in listed] == [alice_old.id, alice_new.id]


async def test_count_by_user_counts_only_that_users_paired_devices(uow_factory: UowFactory):
    async with uow_factory() as uow:
        await uow.devices.save(a_paired_device(id=uuid.uuid4(), hardware_id="a1", user_id=ALICE))
        await uow.devices.save(a_paired_device(id=uuid.uuid4(), hardware_id="a2", user_id=ALICE))
        await uow.devices.save(a_paired_device(id=uuid.uuid4(), hardware_id="b1", user_id=BOB))
        await uow.devices.save(a_pending_device(id=uuid.uuid4(), hardware_id="p1"))
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.devices.count_by_user(ALICE) == 2


async def test_unpaired_device_round_trips_with_a_fresh_code(uow_factory: UowFactory):
    """移除裝置後的狀態要能完整存回(01_資料模型 第 6 節)。"""
    device = a_paired_device()
    async with uow_factory() as uow:
        await uow.devices.save(device)
        await uow.commit()

    async with uow_factory() as uow:
        loaded = await uow.devices.get(device.id)
        assert loaded is not None
        loaded.unpair(a_pairing_code("ZZZZ9999"))
        await uow.devices.save(loaded)
        await uow.commit()

    async with uow_factory() as uow:
        reloaded = await uow.devices.get(device.id)

    assert reloaded is not None
    assert reloaded.status is DeviceStatus.PENDING
    assert reloaded.user_id is None
    assert reloaded.last_seen_at is None
    assert reloaded.pairing_code is not None
    assert reloaded.pairing_code.code == "ZZZZ9999"
