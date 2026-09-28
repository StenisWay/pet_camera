"""use case 的編排行為:載入、權限、呼叫實體、外部 port、commit 與否。

業務規則本身已在 domain 層窮盡測試,這裡每種只驗證「規則有被接上」,
以及失敗路徑**一定沒有 commit**。
"""

import uuid
from datetime import timedelta

import pytest

from app.domains.devices.application.use_cases.get_device_summary import GetDeviceSummary
from app.domains.devices.application.use_cases.list_devices import ListDevices
from app.domains.devices.application.use_cases.pair_device import PairDevice
from app.domains.devices.application.use_cases.record_heartbeat import RecordHeartbeat
from app.domains.devices.application.use_cases.register_device import RegisterDevice
from app.domains.devices.application.use_cases.remove_device import RemoveDevice
from app.domains.devices.application.use_cases.remove_user_devices import RemoveUserDevices
from app.domains.devices.application.use_cases.rename_device import RenameDevice
from app.domains.devices.domain.entities import DeviceStatus
from app.domains.devices.domain.exceptions import (
    DeviceLimitReached,
    DeviceNotFound,
    EventCleanupFailed,
    InvalidDeviceName,
    PairingCodeExpired,
    PairingCodeInvalid,
)
from tests.domains.devices.builders import (
    ALICE,
    BOB,
    HARDWARE_ID,
    NOW,
    VALID_CODE,
    a_paired_device,
    a_pairing_code,
    a_pending_device,
)
from tests.domains.devices.fakes import (
    FakeDeviceSecrets,
    FakeDevicesUnitOfWork,
    FakeEventCleanup,
    FixedClock,
    SequentialIds,
    StubPairingCodeFactory,
)

OFFLINE_AFTER = 90
NAME_MAX = 30
DEVICE_LIMIT = 20


@pytest.fixture
def uow() -> FakeDevicesUnitOfWork:
    return FakeDevicesUnitOfWork()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def codes() -> StubPairingCodeFactory:
    return StubPairingCodeFactory()


@pytest.fixture
def secrets() -> FakeDeviceSecrets:
    return FakeDeviceSecrets()


@pytest.fixture
def events() -> FakeEventCleanup:
    return FakeEventCleanup()


# --- RegisterDevice(審查 #3:以 hardware_id 冪等) ------------------------------


@pytest.fixture
def register(uow, codes, secrets, clock) -> RegisterDevice:
    return RegisterDevice(
        uow,
        codes,
        secrets,
        clock,
        SequentialIds(),
        default_name="未命名鏡頭",
        max_code_attempts=3,
    )


async def test_register_creates_a_pending_device_and_returns_its_secret(register, uow, secrets):
    result = await register.execute(HARDWARE_ID)

    assert result.status is DeviceStatus.PENDING
    assert result.device_secret == secrets.secret
    assert result.pairing_code == "ABCD1234"
    assert result.pairing_code_expires_at == NOW + timedelta(minutes=10)
    assert uow.commit_count == 1

    stored = uow.devices.committed[result.device_id]
    assert stored.hardware_id == HARDWARE_ID
    assert stored.name == "未命名鏡頭"
    assert stored.secret_hash != secrets.secret  # 只存雜湊


async def test_registering_the_same_hardware_again_reuses_the_row_and_reissues_the_code(
    register, uow
):
    """審查 #3:鏡頭重開機不該在 devices 表裡多長出一列。"""
    first = await register.execute(HARDWARE_ID)

    second = await register.execute(HARDWARE_ID)

    assert second.device_id == first.device_id
    assert len(uow.devices.committed) == 1
    assert second.pairing_code == "ZZZZ9999"  # 換了一組新碼
    assert second.pairing_code != first.pairing_code


async def test_registering_an_already_paired_device_does_not_issue_a_pairing_code(
    register, uow, clock
):
    """審查 #3:已配對的鏡頭重開機只要知道自己是誰,不需要也不該再拿到配對碼。"""
    paired = a_paired_device(hardware_id=HARDWARE_ID)
    uow.given(paired)

    result = await register.execute(HARDWARE_ID)

    assert result.device_id == paired.id
    assert result.status is DeviceStatus.PAIRED
    assert result.pairing_code is None
    assert result.pairing_code_expires_at is None


async def test_register_retries_when_the_generated_code_collides(uow, secrets, clock):
    """部分唯一索引 (pairing_code) where not null 會擋下碰撞,所以要換一組再試。"""
    uow.given(
        a_pending_device(
            id=uuid.uuid4(), hardware_id="other", pairing_code=a_pairing_code("ABCD1234")
        )
    )
    codes = StubPairingCodeFactory(["ABCD1234", "ZZZZ9999"])
    use_case = RegisterDevice(
        uow, codes, secrets, clock, SequentialIds(), default_name="未命名鏡頭", max_code_attempts=3
    )

    result = await use_case.execute(HARDWARE_ID)

    assert result.pairing_code == "ZZZZ9999"


