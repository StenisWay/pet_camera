"""Row ↔ Entity。

隔離層的代價,也是價值所在:資料表可以依 postgres-db-master 的規範演進
(加稽核欄位、改索引、換主鍵型別),domain 實體不受影響。

apply_to_row 只同步**可變**欄位——email 與 created_at 建立後就不該再變,
放進來只會讓「改 email」這種沒定義過的操作看起來像是支援的。
"""

from app.domains.accounts.domain.entities import PasswordResetToken, User
from app.domains.accounts.domain.value_objects import Email
from app.domains.accounts.infrastructure.orm import PasswordResetTokenRow, UserRow


def user_to_entity(row: UserRow) -> User:
    return User(
        id=row.id,
        email=Email.parse(row.email),
        password_hash=row.password_hash,
        failed_login_attempts=row.failed_login_attempts,
        locked_until=row.locked_until,
        created_at=row.created_at,
    )


def user_to_new_row(user: User) -> UserRow:
    return UserRow(
        id=user.id,
        email=user.email.value,
        password_hash=user.password_hash,
        failed_login_attempts=user.failed_login_attempts,
        locked_until=user.locked_until,
    )


def apply_user_to_row(user: User, row: UserRow) -> None:
    row.password_hash = user.password_hash
    row.failed_login_attempts = user.failed_login_attempts
    row.locked_until = user.locked_until


def reset_token_to_entity(row: PasswordResetTokenRow) -> PasswordResetToken:
    return PasswordResetToken(
        id=row.id,
        user_id=row.user_id,
        token_hash=row.token_hash,
        expires_at=row.expires_at,
        used_at=row.used_at,
        created_at=row.created_at,
    )


def reset_token_to_new_row(token: PasswordResetToken) -> PasswordResetTokenRow:
    return PasswordResetTokenRow(
        id=token.id,
        user_id=token.user_id,
        token_hash=token.token_hash,
        expires_at=token.expires_at,
        used_at=token.used_at,
    )
