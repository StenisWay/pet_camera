"""MediaObjectStorage 的 Cloudflare R2 實作。

key 命名規則見 01_資料模型與儲存規格.md 第 3.1 節;下載一律用效期 10 分鐘的
presigned URL(同文件第 3.3 節)。R2 相容 S3 API,直接用 aioboto3。
"""

import aioboto3

from app.core.config import Settings
from app.domains.album.application.ports import MediaObjectStorage


class R2ObjectStorage(MediaObjectStorage):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session = aioboto3.Session()

    def _client(self):
        return self._session.client(
            "s3",
            endpoint_url=self._settings.r2_endpoint_url,
            aws_access_key_id=self._settings.r2_access_key_id,
            aws_secret_access_key=self._settings.r2_secret_access_key,
            region_name="auto",
        )

    async def download(self, object_key: str) -> bytes:
        async with self._client() as client:
            response = await client.get_object(Bucket=self._settings.r2_bucket, Key=object_key)
            return await response["Body"].read()

    async def delete(self, object_key: str) -> None:
        async with self._client() as client:
            # S3 的 delete_object 對不存在的 key 本來就回成功,符合介面承諾
            await client.delete_object(Bucket=self._settings.r2_bucket, Key=object_key)

    async def presigned_url(self, object_key: str) -> str:
        async with self._client() as client:
            return await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._settings.r2_bucket, "Key": object_key},
                ExpiresIn=self._settings.presigned_url_ttl_seconds,
            )
