"""冒煙測試:剪輯的完整生命週期能不能串起來。

數量刻意極少——細節都已在內層測過,這裡只確認「受理 → 派工 → worker 回呼 → 可播放」
這條路沒有接錯。用的是真實的 app 與路由,只把外部系統換成 fake。
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import get_current_user_id
from app.domains.media.presentation.dependencies import (
    get_clip_worker,
    get_clock,
    get_event_source,
    get_id_generator,
    get_media_storage,
    get_media_uow,
    get_rate_limit_counter,
)
from app.main import create_app
from tests.domains.media.builders import EVENT, NOW, OWNER, an_event
from tests.domains.media.fakes import (
    FakeClipWorker,
    FakeEventSource,
    FakeMediaStorage,
    FakeMediaUnitOfWork,
    FakeRateLimitCounter,
    FixedClock,
    SequentialIds,
)

INTERNAL_HEADERS = {"X-Internal-Api-Key": "change-me-internal"}


@pytest.fixture
def worker():
    return FakeClipWorker()


@pytest.fixture
async def client(worker):
    app = create_app(lifespan_enabled=False)
    # UnitOfWork 要跨請求共用,否則每個請求都會拿到一個空的「資料庫」
    shared_uow = FakeMediaUnitOfWork()
    app.dependency_overrides.update(
        {
            get_media_uow: lambda: shared_uow,
            get_event_source: lambda: FakeEventSource({EVENT: an_event(duration_sec=45)}),
            get_clip_worker: lambda: worker,
            get_media_storage: lambda: FakeMediaStorage(),
            get_clock: lambda: FixedClock(NOW),
            get_id_generator: lambda: SequentialIds(),
            get_rate_limit_counter: lambda: FakeRateLimitCounter(),
            get_current_user_id: lambda: OWNER,
        }
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_clip_becomes_playable_after_the_worker_reports_back(client, worker):
    accepted = await client.post(f"/events/{EVENT}/clip", json={"start_sec": 5, "end_sec": 20})
    assert accepted.status_code == 202
    item_id = accepted.json()["id"]

    # 處理中:相簿顯示 spinner,沒有可播放的連結
    pending = await client.get(f"/media/{item_id}")
    assert pending.json()["status"] == "processing"
    assert pending.json()["content_url"] is None

    # worker 完成後回呼(審查 #3)
    [job] = worker.dispatched
    done = await client.post(
        f"/internal/media/{item_id}/ready",
        json={
            "object_key": job["object_key"],
            "thumbnail_object_key": job["thumbnail_object_key"],
        },
        headers=INTERNAL_HEADERS,
    )
    assert done.status_code == 204

    ready = await client.get(f"/media/{item_id}")
    assert ready.json()["status"] == "ready"
    assert ready.json()["content_url"].startswith("https://")
