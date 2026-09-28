"""drive_export 的組裝點。

跨領域的 adapter(AlbumContent 的實作)在 composition root(main.py)組好掛在
app.state,這裡只取出——presentation 只認得自己領域定義的 port,連 album.api 這個
名字都不需要出現。
"""

from typing import Annotated

from fastapi import BackgroundTasks, Depends, Request

from app.core.dependencies import (
    ClockDep,
    IdGeneratorDep,
    SessionFactoryDep,
    SettingsDep,
)
from app.domains.drive_export.application.ports import (
    AlbumContent,
    DriveExportUnitOfWork,
    ExportScheduler,
    GoogleDrive,
    GoogleOAuth,
    OAuthStateStore,
)
from app.domains.drive_export.application.use_cases.complete_authorization import (
    CompleteAuthorization,
)
from app.domains.drive_export.application.use_cases.request_export import RequestExport
from app.domains.drive_export.application.use_cases.run_export import RunExport
from app.domains.drive_export.application.use_cases.start_authorization import StartAuthorization
from app.domains.drive_export.infrastructure.unit_of_work import SqlAlchemyDriveExportUnitOfWork
from app.domains.drive_export.presentation.scheduler import BackgroundTaskExportScheduler


def get_google_oauth(request: Request) -> GoogleOAuth:
    return request.app.state.google_oauth


def get_google_drive(request: Request) -> GoogleDrive:
    return request.app.state.google_drive


def get_oauth_state_store(request: Request) -> OAuthStateStore:
    return request.app.state.oauth_state_store


def get_album_content(request: Request) -> AlbumContent:
    return request.app.state.album_content


def get_drive_uow(session_factory: SessionFactoryDep) -> DriveExportUnitOfWork:
    return SqlAlchemyDriveExportUnitOfWork(session_factory)


DriveUowDep = Annotated[DriveExportUnitOfWork, Depends(get_drive_uow)]
AlbumContentDep = Annotated[AlbumContent, Depends(get_album_content)]
GoogleOAuthDep = Annotated[GoogleOAuth, Depends(get_google_oauth)]
GoogleDriveDep = Annotated[GoogleDrive, Depends(get_google_drive)]
OAuthStateStoreDep = Annotated[OAuthStateStore, Depends(get_oauth_state_store)]


def get_export_scheduler(
    background_tasks: BackgroundTasks,
    session_factory: SessionFactoryDep,
    album: AlbumContentDep,
    oauth: GoogleOAuthDep,
    drive: GoogleDriveDep,
    settings: SettingsDep,
) -> ExportScheduler:
    def build_run_export() -> RunExport:
        # 背景任務用自己的 UnitOfWork:請求的 session 在回應送出後就關了
        return RunExport(
            SqlAlchemyDriveExportUnitOfWork(session_factory),
            album,
            oauth,
            drive,
            folder_name=settings.drive_folder_name,
        )

    return BackgroundTaskExportScheduler(background_tasks, build_run_export)


def get_start_authorization(
    oauth: GoogleOAuthDep, states: OAuthStateStoreDep
) -> StartAuthorization:
    return StartAuthorization(oauth, states)


def get_complete_authorization(
    uow: DriveUowDep,
    oauth: GoogleOAuthDep,
    states: OAuthStateStoreDep,
    clock: ClockDep,
    ids: IdGeneratorDep,
) -> CompleteAuthorization:
    return CompleteAuthorization(uow, oauth, states, clock, ids)


def get_request_export(
    uow: DriveUowDep,
    album: AlbumContentDep,
    scheduler: Annotated[ExportScheduler, Depends(get_export_scheduler)],
    settings: SettingsDep,
) -> RequestExport:
    return RequestExport(uow, album, scheduler, batch_limit=settings.export_batch_limit)


StartAuthorizationDep = Annotated[StartAuthorization, Depends(get_start_authorization)]
CompleteAuthorizationDep = Annotated[CompleteAuthorization, Depends(get_complete_authorization)]
RequestExportDep = Annotated[RequestExport, Depends(get_request_export)]
