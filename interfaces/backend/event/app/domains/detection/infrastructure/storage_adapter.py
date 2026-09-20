"""MediaUploader 接到 Cloudflare R2(S3 相容 API)。"""

import aioboto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings
from app.domains.detection.application.ports import MediaUploader
from app.domains.detection.domain.exceptions import UploadFailed


class R2MediaUploader(MediaUploader):
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

    async def upload(self, key: str, data: bytes, *, content_type: str) -> None:
        """失敗一律轉成 UploadFailed,重試策略由 use case 決定(07_spec 第 3 節)。"""
        try:
            async with self._client() as client:
                await client.put_object(
                    Bucket=self.settings.r2_bucket,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                )
        except (ClientError, BotoCoreError, OSError) as exc:
            raise UploadFailed() from exc

    async def delete_many(self, keys: list[str]) -> None:
        """刪除多個物件;不存在的 key 不視為錯誤(S3 的 delete 本來就是冪等的)。"""
        if not keys:
            return
        async with self._client() as client:
            await client.delete_objects(
                Bucket=self.settings.r2_bucket,
                Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
            )
