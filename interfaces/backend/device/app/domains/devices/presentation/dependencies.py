"""組裝點(composition root)。

每個 port 一個 provider 函式,測試時用 app.dependency_overrides 換掉任何一個,
就能在完全不碰資料庫的情況下測 HTTP 契約。
"""

import uuid
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.database import get_session_factory
from app.core.security import decode_user_id, verify_internal_api_key
from app.core.system import SystemClock, Uuid7Generator
from app.domains.devices.application.ports import (
    DeviceSecrets,
    DevicesUnitOfWork,
    EventCleanup,
    PairingCodeFactory,
)
from app.domains.devices.application.use_cases.get_device_summary import GetDeviceSummary
from app.domains.devices.application.use_cases.list_devices import ListDevices
from app.domains.devices.application.use_cases.pair_device import PairDevice
from app.domains.devices.application.use_cases.record_heartbeat import RecordHeartbeat
from app.domains.devices.application.use_cases.register_device import RegisterDevice
from app.domains.devices.application.use_cases.remove_device import RemoveDevice
from app.domains.devices.application.use_cases.remove_user_devices import RemoveUserDevices
from app.domains.devices.application.use_cases.rename_device import RenameDevice
from app.domains.devices.infrastructure.event_cleanup import HttpEventCleanup
from app.domains.devices.infrastructure.security import (
    RandomPairingCodeFactory,
    Sha256DeviceSecrets,
)
from app.domains.devices.infrastructure.unit_of_work import SqlAlchemyDevicesUnitOfWork
from app.shared_kernel.errors import AuthenticationRequired
from app.shared_kernel.ports import Clock, IdGenerator

SettingsDep = Annotated[Settings, Depends(get_settings)]


# --- 基礎設施 -----------------------------------------------------------------


def get_session_factory_dep() -> async_sessionmaker[AsyncSession]:
    return get_session_factory()


def get_devices_uow(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory_dep)
    ],
) -> DevicesUnitOfWork:
    return SqlAlchemyDevicesUnitOfWork(session_factory)


def get_clock() -> Clock:
    return SystemClock()


def get_id_generator() -> IdGenerator:
    return Uuid7Generator()


def get_pairing_codes(settings: SettingsDep) -> PairingCodeFactory:
    return RandomPairingCodeFactory(
        length=settings.pairing_code_length, ttl_seconds=settings.pairing_code_ttl_seconds
    )


def get_device_secrets() -> DeviceSecrets:
    return Sha256DeviceSecrets()


def get_event_cleanup(settings: SettingsDep) -> EventCleanup:
    return HttpEventCleanup(
        base_url=settings.event_service_base_url,
        api_key=settings.internal_api_key,
        timeout_seconds=settings.event_cleanup_timeout_seconds,
    )


# --- 呼叫者身分 ---------------------------------------------------------------


def get_current_user_id(
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> uuid.UUID:
    """使用者端點的身分:Auth 服務簽發的 JWT。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationRequired("請重新登入")
    token = authorization.split(" ", 1)[1].strip()
    return decode_user_id(
        token, jwt_secret=settings.jwt_secret, algorithm=settings.jwt_algorithm
    )


def get_device_secret(
    x_device_secret: Annotated[str | None, Header()] = None,
) -> str:
    """鏡頭端點的身分(審查 #2)。register 當時簽發,鏡頭自行保存。"""
    if not x_device_secret:
        raise AuthenticationRequired("缺少裝置憑證")
    return x_device_secret


def require_internal_api_key(
    settings: SettingsDep,
    x_internal_api_key: Annotated[str | None, Header()] = None,
) -> None:
    """內部端點的把關(審查 #7、#8)。"""
    verify_internal_api_key(x_internal_api_key, settings.internal_api_key)


def get_client_identity(request: Request) -> str:
    """限流的對象。匿名端點只有 IP 可用(審查 #2、#4)。"""
    return request.client.host if request.client else "unknown"


# --- use case -----------------------------------------------------------------

UowDep = Annotated[DevicesUnitOfWork, Depends(get_devices_uow)]
ClockDep = Annotated[Clock, Depends(get_clock)]
CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]
DeviceSecretDep = Annotated[str, Depends(get_device_secret)]


def get_register_device(
    uow: UowDep,
    codes: Annotated[PairingCodeFactory, Depends(get_pairing_codes)],
    secrets: Annotated[DeviceSecrets, Depends(get_device_secrets)],
    clock: ClockDep,
    ids: Annotated[IdGenerator, Depends(get_id_generator)],
    settings: SettingsDep,
) -> RegisterDevice:
    return RegisterDevice(
        uow,
        codes,
        secrets,
        clock,
        ids,
        default_name=settings.default_device_name,
        max_code_attempts=settings.pairing_code_max_attempts,
    )


def get_pair_device(uow: UowDep, clock: ClockDep, settings: SettingsDep) -> PairDevice:
    return PairDevice(
        uow,
        clock,
        offline_after_seconds=settings.offline_after_seconds,
        max_devices_per_user=settings.max_devices_per_user,
    )


def get_record_heartbeat(
    uow: UowDep,
    secrets: Annotated[DeviceSecrets, Depends(get_device_secrets)],
    clock: ClockDep,
) -> RecordHeartbeat:
    return RecordHeartbeat(uow, secrets, clock)


def get_list_devices(uow: UowDep, clock: ClockDep, settings: SettingsDep) -> ListDevices:
    return ListDevices(uow, clock, offline_after_seconds=settings.offline_after_seconds)


def get_rename_device(uow: UowDep, clock: ClockDep, settings: SettingsDep) -> RenameDevice:
    return RenameDevice(
        uow,
        clock,
        offline_after_seconds=settings.offline_after_seconds,
        name_max_length=settings.device_name_max_length,
    )


def get_remove_device(
    uow: UowDep,
    events: Annotated[EventCleanup, Depends(get_event_cleanup)],
    codes: Annotated[PairingCodeFactory, Depends(get_pairing_codes)],
    clock: ClockDep,
) -> RemoveDevice:
    return RemoveDevice(uow, events, codes, clock)


def get_remove_user_devices(
    uow: UowDep,
    events: Annotated[EventCleanup, Depends(get_event_cleanup)],
    codes: Annotated[PairingCodeFactory, Depends(get_pairing_codes)],
    clock: ClockDep,
) -> RemoveUserDevices:
    return RemoveUserDevices(uow, events, codes, clock)


def get_device_summary(
    uow: UowDep, clock: ClockDep, settings: SettingsDep
) -> GetDeviceSummary:
    return GetDeviceSummary(uow, clock, offline_after_seconds=settings.offline_after_seconds)
