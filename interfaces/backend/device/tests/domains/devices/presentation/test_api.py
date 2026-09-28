"""HTTP 契約:狀態碼、回應格式、輸入驗證、授權、例外轉換。

業務規則已在 domain 層窮盡,這裡每種只驗一個代表。用 dependency_overrides 換掉
每個 port,完全不碰資料庫。
"""

import uuid
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.domains.devices.domain.entities import DeviceStatus
from app.domains.devices.presentation.dependencies import (
    get_clock,
    get_current_user_id,
    get_device_secrets,
    get_devices_uow,
    get_event_cleanup,
    get_id_generator,
    get_pairing_codes,
)
from app.main import create_app
from tests.domains.devices.builders import (
    ALICE,
    BOB,
    NOW,
    VALID_CODE,
    a_paired_device,
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

INTERNAL_KEY = get_settings().internal_api_key
INTERNAL_HEADERS = {"X-Internal-Api-Key": INTERNAL_KEY}


@pytest.fixture
def uow() -> FakeDevicesUnitOfWork:
    return FakeDevicesUnitOfWork()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def events() -> FakeEventCleanup:
    return FakeEventCleanup()


@pytest.fixture
def secrets() -> FakeDeviceSecrets:
    return FakeDeviceSecrets()


@pytest.fixture
def app(uow, clock, events, secrets):
    app = create_app()
    app.dependency_overrides.update(
        {
            get_devices_uow: lambda: uow,
            get_clock: lambda: clock,
            get_event_cleanup: lambda: events,
            get_device_secrets: lambda: secrets,
            get_pairing_codes: lambda: StubPairingCodeFactory(),
            get_id_generator: SequentialIds,
            get_current_user_id: lambda: ALICE,
        }
    )
    return app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def owned_device(uow, secrets, **kwargs):
    device = a_paired_device(user_id=ALICE, **kwargs)
    device.secret_hash = secrets.issue()[1]
    return uow.given(device)


# --- POST /devices/register ---------------------------------------------------


async def test_register_returns_201_with_the_secret_and_code(client):
    resp = await client.post("/devices/register", json={"hardware_id": "pi-001"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["device_secret"]
    assert body["pairing_code"] == "ABCD1234"
    assert body["pairing_code_expires_at"]  # 審查 #15


async def test_register_requires_a_hardware_id(client):
    resp = await client.post("/devices/register", json={})

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VAL_001"


async def test_register_rejects_unexpected_fields(client):
    resp = await client.post(
        "/devices/register", json={"hardware_id": "pi-001", "status": "paired"}
    )

    assert resp.status_code == 400


# --- POST /devices/pair -------------------------------------------------------


async def test_pair_returns_the_device(client, uow):
    device = uow.given(a_pending_device())

    resp = await client.post("/devices/pair", json={"pairing_code": VALID_CODE})

    assert resp.status_code == 200
    assert resp.json()["id"] == str(device.id)


async def test_pair_with_an_expired_code_returns_410_device_001(client, uow, clock):
    uow.given(a_pending_device())
    clock.set(NOW + timedelta(minutes=11))

    resp = await client.post("/devices/pair", json={"pairing_code": VALID_CODE})

    assert resp.status_code == 410
    assert resp.json()["error"]["code"] == "DEVICE_001"


async def test_pair_with_a_wrong_code_returns_400_device_002(client, uow):
    uow.given(a_pending_device())

    resp = await client.post("/devices/pair", json={"pairing_code": "ZZZZ9999"})

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DEVICE_002"


async def test_pairing_an_already_paired_device_returns_device_002_not_device_003(client, uow):
    """審查 #5:DEVICE_003 已從規格移除。"""
    uow.given(a_paired_device(user_id=BOB))

    resp = await client.post("/devices/pair", json={"pairing_code": VALID_CODE})

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DEVICE_002"


async def test_pair_requires_authentication(app, uow):
    uow.given(a_pending_device())
    del app.dependency_overrides[get_current_user_id]
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/devices/pair", json={"pairing_code": VALID_CODE})

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_001"


# --- POST /devices/{id}/heartbeat(審查 #2) -----------------------------------


async def test_heartbeat_returns_204(client, uow, secrets):
    device = owned_device(uow, secrets, last_seen_at=None)

    resp = await client.post(
        f"/devices/{device.id}/heartbeat", headers={"X-Device-Secret": secrets.secret}
    )

    assert resp.status_code == 204
    assert uow.devices.committed[device.id].last_seen_at == NOW


async def test_heartbeat_without_a_secret_returns_401(client, uow, secrets):
    device = owned_device(uow, secrets)

    resp = await client.post(f"/devices/{device.id}/heartbeat")

    assert resp.status_code == 401


async def test_heartbeat_with_a_wrong_secret_returns_404_not_403(client, uow, secrets):
    """審查 #2:回 403 等於確認這個 device_id 存在。"""
    device = owned_device(uow, secrets)

    resp = await client.post(
        f"/devices/{device.id}/heartbeat", headers={"X-Device-Secret": "wrong"}
    )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DEVICE_005"


# --- GET /devices -------------------------------------------------------------


async def test_list_returns_only_public_fields(client, uow, secrets):
    owned_device(uow, secrets, name="客廳")

    resp = await client.get("/devices")

    assert resp.status_code == 200
    [item] = resp.json()
    assert item["name"] == "客廳"
    assert set(item) == {"id", "name", "status", "last_seen_at", "created_at"}


async def test_list_shows_offline_for_a_stale_device(client, uow, clock):
    uow.given(a_paired_device(user_id=ALICE, last_seen_at=NOW))
    clock.set(NOW + timedelta(seconds=120))

    resp = await client.get("/devices")

    assert resp.json()[0]["status"] == DeviceStatus.OFFLINE.value


async def test_list_does_not_leak_other_users_devices(client, uow):
    uow.given(a_paired_device(user_id=BOB))

    resp = await client.get("/devices")

    assert resp.json() == []


async def test_list_requires_authentication(app):
    del app.dependency_overrides[get_current_user_id]
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/devices")

    assert resp.status_code == 401


# --- PATCH /devices/{id}(審查 #1、#11、#12) ----------------------------------


async def test_rename_returns_the_updated_device(client, uow, secrets):
    device = owned_device(uow, secrets, name="客廳")

    resp = await client.patch(f"/devices/{device.id}", json={"name": "臥室"})

    assert resp.status_code == 200
    assert resp.json()["name"] == "臥室"


async def test_rename_someone_elses_device_returns_404_device_005(client, uow):
    device = uow.given(a_paired_device(user_id=BOB))

    resp = await client.patch(f"/devices/{device.id}", json={"name": "我的"})

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DEVICE_005"


@pytest.mark.parametrize(
    "payload",
    [
        {"name": ""},
        {"name": "貓" * 31},
        {},
        {"name": "客廳", "status": "paired"},  # mass assignment(審查 #12)
        {"name": "客廳", "user_id": str(BOB)},
    ],
)
async def test_rename_rejects_invalid_payloads(client, uow, secrets, payload):
    device = owned_device(uow, secrets, name="客廳")

    resp = await client.patch(f"/devices/{device.id}", json=payload)

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VAL_001"
    assert uow.devices.committed[device.id].name == "客廳"


# --- DELETE /devices/{id}(審查 #1、#9) ---------------------------------------


async def test_remove_returns_204_and_clears_events(client, uow, secrets, events):
    device = owned_device(uow, secrets)

    resp = await client.delete(f"/devices/{device.id}")

    assert resp.status_code == 204
    assert events.cleaned == [device.id]
    assert uow.devices.committed[device.id].status is DeviceStatus.PENDING


async def test_remove_someone_elses_device_returns_404(client, uow, events):
    device = uow.given(a_paired_device(user_id=BOB))

    resp = await client.delete(f"/devices/{device.id}")

    assert resp.status_code == 404
    assert events.cleaned == []


async def test_remove_returns_503_when_event_cleanup_fails(app, uow, secrets):
    """審查 #9:fail-closed,裝置維持原狀。"""
    device = owned_device(uow, secrets)
    app.dependency_overrides[get_event_cleanup] = lambda: FakeEventCleanup(fails=True)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.delete(f"/devices/{device.id}")

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "SRV_002"
    assert uow.devices.committed[device.id].status is DeviceStatus.PAIRED


# --- 內部端點(審查 #7、#8) ---------------------------------------------------


async def test_summary_returns_owner_and_name(client, uow):
    device = uow.given(a_paired_device(user_id=ALICE, name="客廳"))

    resp = await client.get(f"/internal/devices/{device.id}", headers=INTERNAL_HEADERS)

    assert resp.status_code == 200
    assert resp.json() == {
        "id": str(device.id),
        "name": "客廳",
        "user_id": str(ALICE),
        "status": "paired",
    }


async def test_summary_of_an_unknown_device_returns_404(client):
    resp = await client.get(f"/internal/devices/{uuid.uuid4()}", headers=INTERNAL_HEADERS)

    assert resp.status_code == 404


async def test_internal_endpoints_reject_a_missing_api_key(client, uow):
    device = uow.given(a_paired_device(user_id=ALICE))

    resp = await client.get(f"/internal/devices/{device.id}")

    assert resp.status_code == 401


async def test_internal_endpoints_reject_a_wrong_api_key(client, uow):
    device = uow.given(a_paired_device(user_id=ALICE))

    resp = await client.get(
        f"/internal/devices/{device.id}", headers={"X-Internal-Api-Key": "nope"}
    )

    assert resp.status_code == 401


async def test_remove_user_devices_unpairs_all_of_them(client, uow, events):
    first = uow.given(a_paired_device(id=uuid.uuid4(), hardware_id="hw-1", user_id=ALICE))
    uow.given(a_paired_device(id=uuid.uuid4(), hardware_id="hw-2", user_id=ALICE))

    resp = await client.delete(f"/internal/users/{ALICE}/devices", headers=INTERNAL_HEADERS)

    assert resp.status_code == 200
    assert resp.json() == {"removed": 2}
    assert uow.devices.committed[first.id].user_id is None
    assert len(events.cleaned) == 2


# --- 系統 ---------------------------------------------------------------------


async def test_health_does_not_touch_the_database(client):
    resp = await client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
