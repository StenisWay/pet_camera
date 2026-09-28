"""資料存取特有的正確性。行為承諾本身在 contracts/ 驗,這裡只測 mapping 與約束。

全部標記 integration:需要真實 PostgreSQL,預設不執行(見 tests/conftest.py)。
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.domains.media.domain.entities import MediaItemStatus, MediaItemType
from app.domains.media.infrastructure.unit_of_work import SqlAlchemyMediaUnitOfWork
from tests.domains.media.builders import OWNER, an_item

pytestmark = pytest.mark.integration


async def test_saved_item_round_trips_without_loss(session_factory):
    """存進去再讀出來,業務欄位要完全還原(含時區與狀態)。"""
    item = an_item(
        type=MediaItemType.CLIP,
        status=MediaItemStatus.READY,
        source_event_id=uuid.uuid4(),
        object_key="media/a/2026/09/20/x.mp4",
        thumbnail_object_key="media-thumbnails/a/2026/09/20/x.jpg",
        duration_sec=15,
        captured_at=datetime(2026, 9, 20, 10, 0, tzinfo=UTC),
    )

    async with SqlAlchemyMediaUnitOfWork(session_factory) as uow:
        await uow.media.add(item)
        await uow.commit()

    async with SqlAlchemyMediaUnitOfWork(session_factory) as uow:
        loaded = await uow.media.get(item.id, owner_id=OWNER)

    assert loaded.captured_at == item.captured_at
    assert loaded.captured_at.tzinfo is not None  # timestamptz,不是 naive
    assert loaded.type is MediaItemType.CLIP
    assert loaded.status is MediaItemStatus.READY
    assert loaded.duration_sec == 15
    assert loaded.source_event_id == item.source_event_id


async def test_media_service_never_touches_album_columns(session_factory):
    """13_ADR 第 1 節:drive_export_status / drive_file_id 由 Album 服務寫入。

    兩個服務共用同一張表,本服務的 mapper 碰了那兩欄就會互相覆蓋。
    """
    from sqlalchemy import select

    from app.domains.media.infrastructure.orm import MediaItemRow

    item = an_item(status=MediaItemStatus.PROCESSING)
    async with SqlAlchemyMediaUnitOfWork(session_factory) as uow:
        await uow.media.add(item)
        await uow.commit()
        # 模擬 Album 服務把它標成匯出中
        row = (
            await uow.session.execute(
                select(MediaItemRow).where(MediaItemRow.id == item.id)
            )
        ).scalar_one()
        row.drive_export_status = "exporting"
        await uow.commit()

    async with SqlAlchemyMediaUnitOfWork(session_factory) as uow:
        loaded = await uow.media.get(item.id, owner_id=OWNER)
        loaded.mark_ready(
            object_key="media/a/x.jpg", thumbnail_object_key=None, now=datetime.now(UTC)
        )
        await uow.media.save(loaded)
        await uow.commit()

    async with SqlAlchemyMediaUnitOfWork(session_factory) as uow:
        row = (
            await uow.session.execute(
                select(MediaItemRow).where(MediaItemRow.id == item.id)
            )
        ).scalar_one()

    assert row.status == "ready"
    assert row.drive_export_status == "exporting"  # 沒有被 Media 服務蓋掉


async def test_database_rejects_an_unknown_status(session_factory):
    """資料庫是最後一道防線:即使繞過 domain,CHECK 約束仍會擋下。"""
    from sqlalchemy.exc import IntegrityError

    from app.domains.media.infrastructure.orm import MediaItemRow

    async with SqlAlchemyMediaUnitOfWork(session_factory) as uow:
        uow.session.add(
            MediaItemRow(
                id=uuid.uuid4(),
                user_id=OWNER,
                device_id=uuid.uuid4(),
                type="photo",
                status="uploading",  # 不在值域內
                captured_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError, match="ck_media_items_status_valid"):
            await uow.session.flush()


async def test_database_rejects_a_photo_with_a_duration(session_factory):
    """資料模型 §2.4:duration_sec 只有 clip 才有。"""
    from sqlalchemy.exc import IntegrityError

    from app.domains.media.infrastructure.orm import MediaItemRow

    async with SqlAlchemyMediaUnitOfWork(session_factory) as uow:
        uow.session.add(
            MediaItemRow(
                id=uuid.uuid4(),
                user_id=OWNER,
                device_id=uuid.uuid4(),
                type="photo",
                status="processing",
                duration_sec=10,
                captured_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError, match="ck_media_items_duration_matches_type"):
            await uow.session.flush()
