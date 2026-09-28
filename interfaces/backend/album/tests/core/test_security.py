from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.security import TokenExpired, TokenInvalid, decode_access_token

SECRET = "test-secret-that-is-long-enough-for-hmac"


def make_token(**claims) -> str:
    payload = {"sub": str(uuid4()), "exp": datetime.now(UTC) + timedelta(hours=1), **claims}
    return jwt.encode(payload, SECRET, algorithm="HS256")


def test_returns_the_user_id_from_sub():
    user_id = uuid4()

    assert decode_access_token(make_token(sub=str(user_id)), secret=SECRET) == user_id


def test_expired_token_maps_to_auth_002():
    """10_錯誤處理與狀態規範.md:AUTH_002「登入已逾時」與 AUTH_001「請重新登入」
    是不同文案,前端要分得出來。"""
    token = make_token(exp=datetime.now(UTC) - timedelta(seconds=1))

    with pytest.raises(TokenExpired) as exc:
        decode_access_token(token, secret=SECRET)
    assert exc.value.code == "AUTH_002"


def test_token_signed_with_another_key_is_rejected():
    token = jwt.encode({"sub": str(uuid4())}, "attacker-key-long-enough", algorithm="HS256")

    with pytest.raises(TokenInvalid) as exc:
        decode_access_token(token, secret=SECRET)
    assert exc.value.code == "AUTH_001"


@pytest.mark.parametrize("bad_sub", ["not-a-uuid", "", None])
def test_token_without_a_usable_subject_is_rejected(bad_sub):
    with pytest.raises(TokenInvalid):
        decode_access_token(make_token(sub=bad_sub), secret=SECRET)


def test_alg_none_token_is_rejected():
    """不接受 alg=none:否則任何人自行組一個 token 就能冒充別的使用者。"""
    token = jwt.encode({"sub": str(uuid4())}, key="", algorithm="none")

    with pytest.raises(TokenInvalid):
        decode_access_token(token, secret=SECRET)


def test_token_without_expiry_is_rejected():
    token = jwt.encode({"sub": str(uuid4())}, SECRET, algorithm="HS256")

    with pytest.raises(TokenInvalid):
        decode_access_token(token, secret=SECRET)