async def test_register_gives_up_after_too_many_collisions(uow, secrets, clock):
    uow.given(
        a_pending_device(
            id=uuid.uuid4(), hardware_id="other", pairing_code=a_pairing_code("ABCD1234")
        )
    )
    codes = StubPairingCodeFactory(["ABCD1234"])  # 永遠撞
    use_case = RegisterDevice(
        uow, codes, secrets, clock, SequentialIds(), default_name="未命名鏡頭", max_code_attempts=3
    )

    with pytest.raises(Exception) as exc_info:
        await use_case.execute(HARDWARE_ID)

    assert exc_info.value.code == "SRV_002"
    assert uow.commit_count == 0


# --- PairDevice(03_spec 第 2.2 節、審查 #13) -----------------------------------


@pytest.fixture
def pair(uow, clock) -> PairDevice:
    return PairDevice(
        uow, clock, offline_after_seconds=OFFLINE_AFTER, max_devices_per_user=DEVICE_LIMIT
    )


async def test_pair_binds_the_device_to_the_user(pair, uow):
    device = uow.given(a_pending_device())

    view = await pair.execute(user_id=ALICE, typed_code=VALID_CODE)

    assert view.id == device.id
    assert uow.commit_count == 1
    assert uow.devices.committed[device.id].user_id == ALICE


async def test_pair_with_an_unknown_code_raises_device_002_and_does_not_commit(pair, uow):
    uow.given(a_pending_device())

    with pytest.raises(PairingCodeInvalid):
        await pair.execute(user_id=ALICE, typed_code="ZZZZ9999")

    assert uow.commit_count == 0


async def test_pair_with_an_expired_code_raises_device_001_and_does_not_commit(pair, uow, clock):
    uow.given(a_pending_device())
    clock.set(NOW + timedelta(minutes=11))

    with pytest.raises(PairingCodeExpired):
        await pair.execute(user_id=ALICE, typed_code=VALID_CODE)

    assert uow.commit_count == 0


async def test_pair_is_rejected_once_the_user_hits_the_device_limit(uow, clock):
    """審查 #13:每帳號 20 台上限,配合審查 #2 避免匿名 register 被濫用放大。"""
    uow.given(a_pending_device())
    for n in range(DEVICE_LIMIT):
        uow.given(a_paired_device(id=uuid.uuid4(), hardware_id=f"hw-{n}", user_id=ALICE))
    use_case = PairDevice(
        uow, clock, offline_after_seconds=OFFLINE_AFTER, max_devices_per_user=DEVICE_LIMIT
    )

    with pytest.raises(DeviceLimitReached):
        await use_case.execute(user_id=ALICE, typed_code=VALID_CODE)

    assert uow.commit_count == 0


# --- RecordHeartbeat(審查 #2) --------------------------------------------------


@pytest.fixture
def heartbeat(uow, secrets, clock) -> RecordHeartbeat:
    return RecordHeartbeat(uow, secrets, clock)


async def test_heartbeat_updates_last_seen_at(heartbeat, uow, secrets, clock):
    device = uow.given(
        a_paired_device(last_seen_at=None)
    )
    device.secret_hash = secrets.issue()[1]
    uow.given(device)
    clock.set(NOW + timedelta(seconds=30))

    await heartbeat.execute(device_id=device.id, device_secret=secrets.secret)

    assert uow.devices.committed[device.id].last_seen_at == NOW + timedelta(seconds=30)
    assert uow.commit_count == 1


async def test_heartbeat_with_a_wrong_secret_looks_like_the_device_does_not_exist(
    heartbeat, uow, secrets
):
    """審查 #2:秘密不符不回 401/403,回 404——否則等於確認了這個 device_id 存在。"""
    device = a_paired_device()
    device.secret_hash = secrets.issue()[1]
    uow.given(device)

    with pytest.raises(DeviceNotFound):
        await heartbeat.execute(device_id=device.id, device_secret="wrong")

    assert uow.commit_count == 0


async def test_heartbeat_for_an_unknown_device_raises_not_found(heartbeat, uow, secrets):
    with pytest.raises(DeviceNotFound):
        await heartbeat.execute(device_id=uuid.uuid4(), device_secret=secrets.secret)


# --- ListDevices(04_spec 第 2.1 節、審查 #6、#13) -----------------------------


