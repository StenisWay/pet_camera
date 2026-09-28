"""ThumbnailLinks 的 Cloudflare R2 實作。

通知夾帶的縮圖連結效期 30 分鐘,不是點播時的 10 分鐘(09_spec 第 2.2 節,審查 #6;
01_資料模型與儲存規格.md 第 3.3 節的例外條款)。R2 相容 S3 API;presign 是本機計算,不連線。
"""

import aioboto3

from app.core.config import Settings
from app.domains.notifications.application.ports import ThumbnailLinks


class R2ThumbnailLinks(ThumbnailLinks):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session = aioboto3.Session()

    async def presign(self, object_key: str) -> str:
        async with self._session.client(
            "s3",
            endpoint_url=self._settings.r2_endpoint_url or None,
            aws_access_key_id=self._settings.r2_access_key_id,
            aws_secret_access_key=self._settings.r2_secret_access_key,
            region_name="auto",
        ) as client:
            return await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._settings.r2_bucket, "Key": object_key},
                ExpiresIn=self._settings.thumbnail_url_ttl_seconds,
            )
