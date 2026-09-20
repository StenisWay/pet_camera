"""端到端流程:整條路徑一次走完,跨 accounts 與 sessions 兩個領域。

單元測試各自證明了一塊,但「改完密碼之後,原本那個分頁還能不能繼續用」這種問題
只有把整串接起來才答得出來。資料層用 fake——真實 PostgreSQL 的行為由
tests/domains/*/contracts 與 infrastructure 那組測試負責。
"""

from httpx import AsyncClient

from tests.app_factory import Doubles

EMAIL = "owner@example.com"
PASSWORD = "abcd1234"
NEW_PASSWORD = "brandnew2"


async def register_and_login(client: AsyncClient) -> dict[str, str]:
    registered = await client.post(
        "/auth/register", json={"email": EMAIL, "password": PASSWORD}
    )
    assert registered.status_code == 201

    logged_in = await client.post(
        "/auth/login", json={"email": EMAIL, "password": PASSWORD, "platform": "web"}
    )
    assert logged_in.status_code == 200
    return logged_in.json()


async def test_changing_the_password_keeps_this_session_and_kills_the_others(
    client: AsyncClient,
) -> None:
    """05_spec 第 2.1 節:撤銷其他 session,但不強制登出當前這一個。

    改密碼的動機常常是「我懷疑帳號被盜」;不撤銷其他 session 等於改了也沒用。
    但把使用者自己也踢掉,只會讓人以為操作失敗了。
    """
    this_tab = await register_and_login(client)
    other_tab = await client.post(
        "/auth/login", json={"email": EMAIL, "password": PASSWORD, "platform": "web"}
    )
    other_refresh = other_tab.json()["refresh_token"]

    changed = await client.patch(
        "/auth/password",
        json={
            "current_password": PASSWORD,
            "new_password": NEW_PASSWORD,
            "current_refresh_token": this_tab["refresh_token"],
        },
        headers={"Authorization": f"Bearer {this_tab['access_token']}"},
    )
    assert changed.status_code == 204

    # 另一個分頁被踢掉
    assert (
        await client.post("/auth/token/refresh", json={"refresh_token": other_refresh})
    ).status_code == 401

    # 自己這個分頁還能繼續換發
    assert (
        await client.post(
            "/auth/token/refresh", json={"refresh_token": this_tab["refresh_token"]}
        )
    ).status_code == 200

    # 舊密碼作廢、新密碼可用
    assert (
        await client.post(
            "/auth/login",
            json={"email": EMAIL, "password": PASSWORD, "platform": "web"},
        )
    ).status_code == 401
    assert (
        await client.post(
            "/auth/login",
            json={"email": EMAIL, "password": NEW_PASSWORD, "platform": "web"},
        )
    ).status_code == 200


async def test_forgot_password_flow_end_to_end(
    client: AsyncClient, doubles: Doubles
) -> None:
    """02_spec 第 2.4 節:申請 → 收信 → 重設 → 舊密碼作廢、所有 session 失效。"""
    tokens = await register_and_login(client)

    requested = await client.post("/auth/password/forgot", json={"email": EMAIL})
    assert requested.status_code == 200

    # 從「信」裡把連結挖出來,跟真正的使用者拿到的是同一個東西
    _, reset_url = doubles.mailer.sent[-1]
    reset_token = reset_url.rsplit("token=", 1)[1]

    reset = await client.post(
        "/auth/password/reset",
        json={"token": reset_token, "new_password": NEW_PASSWORD},
    )
    assert reset.status_code == 204

    # 重設不保留任何 session(§2.4):能重設的人未必是原本持有 session 的人
    assert (
        await client.post(
            "/auth/token/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
    ).status_code == 401

    assert (
        await client.post(
            "/auth/login",
            json={"email": EMAIL, "password": PASSWORD, "platform": "web"},
        )
    ).status_code == 401
    assert (
        await client.post(
            "/auth/login",
            json={"email": EMAIL, "password": NEW_PASSWORD, "platform": "web"},
        )
    ).status_code == 200

    # 同一個連結不能再用一次
    assert (
        await client.post(
            "/auth/password/reset",
            json={"token": reset_token, "new_password": "another34"},
        )
    ).status_code == 410


async def test_deleting_the_account_ends_everything(
    client: AsyncClient, doubles: Doubles
) -> None:
    """05_spec 第 2.2 節:串聯清除後帳號消失,原本的 token 也換不到東西。"""
    tokens = await register_and_login(client)

    deleted = await client.request(
        "DELETE",
        "/auth/account",
        json={"confirmation": PASSWORD},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert deleted.status_code == 204
    assert [p.name for p in (doubles.device_purger, doubles.album_purger)] == [
        "device",
        "album",
    ]
    assert doubles.device_purger.purged and doubles.album_purger.purged

    assert (
        await client.post(
            "/auth/login",
            json={"email": EMAIL, "password": PASSWORD, "platform": "web"},
        )
    ).status_code == 401

    # 同一個 email 可以重新註冊——刪除是硬刪除,不留殘影
    assert (
        await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    ).status_code == 201


async def test_app_client_keeps_itself_logged_in_by_extending(
    client: AsyncClient, doubles: Doubles
) -> None:
    """02_spec 第 2.3.2 節:App 靠滑動展延維持長期登入。"""
    from datetime import timedelta

    from tests.e2e.conftest import NOW

    await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    logged_in = await client.post(
        "/auth/login", json={"email": EMAIL, "password": PASSWORD, "platform": "app"}
    )
    assert logged_in.json()["refresh_token"] is None
    token = logged_in.json()["access_token"]

    assert doubles.clock is not None
    headers = {"Authorization": f"Bearer {token}"}

    # 第 6 天:還不需要展延
    doubles.clock.advance_to(NOW + timedelta(days=6))
    assert (await client.post("/auth/token/extend", headers=headers)).status_code == 204

    # 第 7 天:換到一張新的,效期從現在起算 180 天
    doubles.clock.advance_to(NOW + timedelta(days=7))
    extended = await client.post("/auth/token/extend", headers=headers)
    assert extended.status_code == 200
    assert extended.json()["access_token"] != token
