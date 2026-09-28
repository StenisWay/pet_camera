"""MediaStorage 的 R2 實作(01_資料模型與儲存規格.md 第 3 節)。

Postgres 只放 metadata,二進位內容一律進 R2;下載走效期 10 分鐘的 presigned URL
(第 3.3 節),不把 bucket 對外開放。
"""

import aioboto3

from app.core.config import Settings
from app.domains.media.application.ports import MediaStorage


class R2MediaStorage(MediaStorage):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._session = aioboto3.Session()

    def _client(self):
        return self._session.client(
            "s3",
            endpoint_url=self.settings.r2_endpoint_url,
            aws_access_key_id=self.settings.r2_access_key_id,
            aws_secret_access_key=self.settings.r2_secret_access_key,
        )

    async def put_image(self, object_key: str, content: bytes) -> None:
        async with self._client() as client:
            await client.put_object(
                Bucket=self.settings.r2_bucket,
                Key=object_key,
                Body=content,
                ContentType="image/jpeg",
            )

    async def presigned_url(self, object_key: str) -> str:
        async with self._client() as client:
            return await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.settings.r2_bucket, "Key": object_key},
                ExpiresIn=self.settings.presigned_url_ttl_seconds,
            )
