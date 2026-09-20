"""SQLAlchemy 實作特有的正確性:mapping 精度與資料庫約束。

需要真實 PostgreSQL——CHECK 約束、timestamptz、numeric 精度在 SQLite 上行為不同,
用 SQLite 代替等於讓這幾個測試失去意義。

    uv run pytest -m integration
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.detection.domain.entities import Event, UploadedMedia
from app.domains.detection.infrastructure.mappers import to_new_row
from app.domains.detection.infrastructure.unit_of_work import SqlAlchemyDetectionUnitOfWork
from tests.domains.detection.builders import DEVICE, EVENT, at

pytestmark = pytest.mark.integration


def a_ready_event() -> Event:
    event = Event.begin(id=EVENT, device_id=DEVICE, started_at=at(0))
    event.mark_ready(
        UploadedMedia(
            video_object_key=f"videos/{DEVICE}/2026/09/20/{EVENT}.mp4",
            thumbnail_object_key=f"thumbnails/{DEVICE}/2026/09/20/{EVENT}.jpg",
            confidence_score=Decimal("0.95"),
            duration_sec=12,
            ended_at=at(12),
        )
    )
    return event


async def test_event_round_trips_without_loss(session_factory):
    """存進去再讀出來,實體要完全相等——mapper 漏掉任何一個欄位都會在這裡現形。"""
    event = a_ready_event()

    async with SqlAlchemyDetectionUnitOfWork(session_factory) as uow:
        await uow.events.save(event)
        await uow.commit()

    async with SqlAlchemyDetectionUnitOfWork(session_factory) as uow:
        loaded = await uow.events.get(EVENT)

    assert loaded == event


async def test_timestamps_come_back_with_a_timezone(session_factory):
    """timestamptz:沒有時區的時間會讓保留期判定在不同機器上得到不同答案。"""
    async with SqlAlchemyDetectionUnitOfWork(session_factory) as uow:
        await uow.events.save(a_ready_event())
        await uow.commit()

    async with SqlAlchemyDetectionUnitOfWork(session_factory) as uow:
        loaded = await uow.events.get(EVENT)

    assert loaded.started_at.tzinfo is not None
    assert loaded.started_at.astimezone(UTC) == at(0)


async def test_confidence_score_keeps_two_decimal_places(session_factory):
    """numeric(3,2) 對應 Decimal;用 float 的話 0.6 門檻的比較會出現誤差。"""
    event = Event.begin(id=EVENT, device_id=DEVICE, started_at=at(0))
    event.mark_ready(
        UploadedMedia(
            video_object_key="videos/x.mp4",
            thumbnail_object_key="thumbnails/x.jpg",
            confidence_score=Decimal("0.60"),
            duration_sec=1,
            ended_at=at(1),
        )
    )

    async with SqlAlchemyDetectionUnitOfWork(session_factory) as uow:
        await uow.events.save(event)
        await uow.commit()

    async with SqlAlchemyDetectionUnitOfWork(session_factory) as uow:
        loaded = await uow.events.get(EVENT)

    assert loaded.confidence_score == Decimal("0.60")
    assert isinstance(loaded.confidence_score, Decimal)


async def test_updating_an_event_does_not_create_a_second_row(session_factory):
    async with SqlAlchemyDetectionUnitOfWork(session_factory) as uow:
        event = Event.begin(id=EVENT, device_id=DEVICE, started_at=at(0))
        await uow.events.save(event)
        await uow.commit()

    async with SqlAlchemyDetectionUnitOfWork(session_factory) as uow:
        loaded = await uow.events.get(EVENT)
        loaded.mark_failed()
        await uow.events.save(loaded)
        await uow.commit()

    async with SqlAlchemyDetectionUnitOfWork(session_factory) as uow:
        purged = await uow.events.delete_all_by_device(DEVICE)

    assert purged.deleted_count == 1


# --- 資料庫是最後一道防線 -------------------------------------------------


async def test_database_rejects_a_ready_event_without_media(session_factory):
    """繞過領域規則直接塞資料列時,ready_requires_media 仍然擋得下來。"""
    row = to_new_row(Event.begin(id=EVENT, device_id=DEVICE, started_at=at(0)))
    row.status = "ready"  # 沒有 object key 的 ready

    async with session_factory() as session:
        session.add(row)
        with pytest.raises(IntegrityError, match="ready_requires_media"):
            await session.flush()


async def test_database_rejects_an_out_of_range_confidence_score(session_factory):
    row = to_new_row(Event.begin(id=EVENT, device_id=DEVICE, started_at=at(0)))
    row.confidence_score = Decimal("1.50")

    async with session_factory() as session:
        session.add(row)
        with pytest.raises(IntegrityError, match="confidence_range"):
            await session.flush()


async def test_database_rejects_a_zero_duration(session_factory):
    """duration_sec > 0:極短的片段記為 1 秒,不是 0。"""
    row = to_new_row(Event.begin(id=EVENT, device_id=DEVICE, started_at=at(0)))
    row.duration_sec = 0

    async with session_factory() as session:
        session.add(row)
        with pytest.raises(IntegrityError, match="duration_positive"):
            await session.flush()


async def test_database_rejects_an_end_before_the_start(session_factory):
    row = to_new_row(Event.begin(id=EVENT, device_id=DEVICE, started_at=at(0)))
    row.ended_at = at(0) - timedelta(seconds=1)

    async with session_factory() as session:
        session.add(row)
        with pytest.raises(IntegrityError, match="time_order"):
            await session.flush()


async def test_database_rejects_an_unknown_status(session_factory):
    row = to_new_row(Event.begin(id=EVENT, device_id=DEVICE, started_at=at(0)))
    row.status = "uploading"

    async with session_factory() as session:
        session.add(row)
        with pytest.raises(IntegrityError, match="ck_events_status"):
            await session.flush()


async def test_is_partial_defaults_to_false(session_factory):
    """新增欄位的預設值(規格審查 #9):既有資料不會突然變成「不完整」。"""
    async with session_factory() as session:
        session.add(to_new_row(Event.begin(id=EVENT, device_id=DEVICE, started_at=at(0))))
        await session.commit()

    async with SqlAlchemyDetectionUnitOfWork(session_factory) as uow:
        assert (await uow.events.get(EVENT)).is_partial is False


async def test_now_is_not_used_for_timestamps(session_factory):
    """事件的時間來自錄影,不是寫入當下——補寫歷史事件時這個差別會放大。"""
    async with SqlAlchemyDetectionUnitOfWork(session_factory) as uow:
        await uow.events.save(a_ready_event())
        await uow.commit()

    async with SqlAlchemyDetectionUnitOfWork(session_factory) as uow:
        loaded = await uow.events.get(EVENT)

    assert loaded.started_at.astimezone(UTC) == at(0)
    assert loaded.started_at < datetime.now(UTC)
