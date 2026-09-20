"""密碼強度規則。

規格:02_spec_登入註冊與密碼重設.md 第 2.1 節。
「至多 72 碼」是 bcrypt 的 72 **bytes** 上限;規格同時限定可列印 ASCII,
所以字元數等於位元組數(規格審查 #16)。
"""

import pytest

from app.domains.accounts.domain.exceptions import WeakPassword
from app.domains.accounts.domain.value_objects import RawPassword


def test_valid_password_is_accepted() -> None:
    assert RawPassword.parse("abcd1234").value == "abcd1234"


@pytest.mark.parametrize("raw", ["", "a1", "abc123", "abcd123"])
def test_password_shorter_than_8_is_rejected(raw: str) -> None:
    with pytest.raises(WeakPassword):
        RawPassword.parse(raw)


def test_password_without_a_letter_is_rejected() -> None:
    with pytest.raises(WeakPassword):
        RawPassword.parse("12345678")


def test_password_without_a_digit_is_rejected() -> None:
    with pytest.raises(WeakPassword):
        RawPassword.parse("abcdefgh")


def test_password_longer_than_72_bytes_is_rejected() -> None:
    with pytest.raises(WeakPassword):
        RawPassword.parse("a" * 72 + "1")


def test_password_of_exactly_72_bytes_is_accepted() -> None:
    at_limit = "a" * 71 + "1"
    assert len(at_limit.encode()) == 72
    assert RawPassword.parse(at_limit).value == at_limit


@pytest.mark.parametrize("raw", ["密碼abcd1234", "abcd1234🐶", "abcd1234\x00"])
def test_password_with_non_printable_ascii_is_rejected(raw: str) -> None:
    """非 ASCII 會讓字元數與 bcrypt 的位元組上限對不起來,規格直接限定字元集。"""
    with pytest.raises(WeakPassword):
        RawPassword.parse(raw)


def test_password_may_contain_printable_ascii_symbols() -> None:
    assert RawPassword.parse("a1!@#$%^&*()_+ ~").value == "a1!@#$%^&*()_+ ~"


def test_weak_password_uses_auth_006() -> None:
    with pytest.raises(WeakPassword) as exc_info:
        RawPassword.parse("short")
    assert exc_info.value.code == "AUTH_006"


def test_raw_password_is_not_leaked_by_repr() -> None:
    """密碼明碼不該因為一行 log 或例外堆疊就外洩。"""
    assert "abcd1234" not in repr(RawPassword.parse("abcd1234"))
