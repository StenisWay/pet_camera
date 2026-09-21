"""F5 第 3 節的對外端點。

路由邊界(12_spec 第 3 節):GET /media/{id} 屬本服務;GET /media、DELETE /media/{id}、
POST /media/export/google-drive 屬 Album 服務,由 Load Balancer 依此分流。

這裡沒有業務判斷:輸入 schema → use case → 輸出 schema。領域例外由
core/http_errors.py 統一轉成 HTTP 狀態碼與規格書的錯誤碼。
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.security import CurrentUserId
from app.domains.media.application.use_cases.get_media_item import GetMediaItem
from app.domains.media.application.use_cases.request_clip import RequestClip
from app.domains.media.application.use_cases.take_event_screenshot import TakeEventScreenshot
from app.domains.media.application.use_cases.take_live_screenshot import TakeLiveScreenshot
from app.domains.media.presentation.dependencies import (
    enforce_clip_rate_limit,
    enforce_screenshot_rate_limit,
    get_get_media_item,
    get_request_clip,
    get_take_event_screenshot,
    get_take_live_screenshot,
)
from app.domains.media.presentation.schemas import ClipIn, EventScreenshotIn, MediaItemOut

router = APIRouter(tags=["media"])


@router.post(
    "/devices/{device_id}/screenshot",
    response_model=MediaItemOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_screenshot_rate_limit)],
)
async def take_live_screenshot(
    device_id: uuid.UUID,
    user_id: CurrentUserId,
    use_case: Annotated[TakeLiveScreenshot, Depends(get_take_live_screenshot)],
) -> MediaItemOut:
    """即時畫面截圖。同步完成(審查 #1),回傳的已是 ready 的項目。"""
    return MediaItemOut.of(await use_case.execute(device_id, requester_id=user_id))


@router.post(
    "/events/{event_id}/screenshot",
    response_model=MediaItemOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_screenshot_rate_limit)],
)
async def take_event_screenshot(
    event_id: uuid.UUID,
    payload: EventScreenshotIn,
    user_id: CurrentUserId,
    use_case: Annotated[TakeEventScreenshot, Depends(get_take_event_screenshot)],
) -> MediaItemOut:
    """事件回放畫面截圖。"""
    return MediaItemOut.of(
        await use_case.execute(event_id, offset_sec=payload.offset_sec, requester_id=user_id)
    )


@router.post(
    "/events/{event_id}/clip",
    response_model=MediaItemOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_clip_rate_limit)],
)
async def request_clip(
    event_id: uuid.UUID,
    payload: ClipIn,
    user_id: CurrentUserId,
    use_case: Annotated[RequestClip, Depends(get_request_clip)],
) -> MediaItemOut:
    """剪輯請求。202 表示已受理,背景處理(11_spec 第 4 節)。"""
    return MediaItemOut.of(
        await use_case.execute(
            event_id,
            start_sec=payload.start_sec,
            end_sec=payload.end_sec,
            requester_id=user_id,
        )
    )


@router.get("/media/{media_item_id}", response_model=MediaItemOut)
async def get_media_item(
    media_item_id: uuid.UUID,
    user_id: CurrentUserId,
    use_case: Annotated[GetMediaItem, Depends(get_get_media_item)],
) -> MediaItemOut:
    """查詢處理狀態與內容。僅 ready 的項目帶 presigned URL(審查 #12)。"""
    return MediaItemOut.of(await use_case.execute(media_item_id, requester_id=user_id))
