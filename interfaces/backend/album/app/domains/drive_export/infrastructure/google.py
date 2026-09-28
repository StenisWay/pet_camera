"""GoogleOAuth 與 GoogleDrive 的 HTTP 實作(12_spec 第 2.3 節)。

只申請 drive.file scope,因此只看得到本 App 自己建立的檔案,碰不到使用者既有的
雲端硬碟內容——這是規格明文要求的最小權限。
"""

import json
from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.domains.drive_export.application.ports import GoogleDrive, GoogleOAuth, OAuthTokens
from app.domains.drive_export.domain.entities import DRIVE_FILE_SCOPE
from app.domains.drive_export.domain.exceptions import (
    DriveAuthorizationExpired,
    DriveExportFailed,
)

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
DRIVE_FILES_ENDPOINT = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_ENDPOINT = "https://www.googleapis.com/upload/drive/v3/files"
REQUEST_TIMEOUT_SECONDS = 30.0
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


class HttpGoogleOAuth(GoogleOAuth):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def authorization_url(self, *, state: str) -> str:
        params = {
            "client_id": self._settings.google_client_id,
            "redirect_uri": self._settings.google_redirect_uri,
            "response_type": "code",
            "scope": DRIVE_FILE_SCOPE,
            "state": state,
            # 要拿得到 refresh token 就必須帶這兩個;consent 確保重新授權時仍會回傳
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{AUTH_ENDPOINT}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> OAuthTokens:
        payload = await self._token_request(
            {
                "code": code,
                "redirect_uri": self._settings.google_redirect_uri,
                "grant_type": "authorization_code",
            }
        )
        return OAuthTokens(
            access_token=payload["access_token"], refresh_token=payload.get("refresh_token")
        )

    async def refresh_access_token(self, refresh_token: str) -> str:
        payload = await self._token_request(
            {"refresh_token": refresh_token, "grant_type": "refresh_token"}
        )
        return payload["access_token"]

    async def _token_request(self, data: dict[str, str]) -> dict:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                TOKEN_ENDPOINT,
                data={
                    **data,
                    "client_id": self._settings.google_client_id,
                    "client_secret": self._settings.google_client_secret,
                },
            )
        if response.status_code >= 400:
            # invalid_grant = 授權碼已使用,或 refresh token 被撤銷/過期 → DRIVE_003
            raise DriveAuthorizationExpired()
        return response.json()


class HttpGoogleDrive(GoogleDrive):
    async def ensure_folder(self, *, access_token: str, name: str) -> str:
        headers = {"Authorization": f"Bearer {access_token}"}
        query = f"name = '{name}' and mimeType = '{FOLDER_MIME_TYPE}' and trashed = false"
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            # drive.file scope 下只看得到自己建立的檔案,所以這個查詢不會撞到
            # 使用者原本就有的同名資料夾
            found = await client.get(
                DRIVE_FILES_ENDPOINT,
                headers=headers,
                params={"q": query, "fields": "files(id)", "pageSize": 1},
            )
            _raise_for_status(found)
            files = found.json().get("files", [])
            if files:
                return str(files[0]["id"])

            created = await client.post(
                DRIVE_FILES_ENDPOINT,
                headers=headers,
                json={"name": name, "mimeType": FOLDER_MIME_TYPE},
            )
        _raise_for_status(created)
        return str(created.json()["id"])

    async def upload_file(
        self,
        *,
        access_token: str,
        folder_id: str,
        filename: str,
        content: bytes,
        mime_type: str,
    ) -> str:
        metadata = {"name": filename, "parents": [folder_id]}
        files: dict[str, tuple[str, bytes | str, str]] = {
            "metadata": ("metadata", json.dumps(metadata), "application/json; charset=UTF-8"),
            "file": (filename, content, mime_type),
        }
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                DRIVE_UPLOAD_ENDPOINT,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"uploadType": "multipart", "fields": "id"},
                files=files,
            )
        _raise_for_status(response)
        return str(response.json()["id"])


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise DriveAuthorizationExpired()
    if response.status_code >= 400:
        # 403 storageQuotaExceeded 等一律收斂成 DRIVE_002
        raise DriveExportFailed()
