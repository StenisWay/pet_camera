import uuid
from urllib.parse import parse_qs, urlparse

import pytest

from app.domains.drive_export.application.dtos import CompleteAuthorizationCommand
from app.domains.drive_export.application.ports import OAuthTokens
from app.domains.drive_export.application.use_cases.complete_authorization import (
    CompleteAuthorization,
)
from app.domains.drive_export.application.use_cases.start_authorization import StartAuthorization
from app.domains.drive_export.domain.entities import DRIVE_FILE_SCOPE
from app.domains.drive_export.domain.exceptions import InvalidOAuthState
from app.shared_kernel.errors import ServiceUnavailable
from tests.domains.drive_export.builders import OWNER, a_connection


@pytest.fixture
def start(oauth, states) -> StartAuthorization:
    return StartAuthorization(oauth, states)


@pytest.fixture
def complete(uow, oauth, states, clock, ids) -> CompleteAuthorization:
    return CompleteAuthorization(uow, oauth, states, clock, ids)


async def issued_state(start: StartAuthorization, owner_id=OWNER) -> str:
    url = (await start.execute(owner_id)).authorization_url
    return parse_qs(urlparse(url).query)["state"][0]


async def test_authorization_url_requests_only_drive_file_scope(start):
    """12_spec 第 2.3.2 節驗收。"""
    url = (await start.execute(OWNER)).authorization_url

    assert parse_qs(urlparse(url).query)["scope"][0].split() == [DRIVE_FILE_SCOPE]


async def test_state_is_issued_bound_to_the_user(start, states):
    """規格審查 #8:state 綁定 user_id 並設 TTL,回呼時驗證,防 CSRF。"""
    state = await issued_state(start)

    assert states.states[state] == OWNER
    assert states.ttls[state] == 600


async def test_authorization_fails_closed_when_state_store_is_down(start, states):
    """限流可以 fail-open(13_ADR 第 4 節),CSRF 防護不行。"""
    states.available = False

    with pytest.raises(ServiceUnavailable):
        await start.execute(OWNER)


async def test_completing_with_unknown_state_is_rejected(complete):
    with pytest.raises(InvalidOAuthState):
        await complete.execute(
            CompleteAuthorizationCommand(owner_id=OWNER, code="c", state="never-issued")
        )


async def test_state_issued_to_another_user_is_rejected(start, complete):
    """別人的 state 不能拿來把 Drive 綁到自己帳號上。"""
    state = await issued_state(start, owner_id=uuid.uuid4())

    with pytest.raises(InvalidOAuthState):
        await complete.execute(
            CompleteAuthorizationCommand(owner_id=OWNER, code="c", state=state)
        )


async def test_state_can_only_be_used_once(start, complete, oauth, uow):
    state = await issued_state(start)
    oauth.codes["c"] = OAuthTokens(access_token="at", refresh_token="rt-9")
    await complete.execute(CompleteAuthorizationCommand(owner_id=OWNER, code="c", state=state))

    with pytest.raises(InvalidOAuthState):
        await complete.execute(
            CompleteAuthorizationCommand(owner_id=OWNER, code="c", state=state)
        )


async def test_successful_callback_stores_the_refresh_token(start, complete, oauth, uow):
    state = await issued_state(start)
    oauth.codes["c"] = OAuthTokens(access_token="at", refresh_token="rt-9")

    await complete.execute(CompleteAuthorizationCommand(owner_id=OWNER, code="c", state=state))

    assert (await uow.connections.get_by_owner(OWNER)).refresh_token == "rt-9"


async def test_reauthorization_without_new_refresh_token_keeps_the_old_one(
    start, complete, oauth, uow
):
    """Google 對已授權過的帳號可能不再回傳 refresh token——舊憑證仍然有效,
    不可以被覆蓋成空值,否則使用者會莫名其妙斷線。"""
    uow.given(a_connection(refresh_token="rt-1", folder_id="folder-1"))
    state = await issued_state(start)
    oauth.codes["c"] = OAuthTokens(access_token="at", refresh_token=None)

    await complete.execute(CompleteAuthorizationCommand(owner_id=OWNER, code="c", state=state))

    stored = await uow.connections.get_by_owner(OWNER)
    assert stored.refresh_token == "rt-1"
    assert stored.folder_id == "folder-1"


async def test_first_authorization_without_refresh_token_is_rejected(start, complete, oauth):
    """從未綁定過卻拿不到 refresh token,等於什麼都沒綁成,要讓使用者重跑一次。"""
    state = await issued_state(start)
    oauth.codes["c"] = OAuthTokens(access_token="at", refresh_token=None)

    with pytest.raises(InvalidOAuthState):
        await complete.execute(
            CompleteAuthorizationCommand(owner_id=OWNER, code="c", state=state)
        )


async def test_callback_fails_closed_when_state_store_is_down(complete, states):
    states.available = False

    with pytest.raises(ServiceUnavailable):
        await complete.execute(
            CompleteAuthorizationCommand(owner_id=OWNER, code="c", state="s")
        )


async def test_reauthorization_replaces_the_refresh_token(start, complete, oauth, uow):
    """12_spec 第 2.3.4 節:授權變更後重新綁定,換掉舊 token。"""
    uow.given(a_connection(refresh_token="rt-1", folder_id="folder-1"))
    state = await issued_state(start)
    oauth.codes["c"] = OAuthTokens(access_token="at", refresh_token="rt-2")

    await complete.execute(CompleteAuthorizationCommand(owner_id=OWNER, code="c", state=state))

    stored = await uow.connections.get_by_owner(OWNER)
    assert stored.refresh_token == "rt-2"
    assert stored.folder_id == "folder-1"
