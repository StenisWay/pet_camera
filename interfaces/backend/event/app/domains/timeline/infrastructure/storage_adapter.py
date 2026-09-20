"""MediaUrlIssuer 接到 Cloudflare R2(S3 相容 API)。"""

import aioboto3

from app.core.config import Settings
from app.domains.timeline.application.ports import MediaUrlIssuer


class R2MediaUrlIssuer(MediaUrlIssuer):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._session = aioboto3.Session()

    async def presigned_url(self, object_key: str) -> str:
        """有效期 10 分鐘(08_spec 第 2.2 節、01_資料模型第 3.3 節)。

        S3 相容的簽章無法做到一次性——URL 在有效期內可重複使用。這是簽章機制的性質,
        不是實作選擇,所以規格上的承諾是「短效」而不是「一次性」。
        """
        async with self._session.client(
            "s3",
            endpoint_url=self.settings.r2_endpoint_url,
            aws_access_key_id=self.settings.r2_access_key_id,
            aws_secret_access_key=self.settings.r2_secret_access_key,
        ) as client:
            return await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.settings.r2_bucket, "Key": object_key},
                ExpiresIn=self.settings.presigned_url_ttl_seconds,
            )
