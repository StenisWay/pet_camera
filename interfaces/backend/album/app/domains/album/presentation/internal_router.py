"""跨服務內部端點(規格審查 #9)。

01_資料模型與儲存規格.md 第 6 節要求刪除帳號時串聯清除該帳號所有 media_items 與
R2 物件,但原規格沒有定義 Auth 服務要打哪個入口,這裡補上。只走 VCN 私有網路、
不經 Load Balancer(13_ADR 第 1 節),另以共享金鑰把關。
"""

import uuid

from fastapi import APIRouter, Depends

from app.core.security import require_internal_caller
from app.domains.album.presentation.dependencies import PurgeUserAlbumDep
from app.domains.album.presentation.schemas import CascadeDeleteOut

router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    dependencies=[Depends(require_internal_caller)],
)


@router.delete("/users/{user_id}/media", response_model=CascadeDeleteOut)
async def purge_user_album(user_id: uuid.UUID, use_case: PurgeUserAlbumDep) -> CascadeDeleteOut:
    return CascadeDeleteOut(deleted_object_count=await use_case.execute(user_id))
