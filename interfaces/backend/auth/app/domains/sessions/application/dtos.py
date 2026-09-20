"""sessions 的輸入輸出 DTO。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SessionTokens:
    """簽發結果。refresh_token 是**明碼**,只在這一刻存在,之後只剩指紋。"""

    access_token: str
    # App 平台為 None(02_spec 第 2.3 節)
    refresh_token: str | None
