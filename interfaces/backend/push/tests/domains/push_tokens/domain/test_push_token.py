"""push_tokens 領域的業務規則(09_spec 第 2.4 節)。"""

import pytest

from app.domains.push_tokens.domain.entities import ClientPlatform, PushToken
from app.domains.push_tokens.domain.exceptions import BlankPushToken
from tests.domains.push_tokens.builders import ALICE, BOB, NOW, TOKEN_ID, a_push_token


def test_register_binds_endpoint_to_the_logged_in_user():
    """09_spec 第 2.4 節:token 綁定於目前登入的使用者帳號。"""
    token = PushToken.register(
        id=TOKEN_ID, user_id=ALICE, platform=ClientPlatform.APP, token="fcm-abc", now=NOW
    )

    assert token.user_id == ALICE
    assert token.platform is ClientPlatform.APP
    assert token.created_at == NOW


@pytest.mark.parametrize("blank", ["", "   "])
def test_register_rejects_blank_token(blank):
    """空白 token 無法送達任何端點,不該進資料表。"""
    with pytest.raises(BlankPushToken):
        PushToken.register(
            id=TOKEN_ID, user_id=ALICE, platform=ClientPlatform.APP, token=blank, now=NOW
        )


def test_rebinding_to_a_new_owner_keeps_the_same_registration():
    """審查 #4:同一支手機換帳號登入時,既有紀錄改綁新登入者,id 不變。

    唯一鍵是 (platform, token),不含 user_id;若不改綁,前一位使用者的寵物活動
    會推到現在由他人使用的裝置上。
    """
    token = a_push_token(user_id=ALICE)

    token.rebind_to(BOB)

    assert token.user_id == BOB
    assert token.id == TOKEN_ID


def test_is_owned_by_distinguishes_the_owner():
    """審查 #5:刪除前要能判斷擁有者,否則任何登入者可刪除他人的 token。"""
    token = a_push_token(user_id=ALICE)

    assert token.is_owned_by(ALICE) is True
    assert token.is_owned_by(BOB) is False
