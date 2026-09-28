"""配對碼值物件(規格審查 #4)。

8 碼 Crockford Base32,排除易混淆的 I/L/O/U;比對時大小寫不敏感,
並把使用者可能誤打的 I、L 視為 1、O 視為 0,容許輸入含連字號或空白。
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.domains.devices.domain.pairing_code import (
    CROCKFORD_ALPHABET,
    InvalidPairingCodeFormat,
    PairingCode,
)

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def a_code(code: str = "ABCD1234", *, expires_in: timedelta = timedelta(minutes=10)) -> PairingCode:
    return PairingCode(code=code, expires_at=NOW + expires_in)


def test_alphabet_excludes_ambiguous_letters():
    assert len(CROCKFORD_ALPHABET) == 32
    for letter in "ILOU":
        assert letter not in CROCKFORD_ALPHABET


@pytest.mark.parametrize("code", ["ABCD123", "ABCD12345", "", "ABCD-123"])
def test_code_must_be_exactly_eight_characters(code):
    with pytest.raises(InvalidPairingCodeFormat):
        a_code(code)


@pytest.mark.parametrize("code", ["ABCDI234", "ABCDL234", "ABCDO234", "ABCDU234", "abcd1234"])
def test_code_must_use_uppercase_crockford_alphabet(code):
    with pytest.raises(InvalidPairingCodeFormat):
        a_code(code)


@pytest.mark.parametrize(
    "typed",
    [
        "ABCD1234",  # 原樣
        "abcd1234",  # 小寫
        "ABCD-1234",  # 使用者自行加的連字號
        "abcd 1234",  # 貼上時帶空白
        "ABCDI234",  # I 誤打成 1
        "ABCDl234",  # 小寫 l 誤打成 1
        "ABCD1O34",  # O 誤打成 0  -> 對應 ABCD1034
    ],
)
def test_matches_is_case_insensitive_and_forgives_ambiguous_letters(typed):
    expected = "ABCD1034" if "O" in typed.upper() else "ABCD1234"
    assert a_code(expected).matches(typed, now=NOW)


def test_matches_rejects_a_different_code():
    assert not a_code("ABCD1234").matches("ZZZZ9999", now=NOW)


def test_matches_rejects_garbage_input_without_raising():
    assert not a_code("ABCD1234").matches("!!!", now=NOW)


def test_code_is_expired_exactly_at_expiry_time():
    code = a_code(expires_in=timedelta(minutes=10))

    assert not code.is_expired(NOW + timedelta(minutes=10) - timedelta(seconds=1))
    assert code.is_expired(NOW + timedelta(minutes=10))


def test_expired_code_does_not_match_even_when_correct():
    code = a_code("ABCD1234", expires_in=timedelta(minutes=10))

    assert not code.matches("ABCD1234", now=NOW + timedelta(minutes=11))
