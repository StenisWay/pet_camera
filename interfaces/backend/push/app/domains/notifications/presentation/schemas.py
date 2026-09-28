"""內部端點的 Pydantic 模型(09_spec 第 3 節的 body 格式)。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class EventReadyIn(BaseModel):
    event_id: uuid.UUID
    device_id: uuid.UUID
    confidence_score: float = Field(ge=0, le=1)
    thumbnail_object_key: str | None = Field(default=None, max_length=1024)
    started_at: datetime
