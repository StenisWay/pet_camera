"""R2 物件 key 的命名規則(01_資料模型與儲存規格.md 第 3.1 節)。

    media/{user_id}/{yyyy}/{mm}/{dd}/{media_item_id}.{mp4|jpg}
    media-thumbnails/{user_id}/{yyyy}/{mm}/{dd}/{media_item_id}.jpg

放在 domain 而不是 infrastructure:這是規格書定義的、與儲存技術無關的命名約定
(換掉 R2 換成別的物件儲存,key 形狀不變),而且它是純函式,測起來最便宜。

日期取 captured_at(UTC),與相簿的日期分組一致(12_spec 第 2.1 節)——用寫入時間
會讓同一個事件剪出的片段落在不同資料夾。
"""

from app.domains.media.domain.entities import MediaItem, MediaItemType

CONTENT_PREFIX = "media"
THUMBNAIL_PREFIX = "media-thumbnails"
EXTENSION_BY_TYPE = {MediaItemType.PHOTO: "jpg", MediaItemType.CLIP: "mp4"}


def _date_path(item: MediaItem) -> str:
    return item.captured_at.strftime("%Y/%m/%d")


def content_key(item: MediaItem) -> str:
    extension = EXTENSION_BY_TYPE[item.type]
    return f"{CONTENT_PREFIX}/{item.owner_id}/{_date_path(item)}/{item.id}.{extension}"


def thumbnail_key(item: MediaItem) -> str:
    return f"{THUMBNAIL_PREFIX}/{item.owner_id}/{_date_path(item)}/{item.id}.jpg"
