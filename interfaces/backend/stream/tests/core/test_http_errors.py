"""領域例外 -> HTTP 狀態碼的對應表(10_錯誤處理與狀態規範.md 第 3 節、06_spec 第 7 節)。

這張表是前端的契約:錯誤碼決定文案,狀態碼決定要不要重試。
"""

import pytest

from app.core.http_errors import error_body, status_for
from app.domains.streaming.domain.exceptions import (
    DeviceNotFound,
    DeviceOffline,
    SessionExpired,
    SignalingTimeout,
)
from app.shared_kernel.errors import (
    BusinessRuleViolation,
    DomainError,
    PermissionDenied,
    RateLimited,
    ServiceUnavailable,
)


@pytest.mark.parametrize(
    ("exception", "status", "code"),
    [
        (DeviceOffline(), 409, "STREAM_001"),
        (SessionExpired(), 401, "STREAM_002"),
        (SignalingTimeout(), 408, "STREAM_005"),
        (DeviceNotFound(), 404, "DEVICE_005"),
        (BusinessRuleViolation(), 400, "VAL_001"),
        (RateLimited(), 429, "RATE_001"),
        (ServiceUnavailable(), 503, "SRV_002"),
        (PermissionDenied(), 403, "AUTH_001"),
    ],
)
def test_error_table(exception: DomainError, status: int, code: str) -> None:
    assert status_for(exception) == status
    assert exception.code == code


def test_session_expired_is_401_not_409() -> None:
    """第 7 節明定 STREAM_002 是 401。401 讓前端重建 session;
    409 會被當成狀態衝突而一直重試同一個失效的 session_id。"""
    assert status_for(SessionExpired()) == 401


def test_signaling_timeout_is_408() -> None:
    """本專案唯一用到 408 的地方——其餘六個服務都沒有逾時語意的錯誤。"""
    assert status_for(SignalingTimeout()) == 408


def test_unclassified_domain_error_falls_back_to_400() -> None:
    class Weird(DomainError):
        code = "SRV_001"

    assert status_for(Weird()) == 400


def test_error_body_shape() -> None:
    """全服務統一:{"error": {"code": ..., "message": ...}}"""
    assert error_body("STREAM_001", "鏡頭目前離線") == {
        "error": {"code": "STREAM_001", "message": "鏡頭目前離線"}
    }


def test_message_defaults_to_the_user_facing_docstring() -> None:
    assert DeviceOffline().message == "鏡頭目前離線"
