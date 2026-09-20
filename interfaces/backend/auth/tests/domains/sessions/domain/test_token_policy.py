"""Token 效期政策與 refresh token 的可用性。

規格:02_spec_登入註冊與密碼重設.md 第 2.3、2.3.1、2.3.2、2.6、2.8 節。
平台差異表整張都是 sessions 的業務規則,所以這些斷言全部落在 domain。
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.domains.sessions.domain.entities import (
    APP_ACCESS_TOKEN_TTL,
    APP_EXTEND_AFTER,
    WEB_ACCESS_TOKEN_TTL,
    WEB_REFRESH_TOKEN_TTL,
    AccessToken,
    RefreshToken,
)
from app.shared_kernel.platform import Platform

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
USER_ID = uuid.uuid4()


def test_web_access_token_lives_for_one_hour() -> None:
    token = AccessToken.issue(user_id=USER_ID, platform=Platform.WEB, now=NOW)
    assert token.expires_at == NOW + timedelta(hours=1)
    assert WEB_ACCESS_TOKEN_TTL == timedelta(hours=1)


def test_app_access_token_lives_for_180_days() -> None:
    token = AccessToken.issue(user_id=USER_ID, platform=Platform.APP, now=NOW)
    assert token.expires_at == NOW + timedelta(days=180)
    assert APP_ACCESS_TOKEN_TTL == timedelta(days=180)


def test_access_token_carries_the_claims_the_spec_defines() -> None:
    """§2.8:sub / iat / exp / platform,其餘服務只認這四個。"""
    token = AccessToken.issue(user_id=USER_ID, platform=Platform.WEB, now=NOW)
    assert token.claims() == {
        "sub": str(USER_ID),
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(hours=1)).timestamp()),
        "platform": "web",
    }


def test_web_refresh_token_lives_for_30_days() -> None:
    token = RefreshToken.issue(
        id=uuid.uuid4(), user_id=USER_ID, token_hash="hashed", now=NOW
    )
    assert token.expires_at == NOW + timedelta(days=30)
    assert WEB_REFRESH_TOKEN_TTL == timedelta(days=30)
    assert token.revoked_at is None


def test_fresh_refresh_token_is_usable() -> None:
    token = RefreshToken.issue(
        id=uuid.uuid4(), user_id=USER_ID, token_hash="hashed", now=NOW
    )
    assert token.is_usable(now=NOW) is True


def test_expired_refresh_token_is_not_usable() -> None:
    token = RefreshToken.issue(
        id=uuid.uuid4(), user_id=USER_ID, token_hash="hashed", now=NOW
    )
    assert token.is_usable(now=NOW + timedelta(days=30, seconds=1)) is False


def test_revoked_refresh_token_is_not_usable() -> None:
    token = RefreshToken.issue(
        id=uuid.uuid4(), user_id=USER_ID, token_hash="hashed", now=NOW
    )
    token.revoked_at = NOW
    assert token.is_usable(now=NOW) is False


def test_app_token_younger_than_7_days_does_not_need_extension() -> None:
    token = AccessToken.issue(user_id=USER_ID, platform=Platform.APP, now=NOW)
    assert token.needs_extension(now=NOW + timedelta(days=7) - timedelta(seconds=1)) is False


def test_app_token_older_than_7_days_needs_extension() -> None:
    token = AccessToken.issue(user_id=USER_ID, platform=Platform.APP, now=NOW)
    assert token.needs_extension(now=NOW + timedelta(days=7)) is True
    assert APP_EXTEND_AFTER == timedelta(days=7)


def test_web_token_never_needs_extension() -> None:
    """展延是 App 專用機制;Web 走 refresh token rotation(§2.6)。"""
    token = AccessToken.issue(user_id=USER_ID, platform=Platform.WEB, now=NOW)
    assert token.needs_extension(now=NOW + timedelta(days=365)) is False


@pytest.mark.parametrize(
    ("platform", "expected"), [(Platform.WEB, True), (Platform.APP, False)]
)
def test_only_web_issues_a_refresh_token(platform: Platform, expected: bool) -> None:
    """§2.3:App 不使用 refresh token,靠滑動展延維持長期登入。"""
    assert platform.uses_refresh_token is expected
