"""detection 的測試替身。

fake 比 mock 好:它有真實行為,測試讀起來像業務描述,也不綁死呼叫次數與參數順序。
fake 的行為由合約測試保證與 SQLAlchemy 版一致。
"""

import copy
from decimal import Decimal
from types import TracebackType
from typing import Self
from uuid import UUID

from app.domains.detection.application.ports import (
    Backoff,
    DetectionUnitOfWork,
    MediaUploader,
    PushNotifier,
)
from app.domains.detection.domain.entities import Event
from app.domains.detection.domain.exceptions import UploadFailed
from app.domains.detection.domain.repositories import EventRepository, PurgedEvents


class FakeEventRepository(EventRepository):
    """committed 是「資料庫」,pending_* 是還沒 commit 的變更。

    分開兩層才模擬得出交易語意,抓得到「忘了 save」與「忘了 commit」。
    """

    def __init__(self) -> None:
        self.committed: dict[UUID, Event] = {}
        self.pending_saves: dict[UUID, Event] = {}
        self.pending_deletes: set[UUID] = set()

    async def get(self, event_id: UUID) -> Event | None:
        if event_id in self.pending_deletes:
            return None
        found = self.pending_saves.get(event_id) or self.committed.get(event_id)
        # 回傳複本:忘了 save 的修改不會被保存,與真實 repository 一致
        return copy.deepcopy(found)

    async def save(self, event: Event) -> None:
        self.pending_saves[event.id] = copy.deepcopy(event)

    async def delete_all_by_device(self, device_id: UUID) -> PurgedEvents:
        visible = {**self.committed, **self.pending_saves}
        keys: list[str] = []
        count = 0
        for event in visible.values():
            if event.device_id == device_id and event.id not in self.pending_deletes:
                keys.extend(event.object_keys())
                self.pending_deletes.add(event.id)
                count += 1
        return PurgedEvents(deleted_count=count, object_keys=keys)

    def _rollback(self) -> None:
        self.pending_saves.clear()
        self.pending_deletes.clear()

    def _commit(self) -> None:
        self.committed.update(self.pending_saves)
        for event_id in self.pending_deletes:
            self.committed.pop(event_id, None)
        self._rollback()


class FakeDetectionUnitOfWork(DetectionUnitOfWork):
    def __init__(self) -> None:
        self.events = FakeEventRepository()
        self.commit_count = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.events._rollback()  # 未 commit = 回滾

    async def commit(self) -> None:
        self.events._commit()
        self.commit_count += 1

    def given(self, event: Event) -> Event:
        """Arrange 用:直接放一筆已存在的事件。"""
        self.events.committed[event.id] = copy.deepcopy(event)
        return event


class FakeMediaUploader(MediaUploader):
    """可程式化的 R2 替身:fail_times 次之後才會成功。"""

    def __init__(self, *, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.attempts = 0
        self.uploaded: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def upload(self, key: str, data: bytes, *, content_type: str) -> None:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise UploadFailed()
        self.uploaded[key] = data

    async def delete_many(self, keys: list[str]) -> None:
        self.deleted.extend(keys)


class FakePushNotifier(PushNotifier):
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.sent: list[tuple[UUID, UUID, Decimal]] = []

    async def notify_event_ready(
        self, *, device_id: UUID, event_id: UUID, confidence_score: Decimal
    ) -> None:
        if self.fails:
            raise ConnectionError("push service unreachable")
        self.sent.append((device_id, event_id, confidence_score))


class NoWaitBackoff(Backoff):
    """記下等待了幾次,但不真的睡——測試不該花 7 秒在指數退避上。"""

    def __init__(self) -> None:
        self.waits: list[int] = []

    async def wait(self, attempt: int) -> None:
        self.waits.append(attempt)
