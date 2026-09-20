"""accounts 的 HTTP 契約。

只測「這個請求會得到什麼狀態碼與什麼 error.code」——業務規則本身在 domain 與
application 已經測完了,這裡不重複。對照 02_spec 第 5 節與 05_spec 第 5 節的錯誤碼表。
"""

from datetime import timedelta

import pytest
from httpx import AsyncClient

from tests.app_factory import Doubles
from tests.domains.accounts.presentation.conftest import NOW

EMAIL = "owner@example.com"
PASSWORD = "abcd1234"


async def register(client: AsyncClient, *, email: str = EMAIL, password: str = PASSWORD):
    return await client.post("/auth/register", json={"email": email, "password": password})


async def login(
    client: AsyncClient,
    *,
    email: str = EMAIL,
    password: str = PASSWORD,
    platform: str = "web",
):
    return await client.post(
        "/auth/login", json={"email": email, "password": password, "platform": platform}
    )


# ------------------------------ 註冊 ------------------------------


async def test_register_returns_201_with_the_normalized_email(client: AsyncClient) -> None:
    response = await register(client, email="  Owner@Example.COM ")

    assert response.status_code == 201
    assert response.json()["email"] == EMAIL


async def test_register_never_echoes_anything_password_shaped(client: AsyncClient) -> None:
    response = await register(client)

    body = response.text
    assert PASSWORD not in body
    assert "password" not in response.json()


async def test_register_with_a_malformed_email_is_400_val_001(client: AsyncClient) -> None:
    response = await register(client, email="not-an-email")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VAL_001"


async def test_register_with_a_weak_password_is_400_auth_006(client: AsyncClient) -> None:
    response = await register(client, password="short")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "AUTH_006"


async def test_register_with_a_duplicate_email_is_409_auth_004(client: AsyncClient) -> None:
    await register(client)
    response = await register(client)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "AUTH_004"


async def test_register_with_a_missing_field_is_400_val_001(client: AsyncClient) -> None:
    """10_錯誤處理與狀態規範.md 第 3 節:輸入格式錯誤是 400 + VAL_001,不是 422。"""
    response = await client.post("/auth/register", json={"email": EMAIL})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VAL_001"


# ------------------------------ 登入 ------------------------------


async def test_web_login_returns_both_tokens(client: AsyncClient) -> None:
    await register(client)
    response = await login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "Bearer"


async def test_app_login_omits_the_refresh_token(client: AsyncClient) -> None:
    await register(client)
    response = await login(client, platform="app")

    assert response.status_code == 200
    assert response.json()["refresh_token"] is None


async def test_login_with_a_wrong_password_is_401_auth_003(client: AsyncClient) -> None:
    await register(client)
    response = await login(client, password="wrong123")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_003"


async def test_login_for_an_unknown_account_is_also_401_auth_003(
    client: AsyncClient,
) -> None:
    """§2.4 的反列舉設計要一路貫徹到 HTTP 層。"""
    response = await login(client, email="nobody@example.com")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_003"


async def test_lockout_is_423_with_a_countdown(client: AsyncClient) -> None:
    """§5:AUTH_005 的呈現方式是阻斷式對話框 + 倒數時間。"""
    await register(client)
    for _ in range(4):
        await login(client, password="wrong123")

    response = await login(client, password="wrong123")

    assert response.status_code == 423
    body = response.json()
    assert body["error"]["code"] == "AUTH_005"
    assert body["retry_after_seconds"] == 15 * 60
    assert response.headers["Retry-After"] == str(15 * 60)


async def test_unknown_account_lockout_is_indistinguishable(client: AsyncClient) -> None:
    """規格審查 #7:存在與不存在的帳號,鎖定後的回應必須完全一樣。"""
    for _ in range(4):
        await login(client, email="nobody@example.com")

    response = await login(client, email="nobody@example.com")

    assert response.status_code == 423
    assert response.json()["error"]["code"] == "AUTH_005"


async def test_login_with_an_unknown_platform_is_400_val_001(client: AsyncClient) -> None:
    response = await login(client, platform="desktop")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VAL_001"


# ---------------------------- 忘記密碼 ----------------------------


async def test_forgot_password_is_200_for_a_known_address(
    client: AsyncClient, doubles: Doubles
) -> None:
    await register(client)
    response = await client.post("/auth/password/forgot", json={"email": EMAIL})

    assert response.status_code == 200
    assert len(doubles.mailer.sent) == 1


async def test_forgot_password_looks_identical_for_an_unknown_address(
    client: AsyncClient, doubles: Doubles
) -> None:
    known = await client.post("/auth/password/forgot", json={"email": EMAIL})
    await register(client)
    unknown = await client.post(
        "/auth/password/forgot", json={"email": "nobody@example.com"}
    )

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert doubles.mailer.sent == []


