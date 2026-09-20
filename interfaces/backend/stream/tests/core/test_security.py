"""access token 驗證與鏡頭身分驗證。

Stream 只驗證 Auth 服務簽發的 token(02_spec 第 2.3.2 節),不簽發也不換發。
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.security import (
    SharedSecretCameraAuthenticator,
    TokenExpired,
    TokenInvalid,
    decode_access_token,
)
from app.shared_kernel.errors import PermissionDenied
from tests.domains.streaming.builders import ALICE, DEVICE_A

SECRET = "test-secret-at-least-32-bytes-long!!"


def token(**claims: object) -> str:
    payload: dict[str, object] = {
        "sub": str(ALICE),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    payload.update(claims)
    return jwt.encode(payload, SECRET, algorithm="HS256")


def test_valid_token_yields_the_user_id() -> None:
    assert decode_access_token(token(), secret=SECRET) == ALICE


def test_expired_token_is_auth_002() -> None:
    expired = token(exp=datetime.now(UTC) - timedelta(seconds=1))

    with pytest.raises(TokenExpired) as caught:
        decode_access_token(expired, secret=SECRET)

    assert caught.value.code == "AUTH_002"


def test_token_signed_with_another_secret_is_rejected() -> None:
    with pytest.raises(TokenInvalid):
        decode_access_token(token(), secret="a-different-secret-of-sufficient-len")


def test_token_without_exp_is_rejected() -> None:
    """沒有 exp 的 token 等於永久有效,登出與逾時都失去意義。"""
    forever = jwt.encode({"sub": str(ALICE)}, SECRET, algorithm="HS256")

    with pytest.raises(TokenInvalid):
        decode_access_token(forever, secret=SECRET)


def test_token_without_sub_is_rejected() -> None:
    no_subject = jwt.encode(
        {"exp": datetime.now(UTC) + timedelta(hours=1)}, SECRET, algorithm="HS256"
    )

    with pytest.raises(TokenInvalid):
        decode_access_token(no_subject, secret=SECRET)


def test_non_uuid_subject_is_rejected() -> None:
    with pytest.raises(TokenInvalid):
        decode_access_token(token(sub="not-a-uuid"), secret=SECRET)


def test_alg_none_is_rejected() -> None:
    """明確指定演算法清單,擋掉 alg=none 與演算法混淆攻擊。"""
    unsigned = jwt.encode(
        {"sub": str(ALICE), "exp": datetime.now(UTC) + timedelta(hours=1)},
        key="",
        algorithm="none",
    )

    with pytest.raises(TokenInvalid):
        decode_access_token(unsigned, secret=SECRET)


def test_garbage_is_rejected() -> None:
    with pytest.raises(TokenInvalid):
        decode_access_token("not.a.token", secret=SECRET)


async def test_camera_shared_secret_accepts_the_right_credential() -> None:
    await SharedSecretCameraAuthenticator("camera-secret").authenticate(DEVICE_A, "camera-secret")


@pytest.mark.parametrize("credential", [None, "", "wrong"])
async def test_camera_shared_secret_rejects_everything_else(credential: str | None) -> None:
    with pytest.raises(PermissionDenied):
        await SharedSecretCameraAuthenticator("camera-secret").authenticate(DEVICE_A, credential)


async def test_shared_secret_cannot_tell_cameras_apart() -> None:
    """已知限制(06_spec 第 9 節待確認事項):拿到共享金鑰的任一鏡頭都能冒充其他鏡頭。

    這個測試把限制寫下來——Device 服務定出逐裝置憑證後,它應該要失敗,
    那正是提醒換掉實作的訊號。
    """
    authenticator = SharedSecretCameraAuthenticator("camera-secret")

    await authenticator.authenticate(DEVICE_A, "camera-secret")
    await authenticator.authenticate(uuid.uuid4(), "camera-secret")
