"""用戶端平台。

放 shared_kernel 而不是某個領域:平台差異貫穿整個系統——token 機制(sessions)、
登入請求參數(accounts)、推播端點(push_tokens 表),不屬於其中任何一個。
對外契約 interfaces/backend/auth/__init__.py 的 Platform 是同一個值域。
"""

from enum import Enum


class Platform(str, Enum):
    APP = "app"
    WEB = "web"

    @property
    def uses_refresh_token(self) -> bool:
        """02_spec 第 2.3 節:只有 Web 簽發 refresh token,App 靠滑動展延。"""
        return self is Platform.WEB
