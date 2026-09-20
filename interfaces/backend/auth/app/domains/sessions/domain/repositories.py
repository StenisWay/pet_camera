"""sessions 的 repository 介面。

refresh token 一律以**指紋**(雜湊)查詢——明碼只在簽發那一刻回給用戶端一次,
資料庫與程式內部都拿不到(02_spec 第 2.3.1 節、01_資料模型 第 2.5 節)。
"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime

from app.domains.sessions.domain.entities import RefreshToken


class RefreshTokenRepository(ABC):
    @abstractmethod
    async def get_by_fingerprint(self, fingerprint: str) -> RefreshToken | None:
        """以指紋查詢;不存在時回 None。已撤銷、已過期的紀錄**仍會回傳**——
        呼叫端要能分辨「沒有這個 token」與「這個 token 已被撤銷」,後者是重放的徵兆
        (§2.3.1 的重放偵測)。"""

    @abstractmethod
    async def add(self, token: RefreshToken) -> None:
        """實際寫入在 commit() 時生效。"""

    @abstractmethod
    async def revoke(self, token_id: uuid.UUID, *, revoked_at: datetime) -> bool:
        """標記撤銷,回傳「本次呼叫是否真的完成撤銷」。

        已經是撤銷狀態、或紀錄不存在時回 False。rotation 的併發勝負靠這個值判定:
        影響 0 列的一方視為重放,否則一個 refresh token 會換出兩組有效 token
        (§2.3.1、規格審查 #11)。
        """

    @abstractmethod
    async def revoke_all_for_user(
        self,
        user_id: uuid.UUID,
        *,
        revoked_at: datetime,
        except_token_id: uuid.UUID | None = None,
    ) -> int:
        """撤銷該使用者所有**未撤銷**的 token,回傳實際撤銷筆數。

        except_token_id 用於改密碼時保留當前 session(05_spec 第 2.1 節);
        重放偵測與重設密碼則不保留。已撤銷的紀錄不重複計入。
        """

    @abstractmethod
    async def delete_all_for_user(self, user_id: uuid.UUID) -> None:
        """刪除帳號時串聯清除(資料模型第 6 節)。"""
