import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.drive_export.domain.entities import DriveConnection
from app.domains.drive_export.domain.repositories import DriveConnectionRepository
from app.domains.drive_export.infrastructure.mappers import apply_to_row, to_entity, to_new_row
from app.domains.drive_export.infrastructure.orm import DriveCredentialRow


class SqlAlchemyDriveConnectionRepository(DriveConnectionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _row_for(self, owner_id: uuid.UUID) -> DriveCredentialRow | None:
        return await self.session.scalar(
            select(DriveCredentialRow).where(DriveCredentialRow.user_id == owner_id)
        )

    async def get_by_owner(self, owner_id: uuid.UUID) -> DriveConnection | None:
        row = await self._row_for(owner_id)
        return to_entity(row) if row else None

    async def save(self, connection: DriveConnection) -> None:
        row = await self._row_for(connection.owner_id)
        if row is None:
            self.session.add(to_new_row(connection))
        else:
            apply_to_row(connection, row)
        await self.session.flush()

    async def delete_by_owner(self, owner_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(DriveCredentialRow).where(DriveCredentialRow.user_id == owner_id)
        )
