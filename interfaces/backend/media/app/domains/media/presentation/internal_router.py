"""worker 的完成回呼(審查 #3)。

只走 VCN 私有網路、不經 Load Balancer(13_ADR 第 1 節),另以共享金鑰標頭把關。
使用者的 access token 在這裡無效——推進處理狀態不是使用者能做的事。
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.security import require_internal_caller
from app.domains.media.application.use_cases.finish_media_item import (
    CompleteMediaItem,
    FailMediaItem,
)
from app.domains.media.presentation.dependencies import (
    get_complete_media_item,
    get_fail_media_item,
)
from app.domains.media.presentation.schemas import ClipDoneIn

router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    dependencies=[Depends(require_internal_caller)],
)


@router.post("/media/{media_item_id}/ready", status_code=status.HTTP_204_NO_CONTENT)
async def mark_ready(
    media_item_id: uuid.UUID,
    payload: ClipDoneIn,
    use_case: Annotated[CompleteMediaItem, Depends(get_complete_media_item)],
) -> None:
    """轉檔完成:status = ready,相簿即可播放。"""
    await use_case.execute(
        media_item_id,
        object_key=payload.object_key,
        thumbnail_object_key=payload.thumbnail_object_key,
    )


@router.post("/media/{media_item_id}/failed", status_code=status.HTTP_204_NO_CONTENT)
async def mark_failed(
    media_item_id: uuid.UUID,
    use_case: Annotated[FailMediaItem, Depends(get_fail_media_item)],
) -> None:
    """轉檔失敗(CLIP_002):不建立可用內容,相簿卡片顯示錯誤圖示。"""
    await use_case.execute(media_item_id)
