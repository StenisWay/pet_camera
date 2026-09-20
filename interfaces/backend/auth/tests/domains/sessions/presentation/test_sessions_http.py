"""sessions 的 HTTP 契約(02_spec 第 3 節)。"""

from datetime import timedelta

from httpx import AsyncClient

from tests.app_factory import Doubles
from tests.domains.sessions.presentation.conftest import NOW

EMAIL = "owner@example.com"
PASSWORD = "abcd1234"


async def login(client: AsyncClient, *, platform: str = "web") -> dict[str, str]:
    await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    response = await client.post(
        "/auth/login", json={"email": EMAIL, "password": PASSWORD, "platform": platform}
    )
    assert response.status_code == 200
    return response.json()


# --------------------------- token/refresh ---------------------------


async def test_refresh_rotates_both_tokens(client: AsyncClient) -> None:
    tokens = await login(client)

    response = await client.post(
        "/auth/token/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["refresh_token"] != tokens["refresh_token"]
    assert body["access_token"]


async def test_refresh_with_an_unknown_token_is_401_auth_010(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/token/refresh", json={"refresh_token": "never-issued"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_010"


async def test_replaying_a_rotated_token_is_401_auth_010(client: AsyncClient) -> None:
    """§2.3.1:已換發過的 token 再出現就是外洩徵兆。"""
    tokens = await login(client)
    await client.post(
        "/auth/token/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    response = await client.post(
        "/auth/token/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_010"


async def test_refresh_after_logout_is_401_auth_010(client: AsyncClient) -> None:
    """§2.5:撤銷後即使 access token 尚未到期,也換不到新的。"""
    tokens = await login(client)
    await client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})

    response = await client.post(
        "/auth/token/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_010"


# ------------------------------ logout ------------------------------


async def test_logout_is_204(client: AsyncClient) -> None:
    tokens = await login(client)

    response = await client.post(
        "/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 204


async def test_logout_is_idempotent(client: AsyncClient) -> None:
    """§2.5:查無、已撤銷、已過期都回 204;回錯誤會洩漏 token 存不存在。"""
    tokens = await login(client)
    await client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})

    again = await client.post(
        "/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    unknown = await client.post("/auth/logout", json={"refresh_token": "never-issued"})

    assert again.status_code == 204
    assert unknown.status_code == 204


# --------------------------- token/extend ---------------------------


async def test_extend_before_7_days_is_204(client: AsyncClient, doubles: Doubles) -> None:
    tokens = await login(client, platform="app")
    assert doubles.clock is not None
    doubles.clock.advance_to(NOW + timedelta(days=7) - timedelta(seconds=1))

    response = await client.post(
        "/auth/token/extend",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 204


async def test_extend_after_7_days_returns_a_new_token(
    client: AsyncClient, doubles: Doubles
) -> None:
    tokens = await login(client, platform="app")
    assert doubles.clock is not None
    doubles.clock.advance_to(NOW + timedelta(days=7))

    response = await client.post(
        "/auth/token/extend",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] != tokens["access_token"]
    assert body["refresh_token"] is None


async def test_extending_a_web_token_is_401_auth_001(
    client: AsyncClient, doubles: Doubles
) -> None:
    """展延是 App 專用;Web 走 rotation(§2.6)。"""
    tokens = await login(client, platform="web")
    assert doubles.clock is not None
    doubles.clock.advance_to(NOW + timedelta(days=7))

    response = await client.post(
        "/auth/token/extend",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_001"


async def test_extend_without_a_token_is_401_auth_001(client: AsyncClient) -> None:
    response = await client.post("/auth/token/extend")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_001"


async def test_extend_with_a_garbage_token_is_401_auth_001(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/token/extend", headers={"Authorization": "Bearer not-a-jwt"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_001"
