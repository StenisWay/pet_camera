import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.push_tokens.domain.entities import ClientPlatform, PushToken
from app.domains.push_tokens.domain.repositories import PushTokenRepository
from app.domains.push_tokens.infrastructure.mappers import to_entity
from app.domains.push_tokens.infrastructure.orm import PushTokenRow


def upsert_statement(push_token: PushToken):
    """INSERT ... ON CONFLICT (platform, md5(token)) DO UPDATE SET user_id = ...

    衝突目標必須與唯一索引的運算式完全一致,PostgreSQL 才推得出要用哪個索引。
    兩個請求同時登記同一端點時,後到的那個直接改綁既有的一筆(介面承諾),不會撞
    唯一索引而變成 500。
    """
    stmt = insert(PushTokenRow).values(
        id=push_token.id,
        user_id=push_token.user_id,
        platform=push_token.platform.value,
        token=push_token.token,
        created_at=push_token.created_at,
    )
    return stmt.on_conflict_do_update(
        index_elements=[PushTokenRow.platform, func.md5(PushTokenRow.token)],
        set_={"user_id": stmt.excluded.user_id, "updated_at": func.now()},
    ).returning(
        PushTokenRow.id,
        PushTokenRow.user_id,
        PushTokenRow.platform,
        PushTokenRow.token,
        PushTokenRow.created_at,
    )


class SqlAlchemyPushTokenRepository(PushTokenRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, push_token_id: uuid.UUID) -> PushToken | None:
        row = await self.session.get(PushTokenRow, push_token_id)
        return to_entity(row) if row else None

    async def find_by_endpoint(self, platform: ClientPlatform, token: str) -> PushToken | None:
        row = await self.session.scalar(
            select(PushTokenRow).where(
                PushTokenRow.platform == platform.value,
                # md5 條件讓查詢吃得到唯一索引;token 相等是防 md5 碰撞的精確比對
                func.md5(PushTokenRow.token) == func.md5(token),
                PushTokenRow.token == token,
            )
        )
        return to_entity(row) if row else None

    async def list_by_user(self, user_id: uuid.UUID) -> list[PushToken]:
        rows = await self.session.scalars(
            select(PushTokenRow)
            .where(PushTokenRow.user_id == user_id)
            .order_by(PushTokenRow.created_at, PushTokenRow.id)
        )
        return [to_entity(row) for row in rows]

    async def save(self, push_token: PushToken) -> PushToken:
        stored = (await self.session.execute(upsert_statement(push_token))).one()
        # 同一個 session 可能已經載入過這一列;讓下次 get 重新讀取,不拿到改綁前的值
        self.session.expire_all()
        return PushToken(
            id=stored.id,
            user_id=stored.user_id,
            platform=ClientPlatform(stored.platform),
            token=stored.token,
            created_at=stored.created_at,
        )

    async def delete(self, push_token_id: uuid.UUID) -> None:
        await self.session.execute(delete(PushTokenRow).where(PushTokenRow.id == push_token_id))
