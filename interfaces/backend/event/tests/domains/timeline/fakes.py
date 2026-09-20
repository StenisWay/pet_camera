"""timeline 的測試替身。

FakeTimelineQueries 刻意實作了真正的排序與游標邏輯——一個只回傳整份清單的 fake
抓不到分頁的重複與遺漏,而那正是這個讀取端最容易出錯的地方。行為是否與 SQLAlchemy 版
一致,由合約測試保證。
"""

import copy
from types import TracebackType
from typing import Self
from uuid import UUID

from app.domains.timeline.application.ports import (
    DeviceOwnership,
    MediaUrlIssuer,
    TimelinePage,
    TimelineQueries,
    TimelineUnitOfWork,
)
from app.domains.timeline.domain.entities import TimelineEvent
from app.domains.timeline.domain.repositories import TimelineEventRepository
from app.domains.timeline.domain.value_objects import DateRange, PageSize, TimelineCursor


class FakeTimelineEventRepository(TimelineEventRepository):
    def __init__(self, store: dict[UUID, TimelineEvent] | None = None) -> None:
        self.committed: dict[UUID, TimelineEvent] = store if store is not None else {}
        self.pending: dict[UUID, TimelineEvent] = {}

    async def get(self, event_id: UUID) -> TimelineEvent | None:
        found = self.pending.get(event_id) or self.committed.get(event_id)
        return copy.deepcopy(found)

    async def save_read_state(self, event: TimelineEvent) -> None:
        # 只保存 is_read:其餘欄位由 detection 擁有,這裡改了也不該生效
        current = self.committed.get(event.id)
        updated = copy.deepcopy(current if current is not None else event)
        updated.is_read = event.is_read
        self.pending[event.id] = updated


class FakeTimelineUnitOfWork(TimelineUnitOfWork):
    def __init__(self, store: dict[UUID, TimelineEvent] | None = None) -> None:
        self.events = FakeTimelineEventRepository(store)
        self.commit_count = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.events.pending.clear()  # 未 commit = 回滾

    async def commit(self) -> None:
        self.events.committed.update(self.events.pending)
        self.events.pending.clear()
        self.commit_count += 1

    def given(self, event: TimelineEvent) -> TimelineEvent:
        self.events.committed[event.id] = copy.deepcopy(event)
        return event


class FakeTimelineQueries(TimelineQueries):
    def __init__(self, events: list[TimelineEvent] | None = None) -> None:
        self.events = list(events or [])
        self.unavailable: Exception | None = None

    def given(self, *events: TimelineEvent) -> None:
        self.events.extend(events)

    async def list_by_device(
        self,
        device_id: UUID,
        *,
        cursor: TimelineCursor | None,
        page_size: PageSize,
        date_range: DateRange,
    ) -> TimelinePage:
        if self.unavailable is not None:
            raise self.unavailable

        rows = [e for e in self.events if e.device_id == device_id]
        if date_range.started_from is not None:
            rows = [e for e in rows if e.started_at >= date_range.started_from]
        if date_range.started_to is not None:
            rows = [e for e in rows if e.started_at < date_range.started_to]

        # 新到舊;同一時間以 id 遞減決勝,與游標的比較方式必須完全一致
        rows.sort(key=lambda e: (e.started_at, e.id), reverse=True)

        if cursor is not None:
            rows = [
                e
                for e in rows
                if (e.started_at, e.id) < (cursor.started_at, cursor.event_id)
            ]

        # 多取一筆來判斷還有沒有下一頁,而不是另外數一次總數
        window = rows[: page_size.value + 1]
        items = window[: page_size.value]
        next_cursor = (
            TimelineCursor(started_at=items[-1].started_at, event_id=items[-1].id)
            if len(window) > page_size.value
            else None
        )
        return TimelinePage(items=copy.deepcopy(items), next_cursor=next_cursor)


class FakeDeviceOwnership(DeviceOwnership):
    def __init__(self, owners: dict[UUID, UUID] | None = None) -> None:
        self.owners = owners or {}

    def given(self, device_id: UUID, user_id: UUID) -> None:
        self.owners[device_id] = user_id

    async def is_owned_by(self, device_id: UUID, user_id: UUID) -> bool:
        return self.owners.get(device_id) == user_id


class FakeMediaUrlIssuer(MediaUrlIssuer):
    def __init__(self) -> None:
        self.issued: list[str] = []

    async def presigned_url(self, object_key: str) -> str:
        self.issued.append(object_key)
        return f"https://r2.example.com/{object_key}?signed=1"
