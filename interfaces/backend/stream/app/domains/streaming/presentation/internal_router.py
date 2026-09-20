"""鏡頭端 signaling 端點(06_spec_即時串流.md 第 3.2 節)。不對公網開放。

採 HTTP 長輪詢而非 WebSocket:與其餘六個服務的 HTTP 形狀一致,不需要為 WebSocket
調整 Load Balancer 的連線黏性(13_ADR 第 3 節)。

呼叫者身分由 CameraAuthenticator 驗證,機制待 Device 服務定案
(06_spec 第 9 節待確認事項)。
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.core.security import AuthenticatedDeviceId
from app.domains.streaming.domain.entities import Peer
from app.domains.streaming.presentation.dependencies import (
    AddIceCandidatesDep,
    AnswerOfferDep,
    FetchIceCandidatesDep,
    FetchPendingOfferDep,
)
from app.domains.streaming.presentation.schemas import (
    AnswerIn,
    CandidatesIn,
    CandidatesOut,
    IceCandidateSchema,
    PendingOfferOut,
)

router = APIRouter(prefix="/internal/devices/{device_id}/stream", tags=["stream-internal"])


@router.get(
    "/pending-offer",
    response_model=None,
    responses={
        200: {"model": PendingOfferOut},
        204: {"description": "逾時,目前沒有待處理的 offer"},
    },
)
async def pending_offer(
    device_id: AuthenticatedDeviceId,
    use_case: FetchPendingOfferDep,
) -> Response | PendingOfferOut:
    """長輪詢,逾時 30 秒回 204。"""
    offer = await use_case.execute(device_id)
    if offer is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return PendingOfferOut(session_id=offer.session_id, sdp=offer.sdp)


@router.post("/answer", status_code=status.HTTP_204_NO_CONTENT)
async def answer(
    device_id: AuthenticatedDeviceId,
    body: AnswerIn,
    use_case: AnswerOfferDep,
) -> Response:
    await use_case.execute(device_id=device_id, session_id=body.session_id, sdp=body.sdp)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/candidates", status_code=status.HTTP_204_NO_CONTENT)
async def add_candidates(
    device_id: AuthenticatedDeviceId,
    body: CandidatesIn,
    use_case: AddIceCandidatesDep,
) -> Response:
    await use_case.execute(
        device_id=device_id,
        session_id=body.session_id,
        peer=Peer.CAMERA,
        candidates=[c.to_domain() for c in body.candidates],
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/candidates", response_model=CandidatesOut)
async def fetch_candidates(
    device_id: AuthenticatedDeviceId,
    use_case: FetchIceCandidatesDep,
    session_id: Annotated[uuid.UUID, Query()],
    since: Annotated[int, Query(ge=0)] = 0,
) -> CandidatesOut:
    """鏡頭端讀的是觀看端送出的 candidate。"""
    batch = await use_case.execute(
        device_id=device_id,
        session_id=session_id,
        peer=Peer.VIEWER,
        since=since,
    )
    return CandidatesOut(
        candidates=[IceCandidateSchema.of(c) for c in batch.candidates],
        next_since=batch.next_since,
    )
