"""R2 key 命名規則(01_資料模型與儲存規格.md 第 3.1 節)。

media_items 的 key 以 user_id 分層,與依 device_id 分層的事件影片區隔——
移除裝置會清掉 videos/ 底下的物件,相簿內容不該被連帶掃到(資料模型第 6 節)。
"""

from datetime import UTC, datetime

from app.domains.media.domain.entities import MediaItemType
from app.domains.media.domain.object_keys import content_key, thumbnail_key
from tests.domains.media.builders import ITEM, OWNER, an_item


def test_photo_content_key_follows_the_spec_layout():
    item = an_item(type=MediaItemType.PHOTO, captured_at=datetime(2026, 9, 20, 10, 0, tzinfo=UTC))

    assert content_key(item) == f"media/{OWNER}/2026/09/20/{ITEM}.jpg"


def test_clip_content_key_uses_the_video_extension():
    item = an_item(type=MediaItemType.CLIP, captured_at=datetime(2026, 1, 5, 10, 0, tzinfo=UTC))

    assert content_key(item) == f"media/{OWNER}/2026/01/05/{ITEM}.mp4"


def test_thumbnail_key_uses_its_own_prefix():
    item = an_item(type=MediaItemType.CLIP, captured_at=datetime(2026, 9, 20, 10, 0, tzinfo=UTC))

    assert thumbnail_key(item) == f"media-thumbnails/{OWNER}/2026/09/20/{ITEM}.jpg"


def test_key_date_comes_from_captured_at_not_write_time():
    """審查 #11 的延伸:三天前事件剪出的片段,key 要落在事件當天的資料夾。"""
    item = an_item(type=MediaItemType.CLIP, captured_at=datetime(2026, 9, 17, 23, 30, tzinfo=UTC))

    assert "/2026/09/17/" in content_key(item)
