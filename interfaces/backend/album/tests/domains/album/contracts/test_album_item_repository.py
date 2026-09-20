import uuid
from datetime import UTC, datetime, timedelta

from app.domains.album.domain.entities import DriveExportStatus
from tests.domains.album.builders import OWNER, an_item

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


async def test_get_missing_item_returns_none(store):
    async with store.uow() as uow:
        assert await uow.items.get(uuid.uuid4()) is None


async def test_seeded_item_can_be_loaded(store):
    item = await store.seed(an_item())

    async with store.uow() as uow:
        loaded = await uow.items.get(item.id)

    assert loaded.id == item.id
    assert loaded.owner_id == item.owner_id
    assert loaded.status is item.status
    assert loaded.object_key == item.object_key


async def test_get_many_returns_only_existing_items(store):
    item = await store.seed(an_item())

    async with store.uow() as uow:
        found = await uow.items.get_many([item.id, uuid.uuid4()])

    assert list(found) == [item.id]


async def test_get_many_with_no_ids_returns_empty(store):
    async with store.uow() as uow:
        assert await uow.items.get_many([]) == {}


async def test_committed_export_state_is_persisted(store):
    item = await store.seed(an_item())

    async with store.uow() as uow:
        loaded = await uow.items.get(item.id)
        loaded.start_export(NOW)
        loaded.complete_export(drive_file_id="drive-1", now=NOW)
        await uow.items.save(loaded)
        await uow.commit()

    async with store.uow() as uow:
        stored = await uow.items.get(item.id)

    assert stored.drive_export_status is DriveExportStatus.EXPORTED
    assert stored.drive_file_id == "drive-1"


async def test_uncommitted_save_is_rolled_back(store):
    item = await store.seed(an_item())

    async with store.uow() as uow:
        loaded = await uow.items.get(item.id)
        loaded.start_export(NOW)
        await uow.items.save(loaded)  # 沒有 commit

    async with store.uow() as uow:
        stored = await uow.items.get(item.id)

    assert stored.drive_export_status is DriveExportStatus.NOT_EXPORTED


async def test_modifying_loaded_entity_without_save_is_not_persisted(store):
    item = await store.seed(an_item())

    async with store.uow() as uow:
        loaded = await uow.items.get(item.id)
        loaded.start_export(NOW)
        await uow.commit()  # 沒有 save

    async with store.uow() as uow:
        stored = await uow.items.get(item.id)

    assert stored.drive_export_status is DriveExportStatus.NOT_EXPORTED


async def test_committed_delete_removes_the_item(store):
    item = await store.seed(an_item())

    async with store.uow() as uow:
        await uow.items.delete(item.id)
        await uow.commit()

    async with store.uow() as uow:
        assert await uow.items.get(item.id) is None


async def test_uncommitted_delete_is_rolled_back(store):
    item = await store.seed(an_item())

    async with store.uow() as uow:
        await uow.items.delete(item.id)

    async with store.uow() as uow:
        assert await uow.items.get(item.id) is not None


async def test_delete_all_owned_by_returns_object_keys_and_spares_others(store):
    mine = await store.seed(
        an_item(object_key="media/a.mp4", thumbnail_object_key="media-thumbnails/a.jpg")
    )
    theirs = await store.seed(an_item(owner_id=uuid.uuid4()))

    async with store.uow() as uow:
        keys = await uow.items.delete_all_owned_by(OWNER)
        await uow.commit()

    assert set(keys) == {"media/a.mp4", "media-thumbnails/a.jpg"}
    async with store.uow() as uow:
        assert await uow.items.get(mine.id) is None
        assert await uow.items.get(theirs.id) is not None


async def test_list_stale_exports_only_returns_items_past_the_cutoff(store):
    stale = await store.seed(
        an_item(
            drive_export_status=DriveExportStatus.EXPORTING,
            export_state_changed_at=NOW - timedelta(minutes=30),
        )
    )
    await store.seed(an_item())  # 沒在匯出中,不該出現

    async with store.uow() as uow:
        found = await uow.items.list_stale_exports(changed_before=NOW + timedelta(days=1))

    assert [i.id for i in found] == [stale.id]
