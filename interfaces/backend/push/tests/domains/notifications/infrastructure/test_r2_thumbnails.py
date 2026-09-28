from urllib.parse import parse_qs, urlparse

from app.core.config import Settings
from app.domains.notifications.infrastructure.r2_thumbnails import R2ThumbnailLinks
from tests.domains.notifications.builders import THUMBNAIL_KEY


async def test_presigned_url_lives_30_minutes():
    """審查 #6:推播經 APNs/FCM 可能延遲或重送,10 分鐘內未送達就會圖裂。
    簽章是本機計算,不連 R2。"""
    settings = Settings(
        r2_endpoint_url="https://account.r2.example.test",
        r2_access_key_id="id",
        r2_secret_access_key="secret",
    )

    url = await R2ThumbnailLinks(settings).presign(THUMBNAIL_KEY)

    query = parse_qs(urlparse(url).query)
    assert query["X-Amz-Expires"] == ["1800"]
    assert THUMBNAIL_KEY in url
