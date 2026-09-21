"""推播端點登記(09_spec_推播通知.md 第 2.4、3 節)。router 沒有業務判斷。"""

import uuid

from fastapi import APIRouter, Response, status

from app.core.dependencies import RateLimiterDep
from app.core.security import CurrentUserId
from app.domains.push_tokens.application.dtos import PushTokenResult, RegisterPushTokenCommand
from app.domains.push_tokens.domain.entities import ClientPlatform
from app.domains.push_tokens.presentation.dependencies import (
    ListPushTokensDep,
    RegisterPushTokenDep,
    UnregisterPushTokenDep,
)
from app.domains.push_tokens.presentation.schemas import (
    PushTokenListOut,
    PushTokenOut,
    RegisterPushTokenIn,
)

router = APIRouter(prefix="/push-tokens", tags=["push-tokens"])


def _out(result: PushTokenResult) -> PushTokenOut:
    return PushTokenOut(id=result.id, platform=result.platform.value, created_at=result.created_at)


@router.put("", response_model=PushTokenOut)
async def register_push_token(
    body: RegisterPushTokenIn,
    user_id: CurrentUserId,
    use_case: RegisterPushTokenDep,
    rate_limiter: RateLimiterDep,
) -> PushTokenOut:
    # 審查 #16:App 每次啟動都會呼叫,每使用者每分鐘 10 次
    await rate_limiter.check(str(user_id), endpoint="PUT /push-tokens")
    result = await use_case.execute(
        RegisterPushTokenCommand(
            user_id=user_id, platform=ClientPlatform(body.platform), token=body.token
        )
    )
    return _out(result)


@router.get("", response_model=PushTokenListOut)
async def list_push_tokens(user_id: CurrentUserId, use_case: ListPushTokensDep) -> PushTokenListOut:
    return PushTokenListOut(items=[_out(r) for r in await use_case.execute(user_id)])


@router.delete("/{push_token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_push_token(
    push_token_id: uuid.UUID, user_id: CurrentUserId, use_case: UnregisterPushTokenDep
) -> Response:
    await use_case.execute(push_token_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
