"""accounts 的 repository 介面。

介面在 domain、實作在外層,依賴方向因此永遠指向內層。
以**聚合**為單位(整個 User),不做泛用 CRUD——`update(id, **fields)` 這種方法
會讓呼叫端繞過實體的業務規則直接改狀態。

一律用 ABC 而不是 Protocol:實作類別明確繼承,漏實作抽象方法時建立實例當下就
TypeError,而不是等執行到那一行。(跨服務的對外契約 interfaces/backend/auth/__init__.py
用 Protocol,那是給別的服務讀的描述,不是給本服務實作的合約。)
"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime

from app.domains.accounts.domain.entities import PasswordResetToken, User
from app.domains.accounts.domain.value_objects import Email


class UserRepository(ABC):
    @abstractmethod
    async def get(self, user_id: uuid.UUID) -> User | None:
        """取回使用者;不存在時回 None。

        回傳的是新的實體物件,對它的修改必須 save() 才會保存。
        """

    @abstractmethod
    async def get_by_email(self, email: Email) -> User | None:
        """email 已由 Email 值物件保證正規化為小寫;不存在時回 None。"""

    @abstractmethod
    async def add(self, user: User) -> None:
        """新增使用者。email 已存在時拋 EmailAlreadyRegistered——唯一性由約束保證,
        不是先查再寫(§2.2 的競態)。實際寫入在 commit() 時生效。"""

    @abstractmethod
    async def save(self, user: User) -> None:
        """更新既有使用者的可變欄位(password_hash、失敗計數、鎖定時間)。
        實際寫入在 commit() 時生效。"""

    @abstractmethod
    async def delete(self, user_id: uuid.UUID) -> None:
        """刪除使用者。本服務的三張子表由外鍵 ON DELETE CASCADE 一併帶走;
        跨服務的清除(Device、Album)必須在呼叫本方法**之前**已經成功。"""


class PasswordResetTokenRepository(ABC):
    @abstractmethod
    async def get_by_fingerprint(self, fingerprint: str) -> PasswordResetToken | None:
        """以雜湊值查詢;不存在時回 None。明碼只存在於寄出的連結裡。"""

    @abstractmethod
    async def add(self, token: PasswordResetToken) -> None:
        """實際寫入在 commit() 時生效。"""

    @abstractmethod
    async def mark_used(self, token_id: uuid.UUID, *, used_at: datetime) -> bool:
        """標記為已使用,回傳「本次呼叫是否真的完成標記」。

        同一個連結被點兩次、或兩個請求同時進來時,只有一次能回 True;
        False 的一方一律視為連結已失效(AUTH_007)。
        """
