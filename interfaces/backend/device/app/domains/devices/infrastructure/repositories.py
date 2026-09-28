"""DeviceRepository 的 SQLAlchemy 實作。

只 flush 不 commit——交易邊界由 UnitOfWork 負責,use case 決定範圍。
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.devices.domain.entities import Device
from app.domains.devices.domain.pairing_code import normalize
from app.domains.devices.domain.repositories import DeviceRepository
from app.domains.devices.infrastructure.mappers import apply_to_row, to_entity, to_new_row
from app.domains.devices.infrastructure.orm import DeviceRow


class SqlAlchemyDeviceRepository(DeviceRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _row(self, device_id: uuid.UUID) -> DeviceRow | None:
        return await self.session.get(DeviceRow, device_id)

    async def get(self, device_id: uuid.UUID) -> Device | None:
        row = await self._row(device_id)
        return to_entity(row) if row else None

    async def get_by_hardware_id(self, hardware_id: str) -> Device | None:
        row = await self.session.scalar(
            select(DeviceRow).where(DeviceRow.hardware_id == hardware_id)
        )
        return to_entity(row) if row else None

    async def get_by_pairing_code(self, pairing_code: str) -> Device | None:
        # 先正規化再查:使用者會打小寫、加連字號,也可能把 1 打成 I(審查 #4)
        #
        # with_for_update():審查 #10 的併發承諾。兩個使用者同時輸入同一組碼時,
        # 第二個交易會卡在這裡等第一個結束,再讀到的就是已經 paired 的狀態
        # (pairing_code 已清空 → 查不到 → DEVICE_002)。沒有這個鎖,兩邊都會
        # 讀到 pending 然後依序寫入,後者靜悄悄覆蓋前者的 user_id。
        # 查無資料時不鎖任何東西,所以對產碼時的碰撞檢查沒有副作用。
        row = await self.session.scalar(
            select(DeviceRow)
            .where(DeviceRow.pairing_code == normalize(pairing_code))
            .with_for_update()
        )
        return to_entity(row) if row else None

    async def list_by_user(self, user_id: uuid.UUID) -> list[Device]:
        rows = await self.session.scalars(
            select(DeviceRow)
            .where(DeviceRow.user_id == user_id)
            # 審查 #13:排序必須固定,id 決勝避免 created_at 相同時順序不穩
            .order_by(DeviceRow.created_at, DeviceRow.id)
        )
        return [to_entity(row) for row in rows]

    async def count_by_user(self, user_id: uuid.UUID) -> int:
        total = await self.session.scalar(
            select(func.count()).select_from(DeviceRow).where(DeviceRow.user_id == user_id)
        )
        return int(total or 0)

    async def save(self, device: Device) -> None:
        row = await self._row(device.id)
        if row is None:
            self.session.add(to_new_row(device))
        else:
            apply_to_row(device, row)
        await self.session.flush()
