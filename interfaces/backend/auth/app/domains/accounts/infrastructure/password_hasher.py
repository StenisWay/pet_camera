"""bcrypt 密碼雜湊(01_資料模型 第 2.1 節:bcrypt/argon2)。

RawPassword 已經保證了「至多 72 bytes、只含可列印 ASCII」(02_spec 第 2.1 節),
所以這裡不必再處理 bcrypt 的截斷行為——那正是把長度上限寫進值物件的理由:
bcrypt 對超長輸入是**安靜截斷**,不是報錯,放任它會讓兩個不同的長密碼互相通過。
"""

import bcrypt

from app.domains.accounts.domain.services import PasswordHasher
from app.domains.accounts.domain.value_objects import RawPassword


class BcryptPasswordHasher(PasswordHasher):
    def __init__(self, *, rounds: int = 12) -> None:
        self._rounds = rounds

    def hash(self, raw: RawPassword) -> str:
        return bcrypt.hashpw(
            raw.value.encode(), bcrypt.gensalt(rounds=self._rounds)
        ).decode()

    def verify(self, raw: RawPassword, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(raw.value.encode(), password_hash.encode())
        except ValueError:
            # 雜湊字串格式不合法(資料損毀、手動塞過資料):合約說回 False,不拋例外
            return False
