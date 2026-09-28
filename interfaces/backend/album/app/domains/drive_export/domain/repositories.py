import uuid
from abc import ABC, abstractmethod

from app.domains.drive_export.domain.entities import DriveConnection


class DriveConnectionRepository(ABC):
    @abstractmethod
    async def get_by_owner(self, owner_id: uuid.UUID) -> DriveConnection | None:
        """取回該使用者的 Drive 連結;未連結時回傳 None。

        回傳的是新的實體物件,修改後必須 save 才會保存。
        """

    @abstractmethod
    async def save(self, connection: DriveConnection) -> None:
        """新增或更新連結。一個使用者最多一份,實際寫入在 UnitOfWork.commit() 時生效。"""

    @abstractmethod
    async def delete_by_owner(self, owner_id: uuid.UUID) -> None:
        """授權失效(DRIVE_003)或刪除帳號時清除;不存在時不視為錯誤。"""
