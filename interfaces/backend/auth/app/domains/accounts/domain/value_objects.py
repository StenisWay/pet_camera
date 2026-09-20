"""accounts 領域的值物件。純 Python,不依賴框架。"""

import re
from dataclasses import dataclass

from app.domains.accounts.domain.exceptions import InvalidEmail, WeakPassword

# 02_spec 第 2.1 節:本地部分@網域,長度上限 254 字元。
# 刻意不做 RFC 5322 全集——真正的驗證是寄得到信,這裡只擋明顯打錯的輸入。
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EMAIL_MAX_LENGTH = 254


@dataclass(frozen=True)
class Email:
    """登入帳號。一律以小寫、去頭尾空白的形式存在。

    只用 parse() 建立,不直接呼叫建構子——否則就會出現未正規化的 Email 實例,
    正規化保證就失效了(02_spec 第 2.1 節「Email 正規化」)。
    """

    value: str

    @classmethod
    def parse(cls, raw: str) -> "Email":
        normalized = raw.strip().lower()
        if len(normalized) > EMAIL_MAX_LENGTH:
            raise InvalidEmail()
        if not EMAIL_PATTERN.match(normalized):
            raise InvalidEmail()
        return cls(normalized)


# 02_spec 第 2.1 節:至少 8 碼、至多 72 bytes(bcrypt 上限),需含英文字母與數字,
# 且只允許可列印 ASCII(U+0020~U+007E)。
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_BYTES = 72


@dataclass(frozen=True, repr=False)
class RawPassword:
    """使用者輸入的密碼明碼,已通過強度檢查但尚未雜湊。

    只在 use case 內短暫存在,雜湊後就該被丟棄。repr 刻意不顯示內容——
    一行 log 或一個例外堆疊就足以把明碼寫進檔案。
    """

    value: str

    def __repr__(self) -> str:
        return "RawPassword(***)"

    @classmethod
    def parse(cls, raw: str) -> "RawPassword":
        if len(raw) < PASSWORD_MIN_LENGTH:
            raise WeakPassword()
        if len(raw.encode()) > PASSWORD_MAX_BYTES:
            raise WeakPassword()
        if not all("\x20" <= ch <= "\x7e" for ch in raw):
            raise WeakPassword()
        if not any(ch.isascii() and ch.isalpha() for ch in raw):
            raise WeakPassword()
        if not any(ch.isascii() and ch.isdigit() for ch in raw):
            raise WeakPassword()
        return cls(raw)
