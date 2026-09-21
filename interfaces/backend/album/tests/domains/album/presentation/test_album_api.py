"""只驗證「規則有沒有正確接上 HTTP」:狀態碼、錯誤碼、回應欄位、權限。
業務規則本身在 domain / application 測試中窮盡,這裡不重複。"""

import uuid

import pytest

from app.core.security import get_current_user_id
from app.domains.album.domain.entities import MediaItemStatus
from tests.domains.album.builders import OWNER, an_item, taipei

INTERNAL_KEY = "change-me-internal"


async def test_list_returns_presigned_urls_and_hides_object_keys(client, album_uow):
    """回應不得外洩 R2 object key:key 內含 user_id(資料模型第 3.1 節)。"""
    album_uow.given(an_item())

    response = await client.get("/media")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["url"].startswith("https://r2.example.test/")
    assert "object_key" not in item
    assert "user_id" not in item


async def test_processing_item_has_no_content_url(client, album_uow):
    """11_spec 第 4 節:processing 的卡片顯示 spinner,不可點擊播放。"""
    album_uow.given(an_item(status=MediaItemStatus.PROCESSING))

    item = (await client.get("/media")).json()["items"][0]

    assert item["status"] == "processing"
    assert item["url"] is None
    assert item["thumbnail_url"] is None


async def test_date_filter_is_wired_to_taipei_time(client, album_uow):
    """12_spec 第 2.1 節:相簿依台北時間分組。

    這個測試刻意走完整的組裝路徑(設定 → ListAlbum → DateRange),不 override
    時區——否則把 composition root 的時區接錯成 UTC 也不會有人發現。
    台北 9/21 凌晨 1 點的項目在 UTC 還是 9/20 17:00。
    """
    item = album_uow.given(an_item(captured_at=taipei(2026, 9, 21, 1, 0)))

    on_the_20th = await client.get("/media", params={"date": "2026-09-20"})
    on_the_21st = await client.get("/media", params={"date": "2026-09-21"})

    assert on_the_20th.json()["items"] == []
    assert [i["id"] for i in on_the_21st.json()["items"]] == [str(item.id)]


async def test_conflicting_date_filters_return_val_001(client):
    response = await client.get("/media", params={"date": "2026-09-20", "from": "2026-09-01"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VAL_001"


async def test_missing_token_returns_auth_001(app, client):
    """10_錯誤處理與狀態規範.md:AUTH_001,前端阻斷式導向登入頁。"""
    app.dependency_overrides.pop(get_current_user_id)

    response = await client.get("/media")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_001"


async def test_delete_returns_204_and_purges_the_object(client, album_uow, storage):
    item = album_uow.given(an_item(object_key="media/a.jpg"))

    response = await client.delete(f"/media/{item.id}")

    assert response.status_code == 204
    assert storage.deleted == ["media/a.jpg"]


async def test_deleting_another_users_item_returns_404(client, album_uow, storage):
    item = album_uow.given(an_item(owner_id=uuid.uuid4()))

    response = await client.delete(f"/media/{item.id}")

    assert response.status_code == 404
    assert storage.deleted == []


async def test_malformed_id_returns_val_001(client):
    response = await client.delete("/media/not-a-uuid")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VAL_001"


async def test_rate_limit_returns_rate_001(client, album_uow, rate_limit_counter):
    """10_錯誤處理與狀態規範.md:RATE_001,Toast 提示。"""
    rate_limit_counter.counts[f"ratelimit:{OWNER}:GET /media"] = 10_000

    response = await client.get("/media")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_001"


async def test_rate_limiter_fails_open_when_redis_is_down(client, rate_limit_counter):
    """13_ADR 第 4 節:限流是保護機制,故障時不應讓它本身阻斷全站。"""
    rate_limit_counter.available = False

    assert (await client.get("/media")).status_code == 200


@pytest.mark.parametrize("headers", [{}, {"X-Internal-Api-Key": "wrong"}])
async def test_internal_endpoint_requires_the_shared_key(client, headers):
    response = await client.delete(f"/internal/users/{uuid.uuid4()}/media", headers=headers)

    assert response.status_code == 403


async def test_internal_endpoint_purges_the_whole_album(client, album_uow, storage):
    """01_資料模型與儲存規格.md 第 6 節:Auth 刪除帳號時串聯清除(規格審查 #9)。"""
    album_uow.given(an_item(object_key="media/a.jpg"))
    album_uow.given(an_item(object_key="media/b.jpg"))

    response = await client.delete(
        f"/internal/users/{OWNER}/media", headers={"X-Internal-Api-Key": INTERNAL_KEY}
    )

    assert response.status_code == 200
    assert response.json()["deleted_object_count"] == 2
    assert sorted(storage.deleted) == ["media/a.jpg", "media/b.jpg"]


async def test_health_does_not_touch_the_database(client):
    """VM-3 掛掉時不該連帶讓兩台服務節點被 LB 判定為不健康(13_ADR 第 3 節)。"""
    assert (await client.get("/health")).status_code == 200
