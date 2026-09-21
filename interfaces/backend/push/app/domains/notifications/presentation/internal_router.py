"""跨服務內部端點(09_spec 第 3 節,審查 #1)。

只走 VCN 私有網路、不經 Load Balancer(13_ADR 第 1 節),另以 X-Internal-Api-Key 把關。
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status

from app.core.security import require_internal_caller
from app.domains.notifications.application.use_cases.notify_event_ready import NotifyEventReady
from app.domains.notifications.domain.model import ReadyEvent
from app.domains.notifications.presentation.dependencies import NotifyEventReadyDep
from app.domains.notifications.presentation.schemas import EventReadyIn

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    dependencies=[Depends(require_internal_caller)],
)


async def _dispatch(use_case: NotifyEventReady, event: ReadyEvent) -> None:
    report = await use_case.execute(event)
    logger.info("event %s push dispatch: %s", event.event_id, report)


@router.post("/notifications/event-ready", status_code=status.HTTP_202_ACCEPTED)
async def event_ready(
    body: EventReadyIn, use_case: NotifyEventReadyDep, background_tasks: BackgroundTasks
) -> Response:
    """回 202 後於背景查詢與發送,Event worker 不等待發送結果(審查 #1)。"""
    event = ReadyEvent(
        event_id=body.event_id,
        device_id=body.device_id,
        confidence_score=body.confidence_score,
        thumbnail_object_key=body.thumbnail_object_key,
        started_at=body.started_at,
    )
    background_tasks.add_task(_dispatch, use_case, event)
    return Response(status_code=status.HTTP_202_ACCEPTED)
