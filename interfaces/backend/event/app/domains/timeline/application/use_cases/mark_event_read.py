"""已讀標記。"""

from dataclasses import dataclass
from uuid import UUID

from app.domains.timeline.application.ports import DeviceOwnership, TimelineUnitOfWork
from app.domains.timeline.domain.exceptions import DeviceNotFound, EventNotFound


@dataclass(frozen=True)
class ReadStateResult:
    id: UUID
    is_read: bool


class MarkEventRead:
    def __init__(self, *, uow: TimelineUnitOfWork, ownership: DeviceOwnership) -> None:
        self.uow = uow
        self.ownership = ownership

    async def execute(
        self, event_id: UUID, requester_id: UUID, *, is_read: bool
    ) -> ReadStateResult:
        """載入 → 驗證擁有者 → 改旗標 → 保存。

        擁有者驗證在交易內、寫入之前:非本人的請求連 commit 都不該發生。
        """
        async with self.uow:
            event = await self.uow.events.get(event_id)
            if event is None:
                raise EventNotFound()
            if not await self.ownership.is_owned_by(event.device_id, requester_id):
                raise DeviceNotFound()

            event.mark_read(is_read)
            await self.uow.events.save_read_state(event)
            await self.uow.commit()

        return ReadStateResult(id=event.id, is_read=event.is_read)