async def test_list_returns_only_the_requesters_devices_with_derived_status(uow, clock):
    fresh = uow.given(
        a_paired_device(id=uuid.uuid4(), hardware_id="hw-1", user_id=ALICE, last_seen_at=NOW)
    )
    stale = uow.given(
        a_paired_device(
            id=uuid.uuid4(),
            hardware_id="hw-2",
            user_id=ALICE,
            last_seen_at=NOW - timedelta(seconds=120),
            created_at=NOW + timedelta(seconds=1),
        )
    )
    uow.given(a_paired_device(id=uuid.uuid4(), hardware_id="hw-3", user_id=BOB))
    use_case = ListDevices(uow, clock, offline_after_seconds=OFFLINE_AFTER)

    views = await use_case.execute(ALICE)

    assert [v.id for v in views] == [fresh.id, stale.id]
    assert views[0].status is DeviceStatus.PAIRED
    assert views[1].status is DeviceStatus.OFFLINE


async def test_list_for_a_user_with_no_devices_is_empty(uow, clock):
    use_case = ListDevices(uow, clock, offline_after_seconds=OFFLINE_AFTER)

    assert await use_case.execute(ALICE) == []


# --- RenameDevice(04_spec 第 2.2 節、審查 #1、#11) -----------------------------


@pytest.fixture
def rename(uow, clock) -> RenameDevice:
    return RenameDevice(
        uow, clock, offline_after_seconds=OFFLINE_AFTER, name_max_length=NAME_MAX
    )


async def test_rename_updates_the_name(rename, uow):
    device = uow.given(a_paired_device(user_id=ALICE, name="客廳"))

    view = await rename.execute(device_id=device.id, requester_id=ALICE, name="  臥室  ")

    assert view.name == "臥室"
    assert uow.devices.committed[device.id].name == "臥室"
    assert uow.commit_count == 1


async def test_rename_someone_elses_device_looks_like_it_does_not_exist(rename, uow):
    """審查 #1:回 404 而不是 403,不洩漏這個 device_id 存在。"""
    device = uow.given(a_paired_device(user_id=BOB, name="客廳"))

    with pytest.raises(DeviceNotFound):
        await rename.execute(device_id=device.id, requester_id=ALICE, name="我的")

    assert uow.devices.committed[device.id].name == "客廳"
    assert uow.commit_count == 0


async def test_rename_an_unpaired_device_looks_like_it_does_not_exist(rename, uow):
    """04_spec 驗收第 4 條:另一分頁已移除的裝置,這一邊操作要回 DEVICE_005。"""
    device = uow.given(a_pending_device())

    with pytest.raises(DeviceNotFound):
        await rename.execute(device_id=device.id, requester_id=ALICE, name="我的")


async def test_rename_with_an_invalid_name_does_not_commit(rename, uow):
    device = uow.given(a_paired_device(user_id=ALICE, name="客廳"))

    with pytest.raises(InvalidDeviceName):
        await rename.execute(device_id=device.id, requester_id=ALICE, name="   ")

    assert uow.commit_count == 0


# --- RemoveDevice(04_spec 第 2.3 節、審查 #7、#9) ------------------------------


@pytest.fixture
def remove(uow, events, codes, clock) -> RemoveDevice:
    return RemoveDevice(uow, events, codes, clock)


async def test_remove_clears_events_before_unpairing(remove, uow, events):
    device = uow.given(a_paired_device(user_id=ALICE))

    await remove.execute(device_id=device.id, requester_id=ALICE)

    assert events.cleaned == [device.id]
    stored = uow.devices.committed[device.id]
    assert stored.status is DeviceStatus.PENDING
    assert stored.user_id is None
    assert stored.pairing_code is not None  # 重新產生,可供下一位使用者配對
    assert uow.commit_count == 1


async def test_remove_fails_closed_when_event_cleanup_fails(uow, codes, clock):
    """審查 #9:清不掉事件就整個失敗,絕不能留下「事件還在但裝置已解除配對」。"""
    device = uow.given(a_paired_device(user_id=ALICE))
    use_case = RemoveDevice(uow, FakeEventCleanup(fails=True), codes, clock)

    with pytest.raises(EventCleanupFailed):
        await use_case.execute(device_id=device.id, requester_id=ALICE)

    assert uow.commit_count == 0
    assert uow.devices.committed[device.id].status is DeviceStatus.PAIRED
    assert uow.devices.committed[device.id].user_id == ALICE


