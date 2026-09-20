"""把 drive_export 的 AlbumContent port 接到 album 領域的公開 API。

跨領域呼叫只發生在這種 adapter 裡(13_ADR 的服務邊界原則在服務內部的對應規則)。
"""

import uuid

from app.domains.album.api import AlbumApi
from app.domains.drive_export.application.ports import (
    AlbumContent,
    ExportableMedia,
    PreparedExport,
)


class AlbumApiContent(AlbumContent):
    def __init__(self, album: AlbumApi) -> None:
        self._album = album

    async def prepare_export(
        self, owner_id: uuid.UUID, item_ids: list[uuid.UUID]
    ) -> PreparedExport:
        preparation = await self._album.prepare_export(owner_id, item_ids)
        return PreparedExport(
            accepted=[
                ExportableMedia(
                    id=item.id,
                    object_key=item.object_key,
                    media_type=item.type,
                    captured_at=item.captured_at,
                )
                for item in preparation.accepted
            ],
            skipped_ids=list(preparation.skipped_ids),
        )

    async def complete_export(self, item_id: uuid.UUID, *, drive_file_id: str) -> None:
        await self._album.complete_export(item_id, drive_file_id=drive_file_id)

    async def fail_export(self, item_id: uuid.UUID) -> None:
        await self._album.fail_export(item_id)

    async def read_object(self, object_key: str) -> bytes:
        return await self._album.read_object(object_key)
