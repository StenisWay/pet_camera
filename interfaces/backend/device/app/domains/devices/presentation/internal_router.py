"""服務之間的內部端點。

只走 VM 間的 VCN 私有網路,不經過 Load Balancer(13_ADR 第 1.1 節),
一律以 X-Internal-Api-Key 把關。
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.domains.devices.application.use_cases.get_device_summary import GetDeviceSummary
from app.domains.devices.application.use_cases.remove_user_devices import RemoveUserDevices
from app.domains.devices.presentation.dependencies import (
    get_device_summary,
    get_remove_user_devices,
    require_internal_api_key,
)
from app.domains.devices.presentation.schemas import DeviceSummaryOut, RemovedDevicesOut

router = APIRouter(
    prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal_api_key)]
)


@router.get("/devices/{device_id}", response_model=DeviceSummaryOut)
async def get_summary(
    device_id: uuid.UUID,
    use_case: Annotated[GetDeviceSummary, Depends(get_device_summary)],
) -> DeviceSummaryOut:
    """給 Event 與 Push 服務用(見服務對外契約 __init__.py)。

    devices 表屬於本服務,其他服務不可直接讀(13_ADR 第 1 節)。
    """
    return DeviceSummaryOut.model_validate(await use_case.execute(device_id))


@router.delete("/users/{user_id}/devices", response_model=RemovedDevicesOut)
async def remove_user_devices(
    user_id: uuid.UUID,
    use_case: Annotated[RemoveUserDevices, Depends(get_remove_user_devices)],
) -> RemovedDevicesOut:
    """由 Auth 服務在刪除 users 那一列**之前**呼叫(審查 #8)。

    不先走這裡的話,devices.user_id 的 ON DELETE SET NULL 會與
    「status = 'pending' 與 user_id is null 同時成立」的 CHECK 打架,
    刪除帳號那句 SQL 會直接失敗。
    """
    return RemovedDevicesOut(removed=await use_case.execute(user_id))
