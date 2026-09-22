"""detection 的內部端點(08_spec 第 3.3 節)。

只走 VCN 私有網路、不經 Load Balancer,以 X-Internal-Api-Key 把關。
F2 的偵測 worker 不是 HTTP 服務,見 app/worker.py。
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.security import require_internal_caller
from app.domains.detection.application.use_cases.purge_device_events import PurgeDeviceEvents
from app.domains.detection.presentation.dependencies import get_purge_device_events
from app.domains.detection.presentation.schemas import PurgeResultOut

internal_router = APIRouter(prefix="/internal", tags=["internal"])


@internal_router.delete(
    "/devices/{device_id}/events",
    response_model=PurgeResultOut,
    dependencies=[Depends(require_internal_caller)],
)
async def purge_device_events(
    device_id: UUID,
    use_case: Annotated[PurgeDeviceEvents, Depends(get_purge_device_events)],
) -> PurgeResultOut:
    result = await use_case.execute(device_id)
    return PurgeResultOut(deleted_count=result.deleted_count)
