"""accounts 的 HTTP 端點(02_spec 第 3 節、05_spec 第 3 節)。

router 裡沒有業務邏輯:schema → Command → use case → Result → schema。
狀態碼與錯誤碼的對應集中在 app/core/http_errors.py,這裡只宣告成功時的形狀。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.core.security import CurrentUserId
from app.domains.accounts.application.dtos import (
    ChangePasswordCommand,
    DeleteAccountCommand,
    LoginCommand,
    RegisterUserCommand,
    RequestPasswordResetCommand,
    ResetPasswordCommand,
)
from app.domains.accounts.application.use_cases.change_password import ChangePassword
from app.domains.accounts.application.use_cases.delete_account import DeleteAccount
from app.domains.accounts.application.use_cases.login_user import LoginUser
from app.domains.accounts.application.use_cases.register_user import RegisterUser
from app.domains.accounts.application.use_cases.request_password_reset import (
    RequestPasswordReset,
)
from app.domains.accounts.application.use_cases.reset_password import ResetPassword
from app.domains.accounts.presentation.dependencies import (
    get_change_password,
    get_delete_account,
    get_login_user,
    get_register_user,
    get_request_password_reset,
    get_reset_password,
)
from app.domains.accounts.presentation.schemas import (
    ChangePasswordIn,
    DeleteAccountIn,
    ForgotPasswordIn,
    ForgotPasswordOut,
    LoginIn,
    RegisterIn,
    RegisterOut,
    ResetPasswordIn,
    TokensOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    """限流的第二個維度(§2.4)。取不到時回空字串,由 throttle 自行忽略——
    絕不要用固定字串代替,那會讓所有取不到 IP 的請求共用同一個計數。"""
    return request.client.host if request.client else ""


@router.post("/register", response_model=RegisterOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterIn,
    use_case: Annotated[RegisterUser, Depends(get_register_user)],
) -> RegisterOut:
    result = await use_case.execute(
        RegisterUserCommand(email=payload.email, password=payload.password)
    )
    # 註冊成功不自動登入(screens/*/01_page_登入註冊忘記密碼.md)
    return RegisterOut(user_id=result.user_id, email=result.email)


@router.post("/login", response_model=TokensOut)
async def login(
    payload: LoginIn,
    use_case: Annotated[LoginUser, Depends(get_login_user)],
) -> TokensOut:
    result = await use_case.execute(
        LoginCommand(
            email=payload.email, password=payload.password, platform=payload.platform
        )
    )
    return TokensOut(
        access_token=result.access_token, refresh_token=result.refresh_token
    )


@router.post("/password/forgot", response_model=ForgotPasswordOut)
async def forgot_password(
    payload: ForgotPasswordIn,
    request: Request,
    use_case: Annotated[RequestPasswordReset, Depends(get_request_password_reset)],
) -> ForgotPasswordOut:
    await use_case.execute(
        RequestPasswordResetCommand(email=payload.email, client_ip=_client_ip(request))
    )
    # §2.4:email 存不存在、信寄成功與否,這裡的回應完全一樣
    return ForgotPasswordOut()


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: ResetPasswordIn,
    use_case: Annotated[ResetPassword, Depends(get_reset_password)],
) -> None:
    await use_case.execute(
        ResetPasswordCommand(token=payload.token, new_password=payload.new_password)
    )


@router.patch("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordIn,
    user_id: CurrentUserId,
    use_case: Annotated[ChangePassword, Depends(get_change_password)],
) -> None:
    await use_case.execute(
        ChangePasswordCommand(
            user_id=user_id,
            current_password=payload.current_password,
            new_password=payload.new_password,
            current_refresh_token=payload.current_refresh_token,
        )
    )


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    payload: DeleteAccountIn,
    user_id: CurrentUserId,
    use_case: Annotated[DeleteAccount, Depends(get_delete_account)],
) -> None:
    await use_case.execute(
        DeleteAccountCommand(user_id=user_id, confirmation=payload.confirmation)
    )
