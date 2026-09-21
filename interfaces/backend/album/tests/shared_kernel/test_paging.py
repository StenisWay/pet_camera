import uuid
from datetime import UTC, datetime

import pytest

from app.shared_kernel.paging import Cursor, InvalidCursor

CAPTURED_AT = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)


def test_cursor_round_trips():
    cursor = Cursor(CAPTURED_AT, uuid.uuid4())

    assert Cursor.decode(cursor.encode()) == cursor


def test_cursor_is_opaque_to_the_client():
    """游標是不透明字串:前端不該解析它,也就不會依賴它的內部格式。"""
    encoded = Cursor(CAPTURED_AT, uuid.uuid4()).encode()

    assert "|" not in encoded
    assert "2026-09-20" not in encoded


@pytest.mark.parametrize(
    "bad", ["", "not-base64!!", "YWJj", "MjAyNi0wOS0yMHxub3QtYS11dWlk"]
)
def test_tampered_cursor_is_rejected(bad):
    with pytest.raises(InvalidCursor):
        Cursor.decode(bad)