async def test_remove_is_abandoned_if_the_device_is_unpaired_while_events_are_cleared(
    uow, codes, clock
):
    """04_spec 驗收第 4 條:另一個分頁在這期間把裝置移除了。

    清事件與 unpair 之間沒有共同交易,所以 unpair 之前要重新確認擁有者,
    否則會把已經回到 pending、甚至已被別人配對的裝置再 unpair 一次。
    """
    device = uow.given(a_paired_device(user_id=ALICE))

    def another_tab_removes_it() -> None:
        stale = uow.devices.committed[device.id]
        stale.unpair(a_pairing_code("QQQQ7777"))

    use_case = RemoveDevice(
        uow, FakeEventCleanup(on_cleanup=another_tab_removes_it), codes, clock
    )

    with pytest.raises(DeviceNotFound):
        await use_case.execute(device_id=device.id, requester_id=ALICE)

    assert uow.commit_count == 0


async def test_remove_user_devices_skips_devices_removed_along_the_way(uow, codes, clock):
    """使用者在刪除帳號的同時自己移除了某台裝置,不該因此整個失敗。"""
    kept = uow.given(a_paired_device(id=uuid.uuid4(), hardware_id="hw-1", user_id=ALICE))
    racing = uow.given(a_paired_device(id=uuid.uuid4(), hardware_id="hw-2", user_id=ALICE))

    def another_tab_removes_one() -> None:
        uow.devices.committed[racing.id].unpair(a_pairing_code("QQQQ7777"))

    use_case = RemoveUserDevices(
        uow, FakeEventCleanup(on_cleanup=another_tab_removes_one), codes, clock
    )

    removed = await use_case.execute(ALICE)

    assert removed == 1
    assert uow.devices.committed[kept.id].user_id is None


async def test_remove_someone_elses_device_does_not_touch_their_events(remove, uow, events):
    device = uow.given(a_paired_device(user_id=BOB))

    with pytest.raises(DeviceNotFound):
        await remove.execute(device_id=device.id, requester_id=ALICE)

    assert events.cleaned == []
    assert uow.commit_count == 0


# --- RemoveUserDevices(審查 #8) ------------------------------------------------


async def test_remove_user_devices_unpairs_every_device_of_that_user(uow, events, codes, clock):
    first = uow.given(a_paired_device(id=uuid.uuid4(), hardware_id="hw-1", user_id=ALICE))
    second = uow.given(a_paired_device(id=uuid.uuid4(), hardware_id="hw-2", user_id=ALICE))
    untouched = uow.given(a_paired_device(id=uuid.uuid4(), hardware_id="hw-3", user_id=BOB))
    use_case = RemoveUserDevices(uow, events, codes, clock)

    removed = await use_case.execute(ALICE)

    assert removed == 2
    assert set(events.cleaned) == {first.id, second.id}
    assert uow.devices.committed[first.id].user_id is None
    assert uow.devices.committed[second.id].user_id is None
    assert uow.devices.committed[untouched.id].user_id == BOB


async def test_remove_user_devices_fails_closed_if_any_cleanup_fails(uow, codes, clock):
    device = uow.given(a_paired_device(user_id=ALICE))
    use_case = RemoveUserDevices(uow, FakeEventCleanup(fails=True), codes, clock)

    with pytest.raises(EventCleanupFailed):
        await use_case.execute(ALICE)

    assert uow.commit_count == 0
    assert uow.devices.committed[device.id].user_id == ALICE


async def test_remove_user_devices_is_a_no_op_for_a_user_with_no_devices(
    uow, events, codes, clock
):
    use_case = RemoveUserDevices(uow, events, codes, clock)

    assert await use_case.execute(ALICE) == 0
    assert events.cleaned == []


# --- GetDeviceSummary(服務對外契約的內部端點) ---------------------------------


async def test_summary_exposes_owner_and_derived_status(uow, clock):
    device = uow.given(
        a_paired_device(user_id=ALICE, name="客廳", last_seen_at=NOW - timedelta(seconds=120))
    )
    use_case = GetDeviceSummary(uow, clock, offline_after_seconds=OFFLINE_AFTER)

    summary = await use_case.execute(device.id)

    assert summary.id == device.id
    assert summary.name == "客廳"
    assert summary.user_id == ALICE
    assert summary.status is DeviceStatus.OFFLINE


async def test_summary_of_an_unpaired_device_has_no_owner(uow, clock):
    """契約註明:user_id 為 None 代表未配對或已解除,呼叫端(Push)據此捨棄通知。"""
    device = uow.given(a_pending_device())
    use_case = GetDeviceSummary(uow, clock, offline_after_seconds=OFFLINE_AFTER)

    summary = await use_case.execute(device.id)

    assert summary.user_id is None
    assert summary.status is DeviceStatus.PENDING


async def test_summary_of_an_unknown_device_raises_not_found(uow, clock):
    use_case = GetDeviceSummary(uow, clock, offline_after_seconds=OFFLINE_AFTER)

    with pytest.raises(DeviceNotFound):
        await use_case.execute(uuid.uuid4())
