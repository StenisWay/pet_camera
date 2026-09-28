import uuid

from app.domains.album.application.dtos import ExportableItem, ExportPreparation
from app.domains.album.application.ports import AlbumUnitOfWork
from app.domains.album.domain.exceptions import AlbumItemNotFound
from app.shared_kernel.ports import Clock


class PrepareExport:
    """匯出前的檢核與狀態轉移(12_spec 第 2.3 節 + 規格審查 #6、#10)。

    檢核與「轉成 exporting」放在同一個交易內,兩個並行的匯出請求才不會同時把同一個
    項目送上 Drive、產生重複檔案。
    """

    def __init__(self, uow: AlbumUnitOfWork, clock: Clock) -> None:
        self.uow = uow
        self.clock = clock

    async def execute(
        self, owner_id: uuid.UUID, item_ids: list[uuid.UUID]
    ) -> ExportPreparation:
        now = self.clock.now()
        accepted: list[ExportableItem] = []
        skipped: list[uuid.UUID] = []

        async with self.uow:
            found = await self.uow.items.get_many(item_ids)
            for item_id in item_ids:
                item = found.get(item_id)
                if item is None or not item.is_owned_by(owner_id):
                    raise AlbumItemNotFound()
                if item.is_exporting:
                    # 規格審查 #6:重複送出不應在 Drive 產生重複檔案
                    skipped.append(item.id)
                    continue
                item.start_export(now)  # 非 ready 會在這裡丟 MediaItemNotReady
                await self.uow.items.save(item)
                accepted.append(
                    ExportableItem(
                        id=item.id,
                        object_key=item.object_key or "",
                        type=item.type.value,
                        captured_at=item.captured_at,
                    )
                )
            await self.uow.commit()

        return ExportPreparation(accepted=accepted, skipped_ids=skipped)
