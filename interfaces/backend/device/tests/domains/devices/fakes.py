"""測試替身。

fake 而不是 mock:fake 有真實行為,測試讀起來像業務描述,也不會綁死「呼叫了幾次、
參數順序如何」這種實作細節。fake 必須模擬持久化與交易語意,否則抓不到
「忘了 save」「忘了 commit」——這兩個錯誤正是 UnitOfWork 要防的。

fake 與 SQLAlchemy 實作共用同一份合約測試,證明兩者行為一致。
"""

import copy
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Self

from app.domains.devices.application.ports import (
    DeviceSecrets,
    DevicesUnitOfWork,
    EventCleanup,
    PairingCodeFactory,
)
from app.domains.devices.domain.entities import Device
from app.domains.devices.domain.exceptions import EventCleanupFailed
from app.domains.devices.domain.pairing_code import PairingCode, normalize
from app.domains.devices.domain.repositories import DeviceRepository
from app.shared_kernel.ports import Clock, IdGenerator


class FakeDeviceRepository(DeviceRepository):
    def __init__(self) -> None:
        self.committed: dict[uuid.UUID, Device] = {}
        self.pending: dict[uuid.UUID, Device] = {}

    def _visible(self) -> dict[uuid.UUID, Device]:
        """交易內看得到自己未提交的寫入(read-your-writes)。"""
        return {**self.committed, **self.pending}

    async def get(self, device_id: uuid.UUID) -> Device | None:
        found = self._visible().get(device_id)
        # 回傳複本:忘了 save 的修改就不會被保存,與 SQLAlchemy 實作行為一致
        return copy.deepcopy(found) if found else None

    async def get_by_hardware_id(self, hardware_id: str) -> Device | None:
        for device in self._visible().values():
            if device.hardware_id == hardware_id:
                return copy.deepcopy(device)
        return None

    async def get_by_pairing_code(self, pairing_code: str) -> Device | None:
        wanted = normalize(pairing_code)
        for device in self._visible().values():
            if device.pairing_code is not None and device.pairing_code.code == wanted:
                return copy.deepcopy(device)
        return None

    async def list_by_user(self, user_id: uuid.UUID) -> list[Device]:
        owned = [d for d in self._visible().values() if d.user_id == user_id]
        return [copy.deepcopy(d) for d in sorted(owned, key=lambda d: (d.created_at, d.id))]

    async def count_by_user(self, user_id: uuid.UUID) -> int:
        return sum(1 for d in self._visible().values() if d.user_id == user_id)

    async def save(self, device: Device) -> None:
        self.pending[device.id] = copy.deepcopy(device)


class FakeDevicesUnitOfWork(DevicesUnitOfWork):
    def __init__(self) -> None:
        self.devices = FakeDeviceRepository()
        self.commit_count = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.devices.pending.clear()  # 未 commit 即回滾

    async def commit(self) -> None:
        self.devices.committed.update(self.devices.pending)
        self.devices.pending.clear()
        self.commit_count += 1

    def given(self, device: Device) -> Device:
        """Arrange 用:直接放進「已 commit」的狀態。"""
        self.devices.committed[device.id] = copy.deepcopy(device)
        return device


class FixedClock(Clock):
    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime(2026, 9, 20, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def set(self, now: datetime) -> None:
        self._now = now


class SequentialIds(IdGenerator):
    def __init__(self) -> None:
        self._n = 0

    def new_id(self) -> uuid.UUID:
        self._n += 1
        return uuid.UUID(int=self._n)


class StubPairingCodeFactory(PairingCodeFactory):
    """依序發出預先排好的配對碼,讓測試能斷言「發出的就是這一組」。"""

    def __init__(self, codes: list[str] | None = None, *, ttl_seconds: int = 600) -> None:
        self.codes = codes or ["ABCD1234", "ZZZZ9999", "QQQQ7777"]
        self.ttl_seconds = ttl_seconds
        self.issued = 0

    def new_code(self, now: datetime) -> PairingCode:
        from datetime import timedelta

        code = self.codes[min(self.issued, len(self.codes) - 1)]
        self.issued += 1
        return PairingCode(code=code, expires_at=now + timedelta(seconds=self.ttl_seconds))


class FakeDeviceSecrets(DeviceSecrets):
    """明碼加上固定前綴當作「雜湊」,足以驗證流程有把正確的值傳來傳去。"""

    PREFIX = "hashed:"

    def __init__(self, secret: str = "s3cret") -> None:
        self.secret = secret

    def issue(self) -> tuple[str, str]:
        return self.secret, f"{self.PREFIX}{self.secret}"

    def verify(self, plaintext: str, secret_hash: str) -> bool:
        return secret_hash == f"{self.PREFIX}{plaintext}"


class FakeEventCleanup(EventCleanup):
    def __init__(
        self, *, fails: bool = False, on_cleanup: Callable[[], None] | None = None
    ) -> None:
        self.fails = fails
        self.cleaned: list[uuid.UUID] = []
        # 用來模擬「清除事件的這段期間,裝置被另一個分頁移除了」
        self.on_cleanup = on_cleanup

    async def delete_device_events(self, device_id: uuid.UUID) -> None:
        if self.fails:
            raise EventCleanupFailed()
        if self.on_cleanup is not None:
            self.on_cleanup()
        self.cleaned.append(device_id)
