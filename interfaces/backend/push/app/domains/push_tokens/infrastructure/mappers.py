"""Row ↔ Entity。資料表可以依 postgres-db-master 的規範演進,業務模型不受影響。"""

from app.domains.push_tokens.domain.entities import ClientPlatform, PushToken
from app.domains.push_tokens.infrastructure.orm import PushTokenRow


def to_entity(row: PushTokenRow) -> PushToken:
    return PushToken(
        id=row.id,
        user_id=row.user_id,
        platform=ClientPlatform(row.platform),
        token=row.token,
        created_at=row.created_at,
    )
