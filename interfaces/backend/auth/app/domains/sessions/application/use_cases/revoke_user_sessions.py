"""撤銷某個使用者的所有 refresh token。

由 accounts 在改密碼(保留當前 session)與重設密碼(全部撤銷)後呼叫,
經 sessions/api.py 進來,不直接碰本領域的內部結構。
"""

import uuid

from app.domains.sessions.application.ports import SessionsUnitOfWork
from app.domains.sessions.domain.entities import RevocationReason
from app.shared_kernel.ports import Clock, OpaqueTokenFactory


class RevokeUserSessions:
    def __init__(
        self, uow: SessionsUnitOfWork, *, clock: Clock, tokens: OpaqueTokenFactory
    ) -> None:
        self.uow = uow
        self.clock = clock
        self.tokens = tokens

    async def execute(
        self, user_id: uuid.UUID, *, except_refresh_token: str | None = None
    ) -> int:
        """回傳實際撤銷筆數。沒有任何 token 可撤銷(例如 App-only 使用者)時回 0,
        不是錯誤。

        except_refresh_token 查無對應紀錄時視為沒有要保留的——寧可多撤銷,
        也不要因為一個對不上的字串就放過某個 session。
        """
        async with self.uow:
            except_id: uuid.UUID | None = None
            if except_refresh_token:
                current = await self.uow.refresh_tokens.get_by_fingerprint(
                    self.tokens.fingerprint(except_refresh_token)
                )
                except_id = current.id if current is not None else None

            revoked = await self.uow.refresh_tokens.revoke_all_for_user(
                user_id,
                revoked_at=self.clock.now(),
                reason=RevocationReason.SUPERSEDED,
                except_token_id=except_id,
            )
            await self.uow.commit()
        return revoked
