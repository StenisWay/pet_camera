"""Google Drive 授權與匯出端點(12_spec_相簿與雲端匯出.md 第 3 節)。"""

from fastapi import APIRouter, status

from app.core.dependencies import RateLimiterDep
from app.core.security import CurrentUserId
from app.domains.drive_export.application.dtos import (
    CompleteAuthorizationCommand,
    ExportRequestCommand,
)
from app.domains.drive_export.presentation.dependencies import (
    CompleteAuthorizationDep,
    RequestExportDep,
    StartAuthorizationDep,
)
from app.domains.drive_export.presentation.schemas import (
    ExportAcceptedOut,
    ExportRequestIn,
    OAuthCallbackIn,
    OAuthUrlOut,
)

router = APIRouter(tags=["drive-export"])


@router.get("/integrations/google-drive/oauth-url", response_model=OAuthUrlOut)
async def get_oauth_url(
    user_id: CurrentUserId, use_case: StartAuthorizationDep, rate_limiter: RateLimiterDep
) -> OAuthUrlOut:
    await rate_limiter.check(str(user_id), endpoint="GET /integrations/google-drive/oauth-url")
    result = await use_case.execute(user_id)
    return OAuthUrlOut(authorization_url=result.authorization_url)


@router.post("/integrations/google-drive/oauth-callback", status_code=status.HTTP_204_NO_CONTENT)
async def complete_oauth(
    payload: OAuthCallbackIn,
    user_id: CurrentUserId,
    use_case: CompleteAuthorizationDep,
    rate_limiter: RateLimiterDep,
) -> None:
    await rate_limiter.check(
        str(user_id), endpoint="POST /integrations/google-drive/oauth-callback"
    )
    await use_case.execute(
        CompleteAuthorizationCommand(owner_id=user_id, code=payload.code, state=payload.state)
    )


@router.post(
    "/media/export/google-drive",
    response_model=ExportAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def export_to_google_drive(
    payload: ExportRequestIn,
    user_id: CurrentUserId,
    use_case: RequestExportDep,
    rate_limiter: RateLimiterDep,
) -> ExportAcceptedOut:
    """202:只代表已受理。成功與否由 drive_export_status 反映,前端在縮圖上呈現。"""
    await rate_limiter.check(str(user_id), endpoint="POST /media/export/google-drive")
    result = await use_case.execute(
        ExportRequestCommand(owner_id=user_id, media_item_ids=payload.media_item_ids)
    )
    return ExportAcceptedOut(
        accepted_ids=result.accepted_ids, skipped_ids=result.skipped_ids
    )
