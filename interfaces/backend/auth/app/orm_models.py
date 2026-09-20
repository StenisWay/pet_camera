"""匯入所有 ORM model,讓 Base.metadata 拿得到完整的表定義。

測試建 schema、以及需要對照 db/migrations/ 時都從這裡進來。各領域的 model
分散在自己的 infrastructure 層,沒有這個集合點就得逐一 import 才不會漏。
"""

from app.core.database import Base
from app.domains.accounts.infrastructure.orm import PasswordResetTokenRow, UserRow
from app.domains.sessions.infrastructure.orm import RefreshTokenRow

__all__ = ["Base", "PasswordResetTokenRow", "RefreshTokenRow", "UserRow"]
