"""配對碼值物件(規格審查 #4)。

規格書(03_spec 第 2.1 節)只寫了「取得配對碼,有效期 10 分鐘」,沒有定義格式。
審查結論採 8 碼 Crockford Base32:

- 排除 I、L、O、U 四個字母。前三個與 1、0 在多數字體下難以分辨,使用者會照著鏡頭畫面
  逐字抄進手機;U 排除是 Crockford 的原始理由(避免拼出不雅字)。
- 32^8 ≈ 1.1 兆組。全站同時有效的配對碼只有個位數,亂猜命中的機率約 1e-11,
  暴力破解不可行——這才是主要防線,對呼叫端的限流是第二層。
- 比對時大小寫不敏感,並把使用者誤打的 I/L 視為 1、O 視為 0,容許輸入夾帶連字號或空白。
  這是 Crockford Base32 的標準解碼規則,能明顯降低手動輸入的失敗率。
"""

from dataclasses import dataclass
from datetime import datetime

CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# 解碼時的等價字元:使用者看到 1 可能打成 I 或 L,看到 0 可能打成 O
_AMBIGUOUS = str.maketrans({"I": "1", "L": "1", "O": "0"})
_SEPARATORS = str.maketrans({"-": None, " ": None, "\t": None})

CODE_LENGTH = 8


class InvalidPairingCodeFormat(ValueError):
    """配對碼格式不符(長度錯誤或含字母表以外的字元)。"""


def normalize(typed: str) -> str:
    """把使用者輸入正規化成標準形式,供比對使用。

    大寫化 → 去掉連字號與空白 → I/L 轉 1、O 轉 0。
    不驗證結果是否合法:比對不上就是比對不上,不該對輸入拋例外。
    """
    return typed.upper().translate(_SEPARATORS).translate(_AMBIGUOUS)


@dataclass(frozen=True)
class PairingCode:
    """一組尚未使用的配對碼與它的到期時間。

    兩個欄位同時存在或同時不存在(01_資料模型 第 2.2 節),所以綁成一個值物件,
    避免出現「有碼沒效期」或「有效期沒碼」的半套狀態。
    """

    code: str
    expires_at: datetime

    def __post_init__(self) -> None:
        if len(self.code) != CODE_LENGTH:
            raise InvalidPairingCodeFormat(
                f"配對碼須為 {CODE_LENGTH} 碼,收到 {len(self.code)} 碼"
            )
        if any(char not in CROCKFORD_ALPHABET for char in self.code):
            raise InvalidPairingCodeFormat(f"配對碼含字母表以外的字元:{self.code}")

    def is_expired(self, now: datetime) -> bool:
        """到期時間當下即視為過期(不含等號那一瞬間仍有效)。"""
        return now >= self.expires_at

    def equals(self, typed: str) -> bool:
        """輸入正規化後是否等於本配對碼,**不看有效期**。

        呼叫端要能區分「碼打錯」(DEVICE_002)與「碼對但過期」(DEVICE_001),
        這兩者的使用者復原路徑不同,所以比對與到期要分開問。
        """
        return normalize(typed) == self.code

    def matches(self, typed: str, *, now: datetime) -> bool:
        """輸入是否等於本配對碼,且尚未過期。輸入再怎麼亂都只回傳 False,不拋例外。"""
        return self.equals(typed) and not self.is_expired(now)
