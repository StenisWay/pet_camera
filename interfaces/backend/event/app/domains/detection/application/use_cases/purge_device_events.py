"""移除裝置時的串聯清除。"""

from dataclasses import dataclass
from uuid import UUID

from app.domains.detection.application.ports import DetectionUnitOfWork, MediaUploader


@dataclass(frozen=True)
class PurgeResult:
    deleted_count: int


class PurgeDeviceEvents:
    """Device 服務移除裝置時呼叫(08_spec 第 3.3 節)。

    移除裝置要連同事件一起清掉,理由見 01_資料模型與儲存規格.md 第 6 節:
    裝置可能重新配對給別人,不能讓新擁有者看到前一位使用者的寵物活動紀錄。
    """

    def __init__(self, *, uow: DetectionUnitOfWork, uploader: MediaUploader) -> None:
        self.uow = uow
        self.uploader = uploader

    async def execute(self, device_id: UUID) -> PurgeResult:
        """先刪資料列並 commit,再刪 R2 物件。

        順序是刻意的:反過來的話,物件刪掉但資料列刪除失敗,時間軸會留下指向不存在
        物件的事件;現在這個順序最壞只是留下沒人指向的物件,等 lifecycle rule 到期
        自己消失。整個操作是冪等的,Device 服務重試不會出錯。
        """
        async with self.uow:
            purged = await self.uow.events.delete_all_by_device(device_id)
            await self.uow.commit()

        if purged.object_keys:
            await self.uploader.delete_many(purged.object_keys)

        return PurgeResult(deleted_count=purged.deleted_count)
