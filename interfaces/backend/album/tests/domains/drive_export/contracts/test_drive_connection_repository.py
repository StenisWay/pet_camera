import uuid

from tests.domains.drive_export.builders import NOW, OWNER, a_connection


async def test_get_missing_connection_returns_none(store):
    async with store.uow() as uow:
        assert await uow.connections.get_by_owner(uuid.uuid4()) is None


async def test_committed_connection_can_be_loaded(store):
    connection = a_connection(refresh_token="rt-1")

    async with store.uow() as uow:
        await uow.connections.save(connection)
        await uow.commit()

    async with store.uow() as uow:
        loaded = await uow.connections.get_by_owner(OWNER)

    assert loaded.refresh_token == "rt-1"
    assert loaded.owner_id == OWNER
    assert loaded.connected_at == NOW


async def test_uncommitted_save_is_rolled_back(store):
    async with store.uow() as uow:
        await uow.connections.save(a_connection())

    async with store.uow() as uow:
        assert await uow.connections.get_by_owner(OWNER) is None


async def test_saving_again_replaces_the_refresh_token(store):
    """12_spec 第 2.3.4 節:授權變更後可重新綁定,同一使用者只留一份。"""
    connection = a_connection(refresh_token="rt-1")
    async with store.uow() as uow:
        await uow.connections.save(connection)
        await uow.commit()

    async with store.uow() as uow:
        loaded = await uow.connections.get_by_owner(OWNER)
        loaded.reauthorize("rt-2", NOW)
        await uow.connections.save(loaded)
        await uow.commit()

    async with store.uow() as uow:
        assert (await uow.connections.get_by_owner(OWNER)).refresh_token == "rt-2"


async def test_remembered_folder_survives_reauthorization(store):
    async with store.uow() as uow:
        await uow.connections.save(a_connection(folder_id="folder-1"))
        await uow.commit()

    async with store.uow() as uow:
        loaded = await uow.connections.get_by_owner(OWNER)
        loaded.reauthorize("rt-2", NOW)
        await uow.connections.save(loaded)
        await uow.commit()

    async with store.uow() as uow:
        assert (await uow.connections.get_by_owner(OWNER)).folder_id == "folder-1"


async def test_committed_delete_removes_the_connection(store):
    async with store.uow() as uow:
        await uow.connections.save(a_connection())
        await uow.commit()

    async with store.uow() as uow:
        await uow.connections.delete_by_owner(OWNER)
        await uow.commit()

    async with store.uow() as uow:
        assert await uow.connections.get_by_owner(OWNER) is None


async def test_deleting_a_missing_connection_is_not_an_error(store):
    async with store.uow() as uow:
        await uow.connections.delete_by_owner(uuid.uuid4())
        await uow.commit()
