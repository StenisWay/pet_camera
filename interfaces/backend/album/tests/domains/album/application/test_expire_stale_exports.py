from datetime import timedelta

import pytest

from app.domains.album.application.use_cases.expire_stale_exports import ExpireStaleExports
from app.domains.album.domain.entities import DriveExportStatus
from tests.domains.album.builders import an_item

STALE_AFTER = timedelta(minutes=15)


@pytest.fixture
def use_case(uow, clock) -> ExpireStaleExports:
    return ExpireStaleExports(uow, clock, stale_after=STALE_AFTER)


async def test_long_running_export_is_marked_failed(use_case, uow, clock):
    """規格審查 #7:服務複本重啟後進行中的匯出會消失,項目不能永遠停在 exporting。"""
    stale = uow.given(
        an_item(
            drive_export_status=DriveExportStatus.EXPORTING,
            export_state_changed_at=clock.now() - timedelta(minutes=16),
        )
    )

    assert await use_case.execute() == 1
    assert (await uow.items.get(stale.id)).drive_export_status is DriveExportStatus.FAILED


async def test_recent_export_is_left_alone(use_case, uow, clock):
    fresh = uow.given(
        an_item(
            drive_export_status=DriveExportStatus.EXPORTING,
            export_state_changed_at=clock.now() - timedelta(minutes=5),
        )
    )

    assert await use_case.execute() == 0
    assert (await uow.items.get(fresh.id)).drive_export_status is DriveExportStatus.EXPORTING


async def test_nothing_to_expire_still_commits_cleanly(use_case, uow):
    uow.given(an_item())

    assert await use_case.execute() == 0
