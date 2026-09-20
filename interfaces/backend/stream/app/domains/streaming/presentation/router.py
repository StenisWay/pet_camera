"""觀看端 HTTP 端點(06_spec_即時串流.md 第 3.1 節)。需登入。

router 沒有業務判斷:擁有者驗證、接管、逾時都在 use case 裡,這裡只負責
HTTP 契約與限流。
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.core.dependencies import SessionRateLimiterDep
from app.core.security import CurrentUserId
from app.domains.streaming.domain.entities import Peer
from app.domains.streaming.presentation.dependencies import (
    AddIceCandidatesDep,
    EndStreamSessionDep,
    FetchIceCandidatesDep,
    OpenStreamSessionDep,
    SubmitOfferDep,
)
from app.domains.streaming.presentation.schemas import (
    AnswerOut,
    CandidatesIn,
    CandidatesOut,
    IceCandidateSchema,
    OfferIn,
    SessionOut,
)

router = APIRouter(prefix="/devices/{device_id}/stream", tags=["stream"])


@router.post("/session", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def open_session(
    device_id: uuid.UUID,
    user_id: CurrentUserId,
    use_case: OpenStreamSessionDep,
    rate_limiter: SessionRateLimiterDep,
) -> SessionOut:
    """第 2.4 節:同一支鏡頭已有 session 時直接接管,一樣回 201,不回 STREAM_004。"""
    await rate_limiter.check(str(user_id), endpoint="POST /devices/{id}/stream/session")
    session = await use_case.execute(device_id, user_id)
    return SessionOut.of(session)


@router.post("/offer", response_model=AnswerOut)
async def submit_offer(
    device_id: uuid.UUID,
    body: OfferIn,
    user_id: CurrentUserId,
    use_case: SubmitOfferDep,
) -> AnswerOut:
    """同步等待鏡頭端 answer,逾時 5 秒回 STREAM_005(408)。"""
    sdp = await use_case.execute(
        device_id=device_id, session_id=body.session_id, requester_id=user_id, sdp=body.sdp
    )
    return AnswerOut(session_id=body.session_id, sdp=sdp)


@router.post("/candidates", status_code=status.HTTP_204_NO_CONTENT)
async def add_candidates(
    device_id: uuid.UUID,
    body: CandidatesIn,
    user_id: CurrentUserId,
    use_case: AddIceCandidatesDep,
) -> Response:
    await use_case.execute(
        device_id=device_id,
        session_id=body.session_id,
        peer=Peer.VIEWER,
        candidates=[c.to_domain() for c in body.candidates],
        requester_id=user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/candidates", response_model=CandidatesOut)
async def fetch_candidates(
    device_id: uuid.UUID,
    user_id: CurrentUserId,
    use_case: FetchIceCandidatesDep,
    session_id: Annotated[uuid.UUID, Query()],
    since: Annotated[int, Query(ge=0)] = 0,
) -> CandidatesOut:
    """觀看端讀的是鏡頭端送出的 candidate。"""
    batch = await use_case.execute(
        device_id=device_id,
        session_id=session_id,
        peer=Peer.CAMERA,
        since=since,
        requester_id=user_id,
    )
    return CandidatesOut(
        candidates=[IceCandidateSchema.of(c) for c in batch.candidates],
        next_since=batch.next_since,
    )


@router.delete("/session/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def end_session(
    device_id: uuid.UUID,
    session_id: uuid.UUID,
    user_id: CurrentUserId,
    use_case: EndStreamSessionDep,
) -> Response:
    """冪等,一律 204。Redis 不可用時也是 204(第 7 節的 fail-open 例外)。"""
    await use_case.execute(device_id=device_id, session_id=session_id, requester_id=user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
