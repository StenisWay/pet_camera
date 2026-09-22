"""內部端點的回應形狀。"""

from pydantic import BaseModel


class PurgeResultOut(BaseModel):
    """DELETE /internal/devices/{device_id}/events 的回應(08_spec 第 3.3 節)。"""

    deleted_count: int
