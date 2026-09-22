"""密碼重設 token 的有效性判斷。

規格:02_spec_登入註冊與密碼重設.md 第 2.4 節——有效期 30 分鐘、一次性。
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.domains.accounts.domain.entities import RESET_TOKEN_TTL, PasswordResetToken
from app.domains.accounts.domain.exceptions import InvalidResetToken

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def make_token(**overrides: object) -> PasswordResetToken:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "token_hash": "hashed-token",
        "expires_at": NOW + timedelta(minutes=30),
        "used_at": None,
        "created_at": NOW,
    }
    return PasswordResetToken(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_issue_expires_30_minutes_after_creation() -> None:
    token = PasswordResetToken.issue(
        id=uuid.uuid4(), user_id=uuid.uuid4(), token_hash="hashed-token", now=NOW
    )
    assert token.expires_at == NOW + timedelta(minutes=30)
    assert RESET_TOKEN_TTL == timedelta(minutes=30)
    assert token.used_at is None


def test_unused_and_unexpired_token_passes() -> None:
    make_token().ensure_usable(now=NOW)


def test_expired_token_is_rejected() -> None:
    token = make_token(expires_at=NOW - timedelta(seconds=1))
    with pytest.raises(InvalidResetToken):
        token.ensure_usable(now=NOW)


def test_token_expiring_exactly_now_is_rejected() -> None:
    token = make_token(expires_at=NOW)
    with pytest.raises(InvalidResetToken):
        token.ensure_usable(now=NOW)


def test_already_used_token_is_rejected() -> None:
    """一次性:重設成功後 used_at 被寫入,同一個連結再點一次就無效。"""
    token = make_token(used_at=NOW - timedelta(minutes=1))
    with pytest.raises(InvalidResetToken):
        token.ensure_usable(now=NOW)


def test_invalid_reset_token_uses_auth_007() -> None:
    token = make_token(used_at=NOW)
    with pytest.raises(InvalidResetToken) as exc_info:
        token.ensure_usable(now=NOW)
    assert exc_info.value.code == "AUTH_007"
