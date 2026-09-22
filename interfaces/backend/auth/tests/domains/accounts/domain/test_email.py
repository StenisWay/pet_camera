"""Email 值物件。

規格:02_spec_登入註冊與密碼重設.md 第 2.1 節與「Email 正規化」段落。
正規化是後端責任——users.email 有 CHECK email = lower(email) 約束,
不先正規化會讓大寫輸入撞上資料庫約束而回 SRV_001,而不是預期的 AUTH_004。
"""

import pytest

from app.domains.accounts.domain.exceptions import InvalidEmail
from app.domains.accounts.domain.value_objects import Email


def test_email_is_lowercased_and_trimmed() -> None:
    assert Email.parse("  A@X.com  ").value == "a@x.com"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "no-at-sign",
        "@nolocal.com",
        "local@",
        "a b@x.com",  # 本地部分不可含空白
        "a@x",  # 網域需有點號
    ],
)
def test_malformed_email_is_rejected(raw: str) -> None:
    with pytest.raises(InvalidEmail):
        Email.parse(raw)


def test_email_longer_than_254_characters_is_rejected() -> None:
    too_long = "a" * 243 + "@example.com"  # 255 字元
    assert len(too_long) == 255
    with pytest.raises(InvalidEmail):
        Email.parse(too_long)


def test_email_of_exactly_254_characters_is_accepted() -> None:
    at_limit = "a" * 242 + "@example.com"
    assert len(at_limit) == 254
    assert Email.parse(at_limit).value == at_limit


def test_invalid_email_uses_the_global_validation_error_code() -> None:
    """§2.1:Email 必填/格式錯誤沿用全域 VAL_001。"""
    with pytest.raises(InvalidEmail) as exc_info:
        Email.parse("nope")
    assert exc_info.value.code == "VAL_001"
