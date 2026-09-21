"""HTTP 端點。沒有業務邏輯:輸入 schema → use case → 輸出 schema。

路徑取自 03_spec 第 3 節與 04_spec 第 3 節。
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.domains.devices.application.use_cases.list_devices import ListDevices
from app.domains.devices.application.use_cases.pair_device import PairDevice
from app.domains.devices.application.use_cases.record_heartbeat import RecordHeartbeat
from app.domains.devices.application.use_cases.register_device import RegisterDevice
from app.domains.devices.application.use_cases.remove_device import RemoveDevice
from app.domains.devices.application.use_cases.rename_device import RenameDevice
from app.domains.devices.presentation.dependencies import (
    CurrentUserId,
    DeviceSecretDep,
    get_list_devices,
    get_pair_device,
    get_record_heartbeat,
    get_register_device,
    get_remove_device,
    get_rename_device,
)
from app.domains.devices.presentation.schemas import (
    DeviceOut,
    PairDeviceIn,
    RegisterDeviceIn,
    RegisterDeviceOut,
    RenameDeviceIn,
)

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("/register", response_model=RegisterDeviceOut, status_code=status.HTTP_201_CREATED)
async def register_device(
    payload: RegisterDeviceIn,
    use_case: Annotated[RegisterDevice, Depends(get_register_device)],
) -> RegisterDeviceOut:
    """鏡頭端呼叫,取得配對碼(03_spec 第 2.1 節)。

    這是唯一的匿名端點——鏡頭在這一刻還沒有任何憑證可用。以 hardware_id 冪等,
    並在 main.py 以 IP 限流,避免被拿來灌入 pending 列(審查 #2、#3)。
    """
    return RegisterDeviceOut.model_validate(
        await use_case.execute(payload.hardware_id), from_attributes=True
    )


@router.post("/pair", response_model=DeviceOut)
async def pair_device(
    payload: PairDeviceIn,
    user_id: CurrentUserId,
    use_case: Annotated[PairDevice, Depends(get_pair_device)],
) -> DeviceOut:
    """使用者輸入配對碼完成綁定(03_spec 第 2.2 節)。"""
    return DeviceOut.model_validate(
        await use_case.execute(user_id=user_id, typed_code=payload.pairing_code)
    )


@router.post("/{device_id}/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
async def record_heartbeat(
    device_id: uuid.UUID,
    device_secret: DeviceSecretDep,
    use_case: Annotated[RecordHeartbeat, Depends(get_record_heartbeat)],
) -> Response:
    """鏡頭端心跳回報,每 30 秒一次(03_spec 第 2.3 節)。"""
    await use_case.execute(device_id=device_id, device_secret=device_secret)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    user_id: CurrentUserId,
    use_case: Annotated[ListDevices, Depends(get_list_devices)],
) -> list[DeviceOut]:
    """使用者已配對的裝置列表(04_spec 第 2.1 節)。"""
    return [DeviceOut.model_validate(view) for view in await use_case.execute(user_id)]


@router.patch("/{device_id}", response_model=DeviceOut)
async def rename_device(
    device_id: uuid.UUID,
    payload: RenameDeviceIn,
    user_id: CurrentUserId,
    use_case: Annotated[RenameDevice, Depends(get_rename_device)],
) -> DeviceOut:
    """重新命名(04_spec 第 2.2 節)。非本人一律 404(審查 #1)。"""
    return DeviceOut.model_validate(
        await use_case.execute(device_id=device_id, requester_id=user_id, name=payload.name)
    )


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_device(
    device_id: uuid.UUID,
    user_id: CurrentUserId,
    use_case: Annotated[RemoveDevice, Depends(get_remove_device)],
) -> Response:
    """移除裝置,連同事件與影片(04_spec 第 2.3 節)。fail-closed,見審查 #9。"""
    await use_case.execute(device_id=device_id, requester_id=user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
