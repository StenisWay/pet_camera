"""相簿 HTTP 端點(12_spec_相簿與雲端匯出.md 第 3 節)。

路徑刻意與 Media 服務的 GET /media/{id} 區隔:Album 負責列表與刪除,Media 負責單筆
內容查詢(規格審查 #3 的分流決議)。router 沒有業務判斷。
"""

import uuid

from fastapi import APIRouter, Query, Response, status

from app.core.dependencies import RateLimiterDep
from app.core.security import CurrentUserId
from app.domains.album.application.dtos import AlbumItemResult, ListAlbumQuery
from app.domains.album.presentation.dependencies import (
    DeleteAlbumItemDep,
    ListAlbumDep,
    ObjectStorageDep,
)
from app.domains.album.presentation.schemas import AlbumItemOut, AlbumPageOut

router = APIRouter(tags=["album"])

READY = "ready"


async def _to_out(item: AlbumItemResult, storage: ObjectStorageDep) -> AlbumItemOut:
    # 只有 ready 的項目才有可播放內容(01_資料模型與儲存規格.md 第 5 節)
    ready = item.status == READY
    return AlbumItemOut(
        id=item.id,
        type=item.type,
        status=item.status,
        captured_at=item.captured_at,
        duration_sec=item.duration_sec,
        drive_export_status=item.drive_export_status,
        drive_file_id=item.drive_file_id,
        url=await storage.presigned_url(item.object_key) if ready and item.object_key else None,
        thumbnail_url=(
            await storage.presigned_url(item.thumbnail_object_key)
            if ready and item.thumbnail_object_key
            else None
        ),
    )


@router.get("/media", response_model=AlbumPageOut)
async def list_album(
    user_id: CurrentUserId,
    use_case: ListAlbumDep,
    storage: ObjectStorageDep,
    rate_limiter: RateLimiterDep,
    cursor: str | None = None,
    limit: int | None = Query(default=None),
    date: str | None = Query(default=None, description="YYYY-MM-DD,App 端的單日篩選"),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
) -> AlbumPageOut:
    await rate_limiter.check(str(user_id), endpoint="GET /media")
    page = await use_case.execute(
        ListAlbumQuery(
            owner_id=user_id,
            cursor=cursor,
            limit=limit,
            date=date,
            date_from=date_from,
            date_to=date_to,
        )
    )
    return AlbumPageOut(
        items=[await _to_out(item, storage) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.delete("/media/{media_item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_album_item(
    media_item_id: uuid.UUID,
    user_id: CurrentUserId,
    use_case: DeleteAlbumItemDep,
    rate_limiter: RateLimiterDep,
) -> Response:
    await rate_limiter.check(str(user_id), endpoint="DELETE /media/{id}")
    await use_case.execute(media_item_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
