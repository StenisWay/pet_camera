"""把領域例外的業務分類轉成 HTTP 回應。這是唯一知道 HTTP 狀態碼的地方。

狀態碼對應依 rule_doc/功能需求/10_錯誤處理與狀態規範.md 第 3 節,與該文件的錯誤碼表
一致——這也是本專案唯一偏離「BusinessRuleViolation → 422」預設的地方:規格書明定
輸入格式錯誤(VAL_001)回 400。
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError

from app.shared_kernel.errors import (
    AuthenticationRequired,
    BusinessRuleViolation,
    Conflict,
    DomainError,
    NotFound,
    PermissionDenied,
    RateLimited,
    ServiceUnavailable,
)

logger = logging.getLogger(__name__)

STATUS_BY_CATEGORY: dict[type[DomainError], int] = {
    NotFound: 404,
    Conflict: 409,
    PermissionDenied: 403,
    BusinessRuleViolation: 400,  # VAL_001,見 10_錯誤處理與狀態規範.md 第 3 節
    AuthenticationRequired: 401,  # AUTH_001 / AUTH_002 / DRIVE_001 / DRIVE_003
    RateLimited: 429,  # RATE_001
    ServiceUnavailable: 503,  # SRV_002
}


def status_for(exc: DomainError) -> int:
    for cls in type(exc).__mro__:
        if cls in STATUS_BY_CATEGORY:
            return STATUS_BY_CATEGORY[cls]
    return 400


def error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=status_for(exc), content=error_body(exc.code, exc.message))

    async def _handle_backend_unreachable(_: Request, exc: Exception) -> JSONResponse:
        """13_ADR 第 4 節 / 09_spec 審查 #12:寫入 Postgres 的路徑選一致性(C)。

        VM-3 連不到時明確回 SRV_002(前端顯示「服務暫時無法使用」),而不是一般的 500。
        asyncpg 連線被拒時丟的是未包裝的 OSError,所以一併處理。
        """
        logger.warning("backend unreachable: %r", exc)
        return JSONResponse(status_code=503, content=error_body("SRV_002", "服務暫時無法使用"))

    for exc_type in (OperationalError, InterfaceError, OSError):
        app.add_exception_handler(exc_type, _handle_backend_unreachable)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=400, content=error_body("VAL_001", "輸入格式錯誤"))
