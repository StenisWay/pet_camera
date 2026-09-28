"""測試替身。全部明確繼承介面——漏實作任何方法,建立實例當下就失敗。

fake repository 刻意模擬持久化與交易語意(回傳複本、未 commit 就回滾),否則抓不到
「忘了 save」「忘了 commit」;合約測試證明它與 SQLAlchemy 實作行為一致。
"""

import copy
import uuid
from datetime import UTC, datetime

from app.core.rate_limit import RateLimitCounter
from app.domains.media.application.ports import (
    CapturedFrame,
    ClipWorker,
    DeviceDirectory,
    EventSource,
    FrameSource,
    MediaStorage,
    MediaUnitOfWork,
    SourceDevice,
)
from app.domains.media.domain.entities import MediaItem, MediaItemStatus, SourceEvent
from app.domains.media.domain.exceptions import ScreenshotSourceUnavailable
from app.domains.media.domain.repositories import MediaItemRepository
from app.shared_kernel.ports import Clock, IdGenerator

ACTIVE_STATUSES = (MediaItemStatus.PROCESSING, MediaItemStatus.READY)


class FakeMediaItemRepository(MediaItemRepository):
    def __init__(self) -> None:
        self.committed: dict[uuid.UUID, MediaItem] = {}
        self.pending: dict[uuid.UUID, MediaItem] = {}

    def _visible(self) -> dict[uuid.UUID, MediaItem]:
        return {**self.committed, **self.pending}

    async def get(self, item_id: uuid.UUID, *, owner_id: uuid.UUID) -> MediaItem | None:
        found = self._visible().get(item_id)
        if found is None or not found.is_owned_by(owner_id):
            return None
        return copy.deepcopy(found)  # 回傳複本:忘了 save 的修改不會被保存

    async def get_internal(self, item_id: uuid.UUID) -> MediaItem | None:
        return copy.deepcopy(self._visible().get(item_id))

    async def add(self, item: MediaItem) -> None:
        self.pending[item.id] = copy.deepcopy(item)

    async def save(self, item: MediaItem) -> None:
        self.pending[item.id] = copy.deepcopy(item)

    async def find_active_clip(
        self,
        *,
        owner_id: uuid.UUID,
        source_event_id: uuid.UUID,
        captured_at: datetime,
        duration_sec: int,
    ) -> MediaItem | None:
        for item in self._visible().values():
            if (
                item.is_owned_by(owner_id)
                and item.source_event_id == source_event_id
                and item.captured_at == captured_at
                and item.duration_sec == duration_sec
                and item.status in ACTIVE_STATUSES
            ):
                return copy.deepcopy(item)
        return None

    async def list_stale_processing(self, *, changed_before: datetime) -> list[MediaItem]:
        return [
            copy.deepcopy(item)
            for item in self._visible().values()
            if item.status is MediaItemStatus.PROCESSING
            and (item.updated_at is None or item.updated_at < changed_before)
        ]


class FakeMediaUnitOfWork(MediaUnitOfWork):
    def __init__(self) -> None:
        self.media = FakeMediaItemRepository()
        self.commit_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.media.pending.clear()  # 未 commit = rollback

    async def commit(self) -> None:
        self.media.committed.update(self.media.pending)
        self.media.pending.clear()
        self.commit_count += 1

    def given(self, item: MediaItem) -> MediaItem:
        """Arrange 用:直接放一筆已存在的資料。"""
        self.media.committed[item.id] = copy.deepcopy(item)
        return item


class FakeDeviceDirectory(DeviceDirectory):
    def __init__(self, devices: dict[uuid.UUID, SourceDevice] | None = None) -> None:
        self.devices = devices or {}

    async def get(self, device_id: uuid.UUID) -> SourceDevice | None:
        return self.devices.get(device_id)


class FakeEventSource(EventSource):
    def __init__(self, events: dict[uuid.UUID, SourceEvent] | None = None) -> None:
        self.events = events or {}

    async def get(self, event_id: uuid.UUID) -> SourceEvent | None:
        return self.events.get(event_id)


class FakeFrameSource(FrameSource):
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.calls: list[tuple[str, uuid.UUID, int | None]] = []

    async def capture_live_frame(self, device_id: uuid.UUID) -> CapturedFrame:
        self.calls.append(("live", device_id, None))
        if not self.available:
            raise ScreenshotSourceUnavailable()
        return CapturedFrame(image=b"jpeg-bytes", thumbnail=b"jpeg-thumb")

    async def capture_event_frame(
        self, event_id: uuid.UUID, *, offset_sec: int
    ) -> CapturedFrame:
        self.calls.append(("event", event_id, offset_sec))
        if not self.available:
            raise ScreenshotSourceUnavailable()
        return CapturedFrame(image=b"jpeg-bytes", thumbnail=b"jpeg-thumb")


class FakeClipWorker(ClipWorker):
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.dispatched: list[dict[str, object]] = []

    async def dispatch(self, **kwargs: object) -> None:
        if not self.available:
            raise ConnectionError("worker unreachable")
        self.dispatched.append(kwargs)


class FakeMediaStorage(MediaStorage):
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.objects: dict[str, bytes] = {}

    async def put_image(self, object_key: str, content: bytes) -> None:
        if not self.available:
            raise ConnectionError("storage unreachable")
        self.objects[object_key] = content

    async def presigned_url(self, object_key: str) -> str:
        return f"https://r2.example/{object_key}?sig=test"


class FixedClock(Clock):
    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime(2026, 9, 20, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now


class SequentialIds(IdGenerator):
    def __init__(self) -> None:
        self._n = 0

    def new_id(self) -> uuid.UUID:
        self._n += 1
        return uuid.UUID(int=self._n)


class FakeRateLimitCounter(RateLimitCounter):
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def hit(self, key: str, *, window_seconds: int) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]
