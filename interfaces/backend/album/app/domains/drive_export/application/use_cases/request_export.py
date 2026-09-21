from app.domains.drive_export.application.dtos import (
    ExportAcceptedResult,
    ExportJob,
    ExportRequestCommand,
)
from app.domains.drive_export.application.ports import (
    AlbumContent,
    DriveExportUnitOfWork,
    ExportScheduler,
)
from app.domains.drive_export.domain.exceptions import (
    DriveNotConnected,
    EmptyExportRequest,
    ExportBatchTooLarge,
)


class RequestExport:
    """12_spec 第 2.3 節:受理匯出請求,實際上傳交給背景工作。"""

    def __init__(
        self,
        uow: DriveExportUnitOfWork,
        album: AlbumContent,
        scheduler: ExportScheduler,
        *,
        batch_limit: int,
    ) -> None:
        self.uow = uow
        self.album = album
        self.scheduler = scheduler
        self.batch_limit = batch_limit

    async def execute(self, command: ExportRequestCommand) -> ExportAcceptedResult:
        if not command.media_item_ids:
            raise EmptyExportRequest()
        if len(command.media_item_ids) > self.batch_limit:
            raise ExportBatchTooLarge()

        async with self.uow:
            if await self.uow.connections.get_by_owner(command.owner_id) is None:
                # DRIVE_001:前端阻斷式導向 OAuth 授權頁
                raise DriveNotConnected()

        prepared = await self.album.prepare_export(command.owner_id, command.media_item_ids)
        for media in prepared.accepted:
            self.scheduler.schedule(
                ExportJob(
                    media_item_id=media.id,
                    owner_id=command.owner_id,
                    object_key=media.object_key,
                    media_type=media.media_type,
                    captured_at=media.captured_at,
                )
            )
        return ExportAcceptedResult(
            accepted_ids=[m.id for m in prepared.accepted],
            skipped_ids=list(prepared.skipped_ids),
        )
