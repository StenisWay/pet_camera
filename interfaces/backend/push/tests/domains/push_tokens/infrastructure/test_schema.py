"""資料庫約束本身有效——即使有人繞過 repository 直接寫入(01_資料模型第 2.6 節)。"""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.push_tokens.infrastructure.orm import PushTokenRow

pytestmark = pytest.mark.integration


def _row(**overrides) -> PushTokenRow:
    values = {"id": uuid.uuid4(), "user_id": uuid.uuid4(), "platform": "app", "token": "t"}
    return PushTokenRow(**{**values, **overrides})


async def test_platform_outside_app_or_web_is_rejected(session_factory):
    async with session_factory() as session:
        session.add(_row(platform="ios"))
        with pytest.raises(IntegrityError, match="ck_push_tokens_platform"):
            await session.commit()


async def test_same_endpoint_cannot_be_registered_twice(session_factory):
    async with session_factory() as session:
        session.add(_row())
        await session.commit()
        session.add(_row(user_id=uuid.uuid4()))
        with pytest.raises(IntegrityError, match="uq_push_tokens_platform_token"):
            await session.commit()


async def test_long_web_push_subscription_fits_the_md5_index(session_factory):
    """直接對 token 建 B-tree 會在約 2.7KB 撞到上限;md5 索引不受影響。"""
    async with session_factory() as session:
        session.add(_row(platform="web", token="x" * 4000))
        await session.commit()