async def test_forgot_password_over_the_limit_is_429_rate_001(
    client: AsyncClient, doubles: Doubles
) -> None:
    doubles.throttle.allow = False
    response = await client.post("/auth/password/forgot", json={"email": EMAIL})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_001"


# ---------------------------- 重設密碼 ----------------------------


async def test_reset_password_succeeds_and_the_new_password_works(
    client: AsyncClient, doubles: Doubles
) -> None:
    await register(client)
    await client.post("/auth/password/forgot", json={"email": EMAIL})
    secret = doubles.tokens.generated[-1]

    response = await client.post(
        "/auth/password/reset", json={"token": secret, "new_password": "brandnew2"}
    )

    assert response.status_code == 204
    assert (await login(client, password="brandnew2")).status_code == 200
    assert (await login(client, password=PASSWORD)).status_code == 401


async def test_reset_password_with_an_expired_token_is_410_auth_007(
    client: AsyncClient, doubles: Doubles
) -> None:
    await register(client)
    await client.post("/auth/password/forgot", json={"email": EMAIL})
    secret = doubles.tokens.generated[-1]
    assert doubles.clock is not None
    doubles.clock.advance_to(NOW + timedelta(minutes=31))

    response = await client.post(
        "/auth/password/reset", json={"token": secret, "new_password": "brandnew2"}
    )

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "AUTH_007"


async def test_reusing_a_reset_link_is_410_auth_007(
    client: AsyncClient, doubles: Doubles
) -> None:
    await register(client)
    await client.post("/auth/password/forgot", json={"email": EMAIL})
    secret = doubles.tokens.generated[-1]
    await client.post(
        "/auth/password/reset", json={"token": secret, "new_password": "brandnew2"}
    )

    response = await client.post(
        "/auth/password/reset", json={"token": secret, "new_password": "another34"}
    )

    assert response.status_code == 410


# ---------------------------- 修改密碼 ----------------------------


async def authenticated(client: AsyncClient) -> dict[str, str]:
    await register(client)
    tokens = (await login(client)).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_change_password_without_a_token_is_401_auth_001(
    client: AsyncClient,
) -> None:
    response = await client.patch(
        "/auth/password", json={"current_password": PASSWORD, "new_password": "brandnew2"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_001"


async def test_change_password_with_a_wrong_current_one_is_401_auth_008(
    client: AsyncClient,
) -> None:
    headers = await authenticated(client)

    response = await client.patch(
        "/auth/password",
        json={"current_password": "wrong123", "new_password": "brandnew2"},
        headers=headers,
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_008"


async def test_change_password_succeeds(client: AsyncClient) -> None:
    headers = await authenticated(client)

    response = await client.patch(
        "/auth/password",
        json={"current_password": PASSWORD, "new_password": "brandnew2"},
        headers=headers,
    )

    assert response.status_code == 204
    assert (await login(client, password="brandnew2")).status_code == 200


# ---------------------------- 刪除帳號 ----------------------------


async def test_delete_account_removes_it_and_purges_other_services(
    client: AsyncClient, doubles: Doubles
) -> None:
    headers = await authenticated(client)

    response = await client.request(
        "DELETE", "/auth/account", json={"confirmation": PASSWORD}, headers=headers
    )

    assert response.status_code == 204
    assert len(doubles.device_purger.purged) == 1
    assert len(doubles.album_purger.purged) == 1
    assert (await login(client)).status_code == 401


async def test_delete_account_with_a_wrong_password_is_401_auth_009(
    client: AsyncClient,
) -> None:
    headers = await authenticated(client)

    response = await client.request(
        "DELETE", "/auth/account", json={"confirmation": "wrong123"}, headers=headers
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_009"


async def test_delete_account_is_503_srv_002_when_a_purge_fails(
    client: AsyncClient, doubles: Doubles
) -> None:
    """13_ADR 第 4 節:寧可刪不掉,也不要留下一個登不進去卻還有資料殘留的帳號。"""
    headers = await authenticated(client)
    doubles.album_purger.fails = True

    response = await client.request(
        "DELETE", "/auth/account", json={"confirmation": PASSWORD}, headers=headers
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SRV_002"
    assert (await login(client)).status_code == 200  # 帳號還在


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", "/auth/register"), ("post", "/auth/login")],
)
async def test_no_endpoint_ever_returns_a_password_hash(
    client: AsyncClient, method: str, path: str
) -> None:
    response = await getattr(client, method)(
        path, json={"email": EMAIL, "password": PASSWORD, "platform": "web"}
    )

    assert "password_hash" not in response.text
    assert "hashed:" not in response.text
