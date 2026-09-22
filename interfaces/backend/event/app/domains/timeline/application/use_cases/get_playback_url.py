"""播放連結換發。"""

from dataclasses import dataclass
from uuid import UUID

from app.domains.timeline.application.ports import (
    DeviceOwnership,
    MediaUrlIssuer,
    TimelineUnitOfWork,
)
from app.domains.timeline.domain.exceptions import DeviceNotFound, EventNotFound
from app.shared_kernel.ports import Clock


@dataclass(frozen=True)
class PlaybackUrlResult:
    url: str


class GetPlaybackUrl:
    def __init__(
        self,
        *,
        uow: TimelineUnitOfWork,
        ownership: DeviceOwnership,
        urls: MediaUrlIssuer,
        clock: Clock,
    ) -> None:
        self.uow = uow
        self.ownership = ownership
        self.urls = urls
        self.clock = clock

    async def execute(self, event_id: UUID, requester_id: UUID) -> PlaybackUrlResult:
        """事件 → 擁有者 → 可播放性 → 換發,任何一關沒過都不會走到 R2。

        順序是刻意的:先確認是本人的事件才回答「能不能播」,否則光憑錯誤碼的差異
        (409 還是 410)就能探出別人有沒有那筆事件。
        """
        async with self.uow:
            event = await self.uow.events.get(event_id)

        if event is None:
            raise EventNotFound()
        if not await self.ownership.is_owned_by(event.device_id, requester_id):
            raise DeviceNotFound()

        url = await self.urls.presigned_url(event.playable_video_key(self.clock.now()))
        return PlaybackUrlResult(url=url)
