import logging

from app.domains.drive_export.application.dtos import ExportJob
from app.domains.drive_export.application.ports import (
    AlbumContent,
    DriveExportUnitOfWork,
    GoogleDrive,
    GoogleOAuth,
)
from app.domains.drive_export.domain.entities import DriveFile
from app.domains.drive_export.domain.exceptions import (
    DriveAuthorizationExpired,
    DriveNotConnected,
)

logger = logging.getLogger(__name__)


class RunExport:
    """背景工作:把 R2 上的檔案上傳到使用者 Drive 的「寵物攝影機」資料夾。

    刻意不往外丟例外——呼叫端是背景任務,沒有人接得住。所有失敗都收斂成該項目的
    drive_export_status = failed(DRIVE_002),使用者在相簿縮圖上看到錯誤圖示,
    項目本身仍可正常瀏覽(12_spec 第 6 節驗收)。
    """

    def __init__(
        self,
        uow: DriveExportUnitOfWork,
        album: AlbumContent,
        oauth: GoogleOAuth,
        drive: GoogleDrive,
        *,
        folder_name: str,
    ) -> None:
        self.uow = uow
        self.album = album
        self.oauth = oauth
        self.drive = drive
        self.folder_name = folder_name

    async def execute(self, job: ExportJob) -> None:
        try:
            file_id = await self._upload(job)
        except DriveAuthorizationExpired:
            # DRIVE_003:refresh token 已失效,清掉連結,下一次請求才會回 DRIVE_001
            # 並把使用者導回 OAuth 授權頁
            logger.warning("drive authorization expired for user %s", job.owner_id)
            async with self.uow:
                await self.uow.connections.delete_by_owner(job.owner_id)
                await self.uow.commit()
            await self._mark_failed(job)
        except Exception:
            logger.warning("drive export failed for %s", job.media_item_id, exc_info=True)
            await self._mark_failed(job)
        else:
            await self.album.complete_export(job.media_item_id, drive_file_id=file_id)

    async def _upload(self, job: ExportJob) -> str:
        async with self.uow:
            connection = await self.uow.connections.get_by_owner(job.owner_id)
            if connection is None:
                raise DriveNotConnected()
            access_token = await self.oauth.refresh_access_token(connection.refresh_token)
            folder_id = connection.folder_id
            if folder_id is None:
                # 「寵物攝影機」資料夾只建一次,建好就記在連結上重用
                folder_id = await self.drive.ensure_folder(
                    access_token=access_token, name=self.folder_name
                )
                connection.remember_folder(folder_id)
                await self.uow.connections.save(connection)
                await self.uow.commit()

        drive_file = DriveFile.for_media(
            object_key=job.object_key, media_type=job.media_type, captured_at=job.captured_at
        )
        content = await self.album.read_object(drive_file.object_key)
        return await self.drive.upload_file(
            access_token=access_token,
            folder_id=folder_id,
            filename=drive_file.filename,
            content=content,
            mime_type=drive_file.mime_type,
        )

    async def _mark_failed(self, job: ExportJob) -> None:
        try:
            await self.album.fail_export(job.media_item_id)
        except Exception:
            # 項目可能已被使用者刪掉(規格審查 #10):沒有東西要標記,不是錯誤
            logger.info("cannot mark %s as failed, it may be deleted", job.media_item_id)
