"""User 實體:帳密驗證與登入失敗鎖定。

規格:02_spec_登入註冊與密碼重設.md 第 2.3 節、05_spec_帳號設定.md 第 2.1 節。
時間一律由外部傳入,實體不呼叫 datetime.now()——否則鎖定期滿這類規則無法確定地測試。
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.domains.accounts.domain.entities import LOCKOUT_DURATION, MAX_LOGIN_ATTEMPTS, User
from app.domains.accounts.domain.exceptions import (
    AccountLocked,
    InvalidCredentials,
    InvalidCurrentPassword,
)
from app.domains.accounts.domain.services import PasswordHasher
from app.domains.accounts.domain.value_objects import Email, RawPassword

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


class ReversingHasher(PasswordHasher):
    """測試用雜湊:可逆、確定,但形狀與真實雜湊一樣是不透明字串。

    正式實作是 bcrypt;兩者由 tests/domains/accounts/contracts/ 的合約測試保證
    行為一致(hash 後 verify 得過、換個密碼驗不過)。
    """

    def hash(self, raw: RawPassword) -> str:
        return "hashed:" + raw.value

    def verify(self, raw: RawPassword, password_hash: str) -> bool:
        return password_hash == "hashed:" + raw.value


HASHER = ReversingHasher()


def make_user(**overrides: object) -> User:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "email": Email.parse("owner@example.com"),
        "password_hash": HASHER.hash(RawPassword.parse("correct1")),
        "failed_login_attempts": 0,
        "locked_until": None,
        "created_at": NOW,
    }
    return User(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_register_creates_user_with_hashed_password_and_clean_counters() -> None:
    user = User.register(
        id=uuid.uuid4(),
        email=Email.parse("New@Example.com"),
        password=RawPassword.parse("abcd1234"),
        hasher=HASHER,
        now=NOW,
    )
    assert user.email.value == "new@example.com"
    assert user.password_hash == "hashed:abcd1234"
    assert user.password_hash != "abcd1234"
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def test_authenticate_with_correct_password_succeeds() -> None:
    user = make_user()
    user.authenticate(RawPassword.parse("correct1"), hasher=HASHER, now=NOW)
    assert user.failed_login_attempts == 0


def test_successful_authentication_resets_the_failure_counter() -> None:
    user = make_user(failed_login_attempts=3)
    user.authenticate(RawPassword.parse("correct1"), hasher=HASHER, now=NOW)
    assert user.failed_login_attempts == 0


@pytest.mark.parametrize("already_failed", [0, 1, 2, 3])
def test_failed_attempt_below_the_threshold_raises_invalid_credentials(
    already_failed: int,
) -> None:
    user = make_user(failed_login_attempts=already_failed)
    with pytest.raises(InvalidCredentials):
        user.authenticate(RawPassword.parse("wrong123"), hasher=HASHER, now=NOW)
    assert user.failed_login_attempts == already_failed + 1
    assert user.locked_until is None


def test_fifth_consecutive_failure_locks_the_account_for_15_minutes() -> None:
    user = make_user(failed_login_attempts=MAX_LOGIN_ATTEMPTS - 1)
    with pytest.raises(AccountLocked):
        user.authenticate(RawPassword.parse("wrong123"), hasher=HASHER, now=NOW)
    assert user.failed_login_attempts == MAX_LOGIN_ATTEMPTS
    assert user.locked_until == NOW + LOCKOUT_DURATION
    assert LOCKOUT_DURATION == timedelta(minutes=15)


def test_locked_account_rejects_even_the_correct_password() -> None:
    """鎖定期間一律 AUTH_005,不得放行——否則暴力破解只要猜中就繞過鎖定。"""
    user = make_user(
        failed_login_attempts=MAX_LOGIN_ATTEMPTS,
        locked_until=NOW + timedelta(minutes=5),
    )
    with pytest.raises(AccountLocked):
        user.authenticate(RawPassword.parse("correct1"), hasher=HASHER, now=NOW)
    assert user.failed_login_attempts == MAX_LOGIN_ATTEMPTS  # 不重新計數


def test_account_locked_carries_remaining_seconds() -> None:
    """§5:AUTH_005 的呈現方式是阻斷式對話框 + 倒數時間。"""
    user = make_user(
        failed_login_attempts=MAX_LOGIN_ATTEMPTS,
        locked_until=NOW + timedelta(minutes=5),
    )
    with pytest.raises(AccountLocked) as exc_info:
        user.authenticate(RawPassword.parse("correct1"), hasher=HASHER, now=NOW)
    assert exc_info.value.code == "AUTH_005"
    assert exc_info.value.retry_after_seconds == 300


def test_counter_restarts_after_the_lockout_expires() -> None:
    user = make_user(
        failed_login_attempts=MAX_LOGIN_ATTEMPTS,
        locked_until=NOW - timedelta(seconds=1),
    )
    with pytest.raises(InvalidCredentials):
        user.authenticate(RawPassword.parse("wrong123"), hasher=HASHER, now=NOW)
    assert user.failed_login_attempts == 1
    assert user.locked_until is None


def test_successful_login_after_the_lockout_expires_clears_the_lock() -> None:
    user = make_user(
        failed_login_attempts=MAX_LOGIN_ATTEMPTS,
        locked_until=NOW - timedelta(seconds=1),
    )
    user.authenticate(RawPassword.parse("correct1"), hasher=HASHER, now=NOW)
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def test_oauth_only_account_can_never_authenticate_with_a_password() -> None:
    """§2.7:password_hash 為 null 的帳號不得被任何密碼登入。"""
    user = make_user(password_hash=None)
    with pytest.raises(InvalidCredentials):
        user.authenticate(RawPassword.parse("anything1"), hasher=HASHER, now=NOW)
    assert user.failed_login_attempts == 1


def test_invalid_credentials_uses_auth_003() -> None:
    user = make_user()
    with pytest.raises(InvalidCredentials) as exc_info:
        user.authenticate(RawPassword.parse("wrong123"), hasher=HASHER, now=NOW)
    assert exc_info.value.code == "AUTH_003"


def test_change_password_requires_the_current_one_when_a_password_is_set() -> None:
    user = make_user()
    user.change_password(
        current=RawPassword.parse("correct1"),
        new=RawPassword.parse("brandnew2"),
        hasher=HASHER,
        now=NOW,
    )
    assert user.password_hash == "hashed:brandnew2"


def test_change_password_with_a_wrong_current_password_raises_auth_008() -> None:
    user = make_user()
    with pytest.raises(InvalidCurrentPassword) as exc_info:
        user.change_password(
            current=RawPassword.parse("wrong123"),
            new=RawPassword.parse("brandnew2"),
            hasher=HASHER,
            now=NOW,
        )
    assert exc_info.value.code == "AUTH_008"
    assert user.password_hash == "hashed:correct1"


def test_oauth_only_account_sets_a_password_without_supplying_the_current_one() -> None:
    """05_spec 第 2.1 節:password_hash 為 null 時顯示「設定密碼」,不需目前密碼。"""
    user = make_user(password_hash=None)
    assert user.has_password() is False
    user.change_password(
        current=None, new=RawPassword.parse("brandnew2"), hasher=HASHER, now=NOW
    )
    assert user.password_hash == "hashed:brandnew2"
    assert user.has_password() is True


def test_account_with_a_password_must_supply_the_current_one() -> None:
    user = make_user()
    with pytest.raises(InvalidCurrentPassword):
        user.change_password(
            current=None, new=RawPassword.parse("brandnew2"), hasher=HASHER, now=NOW
        )


def test_changing_password_does_not_lock_out_on_repeated_mistakes() -> None:
    """鎖定只計算 /auth/login 的失敗(§2.3),改密碼打錯不該把自己鎖出去。"""
    user = make_user()
    for _ in range(MAX_LOGIN_ATTEMPTS + 1):
        with pytest.raises(InvalidCurrentPassword):
            user.change_password(
                current=RawPassword.parse("wrong123"),
                new=RawPassword.parse("brandnew2"),
                hasher=HASHER,
                now=NOW,
            )
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def test_reset_password_does_not_require_the_current_one() -> None:
    """§2.4:重設流程的憑據是信裡的 token,不是舊密碼——使用者正是因為忘記才來的。"""
    user = make_user()
    user.reset_password(RawPassword.parse("brandnew2"), hasher=HASHER)
    assert user.password_hash == "hashed:brandnew2"


def test_reset_password_clears_an_active_lockout() -> None:
    """重設密碼等於證明了信箱所有權,沒理由讓使用者繼續被鎖在門外。"""
    user = make_user(
        failed_login_attempts=MAX_LOGIN_ATTEMPTS,
        locked_until=NOW + timedelta(minutes=10),
    )
    user.reset_password(RawPassword.parse("brandnew2"), hasher=HASHER)
    assert user.failed_login_attempts == 0
    assert user.locked_until is None
    user.authenticate(RawPassword.parse("brandnew2"), hasher=HASHER, now=NOW)


def test_reset_password_works_for_an_oauth_only_account() -> None:
    """§2.7:純第三方帳號可以透過忘記密碼流程設定密碼。"""
    user = make_user(password_hash=None)
    user.reset_password(RawPassword.parse("brandnew2"), hasher=HASHER)
    assert user.has_password() is True
