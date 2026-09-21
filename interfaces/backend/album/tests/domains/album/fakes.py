"""測試替身:有真實行為的 fake,不是 mock。

每個 fake 都明確繼承正式介面,和 infrastructure 的實作是「同一份合約的兩個實作」,
由 tests/domains/album/contracts/ 的合約測試保證兩者行為一致。
"""

import copy
import uuid
from datetime import UTC, datetime
from types import TracebackType
from typing import Self

from app.core.rate_limit import RateLimitCounter
from app.domains.album.application.dtos import AlbumItemResult, AlbumPageResult
from app.domains.album.application.ports import (
    AlbumQueries,
    AlbumUnitOfWork,
    MediaObjectStorage,
)
from app.domains.album.domain.entities import AlbumItem
from app.domains.album.domain.repositories import AlbumItemRepository
from app.domains.album.domain.value_objects import DateRange, PageSize
from app.shared_kernel.paging import Cursor
from app.shared_kernel.ports import Clock, IdGenerator


class FakeAlbumItemRepository(AlbumItemRepository):
    def __init__(self) -> None:
        self.committed: dict[uuid.UUID, AlbumItem] = {}
        self.pending: dict[uuid.UUID, AlbumItem] = {}
        self.deleted: set[uuid.UUID] = set()

    def _visible(self) -> dict[uuid.UUID, AlbumItem]:
        merged = {**self.committed, **self.pending}
        return {k: v for k, v in merged.items() if k not in self.deleted}

    async def get(self, item_id: uuid.UUID) -> AlbumItem | None:
        # 回傳複本:模擬「從資料庫載入」,忘了 save 的修改不會被保存
        return copy.deepcopy(self._visible().get(item_id))

    async def get_many(self, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, AlbumItem]:
        visible = self._visible()
        return {i: copy.deepcopy(visible[i]) for i in item_ids if i in visible}

    async def save(self, item: AlbumItem) -> None:
        self.pending[item.id] = copy.deepcopy(item)

    async def delete(self, item_id: uuid.UUID) -> None:
        self.deleted.add(item_id)

    async def delete_all_owned_by(self, owner_id: uuid.UUID) -> list[str]:
        keys: list[str] = []
        for item in list(self._visible().values()):
            if item.owner_id == owner_id:
                keys.extend(item.object_keys)
                self.deleted.add(item.id)
        return keys

    async def list_stale_exports(self, *, changed_before: datetime) -> list[AlbumItem]:
        return [
            copy.deepcopy(i)
            for i in self._visible().values()
            if i.is_exporting
            and (i.export_state_changed_at is None or i.export_state_changed_at < changed_before)
        ]


class FakeAlbumUnitOfWork(AlbumUnitOfWork):
    def __init__(self) -> None:
        self.items = FakeAlbumItemRepository()
        self.commit_count = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # 未 commit 的變更丟棄 = rollback
        self.items.pending.clear()
        self.items.deleted.clear()

    async def commit(self) -> None:
        self.items.committed.update(self.items.pending)
        for item_id in self.items.deleted:
            self.items.committed.pop(item_id, None)
        self.items.pending.clear()
        self.items.deleted.clear()
        self.commit_count += 1

    def given(self, item: AlbumItem) -> AlbumItem:
        """Arrange 用:直接放入已提交的資料。"""
        self.items.committed[item.id] = copy.deepcopy(item)
        return item


class FakeAlbumQueries(AlbumQueries):
    """讀取端的 fake。排序/游標的正確性由 infrastructure 的整合測試保證,
    這裡只提供足夠讓 use case 測試成立的行為。"""

    def __init__(self, uow: FakeAlbumUnitOfWork) -> None:
        self.uow = uow
        self.last_call: dict[str, object] = {}

    async def list_page(
        self,
        owner_id: uuid.UUID,
        *,
        cursor: str | None,
        page_size: PageSize,
        date_range: DateRange,
    ) -> AlbumPageResult:
        self.last_call = {
            "owner_id": owner_id,
            "cursor": cursor,
            "page_size": page_size,
            "date_range": date_range,
        }
        items = sorted(
            (i for i in self.uow.items.committed.values() if i.owner_id == owner_id),
            key=lambda i: (i.captured_at, i.id),
            reverse=True,
        )
        if date_range.start:
            items = [i for i in items if i.captured_at >= date_range.start]
        if date_range.end:
            items = [i for i in items if i.captured_at < date_range.end]
        page = items[: page_size.value]
        has_more = len(items) > page_size.value
        next_cursor = Cursor(page[-1].captured_at, page[-1].id).encode() if has_more else None
        return AlbumPageResult(
            items=[AlbumItemResult.from_entity(i) for i in page], next_cursor=next_cursor
        )


class FakeMediaObjectStorage(MediaObjectStorage):
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.fail_delete_keys: set[str] = set()

    async def download(self, object_key: str) -> bytes:
        return self.objects.get(object_key, b"binary-content")

    async def delete(self, object_key: str) -> None:
        if object_key in self.fail_delete_keys:
            raise RuntimeError(f"R2 unavailable for {object_key}")
        self.deleted.append(object_key)
        self.objects.pop(object_key, None)

    async def presigned_url(self, object_key: str) -> str:
        return f"https://r2.example.test/{object_key}?signed=1"


class InMemoryRateLimitCounter(RateLimitCounter):
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.available = True

    async def hit(self, key: str, *, window_seconds: int) -> int:
        if not self.available:
            raise ConnectionError("redis unreachable")
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]


class FixedClock(Clock):
    def __init__(self, now: datetime = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def set(self, now: datetime) -> None:
        self._now = now


class SequentialIds(IdGenerator):
    def __init__(self) -> None:
        self._n = 0

    def new_id(self) -> uuid.UUID:
        self._n += 1
        return uuid.UUID(int=self._n)
