from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from tests.app_factory import Doubles, build_test_app
from tests.domains.accounts.fakes import FixedClock

NOW = datetime.now(UTC).replace(microsecond=0)


@pytest.fixture
def doubles() -> Doubles:
    return Doubles(clock=FixedClock(NOW))


@pytest.fixture
async def client(doubles: Doubles) -> AsyncIterator[AsyncClient]:
    app = build_test_app(doubles)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
