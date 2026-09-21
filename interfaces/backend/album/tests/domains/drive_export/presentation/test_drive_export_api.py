import uuid
from urllib.parse import parse_qs, urlparse

from app.domains.drive_export.application.ports import OAuthTokens, PreparedExport
from tests.domains.album.builders import OWNER
from tests.domains.drive_export.builders import a_connection, exportable

pytest_plugins = ["tests.domains.album.presentation.conftest"]


async def issue_state(client) -> str:
    url = (await client.get("/integrations/google-drive/oauth-url")).json()["authorization_url"]
    return parse_qs(urlparse(url).query)["state"][0]


async def test_oauth_url_endpoint_returns_google_link(client):
    response = await client.get("/integrations/google-drive/oauth-url")

    assert response.status_code == 200
    assert response.json()["authorization_url"].startswith("https://accounts.google.com/")


async def test_oauth_callback_binds_the_connection(client, drive_uow, oauth):
    state = await issue_state(client)
    oauth.codes["code-1"] = OAuthTokens(access_token="at", refresh_token="rt-9")

    response = await client.post(
        "/integrations/google-drive/oauth-callback", json={"code": "code-1", "state": state}
    )

    assert response.status_code == 204
    assert (await drive_uow.connections.get_by_owner(OWNER)).refresh_token == "rt-9"


async def test_forged_state_returns_403(client):
    response = await client.post(
        "/integrations/google-drive/oauth-callback", json={"code": "c", "state": "forged"}
    )

    assert response.status_code == 403


async def test_export_without_connection_returns_drive_001(client):
    """12_spec 第 5 節:DRIVE_001 / 401,前端阻斷式導向 OAuth 授權頁。"""
    response = await client.post(
        "/media/export/google-drive", json={"media_item_ids": [str(uuid.uuid4())]}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "DRIVE_001"


async def test_accepted_export_returns_202_and_schedules_a_job(
    client, drive_uow, album_content, scheduler
):
    drive_uow.given(a_connection())
    media = exportable()
    album_content.will_prepare(media)

    response = await client.post(
        "/media/export/google-drive", json={"media_item_ids": [str(media.id)]}
    )

    assert response.status_code == 202
    assert response.json()["accepted_ids"] == [str(media.id)]
    assert [j.media_item_id for j in scheduler.jobs] == [media.id]


async def test_skipped_items_are_reported(client, drive_uow, album_content):
    drive_uow.given(a_connection())
    skipped = uuid.uuid4()
    album_content.prepared = PreparedExport(accepted=[], skipped_ids=[skipped])

    body = (
        await client.post(
            "/media/export/google-drive", json={"media_item_ids": [str(skipped)]}
        )
    ).json()

    assert body["accepted_ids"] == []
    assert body["skipped_ids"] == [str(skipped)]


async def test_batch_over_the_limit_is_rejected_by_the_schema(client, drive_uow):
    """規格審查 #6:51 筆在 schema 層就擋掉,不必進到 use case。"""
    drive_uow.given(a_connection())

    response = await client.post(
        "/media/export/google-drive",
        json={"media_item_ids": [str(uuid.uuid4()) for _ in range(51)]},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VAL_001"


async def test_empty_selection_is_rejected(client, drive_uow):
    drive_uow.given(a_connection())

    response = await client.post("/media/export/google-drive", json={"media_item_ids": []})

    assert response.status_code == 400
