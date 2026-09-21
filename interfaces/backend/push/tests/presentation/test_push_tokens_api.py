"""只驗證「規則有沒有正確接上 HTTP」:狀態碼、錯誤碼、回應欄位、權限。
業務規則本身在 domain / application 測試中窮盡,這裡不重複。"""

import uuid

import pytest

from app.core.security import get_current_user_id
from tests.domains.push_tokens.builders import BOB, FCM_TOKEN, a_push_token


async def _register(client, token=FCM_TOKEN, platform="app"):
    return await client.put("/push-tokens", json={"platform": platform, "token": token})


async def test_register_returns_id_platform_created_at_and_never_the_token(client):
    """審查 #10:回 200 {id, platform, created_at},不含 token。"""
    response = await _register(client)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "platform", "created_at"}
    assert body["platform"] == "app"


@pytest.mark.parametrize(
    "payload",
    [
        {"platform": "ios", "token": FCM_TOKEN},  # 值域只有 app / web
        {"platform": "app", "token": "   "},
        {"platform": "app"},
    ],
)
async def test_invalid_registration_returns_val_001(client, payload):
    response = await client.put("/push-tokens", json=payload)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VAL_001"


async def test_eleventh_registration_in_a_minute_is_rate_limited(client):
    """審查 #16:每使用者每分鐘 10 次。"""
    for _ in range(10):
        assert (await _register(client)).status_code == 200

    response = await _register(client)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_001"


async def test_registration_when_database_is_unreachable_returns_srv_002(client, uow):
    """審查 #12:註冊路徑寫入 Postgres,依 13_ADR 第 4 節選 C,拒絕並回 SRV_002。"""
    uow.unavailable = ConnectionRefusedError("VM-3 unreachable")

    response = await _register(client)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SRV_002"


async def test_list_returns_own_registrations_without_tokens(client, uow):
    mine = uow.given(a_push_token(id=uuid.uuid4(), token="a"))
    uow.given(a_push_token(id=uuid.uuid4(), token="b", user_id=BOB))

    response = await client.get("/push-tokens")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": str(mine.id),
                "platform": "app",
                "created_at": mine.created_at.isoformat().replace("+00:00", "Z"),
            }
        ]
    }


async def test_unregister_own_registration_returns_204(client, uow):
    registration = uow.given(a_push_token())

    response = await client.delete(f"/push-tokens/{registration.id}")

    assert response.status_code == 204
    assert await uow.tokens.get(registration.id) is None


async def test_unregister_someone_elses_registration_returns_404(client, uow):
    """審查 #5:非本人與不存在一律 404,不回 403。"""
    registration = uow.given(a_push_token(user_id=BOB))

    response = await client.delete(f"/push-tokens/{registration.id}")

    assert response.status_code == 404
    assert await uow.tokens.get(registration.id) is not None


async def test_missing_token_returns_auth_001(app, client):
    app.dependency_overrides.pop(get_current_user_id)

    for response in (
        await client.get("/push-tokens"),
        await _register(client),
        await client.delete(f"/push-tokens/{uuid.uuid4()}"),
    ):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_001"
