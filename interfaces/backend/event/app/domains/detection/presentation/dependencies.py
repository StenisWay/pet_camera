"""detection 的組裝點。

F2 本身不對外提供 API(13_ADR 第 1 節),這裡只有一個內部端點:
Device 服務移除裝置時的串聯清除。
"""

from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.core.database import get_session_factory
from app.domains.detection.application.ports import DetectionUnitOfWork, MediaUploader
from app.domains.detection.application.use_cases.purge_device_events import PurgeDeviceEvents
from app.domains.detection.infrastructure.storage_adapter import R2MediaUploader
from app.domains.detection.infrastructure.unit_of_work import SqlAlchemyDetectionUnitOfWork

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_detection_uow(settings: SettingsDep) -> DetectionUnitOfWork:
    return SqlAlchemyDetectionUnitOfWork(get_session_factory())


def get_media_uploader(settings: SettingsDep) -> MediaUploader:
    return R2MediaUploader(settings)


def get_purge_device_events(
    uow: Annotated[DetectionUnitOfWork, Depends(get_detection_uow)],
    uploader: Annotated[MediaUploader, Depends(get_media_uploader)],
) -> PurgeDeviceEvents:
    return PurgeDeviceEvents(uow=uow, uploader=uploader)
