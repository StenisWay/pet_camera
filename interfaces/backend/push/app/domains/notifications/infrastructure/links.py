"""把 DeepLinkTarget 轉成各平台的網址。

App:petcamera://devices/{device_id}(screens/app/02:推播 deep link 導向攝影機畫面)
Web:{web_base_url}/dashboard/devices/{device_id}(screens/web/02、web/04 的路由)
首發通知另帶 ?event_id=,讓攝影機畫面直接播放該事件;合併通知不帶(審查 #14)。
"""

from urllib.parse import urlencode

from app.core.config import Settings
from app.domains.notifications.application.ports import Channel
from app.domains.notifications.domain.model import DeepLinkTarget


def deep_link(channel: Channel, target: DeepLinkTarget, settings: Settings) -> str:
    if channel is Channel.WEB:
        base = f"{settings.web_base_url.rstrip('/')}/dashboard/devices/{target.device_id}"
    else:
        base = f"{settings.deep_link_base.rstrip('/')}/{target.device_id}"
    if target.event_id is None:
        return base
    return f"{base}?{urlencode({'event_id': str(target.event_id)})}"
