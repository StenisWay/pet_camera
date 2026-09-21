"""drive_export 的測試替身。全部明確繼承正式介面。"""

import copy
import uuid
from types import TracebackType
from typing import Self
from urllib.parse import urlencode

from app.domains.drive_export.application.dtos import ExportJob
from app.domains.drive_export.application.ports import (
    AlbumContent,
    DriveExportUnitOfWork,
    ExportableMedia,
    ExportScheduler,
    GoogleDrive,
    GoogleOAuth,
    OAuthStateStore,
    OAuthTokens,
    PreparedExport,
)
from app.domains.drive_export.domain.entities import DRIVE_FILE_SCOPE, DriveConnection
from app.domains.drive_export.domain.exceptions import (
    DriveAuthorizationExpired,
    DriveExportFailed,
)
from app.domains.drive_export.domain.repositories import DriveConnectionRepository


class FakeDriveConnectionRepository(DriveConnectionRepository):
    def __init__(self) -> None:
        self.committed: dict[uuid.UUID, DriveConnection] = {}
        self.pending: dict[uuid.UUID, DriveConnection] = {}
        self.deleted: set[uuid.UUID] = set()

    def _visible(self) -> dict[uuid.UUID, DriveConnection]:
        merged = {**self.committed, **self.pending}
        return {k: v for k, v in merged.items() if k not in self.deleted}

    async def get_by_owner(self, owner_id: uuid.UUID) -> DriveConnection | None:
        return copy.deepcopy(self._visible().get(owner_id))

    async def save(self, connection: DriveConnection) -> None:
        self.pending[connection.owner_id] = copy.deepcopy(connection)
        self.deleted.discard(connection.owner_id)

    async def delete_by_owner(self, owner_id: uuid.UUID) -> None:
        self.deleted.add(owner_id)


class FakeDriveExportUnitOfWork(DriveExportUnitOfWork):
    def __init__(self) -> None:
        self.connections = FakeDriveConnectionRepository()
        self.commit_count = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.connections.pending.clear()
        self.connections.deleted.clear()

    async def commit(self) -> None:
        self.connections.committed.update(self.connections.pending)
        for owner_id in self.connections.deleted:
            self.connections.committed.pop(owner_id, None)
        self.connections.pending.clear()
        self.connections.deleted.clear()
        self.commit_count += 1

    def given(self, connection: DriveConnection) -> DriveConnection:
        self.connections.committed[connection.owner_id] = copy.deepcopy(connection)
        return connection


class FakeGoogleOAuth(GoogleOAuth):
    def __init__(self) -> None:
        self.codes: dict[str, OAuthTokens] = {}
        self.revoked_refresh_tokens: set[str] = set()

    def authorization_url(self, *, state: str) -> str:
        query = urlencode({"scope": DRIVE_FILE_SCOPE, "state": state, "response_type": "code"})
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"

    async def exchange_code(self, code: str) -> OAuthTokens:
        if code not in self.codes:
            raise DriveAuthorizationExpired()
        return self.codes[code]

    async def refresh_access_token(self, refresh_token: str) -> str:
        if refresh_token in self.revoked_refresh_tokens:
            raise DriveAuthorizationExpired()
        return f"access-for-{refresh_token}"


class FakeGoogleDrive(GoogleDrive):
    def __init__(self) -> None:
        self.folders: dict[str, str] = {}
        self.uploads: list[dict[str, object]] = []
        self.quota_exceeded = False
        self.ensure_folder_calls = 0
        self._n = 0

    async def ensure_folder(self, *, access_token: str, name: str) -> str:
        self.ensure_folder_calls += 1
        if name not in self.folders:
            self._n += 1
            self.folders[name] = f"folder-{self._n}"
        return self.folders[name]

    async def upload_file(
        self,
        *,
        access_token: str,
        folder_id: str,
        filename: str,
        content: bytes,
        mime_type: str,
    ) -> str:
        if self.quota_exceeded:
            raise DriveExportFailed("Google Drive 額度不足")
        self._n += 1
        file_id = f"file-{self._n}"
        self.uploads.append(
            {
                "file_id": file_id,
                "folder_id": folder_id,
                "filename": filename,
                "mime_type": mime_type,
                "size": len(content),
            }
        )
        return file_id


class InMemoryOAuthStateStore(OAuthStateStore):
    def __init__(self) -> None:
        self.states: dict[str, uuid.UUID] = {}
        self.ttls: dict[str, int] = {}
        self.available = True

    async def issue(self, state: str, owner_id: uuid.UUID, *, ttl_seconds: int) -> None:
        if not self.available:
            raise ConnectionError("redis unreachable")
        self.states[state] = owner_id
        self.ttls[state] = ttl_seconds

    async def consume(self, state: str) -> uuid.UUID | None:
        if not self.available:
            raise ConnectionError("redis unreachable")
        return self.states.pop(state, None)


class CollectingExportScheduler(ExportScheduler):
    """把背景任務記下來,測試自行決定何時執行。"""

    def __init__(self) -> None:
        self.jobs: list[ExportJob] = []

    def schedule(self, job: ExportJob) -> None:
        self.jobs.append(job)


class FakeAlbumContent(AlbumContent):
    """album 領域的替身,讓 drive_export 的測試完全不碰相簿的資料。"""

    def __init__(self) -> None:
        self.prepared = PreparedExport(accepted=[], skipped_ids=[])
        self.prepare_error: Exception | None = None
        self.objects: dict[str, bytes] = {}
        self.completed: dict[uuid.UUID, str] = {}
        self.failed: list[uuid.UUID] = []
        self.missing_items: set[uuid.UUID] = set()

    def will_prepare(self, *media: ExportableMedia) -> None:
        self.prepared = PreparedExport(accepted=list(media), skipped_ids=[])

    async def prepare_export(
        self, owner_id: uuid.UUID, item_ids: list[uuid.UUID]
    ) -> PreparedExport:
        if self.prepare_error:
            raise self.prepare_error
        return self.prepared

    async def complete_export(self, item_id: uuid.UUID, *, drive_file_id: str) -> None:
        self.completed[item_id] = drive_file_id

    async def fail_export(self, item_id: uuid.UUID) -> None:
        if item_id in self.missing_items:
            raise LookupError(item_id)
        self.failed.append(item_id)

    async def read_object(self, object_key: str) -> bytes:
        return self.objects.get(object_key, b"binary-content")
